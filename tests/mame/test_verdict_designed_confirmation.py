"""Regression tests for three verdict/consensus scoring defects.

1. The indel-event gate awarded AMBIGUOUS (counted as ``detected``, ranked first
   by ``select/best_pick``) before the designed mutations were compared, so a
   deletion-bearing well with no designed mutation inflated recovery_rate.
2. ``consensus_n_fraction`` divided by the whole reference length, so a plasmid
   map reference (CDS plus backbone) drove every well to NO_CALL.
3. The expected WT residue was parsed and discarded, so a coordinate-origin
   mismatch between the KURO sheet and the CDS scored the plate against the wrong
   residue while still reporting PASS.

Synthetic ``Alignment`` objects are fed through the real consensus caller,
translator, and verdict classifier; no minimap2 binary is needed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.compare import classify_verdict
from kuma_core.mame.compare.verdict import ExpectedCoordinateMismatchError
from kuma_core.mame.detected import compute_recovery, is_detected
from kuma_core.mame.ingest.align import Alignment
from kuma_core.mame.ingest.consensus import call_consensus_with_metrics
from kuma_core.mame.models import BarcodeRecord, CompareParams, ReplicateResult
from kuma_core.mame.translate.aa_translator import translate_and_diff

# 20-codon CDS. Residue 5 is I (ATT).
CDS = (
    "ATGAAAGGTCTGATTGAATTCCATAGCGTT"
    "AACGGCTATCTGACCGAATTTCAGAGCGTG"
)
CDS_I5F = CDS[:12] + "TTT" + CDS[15:]


def _aln(ref: str, seq: str, cigar: list[list[int]], r_st: int, rid: str) -> Alignment:
    ref_span = sum(length for length, op in cigar if op in (0, 2, 3, 7, 8))
    return Alignment(
        read_id=rid,
        read_seq=seq,
        mapq=60,
        cigar=cigar,
        r_st=r_st,
        r_en=r_st + ref_span,
        q_st=0,
        q_en=len(seq),
        strand=1,
        reference_length=len(ref),
    )


def _record(call, read_count: int) -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq=call.consensus_seq,
        file_size_kb=60.0,
        source_path=Path("/tmp/mock.fasta"),
        read_count=read_count,
        n_mixed_positions=call.n_mixed_positions,
        max_minor_allele_fraction=call.max_minor_allele_fraction,
        n_low_depth_positions=call.n_low_depth_positions,
        consensus_n_fraction=call.consensus_n_fraction,
        n_low_quality_bases=call.n_low_quality_bases,
        n_indel_event_positions=call.n_indel_event_positions,
        max_indel_event_fraction=call.max_indel_event_fraction,
        max_del_run_length=call.max_del_run_length,
    )


def _well(
    ref: str,
    reads: list[tuple[str, list[list[int]], int]],
    cds_start: int,
    cds_end: int,
    min_depth: int = 3,
):
    alns = [
        _aln(ref, seq, cigar, r_st, f"r{i}")
        for i, (seq, cigar, r_st) in enumerate(reads)
    ]
    call = call_consensus_with_metrics(alns, ref, min_depth=min_depth)
    record = _record(call, read_count=len(reads))
    return call, translate_and_diff(record, ref, cds_start, cds_end)


def _deletion_reads(template: str, n: int) -> list[tuple[str, list[list[int]], int]]:
    """n reads carrying a 2 bp deletion at reference positions 30-31."""
    seq = template[:30] + template[32:]
    cigar = [[30, 0], [2, 2], [len(template) - 32, 0]]
    return [(seq, cigar, 0)] * n


# ------------------------------------------------------------------ defect 1


def test_indel_gate_does_not_report_detected_without_the_designed_mutation() -> None:
    """A deletion-bearing well missing its designed mutation is not detected."""
    _call, translated = _well(CDS, _deletion_reads(CDS, 150), 0, len(CDS))

    assert translated.observed_aa_changes == []
    verdict = classify_verdict(translated, ["I5F"], CompareParams())

    assert not is_detected(verdict.verdict)
    # The indel evidence is still carried forward for the user.
    assert "indel event signal" in verdict.verdict_notes

    replicate = ReplicateResult(mutant_id="M1", plate_verdicts={"NB01": verdict})
    metrics = compute_recovery([replicate], {"M1"})
    assert metrics is not None
    assert metrics.recovery_rate == 0.0


def test_indel_gate_still_reports_ambiguous_when_the_design_is_confirmed() -> None:
    """Designed mutation present plus indel evidence stays AMBIGUOUS/detected."""
    _call, translated = _well(CDS, _deletion_reads(CDS_I5F, 150), 0, len(CDS))

    assert "I5F" in translated.observed_aa_changes
    verdict = classify_verdict(translated, ["I5F"], CompareParams())

    assert is_detected(verdict.verdict)
    assert "indel event signal" in verdict.verdict_notes


def test_indel_gate_flags_wrong_mt_rather_than_ambiguous() -> None:
    """An indel well whose observed MT differs from the design is not detected."""
    _call, translated = _well(CDS, _deletion_reads(CDS_I5F, 150), 0, len(CDS))

    # Same position, different designed MT.
    verdict = classify_verdict(translated, ["I5W"], CompareParams())

    assert not is_detected(verdict.verdict)
    assert "indel event signal" in verdict.verdict_notes


# ------------------------------------------------------------------ defect 2


def test_consensus_n_fraction_ignores_reference_outside_the_amplicon() -> None:
    """A CDS embedded in plasmid backbone must not read as a no-call well."""
    ref = "A" * 800 + CDS + "C" * 900
    cds_start, cds_end = 800, 800 + len(CDS)
    reads = [(CDS_I5F, [[len(CDS_I5F), 0]], cds_start) for _ in range(150)]

    call, translated = _well(ref, reads, cds_start, cds_end)

    assert call.consensus_n_fraction == 0.0
    verdict = classify_verdict(translated, ["I5F"], CompareParams())
    assert verdict.verdict.value == "PASS"


def test_consensus_n_fraction_ignores_ragged_read_ends() -> None:
    """Positions below min_depth are a coverage shortfall, not consensus noise."""
    reads: list[tuple[str, list[list[int]], int]] = []
    for i in range(150):
        offset = 0 if i < 2 else 3 + (i % 4)
        seq = CDS_I5F[offset : len(CDS_I5F) - offset]
        reads.append((seq, [[len(seq), 0]], offset))

    call, translated = _well(CDS, reads, 0, len(CDS))

    assert call.n_low_depth_positions > 0  # the ragged ends are still reported
    assert call.consensus_n_fraction == 0.0
    verdict = classify_verdict(translated, ["I5F"], CompareParams())
    assert verdict.verdict.value == "PASS"


def test_consensus_n_fraction_still_flags_a_genuine_no_call_well() -> None:
    """Deletion-majority positions inside the amplicon keep driving NO_CALL."""
    half = len(CDS) // 2
    reads = [
        (CDS[:half], [[half, 0], [len(CDS) - half, 2]], 0) for _ in range(150)
    ]

    call, translated = _well(CDS, reads, 0, len(CDS))

    assert call.consensus_n_fraction == pytest.approx(0.5)
    verdict = classify_verdict(
        translated, ["I5F"], CompareParams(max_indel_event_fraction=None)
    )
    assert verdict.verdict.value == "NO_CALL"


def test_consensus_n_fraction_is_one_when_nothing_reaches_min_depth() -> None:
    """A well with no usable coverage is fully no-call, not vacuously clean."""
    reads = [(CDS, [[len(CDS), 0]], 0)]
    call, _translated = _well(CDS, reads, 0, len(CDS), min_depth=5)

    assert call.consensus_n_fraction == 1.0


# ------------------------------------------------------------------ defect 3


def test_expected_wt_mismatch_aborts_instead_of_passing() -> None:
    """A coordinate-origin mismatch fails fast instead of scoring a silent PASS."""
    reads = [(CDS_I5F, [[len(CDS_I5F), 0]], 0) for _ in range(150)]
    _call, translated = _well(CDS, reads, 0, len(CDS))

    assert translated.observed_aa_changes == ["I5F"]
    with pytest.raises(ExpectedCoordinateMismatchError) as excinfo:
        classify_verdict(translated, ["V5F"], CompareParams())

    message = str(excinfo.value)
    assert "position 5 is I" in message
    assert "claims V" in message


def test_expected_wt_mismatch_reports_a_candidate_offset() -> None:
    """The error names an offset that would line the two coordinate systems up."""
    # Two designed sites; the second label uses the reference residue found one
    # position away, which is the offset hint the message should surface.
    mutant = CDS_I5F[:18] + "TAT" + CDS_I5F[21:]  # codon 7 F -> Y
    reads = [(mutant, [[len(mutant), 0]], 0) for _ in range(150)]
    _call, translated = _well(CDS, reads, 0, len(CDS))

    assert translated.observed_aa_changes == ["I5F", "F7Y"]
    with pytest.raises(ExpectedCoordinateMismatchError) as excinfo:
        classify_verdict(translated, ["F5Y"], CompareParams())

    assert "offset +2" in str(excinfo.value)


def test_matching_expected_wt_is_unaffected() -> None:
    """The guard stays silent when the two coordinate systems agree."""
    reads = [(CDS_I5F, [[len(CDS_I5F), 0]], 0) for _ in range(150)]
    _call, translated = _well(CDS, reads, 0, len(CDS))

    verdict = classify_verdict(translated, ["I5F"], CompareParams())
    assert verdict.verdict.value == "PASS"
