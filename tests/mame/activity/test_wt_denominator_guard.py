"""One rule for every GC activity reader: a measurement is finite and not
negative, and the WT denominator is positive.

Before this the rule existed three times and differently: the long reader
refused negatives, numeric decode and ``compute_relative_activity`` refused a
non-positive WT mean, and the well/label report readers did neither, so a
negative WT area flipped the sign of every exported activity and an all-zero
WT baseline crashed with ZeroDivisionError.
"""
from pathlib import Path

import pytest
from openpyxl import Workbook

import importlib

_mod = importlib.import_module("kuma_core.mame.activity.build_evolvepro_input")

assert Path(_mod.__file__ or "").resolve().is_relative_to(Path(__file__).resolve().parents[3]), _mod.__file__

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.normalize import compute_relative_activity, wt_denominator


def _report(path: Path, rows: list[tuple[str, float]]) -> Path:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for label, area in rows:
        sheet.append(["Signal:", "FID1B"])
        sheet.append(["Area", "Sample Name"])
        sheet.append([area, label])
        sheet.append(["Sum", area])
        sheet.append([])
    book.save(path)
    return path


def _verdict(tmp_path: Path, rows=(("A1", "F89W", "PASS"),)) -> Path:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["well_id", "mutant_id", "verdict"])
    for row in rows:
        sheet.append(list(row))
    path = tmp_path / "verdict.xlsx"
    book.save(path)
    return path


def _round1(tmp_path: Path, wt: float, a1: float):
    raw = _report(tmp_path / "raw.xlsx", [("WT_1", wt), ("A1", a1)])
    return build_evolvepro_input(tmp_path / "out.xlsx", round1_report_xlsx=raw, verdict_xlsx=_verdict(tmp_path))


def test_valid_round1_report_normalises(tmp_path: Path):
    assert _round1(tmp_path, 10, 20).variant_replicates == {"89W": [2.0]}


def test_zero_mutant_activity_is_a_value(tmp_path: Path):
    assert _round1(tmp_path, 10, 0).variant_replicates == {"89W": [0.0]}


@pytest.mark.parametrize("wt, a1", [(-10, 20), (10, -20)])
def test_negative_area_is_refused(tmp_path: Path, wt: float, a1: float):
    with pytest.raises(ValueError, match="negative"):
        _round1(tmp_path, wt, a1)


def test_zero_wt_baseline_is_refused_with_context(tmp_path: Path):
    with pytest.raises(ValueError, match="round1_report_xlsx WT mean area must be > 0"):
        _round1(tmp_path, 0, 20)


def test_well_confirmation_zero_wt_is_refused(tmp_path: Path):
    primary = tmp_path / "primary.csv"
    primary.write_text("variant,value\n89W,2\n")
    confirmation = _report(tmp_path / "confirm.xlsx", [("WT1", 0), ("A1-1", 5)])
    with pytest.raises(ValueError, match="remeasure_well_xlsx WT mean area must be > 0"):
        build_evolvepro_input(
            tmp_path / "out.xlsx", activity_path=primary, activity_scale="relative_to_wt",
            remeasure_well_xlsx=confirmation, verdict_xlsx=_verdict(tmp_path),
        )


def test_long_reader_zero_wt_is_refused(tmp_path: Path):
    primary = tmp_path / "primary.csv"
    primary.write_text("variant,value\nWT_1,0\nF89W,2\n")
    with pytest.raises(ValueError, match="activity_path WT mean area must be > 0"):
        build_evolvepro_input(tmp_path / "out.xlsx", activity_path=primary, verdict_xlsx=_verdict(tmp_path))


def test_shared_helper_contract():
    assert wt_denominator([1.0, 3.0], "src") == 2.0
    with pytest.raises(ValueError, match="src has no WT"):
        wt_denominator([], "src")
    with pytest.raises(ValueError, match="src WT mean area must be > 0"):
        wt_denominator([0.0, 0.0], "src")
    assert compute_relative_activity(0.0, [2.0]) == 0.0
    with pytest.raises(ValueError, match="> 0"):
        compute_relative_activity(1.0, [0.0])
