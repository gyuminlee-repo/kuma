"""3-replicate best pick tests (T-01 .. T-07)."""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.models import (
    BarcodeRecord,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.select import pick_best_replicate


def _vr(nb: str, verdict: VerdictClass, file_size_kb: float = 60.0) -> VerdictRecord:
    barcode = BarcodeRecord(
        native_barcode=nb,
        custom_barcode="1_1",
        consensus_seq="",
        file_size_kb=file_size_kb,
        source_path=Path("/tmp/mock.fasta"),
    )
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=[],
        observed_aa_changes=[],
    )
    return VerdictRecord(
        translated=translated,
        expected_mutations=[],
        verdict=verdict,
        verdict_notes="",
    )


def test_t01_pass_wins_over_ambiguous_and_many() -> None:
    verdicts = {
        "NB01": _vr("NB01", VerdictClass.AMBIGUOUS),
        "NB02": _vr("NB02", VerdictClass.PASS),
        "NB03": _vr("NB03", VerdictClass.MANY),
    }
    result = pick_best_replicate("K53N", verdicts)
    assert result.selected_plate == "NB02"
    assert result.failed is False


def test_t02_nb_order_tiebreak_between_equal_pass() -> None:
    verdicts = {
        "NB02": _vr("NB02", VerdictClass.PASS),
        "NB03": _vr("NB03", VerdictClass.PASS),
    }
    result = pick_best_replicate("V5F", verdicts)
    assert result.selected_plate == "NB02"


def test_t03_all_fail_yields_failed_true() -> None:
    """Empty dict produces failed=True (no identity info at all).

    Note: WRONG_AA/FRAMESHIFT/MANY carry identity info and trigger the G1
    fallback.  This test uses an empty dict to exercise the strict fail path.
    """
    result = pick_best_replicate("N63F", {})
    assert result.selected_plate is None
    assert result.failed is True


def test_t03b_all_unpickable_verdicts_trigger_fallback() -> None:
    """WRONG_AA/FRAMESHIFT/MANY have identity info → G1 fallback fires."""
    verdicts = {
        "NB01": _vr("NB01", VerdictClass.WRONG_AA),
        "NB02": _vr("NB02", VerdictClass.FRAMESHIFT),
        "NB03": _vr("NB03", VerdictClass.MANY),
    }
    result = pick_best_replicate("N63F", verdicts)
    # All three verdicts are in _FALLBACK_ELIGIBLE → fallback, not hard fail
    assert result.selected_plate is not None
    assert result.failed is False
    assert result.is_fallback is True


def test_t03c_mixed_is_unpickable_but_fallback_eligible() -> None:
    """MIXED (within-well contamination) is not auto-picked, but recoverable via G1.

    A mixed well carries mutant identity, so it must not hard-fail; it falls
    back like WRONG_AA/MANY/FRAMESHIFT instead of being silently dropped.
    """
    verdicts = {
        "NB01": _vr("NB01", VerdictClass.MIXED, file_size_kb=120.0),
        "NB02": _vr("NB02", VerdictClass.MIXED, file_size_kb=450.0),
    }
    result = pick_best_replicate("N63F", verdicts)
    assert result.selected_plate == "NB02", "highest-volume mixed plate as fallback"
    assert result.failed is False
    assert result.is_fallback is True


def test_t04_lowdepth_picked_when_no_better_class() -> None:
    verdicts = {
        "NB01": _vr("NB01", VerdictClass.LOWDEPTH),
        "NB02": _vr("NB02", VerdictClass.WRONG_AA),
    }
    result = pick_best_replicate("X", verdicts)
    assert result.selected_plate == "NB01"
    assert result.failed is False


# ── G1 Fallback tests (T-05 .. T-07) ────────────────────────────────────────


def test_t05_fallback_fires_when_all_unpickable_with_identity_info() -> None:
    """All plates carry unpickable verdicts (WRONG_AA, MANY) but have identity info.

    Expected: fallback fires, highest-volume plate is selected, is_fallback=True.
    """
    verdicts = {
        "NB01": _vr("NB01", VerdictClass.WRONG_AA, file_size_kb=120.0),
        "NB02": _vr("NB02", VerdictClass.MANY, file_size_kb=450.0),
        "NB03": _vr("NB03", VerdictClass.FRAMESHIFT, file_size_kb=200.0),
    }
    result = pick_best_replicate("G1_target", verdicts)
    assert result.selected_plate == "NB02", "highest-volume plate should be NB02"
    assert result.failed is False
    assert result.is_fallback is True
    assert result.fallback_reason is not None
    assert "NB02" in result.fallback_reason


def test_t06_fallback_does_not_fire_when_no_identity_info() -> None:
    """Empty verdicts dict: no identity information at all.

    Expected: fallback must NOT fire — failed=True, selected_plate=None.
    """
    result = pick_best_replicate("G1_notfound", {})
    assert result.selected_plate is None
    assert result.failed is True
    assert result.is_fallback is False


def test_t07_normal_case_regression_no_fallback() -> None:
    """Standard PASS path must not set is_fallback."""
    verdicts = {
        "NB01": _vr("NB01", VerdictClass.PASS, file_size_kb=300.0),
        "NB02": _vr("NB02", VerdictClass.AMBIGUOUS, file_size_kb=250.0),
    }
    result = pick_best_replicate("N_ctrl", verdicts)
    assert result.selected_plate == "NB01"
    assert result.failed is False
    assert result.is_fallback is False
    assert result.fallback_reason is None
