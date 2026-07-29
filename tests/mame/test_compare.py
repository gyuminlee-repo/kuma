"""6-class verdict tests (F-01 .. F-06) + min_file_size parameterization."""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.compare import classify_verdict
from kuma_core.mame.models import (
    BarcodeRecord,
    CompareParams,
    TranslatedRecord,
    VerdictClass,
)


def _tr(
    observed_aa: list[str],
    observed_nt: list[str] | None = None,
    file_size_kb: float = 60.0,
    read_count: int | None = None,
    n_mixed_positions: int = 0,
    max_minor_allele_fraction: float = 0.0,
    n_low_depth_positions: int = 0,
    consensus_n_fraction: float = 0.0,
    n_low_quality_bases: int = 0,
) -> TranslatedRecord:
    barcode = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq="",
        file_size_kb=file_size_kb,
        source_path=Path("/tmp/mock.fasta"),
        read_count=read_count,
        n_mixed_positions=n_mixed_positions,
        max_minor_allele_fraction=max_minor_allele_fraction,
        n_low_depth_positions=n_low_depth_positions,
        consensus_n_fraction=consensus_n_fraction,
        n_low_quality_bases=n_low_quality_bases,
    )
    return TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=list(observed_nt or []),
        observed_aa_changes=list(observed_aa),
    )


def _params(**overrides: object) -> CompareParams:
    base = CompareParams()
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def test_f01_pass() -> None:
    tr = _tr(["V5F"])
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.PASS


def test_f02_ambiguous() -> None:
    # K48del + K53N; distance 5 codons == indel_window_codon (inclusive boundary).
    tr = _tr(["K48-", "K53N"])
    result = classify_verdict(tr, ["K53N"], _params())
    assert result.verdict is VerdictClass.AMBIGUOUS
    assert "within" in result.verdict_notes


def test_f03_frameshift() -> None:
    tr = _tr(
        observed_aa=[],
        observed_nt=["211_INDEL", "212_INDEL"],
    )
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.FRAMESHIFT


def test_f04_many() -> None:
    tr = _tr(["M1L", "V3L", "V5F", "K18L", "K48L", "K53L"])  # 6 changes
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.MANY


def test_many_is_an_excess_gate_not_absolute() -> None:
    """A multi-site design that perfectly matches expected is PASS, never MANY.

    Regression: the MANY gate compared the raw observed count against the cutoff,
    so a legitimate >5-site (e.g. combinatorial) well whose observed AA changes
    exactly equalled its expected list was misclassified MANY and surfaced in the
    plate plan as a fail. MANY must only fire when a well carries MORE changes
    than its own design calls for.
    """
    six = ["M1L", "V3L", "V5F", "K18L", "K48L", "K53L"]  # 6 changes, cutoff 5
    perfect = classify_verdict(_tr(six), six, _params())
    assert perfect.verdict is VerdictClass.PASS, perfect.verdict_notes

    # One unexpected change on top of the 6-site design IS excess -> MANY.
    contaminated = classify_verdict(_tr([*six, "A9P"]), six, _params())
    assert contaminated.verdict is VerdictClass.MANY


def test_f05_lowdepth() -> None:
    tr = _tr(["V5F"], file_size_kb=30.0)
    result = classify_verdict(tr, ["V5F"], _params(min_file_size_kb=50.0))
    assert result.verdict is VerdictClass.LOWDEPTH


def test_f06_wrong_aa() -> None:
    tr = _tr(["N63S"])
    result = classify_verdict(tr, ["N63F"], _params())
    assert result.verdict is VerdictClass.WRONG_AA


def test_min_file_size_parameterization() -> None:
    """LOWDEPTH threshold is driven by CompareParams.min_file_size_kb."""

    tr = _tr(["V5F"], file_size_kb=75.0)
    # With default 50 KB threshold the record is not LOWDEPTH.
    assert (
        classify_verdict(tr, ["V5F"], _params(min_file_size_kb=50.0)).verdict
        is VerdictClass.PASS
    )
    # Raising the threshold above file size flips the verdict.
    assert (
        classify_verdict(tr, ["V5F"], _params(min_file_size_kb=200.0)).verdict
        is VerdictClass.LOWDEPTH
    )


def test_min_read_count_parameterization_when_available() -> None:
    """Optional LOWDEPTH read-count gate uses real consensus depth metadata."""

    tr = _tr(["V5F"], file_size_kb=75.0, read_count=2)
    result = classify_verdict(
        tr,
        ["V5F"],
        _params(min_file_size_kb=50.0, min_read_count=3),
    )
    assert result.verdict is VerdictClass.LOWDEPTH
    assert "read_count=2" in result.verdict_notes


def test_min_read_count_default_uses_real_depth() -> None:
    """The default read-depth gate (min_read_count=30) drives LOWDEPTH.

    A well whose consensus carries a real depth below the recommended 30 is
    LOWDEPTH via the read_count gate, even when its FASTA file clears the
    file-size proxy. This is the documented default behavior after the gate
    moved from file size to read depth.
    """

    tr = _tr(["V5F"], file_size_kb=75.0, read_count=1)
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.LOWDEPTH
    assert "read_count=1" in result.verdict_notes

    # Disabling the gate (min_read_count=None) restores legacy PASS for the same
    # record once it clears the file-size proxy.
    relaxed = classify_verdict(tr, ["V5F"], _params(min_read_count=None))
    assert relaxed.verdict is VerdictClass.PASS


def test_mixed_consensus_signal_blocks_clean_pass() -> None:
    """51/49-style mixed wells become MIXED even if majority matches expected."""

    tr = _tr(["V5F"], n_mixed_positions=1, max_minor_allele_fraction=0.49)
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.MIXED
    assert "mixed consensus signal" in result.verdict_notes
    assert "0.490" in result.verdict_notes


def test_mixed_takes_priority_over_wrong_aa() -> None:
    """A mixed well that also carries an unexpected AA change is MIXED, not WRONG_AA.

    Priority MIXED -> WRONG_AA ensures within-well contamination is reported as
    its own class rather than being masked by an AA-mismatch verdict.
    """

    # Observed N63S where N63F was expected (would be WRONG_AA on its own),
    # but the well is also mixed (n_mixed_positions > 0).
    tr = _tr(
        ["N63S"],
        n_mixed_positions=1,
        max_minor_allele_fraction=0.45,
    )
    # Sanity: same input without the mixed signal is WRONG_AA.
    clean = classify_verdict(_tr(["N63S"]), ["N63F"], _params())
    assert clean.verdict is VerdictClass.WRONG_AA
    # With the mixed signal, MIXED wins (higher priority).
    result = classify_verdict(tr, ["N63F"], _params())
    assert result.verdict is VerdictClass.MIXED
    assert "mixed consensus signal" in result.verdict_notes


def test_mixed_below_confidence_floor_is_lowdepth() -> None:
    """A mixed signal below min_read_count x factor is inconclusive (too few reads
    to separate a real minor allele from ONT error) and reported LOWDEPTH rather
    than a confident MIXED. Recovery is unchanged (both are non-PASS)."""

    # read_count 50 clears the LOWDEPTH gate (>= min_read_count 30) but is below
    # the MIXED confidence floor 30 * 3 = 90.
    tr = _tr(["V5F"], read_count=50, n_mixed_positions=4, max_minor_allele_fraction=0.42)
    result = classify_verdict(tr, ["V5F"], _params(min_read_count=30))
    assert result.verdict is VerdictClass.LOWDEPTH
    assert "mixed signal at insufficient depth" in result.verdict_notes
    assert "read_count=50" in result.verdict_notes


def test_mixed_at_adequate_depth_stays_mixed() -> None:
    """The same mixed signal at adequate depth (>= floor) stays a confident MIXED."""

    tr = _tr(["V5F"], read_count=500, n_mixed_positions=4, max_minor_allele_fraction=0.42)
    result = classify_verdict(tr, ["V5F"], _params(min_read_count=30))
    assert result.verdict is VerdictClass.MIXED
    assert "mixed consensus signal" in result.verdict_notes


def test_consensus_n_fraction_blocks_clean_pass_by_default() -> None:
    """High consensus N fraction is NO_CALL: the consensus is too ambiguous to trust."""

    tr = _tr(
        ["V5F"],
        n_low_depth_positions=2,
        consensus_n_fraction=0.02,
        n_low_quality_bases=4,
    )
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.NO_CALL
    assert "consensus_n_fraction=0.020" in result.verdict_notes
    assert "low_depth_positions=2" in result.verdict_notes
    assert "low_quality_bases=4" in result.verdict_notes


def test_consensus_n_fraction_gate_can_be_relaxed() -> None:
    """Operators can permit a small N fraction without disabling other gates."""

    tr = _tr(["V5F"], n_low_depth_positions=1, consensus_n_fraction=0.01)
    result = classify_verdict(
        tr,
        ["V5F"],
        _params(max_consensus_n_fraction=0.02),
    )
    assert result.verdict is VerdictClass.PASS


# Depth-gate regression (v0.13.0.1).
# Every well used to falsely fail LOWDEPTH because the file_size_kb gate
# compared a fixed ~1.8 KB per-well consensus FASTA against min_file_size_kb=50,
# which a consensus FASTA can never reach. The real depth signal (depth=N
# header, parsed into read_count) was present but the read_count gate was
# disabled. These tests pin the corrected behavior: depth drives LOWDEPTH; the
# file_size proxy is a fallback that fires only when depth=N is genuinely
# absent.


def test_depth_present_and_clean_consensus_is_not_lowdepth() -> None:
    """The exact regression: a depth-sufficient, clean well with a tiny FASTA.

    read_count=142 (>= default 30), N fraction 0, file_size ~1.8 KB (< 50 KB).
    The well must NOT be LOWDEPTH: the small consensus FASTA must no longer
    drag a depth-sufficient well into LOWDEPTH.
    """

    tr = _tr(["V5F"], file_size_kb=1.84, read_count=142, consensus_n_fraction=0.0)
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.PASS, result.verdict_notes


def test_depth_below_threshold_is_lowdepth() -> None:
    """A well whose real read depth is below min_read_count is LOWDEPTH."""

    tr = _tr(["V5F"], file_size_kb=1.84, read_count=12)
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.LOWDEPTH
    assert "read_count=12" in result.verdict_notes
    assert "min_read_count=30" in result.verdict_notes


def test_high_consensus_n_fraction_is_no_call_even_with_good_depth() -> None:
    """The consensus_n_fraction gate fires NO_CALL for a depth-sufficient well.

    read_count=200 clears the read_count gate, so a NO_CALL verdict here can
    only come from the N-fraction gate, proving it is not preempted and is
    distinct from LOWDEPTH (genuine read-count shortage).
    """

    tr = _tr(
        ["V5F"],
        file_size_kb=1.84,
        read_count=200,
        consensus_n_fraction=0.5,
        n_low_depth_positions=4,
    )
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.NO_CALL
    assert "consensus_n_fraction=0.500" in result.verdict_notes


def test_no_depth_header_falls_back_to_file_size_gate() -> None:
    """When depth=N is absent (read_count is None) the file_size proxy fires.

    A directly-constructed record with read_count=None and a sub-threshold
    file size must still be LOWDEPTH via the preserved fallback path; raising
    the file above the threshold restores PASS.
    """

    small = _tr(["V5F"], file_size_kb=30.0, read_count=None)
    fallback = classify_verdict(small, ["V5F"], _params(min_file_size_kb=50.0))
    assert fallback.verdict is VerdictClass.LOWDEPTH
    assert "file_size_kb=30.00" in fallback.verdict_notes

    large = _tr(["V5F"], file_size_kb=75.0, read_count=None)
    assert (
        classify_verdict(large, ["V5F"], _params(min_file_size_kb=50.0)).verdict
        is VerdictClass.PASS
    )
