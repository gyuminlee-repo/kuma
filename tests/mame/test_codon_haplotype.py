"""Read-level codon haplotype counting, its sidecar, and the verdict note.

The load-bearing case is CODON OVERLAP: several designed variants on one codon
that share letters. Per-position base counts cannot separate those, and that is
the entire reason this table exists, so it is tested first and with numbers
chosen so a per-position estimator would visibly disagree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kuma_core.mame.compare.verdict import classify_verdict
from kuma_core.mame.ingest import codon_haplotype as ch
from kuma_core.mame.ingest.align import Alignment, _CIGAR_M
from kuma_core.mame.ingest.consensus import call_consensus_with_metrics
from kuma_core.mame.models import (
    BarcodeRecord,
    CompareParams,
    TranslatedRecord,
    VerdictClass,
)

# 4 codons. Codon 2 (0-based) is the designed position, reference CGC, matching
# the IspS R560 layout that motivated the feature.
REFERENCE = "ATG" "AAA" "CGC" "TAA"
CODON_OF_INTEREST = 2


def _aln(seq: str) -> Alignment:
    return Alignment(
        read_id="r",
        read_seq=seq,
        mapq=60,
        cigar=[[len(seq), _CIGAR_M]],
        r_st=0,
        r_en=len(seq),
        q_st=0,
        q_en=len(seq),
        strand=1,
        reference_length=len(REFERENCE),
    )


def _reads(spec: dict[str, int]) -> list[Alignment]:
    """Build reads that are the reference with codon 2 replaced by *spec* keys."""
    out: list[Alignment] = []
    for codon, n in spec.items():
        seq = REFERENCE[:6] + codon + REFERENCE[9:]
        out.extend(_aln(seq) for _ in range(n))
    return out


def _table(spec: dict[str, int]):
    call = call_consensus_with_metrics(_reads(spec), REFERENCE, min_depth=1)
    return call, call.codon_haplotypes


# ---------------------------------------------------------------------------
# Counting
# ---------------------------------------------------------------------------


def test_codon_overlap_is_counted_per_read_not_per_position():
    """Variants sharing letters within one codon must not inherit each other.

    GAC, GTC and CTG pairwise share a base position with each other, so the
    per-position minimum over-reports the rarest. The read-level count must
    return the planted numbers exactly.
    """
    spec = {"CGC": 900, "CTG": 60, "GAC": 30, "GTC": 6, "AAC": 4}
    _call, counts = _table(spec)
    row = counts[CODON_OF_INTEREST]

    for codon, planted in spec.items():
        idx = ch.haplotype_index(codon)
        assert row[idx] == planted, f"{codon}: {row[idx]} != {planted}"

    # The estimator this replaces, computed from the same reads, is wrong here.
    per_position = []
    for offset in range(3):
        base_counts: dict[str, int] = {}
        for codon, n in spec.items():
            base_counts[codon[offset]] = base_counts.get(codon[offset], 0) + n
        per_position.append(base_counts)
    approx_gtc = min(per_position[i]["GTC"[i]] for i in range(3))
    assert approx_gtc == 36  # G from GAC+GTC, T from CTG+GTC, C from CGC+...
    assert approx_gtc > spec["GTC"] * 5  # inflated more than fivefold
    assert row[ch.haplotype_index("GTC")] == 6


def test_depth_counts_only_complete_unambiguous_codons():
    spec = {"CGC": 10}
    _call, counts = _table(spec)
    assert int(counts[CODON_OF_INTEREST].sum()) == 10

    # An N anywhere in the codon removes the whole read from that codon, and
    # leaves the neighbouring codons untouched.
    with_n = _reads({"CGC": 10})
    seq = REFERENCE[:6] + "CNC" + REFERENCE[9:]
    with_n.extend(_aln(seq) for _ in range(5))
    call = call_consensus_with_metrics(with_n, REFERENCE, min_depth=1)
    assert int(call.codon_haplotypes[CODON_OF_INTEREST].sum()) == 10
    assert int(call.codon_haplotypes[0].sum()) == 15


def test_counts_are_independent_of_batch_splitting(monkeypatch):
    """Batching is a memory bound and must not move a single count."""
    spec = {"CGC": 40, "CTG": 17, "GTC": 3}
    _call, whole = _table(spec)
    monkeypatch.setattr(
        "kuma_core.mame.ingest.consensus._BATCH_BASE_BUDGET", 24
    )
    _call2, split = _table(spec)
    assert (whole == split).all()


def test_empty_well_yields_a_zero_table():
    call = call_consensus_with_metrics([], REFERENCE, min_depth=1)
    assert call.codon_haplotypes.shape == (len(REFERENCE) // 3, 64)
    assert int(call.codon_haplotypes.sum()) == 0


# ---------------------------------------------------------------------------
# Bounded summary and lookup
# ---------------------------------------------------------------------------


def test_summary_retains_top_k_and_bounds_the_rest():
    spec = {"CGC": 500, "CTG": 40, "GAC": 30, "AAC": 20, "GTC": 3, "ACC": 2}
    _call, counts = _table(spec)
    summary = ch.summarize(counts, top_k=2, min_count=2)
    entry = summary["codons"][str(CODON_OF_INTEREST)]
    assert [seq for seq, _n in entry] == ["CTG", "GAC"]

    wells = {"1_1": summary}
    parsed = ch._parse_well(summary, 0)
    exact = parsed.lookup(CODON_OF_INTEREST, "CTG")
    assert exact.exact and exact.count == 40
    assert exact.majority_seq == "CGC" and exact.majority_count == 500

    dropped = parsed.lookup(CODON_OF_INTEREST, "GTC")
    assert not dropped.exact
    # Cannot exceed the smallest retained count, nor the unaccounted residual.
    residual = 595 - 500 - 40 - 30
    assert dropped.count == min(30, residual) == 25
    assert dropped.count >= spec["GTC"]  # a bound, never an under-report
    assert wells  # summary is JSON-shaped


def test_summary_is_deterministic_for_equal_counts():
    spec = {"CGC": 100, "AAA": 5, "TTT": 5, "GGG": 5}
    _call, counts = _table(spec)
    first = ch.summarize(counts, top_k=8, min_count=2)
    second = ch.summarize(counts, top_k=8, min_count=2)
    assert json.dumps(first) == json.dumps(second)
    assert [s for s, _n in first["codons"][str(CODON_OF_INTEREST)]] == [
        "AAA",
        "GGG",
        "TTT",
    ]


def test_sidecar_round_trip(tmp_path: Path):
    spec = {"CGC": 100, "CTG": 9}
    _call, counts = _table(spec)
    ch.write_sidecar(
        tmp_path,
        unit="sort_barcode07",
        per_well={"1_1": ch.summarize(counts)},
        n_codons=len(REFERENCE) // 3,
    )
    loaded = ch.read_sidecar(tmp_path)
    assert loaded is not None
    obs = loaded["1_1"].lookup(CODON_OF_INTEREST, "CTG")
    assert obs.exact and obs.count == 9


def test_missing_sidecar_reads_as_none(tmp_path: Path):
    assert ch.read_sidecar(tmp_path) is None
    ch.sidecar_path(tmp_path).write_text("not json", encoding="utf-8")
    assert ch.read_sidecar(tmp_path) is None


def test_sidecar_name_is_invisible_to_the_consensus_inventory_guard():
    from kuma_core.mame.ingest.stage_marker import CONSENSUS_FILE_PATTERNS
    import fnmatch

    assert not any(
        fnmatch.fnmatch(ch.SIDECAR_FILENAME, pattern)
        for pattern in CONSENSUS_FILE_PATTERNS
    )


@pytest.mark.parametrize(
    "cds_start,expected",
    [(0, 559), (3, 560), (1, None), (2, None)],
)
def test_codon_index_requires_a_matching_frame(cds_start, expected):
    assert ch.codon_index_for_aa_position(560, cds_start, 0) == expected


# ---------------------------------------------------------------------------
# Verdict reporting: the three outcomes must be distinguishable
# ---------------------------------------------------------------------------


def _record(spec: dict[str, int] | None, consensus_codon: str, read_count: int):
    haplotypes = None
    if spec is not None:
        _call, counts = _table(spec)
        haplotypes = ch._parse_well(ch.summarize(counts), 0)
    consensus = REFERENCE[:6] + consensus_codon + REFERENCE[9:]
    barcode = BarcodeRecord(
        native_barcode="sort_barcode07",
        custom_barcode="1_1",
        consensus_seq=consensus,
        file_size_kb=1.0,
        source_path=Path("1_1.fasta"),
        read_count=read_count,
        codon_haplotypes=haplotypes,
    )
    return barcode


def _verdict(spec, consensus_codon, expected_label, mutant_codon, read_count=600):
    barcode = _record(spec, consensus_codon, read_count)
    observed = [] if consensus_codon == "CGC" else ["R3L"]
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=[],
        observed_aa_changes=observed,
    )
    return classify_verdict(
        translated,
        [expected_label],
        CompareParams(min_read_count=None, max_consensus_n_fraction=None),
        expected_codons={expected_label: mutant_codon},
        cds_start=0,
    )


def test_expected_variant_is_the_majority():
    vr = _verdict({"CTG": 580, "CGC": 20}, "CTG", "R3L", "CTG")
    ev = vr.expected_codon_evidence[0]
    assert ev.count == 580 and ev.codon_depth == 600
    assert ev.majority_codon == "CTG"


def test_expected_variant_present_as_a_minority_is_reported_not_hidden():
    """The case the feature exists for: real but outvoted."""
    vr = _verdict({"CGC": 595, "CTG": 5}, "CGC", "R3L", "CTG")
    assert vr.verdict is VerdictClass.WRONG_AA  # classification unchanged
    ev = vr.expected_codon_evidence[0]
    assert ev.count == 5 and ev.codon_depth == 600
    assert ev.count_is_upper_bound is False
    assert "missing expected: R3L" in vr.verdict_notes
    assert "seen at 0.83% (5/600)" in vr.verdict_notes
    assert "majority codon CGC at 99.2%" in vr.verdict_notes


def test_expected_variant_wholly_absent_is_distinguishable_from_a_minority():
    vr = _verdict({"CGC": 600}, "CGC", "R3L", "CTG")
    assert vr.verdict is VerdictClass.WRONG_AA
    ev = vr.expected_codon_evidence[0]
    assert ev.count == 0 and ev.codon_depth == 600
    assert "seen in no read (0/600)" in vr.verdict_notes


def test_absent_sidecar_is_reported_rather_than_read_as_zero():
    vr = _verdict(None, "CGC", "R3L", "CTG")
    ev = vr.expected_codon_evidence[0]
    assert ev.unavailable_reason
    assert "minor-allele evidence unavailable" in vr.verdict_notes
    assert "re-run" in vr.verdict_notes


def test_thin_codon_coverage_is_flagged_as_inconclusive():
    """A codon the aligner barely covered must not read as 'variant absent'.

    This is the IspS terminal-codon failure: 5 reads placed over the last codon
    of a 446 read well, so the consensus calls wild type from a handful of reads
    while the well is overwhelmingly mutant.
    """
    vr = _verdict({"CGC": 5}, "CGC", "R3L", "CTG", read_count=446)
    ev = vr.expected_codon_evidence[0]
    assert ev.codon_depth == 5 and ev.well_read_count == 446
    assert "codon coverage 5/446 of well reads" in vr.verdict_notes
    assert "inconclusive" in vr.verdict_notes


def test_evidence_is_absent_when_no_design_codons_are_supplied():
    """Existing callers must be untouched."""
    barcode = _record({"CGC": 600}, "CGC", 600)
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=[],
        observed_aa_changes=[],
    )
    vr = classify_verdict(
        translated,
        ["R3L"],
        CompareParams(min_read_count=None, max_consensus_n_fraction=None),
    )
    assert vr.expected_codon_evidence == []
    assert vr.verdict_notes == "missing expected: R3L"
