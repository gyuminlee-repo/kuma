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


def test_min_read_count_default_preserves_legacy_file_size_gate() -> None:
    """A low read_count does not change verdicts unless min_read_count is set."""

    tr = _tr(["V5F"], file_size_kb=75.0, read_count=1)
    result = classify_verdict(tr, ["V5F"], _params(min_file_size_kb=50.0))
    assert result.verdict is VerdictClass.PASS


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


def test_consensus_n_fraction_blocks_clean_pass_by_default() -> None:
    """Consensus N calls are MAME-native per-base low-depth evidence."""

    tr = _tr(
        ["V5F"],
        n_low_depth_positions=2,
        consensus_n_fraction=0.02,
        n_low_quality_bases=4,
    )
    result = classify_verdict(tr, ["V5F"], _params())
    assert result.verdict is VerdictClass.LOWDEPTH
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
