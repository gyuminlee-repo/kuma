import json
from dataclasses import replace
from pathlib import Path

import pytest

from kuma_core.mame.compare import classify_verdict
from kuma_core.mame.compare.verdict import gate_consensus_n_fraction
from kuma_core.mame.ingest.align import Alignment
from kuma_core.mame.ingest.consensus import ConsensusCall, call_consensus_with_metrics
from kuma_core.mame.ingest.consensus_metadata import (
    ConsensusMetadata,
    format_consensus_fasta_record,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file
from kuma_core.mame.models import BarcodeRecord, CompareParams, ReplicateResult, VerdictClass
from kuma_core.mame.translate.aa_translator import translate_and_diff
from sidecar_mame.core import get_state, reset_state
from sidecar_mame.handlers.analyze import _serialize_replicate, _serialize_verdict
from sidecar_mame.handlers.load import handle_load_analyze_result

REF = "ATG" + "GCT" * 59
MUTANT = REF[:4] + "T" + REF[5:]


def _read(seq: str, cigar: list[list[int]]) -> Alignment:
    return Alignment(
        read_id="read", read_seq=seq, mapq=60, cigar=cigar,
        r_st=0, r_en=len(REF), q_st=0, q_en=len(seq),
        strand=1, reference_length=len(REF),
    )


def _reads(deletions: int) -> list[Alignment]:
    deleted = _read(MUTANT[:60] + MUTANT[63:], [[60, 0], [3, 2], [117, 0]])
    alt = MUTANT[:60] + "AAA" + MUTANT[63:]
    return (
        [deleted] * deletions
        + [_read(MUTANT, [[180, 0]])] * ((10 - deletions) // 2)
        + [_read(alt, [[180, 0]])] * (10 - deletions - (10 - deletions) // 2)
    )


def _fasta_roundtrip(tmp_path: Path, call: ConsensusCall) -> BarcodeRecord:
    metadata = ConsensusMetadata(
        depth=10, input_reads=10, aligned_reads=10, mapq_failed=0,
        span_failed=0, mixed_positions=call.n_mixed_positions,
        max_minor_allele_fraction=call.max_minor_allele_fraction,
        low_depth_positions=call.n_low_depth_positions,
        consensus_n_fraction=call.consensus_n_fraction, low_quality_bases=0,
        n_no_call_deletion=call.n_no_call_deletion,
        n_no_call_deletion_majority=call.n_no_call_deletion_majority,
        n_no_call_zero_depth=call.n_no_call_zero_depth,
        n_no_call_ambiguous=call.n_no_call_ambiguous,
        n_no_call_no_majority=call.n_no_call_no_majority,
        del_majority_positions=call.del_majority_positions,
        n_del_majority_positions=call.n_del_majority_positions,
        noisy_positions=call.noisy_positions,
        max_indel_event_fraction=call.max_indel_event_fraction,
        consensus_net_indel=call.consensus_net_indel_bp,
    )
    path = tmp_path / "1_1.fasta"
    path.write_text(format_consensus_fasta_record("1_1", call.consensus_seq, metadata))
    return parse_fasta_file(path, native_barcode="NB01")


@pytest.mark.parametrize("deletions,expected", [
    (4, VerdictClass.NO_CALL),
    (5, VerdictClass.NO_CALL),
    (6, VerdictClass.PASS),
])
def test_reads_to_fasta_to_verdict_require_strict_majority(
    tmp_path: Path, deletions: int, expected: VerdictClass,
) -> None:
    # Given: A2V is confirmed in the CDS; the disputed deletion is outside it.
    call = call_consensus_with_metrics(_reads(deletions), REF)
    barcode = _fasta_roundtrip(tmp_path, call)
    translated = translate_and_diff(barcode, REF, 0, 30)
    assert translated.observed_aa_changes == ["A2V"]

    # When: the normal default N threshold judges the real translated record.
    verdict = classify_verdict(
        translated, ["A2V"], CompareParams(min_read_count=10, max_indel_event_fraction=None),
    )

    # Then: plurality and exact ties cannot borrow the decided-deletion exemption.
    print(f"del={deletions}/10 raw={barcode.consensus_n_fraction} "
          f"bucket={barcode.n_no_call_deletion} strict={barcode.n_del_majority_positions} "
          f"gate={gate_consensus_n_fraction(barcode)} verdict={verdict.verdict.value}")
    assert verdict.verdict is expected
    assert gate_consensus_n_fraction(barcode)[1] == (3 if deletions > 5 else 0)

    replicate = ReplicateResult(
        mutant_id="A2V", plate_verdicts={"NB01": verdict},
        selected_plate="NB01", selection_reason="only replicate",
    )
    payload = json.loads(json.dumps({
        "verdicts": [_serialize_verdict(verdict)],
        "replicates": [_serialize_replicate(replicate)],
        "output_path": str(tmp_path / "unused.xlsx"),
    }))
    try:
        assert handle_load_analyze_result(payload)["restored"] is True
        state = get_state()
        assert state.last_verdicts is not None
        assert state.last_replicates is not None
        for restored in (
            state.last_verdicts[0],
            state.last_replicates[0].plate_verdicts["NB01"],
        ):
            assert restored.verdict is expected
            assert gate_consensus_n_fraction(restored.translated.barcode) == (
                gate_consensus_n_fraction(barcode)
            )
            assert classify_verdict(
                restored.translated, ["A2V"],
                CompareParams(min_read_count=10, max_indel_event_fraction=None),
            ).verdict is expected
    finally:
        reset_state()


@pytest.mark.parametrize("strict", [None, -1, 4])
def test_legacy_or_inconsistent_subset_cannot_exempt_deletion(
    tmp_path: Path, strict: int | None,
) -> None:
    barcode = _fasta_roundtrip(tmp_path, call_consensus_with_metrics(_reads(6), REF))
    barcode = replace(barcode, n_no_call_deletion_majority=strict)
    assert gate_consensus_n_fraction(barcode) == (barcode.consensus_n_fraction, 0)


@pytest.mark.parametrize("suffix", ["", " no_call_deletion_majority=bad"])
def test_legacy_or_malformed_header_keeps_reported_fraction(
    tmp_path: Path, suffix: str,
) -> None:
    path = tmp_path / "1_1.fasta"
    path.write_text(
        ">1_1 depth=40 consensus_n_fraction=0.017 "
        "consensus_n_fraction_basis=covered no_call_deletion=3" + suffix
        + "\n" + MUTANT[:60] + "NNN" + MUTANT[63:] + "\n"
    )
    barcode = parse_fasta_file(path, native_barcode="NB01")
    assert barcode.n_no_call_deletion_majority is None
    assert gate_consensus_n_fraction(barcode) == (0.017, 0)
    assert classify_verdict(
        translate_and_diff(barcode, REF, 0, 30), ["A2V"], CompareParams(),
    ).verdict is VerdictClass.NO_CALL


def test_uncovered_strict_deletion_does_not_cancel_covered_plurality(
    tmp_path: Path,
) -> None:
    reads = [
        replace(
            read, r_en=80, q_en=77 if i < 4 else 80,
            cigar=[[60, 0], [3, 2], [17, 0]] if i < 4 else [[80, 0]],
            read_seq=read.read_seq[:77 if i < 4 else 80],
        )
        for i, read in enumerate(_reads(4))
    ]
    reads.append(replace(_read(
        MUTANT[80:90] + MUTANT[93:],
        [[10, 0], [3, 2], [87, 0]],
    ), r_st=80))
    call = call_consensus_with_metrics(reads, REF, min_depth=2)
    assert call.n_del_majority_positions == 3
    assert call.n_no_call_deletion == 3
    assert call.n_no_call_deletion_majority == 0
    barcode = _fasta_roundtrip(tmp_path, call)
    assert gate_consensus_n_fraction(barcode) == (barcode.consensus_n_fraction, 0)


def test_strict_deletion_leaves_ambiguous_positions_unresolved(tmp_path: Path) -> None:
    reads = [
        replace(read, read_seq=read.read_seq[:75] + "N" + read.read_seq[76:])
        for read in _reads(6)
    ]
    call = call_consensus_with_metrics(reads, REF)
    assert call.n_no_call_deletion_majority == 3
    assert call.n_no_call_ambiguous > 0
    barcode = _fasta_roundtrip(tmp_path, call)
    fraction, excluded = gate_consensus_n_fraction(barcode)
    assert 0 < fraction < barcode.consensus_n_fraction
    assert excluded == 3
    assert classify_verdict(
        translate_and_diff(barcode, REF, 0, 30), ["A2V"],
        CompareParams(min_read_count=10, max_indel_event_fraction=None),
    ).verdict is VerdictClass.NO_CALL


def test_majority_subset_survives_omitted_coordinate_budget(tmp_path: Path) -> None:
    cigar = [[1, op] for _ in range(66) for op in (2, 0)] + [[48, 0]]
    seq = "".join(base for i, base in enumerate(MUTANT) if i >= 132 or i % 2)
    call = call_consensus_with_metrics([_read(seq, cigar)] * 10, REF)
    assert call.del_majority_positions == ()
    assert call.n_del_majority_positions == 66
    barcode = _fasta_roundtrip(tmp_path, call)
    assert gate_consensus_n_fraction(barcode) == (0.0, 66)


@pytest.mark.parametrize("remove_decomposition", [False, True])
def test_legacy_public_snapshot_keeps_verdict_but_does_not_invent_subset(
    tmp_path: Path, remove_decomposition: bool,
) -> None:
    barcode = _fasta_roundtrip(tmp_path, call_consensus_with_metrics(_reads(6), REF))
    verdict = classify_verdict(
        translate_and_diff(barcode, REF, 0, 30), ["A2V"],
        CompareParams(min_read_count=10, max_indel_event_fraction=None),
    )
    serialized = _serialize_verdict(verdict)
    del serialized["n_no_call_deletion_majority"]
    if remove_decomposition:
        for key in ("n_no_call_zero_depth", "n_no_call_deletion",
                    "n_no_call_ambiguous", "n_no_call_no_majority"):
            del serialized[key]
    try:
        payload = json.loads(json.dumps({
            "verdicts": [serialized], "replicates": [],
            "output_path": str(tmp_path / "unused.xlsx"),
        }))
        assert handle_load_analyze_result(payload)["restored"] is True
        restored = get_state().last_verdicts
        assert restored is not None
        assert restored[0].verdict is VerdictClass.PASS
        assert restored[0].translated.barcode.n_no_call_deletion_majority is None
        assert gate_consensus_n_fraction(restored[0].translated.barcode) == (
            barcode.consensus_n_fraction, 0,
        )
    finally:
        reset_state()


def test_single_position_review_reproduction(tmp_path: Path) -> None:
    deleted = _read(MUTANT[:60] + MUTANT[61:], [[60, 0], [1, 2], [119, 0]])
    alt = _read(MUTANT[:60] + "A" + MUTANT[61:], [[180, 0]])
    reads = [deleted] * 4 + [_read(MUTANT, [[180, 0]])] * 3 + [alt] * 3
    call = call_consensus_with_metrics(reads, REF)
    assert call.consensus_n_fraction == 1 / 180
    assert call.n_no_call_deletion == 1
    assert call.n_del_majority_positions == 0
    barcode = _fasta_roundtrip(tmp_path, call)
    direct = replace(barcode, consensus_n_fraction=call.consensus_n_fraction)
    for record in (direct, barcode):
        assert gate_consensus_n_fraction(record) == (record.consensus_n_fraction, 0)
        verdict = classify_verdict(
            translate_and_diff(record, REF, 0, 30), ["A2V"],
            CompareParams(min_read_count=10),
        )
        assert verdict.verdict is VerdictClass.NO_CALL
        print(f"single-position raw={record.consensus_n_fraction} "
              f"gate={gate_consensus_n_fraction(record)} verdict={verdict.verdict.value}")
