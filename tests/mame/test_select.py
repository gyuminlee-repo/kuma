"""3-replicate best pick tests (T-01 .. T-07)."""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.models import (
    BarcodeRecord,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.select import pick_best_replicate, prefer_within_plate


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


# Within-plate representative selection (one mutant, several wells, same NB).


def _vr_rc(
    nb: str,
    verdict: VerdictClass,
    read_count: int,
    well: str = "A1",
) -> VerdictRecord:
    """VerdictRecord with an explicit read_count for within-plate volume tiebreak."""
    barcode = BarcodeRecord(
        native_barcode=nb,
        custom_barcode=well,
        consensus_seq="",
        file_size_kb=60.0,
        source_path=Path("/tmp/mock.fasta"),
        read_count=read_count,
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


def _collapse(vr_list: list[VerdictRecord]) -> dict[str, VerdictRecord]:
    """Mirror the per-plate collapse in pipeline.run_analyze (lines ~241-247)."""
    plate_verdicts: dict[str, VerdictRecord] = {}
    for vr in vr_list:
        nb = vr.translated.barcode.native_barcode
        incumbent = plate_verdicts.get(nb)
        if incumbent is None or prefer_within_plate(vr, incumbent):
            plate_verdicts[nb] = vr
    return plate_verdicts


def test_within_plate_pass_beats_higher_read_ambiguous() -> None:
    """A PASS well must win over an AMBIGUOUS well even with fewer reads.

    Reproduces the K53N/3_2 report: PASS (5095 reads) vs AMBIGUOUS (7891 reads)
    on the same native barcode. Verdict priority, not read count, decides.
    """
    pass_well = _vr_rc("3_2", VerdictClass.PASS, read_count=5095, well="A3")
    amb_well = _vr_rc("3_2", VerdictClass.AMBIGUOUS, read_count=7891, well="C2")
    assert prefer_within_plate(pass_well, amb_well) is True
    assert prefer_within_plate(amb_well, pass_well) is False


def test_within_plate_collapse_is_order_independent() -> None:
    """Same wells, any encounter order yields the PASS well as representative."""
    pass_well = _vr_rc("3_2", VerdictClass.PASS, read_count=5095, well="A3")
    amb_well = _vr_rc("3_2", VerdictClass.AMBIGUOUS, read_count=7891, well="C2")
    mixed_well = _vr_rc("3_2", VerdictClass.MIXED, read_count=149, well="B1")

    for order in (
        [amb_well, pass_well, mixed_well],  # bug-reproducing order (AMB first)
        [pass_well, amb_well, mixed_well],
        [mixed_well, amb_well, pass_well],
    ):
        kept = _collapse(order)["3_2"]
        assert kept.verdict is VerdictClass.PASS
        assert kept.translated.barcode.custom_barcode == "A3"


def test_within_plate_equal_class_prefers_higher_volume() -> None:
    """Two PASS wells on one plate: higher read_count wins, order-independent."""
    lo = _vr_rc("3_2", VerdictClass.PASS, read_count=1000, well="A1")
    hi = _vr_rc("3_2", VerdictClass.PASS, read_count=9000, well="H12")
    assert _collapse([lo, hi])["3_2"].translated.barcode.read_count == 9000
    assert _collapse([hi, lo])["3_2"].translated.barcode.read_count == 9000


def test_within_plate_unpickable_keeps_highest_volume_for_fallback() -> None:
    """All wells unpickable on a plate: highest-volume survives so the G1
    fallback (highest-volume plate) still selects the right record."""
    lo = _vr_rc("3_2", VerdictClass.WRONG_AA, read_count=300, well="A1")
    hi = _vr_rc("3_2", VerdictClass.WRONG_AA, read_count=8000, well="D4")
    assert _collapse([lo, hi])["3_2"].translated.barcode.read_count == 8000
    assert _collapse([hi, lo])["3_2"].translated.barcode.read_count == 8000
