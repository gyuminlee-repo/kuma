"""3-replicate best pick tests (T-01 .. T-04)."""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.models import (
    BarcodeRecord,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.select import pick_best_replicate


def _vr(nb: str, verdict: VerdictClass) -> VerdictRecord:
    barcode = BarcodeRecord(
        native_barcode=nb,
        custom_barcode="1_1",
        consensus_seq="",
        file_size_kb=60.0,
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
    verdicts = {
        "NB01": _vr("NB01", VerdictClass.WRONG_AA),
        "NB02": _vr("NB02", VerdictClass.FRAMESHIFT),
        "NB03": _vr("NB03", VerdictClass.MANY),
    }
    result = pick_best_replicate("N63F", verdicts)
    assert result.selected_plate is None
    assert result.failed is True


def test_t04_lowdepth_picked_when_no_better_class() -> None:
    verdicts = {
        "NB01": _vr("NB01", VerdictClass.LOWDEPTH),
        "NB02": _vr("NB02", VerdictClass.WRONG_AA),
    }
    result = pick_best_replicate("X", verdicts)
    assert result.selected_plate == "NB01"
    assert result.failed is False
