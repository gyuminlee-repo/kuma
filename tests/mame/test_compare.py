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
) -> TranslatedRecord:
    barcode = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq="",
        file_size_kb=file_size_kb,
        source_path=Path("/tmp/mock.fasta"),
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
