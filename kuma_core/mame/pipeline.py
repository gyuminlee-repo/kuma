"""End-to-end analyze pipeline glue (ingest -> translate -> compare -> select -> export)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from kuma_core.mame.compare import classify_verdict, parse_mutation_label
from kuma_core.mame.export import WellMapper, write_excel
from kuma_core.mame.ingest import IngestMode, route_ingest
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
    many_cutoff: int = 5,
    ingest_mode: IngestMode = IngestMode.BARCODE,
) -> tuple[list[VerdictRecord], list[ReplicateResult]]:
    """Run the full pipeline and write the Excel output. Returns in-memory results."""

    reference_seq = _read_reference_fasta(reference_path)
    expected_mutations = read_expected_mutations(expected_path)
    expected_labels = expected_to_labels(expected_mutations)

    records = route_ingest(input_dir, ingest_mode)
    params = CompareParams(
        min_file_size_kb=min_file_size_kb,
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
        verdict = classify_verdict(translated, expected_labels, params)
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
