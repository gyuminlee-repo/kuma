"""End-to-end analyze pipeline glue (ingest -> translate -> compare -> select -> export)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from kuma_core.mame.compare import classify_verdict, parse_mutation_label
from kuma_core.mame.export import WellMapper, write_excel
from kuma_core.mame.export.excel_writer import _custom_barcode_to_seq
from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.ingest import IngestMode, route_ingest
from kuma_core.mame.ingest.sort_barcode import parse_sample_map
from kuma_core.mame.io.kuro_reader import expected_to_labels, read_expected_mutations
from kuma_core.mame.models import (
    CompareParams,
    ExpectedMutation,
    ReplicateResult,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.select import pick_best_replicate
from kuma_core.mame.translate import translate_and_diff


def _norm_well(w: str) -> str:
    """Normalise a well label to zero-padded form (e.g. 'A2' -> 'A02', 'A02' -> 'A02')."""
    w = str(w).strip().upper()
    if len(w) >= 2 and w[1:].isdigit():
        return f"{w[0]}{int(w[1:]):02d}"
    return w


def _read_reference_fasta(path: Path) -> str:
    seq_parts: list[str] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if line.startswith(">"):
                continue
            if line:
                seq_parts.append(line.strip())
    return "".join(seq_parts).upper()


def _assign_mutant_ids(
    verdicts: list[VerdictRecord],
    expected: list[ExpectedMutation],
    well_to_mutant: dict[str, str] | None = None,
) -> dict[str, list[VerdictRecord]]:
    """Group verdict records by the best-matching mutant_id.

    When *well_to_mutant* is provided (keyed by normalised well_id, e.g. "A02"),
    a well is attributed to the mutant physically placed there according to the
    sample_map (ground truth), overriding observation-based heuristics.  This
    makes Final/matrix grouping coherent with the per-well verdict scoping that
    uses the same sample_map.  Falls through to the existing 4-step heuristics
    for wells with a non-R_F custom_barcode or no sample_map entry.

    Strategy (observation-based fallback): iterate expected mutations and attach
    any verdict whose observed AA set contains the expected substitution label,
    or whose verdict class is WRONG_AA at the expected position, or whose verdict
    is LOWDEPTH/NO_CALL/FRAMESHIFT/MANY (unknown target — still attempt assignment based
    on file naming).
    """

    grouped: dict[str, list[VerdictRecord]] = defaultdict(list)

    expected_by_pos: dict[int, ExpectedMutation] = {m.position: m for m in expected}
    assigned: set[int] = set()

    for idx, vr in enumerate(verdicts):
        if well_to_mutant is not None:
            _seq = _custom_barcode_to_seq(vr.translated.barcode.custom_barcode)
            if _seq is not None:
                _placed = well_to_mutant.get(_norm_well(seq_to_well(_seq)))
                if _placed is not None:
                    vr.mutant_id = _placed
                    grouped[_placed].append(vr)
                    assigned.add(idx)
                    continue
        matched_id: str | None = None
        # 1) Direct label match.
        for exp in expected:
            label = f"{exp.wt_aa}{exp.position}{exp.mt_aa}"
            if label in vr.translated.observed_aa_changes:
                matched_id = exp.mutant_id
                break
        if matched_id is None:
            # 2) Position-based match (WRONG_AA or AMBIGUOUS with expected position).
            observed_positions = {
                parsed[1]
                for lbl in vr.translated.observed_aa_changes
                if (parsed := parse_mutation_label(lbl)) is not None
            }
            for pos in observed_positions:
                if pos in expected_by_pos:
                    matched_id = expected_by_pos[pos].mutant_id
                    break
        if matched_id is None:
            # 3) Missing-expected (WRONG_AA with "missing expected" note) — use the
            # first unmet expected mutant id round-robin.
            if vr.verdict is VerdictClass.WRONG_AA and expected:
                matched_id = expected[idx % len(expected)].mutant_id
            elif vr.verdict in (VerdictClass.LOWDEPTH, VerdictClass.NO_CALL) and expected:
                matched_id = expected[idx % len(expected)].mutant_id
            else:
                # 4) Fall back to `<native>_<custom>` to keep the record addressable.
                matched_id = (
                    f"UNKNOWN_{vr.translated.barcode.native_barcode}_"
                    f"{vr.translated.barcode.custom_barcode}"
                )
        vr.mutant_id = matched_id
        grouped[matched_id].append(vr)
        assigned.add(idx)
    return grouped


def run_analyze(
    input_dir: Path,
    reference_path: Path,
    expected_path: Path,
    output_path: Path,
    cds_start: int,
    cds_end: int,
    mode: str = "amplicon",
    min_file_size_kb: float = 50.0,
    min_read_count: int | None = 30,
    max_consensus_n_fraction: float | None = 0.0,
    many_cutoff: int = 5,
    ingest_mode: IngestMode = IngestMode.BARCODE,
    sample_map_path: Path | None = None,
    well_layout: dict[str, str] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[VerdictRecord], list[ReplicateResult]]:
    """Run the full pipeline and write the Excel output. Returns in-memory results.

    ``progress_callback`` is an optional ``(index, total)`` sink invoked once per
    processed record during the per-record verdict loop (``index`` is 1-based and
    the final call has ``index == total``). It defaults to ``None`` so existing
    callers and tests are unaffected. The handler layer uses it to surface live
    sub-progress; the domain layer stays I/O-agnostic and never throttles.
    """

    reference_seq = _read_reference_fasta(reference_path)
    expected_mutations = read_expected_mutations(expected_path)
    expected_labels = expected_to_labels(expected_mutations)

    # Build per-mutant label lists for verdict scoping.
    # Keys are mutant_id strings (e.g. "V5F", "K53N"); values are lists of
    # human-readable AA labels (e.g. ["V5F"]).  Only non-empty entries are kept.
    mutant_to_labels: dict[str, list[str]] = defaultdict(list)
    for m in expected_mutations:
        mutant_to_labels[m.mutant_id].append(f"{m.wt_aa}{m.position}{m.mt_aa}")

    # Build well_id -> scoped label list from a well->sample source.
    # - If neither well_layout nor sample_map_path is given (amplicon / non-
    #   combinatorial modes): well_to_labels stays None and every well is compared
    #   against the full expected_labels list, preserving byte-identical legacy
    #   behaviour.
    # - If a well's custom_barcode cannot be resolved to a well coordinate (non-R_F
    #   barcode format), _custom_barcode_to_seq returns None -> fallback to full list.
    # - If a well_id appears in the source but the sample name is not a known
    #   mutant_id (and not "WT"), it is omitted -> verdict-time lookup returns None
    #   -> fallback to full list (defensive "unknown well" path; the well will
    #   receive WRONG_AA, the correct result when the intended mutation is unknown).
    # well->sample source priority: (a) well_layout override, (b) sample_map_path,
    # (c) None (full-scope comparison, byte-identical legacy behaviour).
    well_to_sample: dict[str, str] | None = None
    if well_layout is not None:
        well_to_sample = well_layout
    elif sample_map_path is not None:
        well_to_sample = parse_sample_map(sample_map_path)   # {"A01": "V5F", ...}

    well_to_labels: dict[str, list[str]] | None = None
    well_to_mutant: dict[str, str] | None = None
    if well_to_sample is not None:
        well_to_labels = {}
        well_to_mutant = {}
        # Single loop builds both maps. A "WT" sample (case-insensitive) maps to an
        # EMPTY expected scope ([]): a clean consensus PASSes, any observed variant
        # fails. The empty list is intentionally distinct from None (full-scope):
        # the verdict-time lookup uses `is not None`, so [] survives. The WT well is
        # also pinned to "WT" in well_to_mutant so _assign_mutant_ids attributes it
        # by ground truth (not by the position-based heuristic, which would pull a
        # contaminated WT well into a real mutant's group).
        for well_id, sample in well_to_sample.items():
            nw = _norm_well(well_id)
            sample_str = str(sample).strip()
            if sample_str.upper() == "WT":
                well_to_labels[nw] = []
                well_to_mutant[nw] = "WT"
                continue
            labels = mutant_to_labels.get(sample_str)
            if labels:
                well_to_labels[nw] = labels
                well_to_mutant[nw] = sample_str

    records = route_ingest(input_dir, ingest_mode)
    params = CompareParams(
        min_file_size_kb=min_file_size_kb,
        min_read_count=min_read_count,
        max_consensus_n_fraction=max_consensus_n_fraction,
        many_mutation_cutoff=many_cutoff,
    )

    verdicts: list[VerdictRecord] = []
    total_records = len(records)
    for i, rec in enumerate(records, 1):
        translated = translate_and_diff(
            record=rec,
            reference_seq=reference_seq,
            cds_start=cds_start,
            cds_end=cds_end,
        )
        # Scope verdict to this well's own expected label(s) when a sample_map is
        # available.  Falls back to the full expected_labels list for wells whose
        # custom_barcode cannot be parsed or whose sample name is not a known mutant.
        scoped_labels = expected_labels
        if well_to_labels is not None:
            seq = _custom_barcode_to_seq(rec.custom_barcode)
            if seq is not None:
                wid = _norm_well(seq_to_well(seq))
                scoped = well_to_labels.get(wid)
                if scoped is not None:
                    scoped_labels = scoped
        verdict = classify_verdict(translated, scoped_labels, params)
        verdicts.append(verdict)
        # Live per-record sub-progress. Unthrottled and I/O-free here; the
        # handler layer throttles emissions to avoid a stdout flood.
        if progress_callback is not None:
            progress_callback(i, total_records)

    grouped = _assign_mutant_ids(verdicts, expected_mutations, well_to_mutant=well_to_mutant)

    replicate_results: list[ReplicateResult] = []
    for mutant_id, vr_list in grouped.items():
        plate_verdicts: dict[str, VerdictRecord] = {}
        for vr in vr_list:
            nb = vr.translated.barcode.native_barcode
            if nb not in plate_verdicts:
                plate_verdicts[nb] = vr
        result = pick_best_replicate(mutant_id, plate_verdicts)
        replicate_results.append(result)

    write_excel(
        verdict_records=verdicts,
        replicate_results=replicate_results,
        output_path=output_path,
        mapper=WellMapper(),
        mode="amplicon" if mode == "amplicon" else "plasmid",
    )
    return verdicts, replicate_results
