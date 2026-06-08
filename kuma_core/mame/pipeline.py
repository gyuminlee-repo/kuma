"""End-to-end analyze pipeline glue (ingest -> translate -> compare -> select -> export)."""

from __future__ import annotations

from collections import defaultdict
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
) -> dict[str, list[VerdictRecord]]:
    """Group verdict records by the best-matching mutant_id.

    Strategy: iterate expected mutations and attach any verdict whose observed AA
    set contains the expected substitution label, or whose verdict class is
    WRONG_AA at the expected position, or whose verdict is LOWDEPTH/FRAMESHIFT/
    MANY (unknown target — still attempt assignment based on file naming).
    """

    grouped: dict[str, list[VerdictRecord]] = defaultdict(list)

    expected_by_pos: dict[int, ExpectedMutation] = {m.position: m for m in expected}
    assigned: set[int] = set()

    for idx, vr in enumerate(verdicts):
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
            elif vr.verdict is VerdictClass.LOWDEPTH and expected:
                matched_id = expected[idx % len(expected)].mutant_id
            else:
                # 4) Fall back to `<native>_<custom>` to keep the record addressable.
                matched_id = (
                    f"UNKNOWN_{vr.translated.barcode.native_barcode}_"
                    f"{vr.translated.barcode.custom_barcode}"
                )
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
    min_read_count: int | None = None,
    max_consensus_n_fraction: float | None = 0.0,
    many_cutoff: int = 5,
    ingest_mode: IngestMode = IngestMode.BARCODE,
    sample_map_path: Path | None = None,
) -> tuple[list[VerdictRecord], list[ReplicateResult]]:
    """Run the full pipeline and write the Excel output. Returns in-memory results."""

    reference_seq = _read_reference_fasta(reference_path)
    expected_mutations = read_expected_mutations(expected_path)
    expected_labels = expected_to_labels(expected_mutations)

    # Build per-mutant label lists for verdict scoping.
    # Keys are mutant_id strings (e.g. "V5F", "K53N"); values are lists of
    # human-readable AA labels (e.g. ["V5F"]).  Only non-empty entries are kept.
    mutant_to_labels: dict[str, list[str]] = defaultdict(list)
    for m in expected_mutations:
        mutant_to_labels[m.mutant_id].append(f"{m.wt_aa}{m.position}{m.mt_aa}")

    # Build well_id -> scoped label list when sample_map_path is provided.
    # - If sample_map_path is None (amplicon / non-combinatorial modes): well_to_labels
    #   stays None and every well is compared against the full expected_labels list,
    #   preserving byte-identical backward-compatible behaviour.
    # - If a well's custom_barcode cannot be resolved to a well coordinate (non-R_F
    #   barcode format), _custom_barcode_to_seq returns None -> fallback to full list.
    # - If a well_id appears in the sample_map but the sample name is not a known
    #   mutant_id, scoped is None -> fallback to full list (defensive "unknown well"
    #   path; the well will receive WRONG_AA, which is the correct result when we
    #   genuinely cannot identify its intended mutation).
    well_to_labels: dict[str, list[str]] | None = None
    if sample_map_path is not None:
        well_to_sample = parse_sample_map(sample_map_path)   # {"A01": "V5F", ...}
        well_to_labels = {}
        for well_id, sample in well_to_sample.items():
            labels = mutant_to_labels.get(str(sample).strip())
            if labels:
                well_to_labels[_norm_well(well_id)] = labels

    records = route_ingest(input_dir, ingest_mode)
    params = CompareParams(
        min_file_size_kb=min_file_size_kb,
        min_read_count=min_read_count,
        max_consensus_n_fraction=max_consensus_n_fraction,
        many_mutation_cutoff=many_cutoff,
    )

    verdicts: list[VerdictRecord] = []
    for rec in records:
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

    grouped = _assign_mutant_ids(verdicts, expected_mutations)

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
