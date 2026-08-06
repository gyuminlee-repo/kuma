"""End-to-end analyze pipeline glue (ingest -> translate -> compare -> select -> export)."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from kuma_core.mame.compare import classify_verdict, parse_mutation_label
from kuma_core.mame.detected import designed_mutant_ids as _designed_mutant_ids_from_expected
from kuma_core.mame.export import WellMapper, write_excel
from kuma_core.mame.export.excel_writer import _custom_barcode_to_seq
from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.ingest import IngestMode, route_ingest
from kuma_core.mame.io.kuro_reader import expected_to_labels
from kuma_core.mame.io.variant_list import read_variant_source
from kuma_core.mame.perf import TIMER
from kuma_core.mame.plate_geometry import norm_well as _norm_well
from kuma_core.mame.models import (
    BarcodeRecord,
    CompareParams,
    ExpectedMutation,
    ReplicateResult,
    VerdictRecord,
)
from kuma_core.mame.select import pick_best_replicate, prefer_within_plate
from kuma_core.mame.translate import translate_and_diff


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
    a well is attributed to the mutant placed there by the run layout (ground
    truth), overriding observation-based heuristics.  This makes Final/matrix
    grouping coherent with the per-well verdict scoping that reads the same
    layout.  Falls through to the observation-based heuristics for wells with a
    non-R_F custom_barcode or no layout entry.

    Strategy (observation-based fallback): attach a verdict whose observed AA set
    contains an expected substitution label, then a verdict observing an expected
    position (WRONG_AA / AMBIGUOUS).  A record with neither signal (LOWDEPTH,
    NO_CALL, or a WRONG_AA at an unexpected position) is left unattributed under
    an ``UNKNOWN_<native>_<custom>`` key rather than guessed at.
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
            # 3) No placement map, no label match, no position match. The record
            # carries no evidence of which mutant it belongs to, so it stays
            # unattributed: attributing it (previously `expected[idx % len]`,
            # i.e. list position deciding the mutant) reports a guess as fact and
            # pollutes per-mutant replicate counts. Supply a well_layout to
            # place these wells.
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
    well_layout: dict[str, str] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    designed_mutant_ids: frozenset[str] | None = None,
    records: list[BarcodeRecord] | None = None,
    expected_mutations: list[ExpectedMutation] | None = None,
    perf_scope: str | None = "analyze",
    variant_sheet: str | None = None,
    variant_column: str | None = None,
    barcode_prefix_note: str | None = None,
) -> tuple[list[VerdictRecord], list[ReplicateResult]]:
    """Run the full pipeline and write the Excel output. Returns in-memory results.

    ``progress_callback`` is an optional ``(index, total)`` sink invoked once per
    processed record during the per-record verdict loop (``index`` is 1-based and
    the final call has ``index == total``). It defaults to ``None`` so existing
    callers and tests are unaffected. The handler layer uses it to surface live
    sub-progress; the domain layer stays I/O-agnostic and never throttles.

    ``records`` and ``expected_mutations`` let a caller that has ALREADY paid for
    those two reads hand them in instead of having them re-read here.  The sidecar
    handler ingests the same directory for its distribution stats and reads the
    same expected-mutations xlsx for the recovery denominator, so without these
    the consensus tree was walked twice per analyze (0.9 s of duplicated 9p round
    trips on the reference workload) and the xlsx parsed twice.  ``input_dir`` /
    ``expected_path`` stay required because they are still the identity of the run
    that is reported and exported.

    ``perf_scope`` names the :mod:`kuma_core.mame.perf` scope reported for this
    call.  ``None`` means the caller owns the measurement window (it called
    ``TIMER.begin()`` itself and will call ``TIMER.end()``), which is how the
    handler gets ONE report covering the work it does around this function
    instead of a nested second report that would double-count every phase.

    ``variant_sheet`` / ``variant_column`` name the sheet and column to read
    ``expected_path`` from when it is a plain variant list rather than a KURO
    export.  Both default to ``None``, which is auto-detection and leaves a KURO
    export on exactly the path it took before.  They are ignored when
    ``expected_mutations`` is supplied, since nothing is read then.
    """

    _perf_base = TIMER.begin() if perf_scope is not None else None
    reference_seq = _read_reference_fasta(reference_path)
    if expected_mutations is None:
        with TIMER.phase("expected_read"):
            expected_mutations = read_variant_source(
                expected_path, sheet=variant_sheet, variant_column=variant_column
            ).expected
    expected_labels = expected_to_labels(expected_mutations)

    # Build per-mutant label lists for verdict scoping.
    # Keys are mutant_id strings (e.g. "V5F", "K53N"); values are lists of
    # human-readable AA labels (e.g. ["V5F"]).  Only non-empty entries are kept.
    mutant_to_labels: dict[str, list[str]] = defaultdict(list)
    for m in expected_mutations:
        mutant_to_labels[m.mutant_id].append(f"{m.wt_aa}{m.position}{m.mt_aa}")

    # Build well_id -> scoped label list from the run layout.
    # - If no well_layout is given (amplicon / non-combinatorial modes):
    #   well_to_labels stays None and every well is compared against the full
    #   expected_labels list, preserving byte-identical legacy behaviour.
    # - If a well's custom_barcode cannot be resolved to a well coordinate (non-R_F
    #   barcode format), _custom_barcode_to_seq returns None -> fallback to full list.
    # - If a well_id appears in the layout but the sample name is not a known
    #   mutant_id (and not "WT"), it is omitted -> verdict-time lookup returns None
    #   -> fallback to full list (defensive "unknown well" path; the well will
    #   receive WRONG_AA, the correct result when the intended mutation is unknown).
    # There used to be a second source here, a sample-map xlsx of (sample, well)
    # pairs. It is gone: the computed draft states the same thing without a file
    # to keep in step with the variant list, and two sources for one plate meant
    # one of them was always the one nobody had updated.
    well_to_sample: dict[str, str] | None = well_layout

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

    if records is None:
        with TIMER.phase("ingest"):
            records = route_ingest(input_dir, ingest_mode)
    params = CompareParams(
        min_file_size_kb=min_file_size_kb,
        min_read_count=min_read_count,
        max_consensus_n_fraction=max_consensus_n_fraction,
        many_mutation_cutoff=many_cutoff,
    )

    verdicts: list[VerdictRecord] = []
    total_records = len(records)
    # Per-record timing (records are wells, not reads) accumulated in locals and
    # committed once after the loop, so the timer costs two perf_counter calls
    # per record and no lock traffic inside it.
    _t_translate = 0.0
    _t_verdict = 0.0
    for i, rec in enumerate(records, 1):
        _t0 = time.perf_counter()
        translated = translate_and_diff(
            record=rec,
            reference_seq=reference_seq,
            cds_start=cds_start,
            cds_end=cds_end,
        )
        _t1 = time.perf_counter()
        _t_translate += _t1 - _t0
        # Scope verdict to this well's own expected label(s) when a layout is
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
        _t2 = time.perf_counter()
        verdict = classify_verdict(translated, scoped_labels, params)
        verdicts.append(verdict)
        _t_verdict += time.perf_counter() - _t2
        # Live per-record sub-progress. Unthrottled and I/O-free here; the
        # handler layer throttles emissions to avoid a stdout flood.
        if progress_callback is not None:
            progress_callback(i, total_records)

    TIMER.add("translate_diff", _t_translate)
    TIMER.add("verdict_classify", _t_verdict)

    grouped = _assign_mutant_ids(verdicts, expected_mutations, well_to_mutant=well_to_mutant)

    replicate_results: list[ReplicateResult] = []
    for mutant_id, vr_list in grouped.items():
        plate_verdicts: dict[str, VerdictRecord] = {}
        for vr in vr_list:
            nb = vr.translated.barcode.native_barcode
            # When one mutant occupies several wells of the same plate, keep the
            # best-verdict well (PASS over AMBIGUOUS, etc.) rather than whichever
            # record happens to come first; ties break on read volume.
            incumbent = plate_verdicts.get(nb)
            if incumbent is None or prefer_within_plate(vr, incumbent):
                plate_verdicts[nb] = vr
        result = pick_best_replicate(mutant_id, plate_verdicts)
        replicate_results.append(result)

    designed = (
        designed_mutant_ids
        if designed_mutant_ids is not None
        else _designed_mutant_ids_from_expected(expected_mutations)
    )
    with TIMER.phase("export_excel"):
        write_excel(
            verdict_records=verdicts,
            replicate_results=replicate_results,
            output_path=output_path,
            mapper=WellMapper(),
            mode="amplicon" if mode == "amplicon" else "plasmid",
            designed_mutant_ids=designed,
            # Provenance for the seeds this run matched against; the caller that
            # read the barcode workbook is the only layer that knows it.
            barcode_prefix_note=barcode_prefix_note,
        )

    if perf_scope is not None and _perf_base is not None:
        TIMER.end(perf_scope, _perf_base, records=total_records)

    return verdicts, replicate_results
