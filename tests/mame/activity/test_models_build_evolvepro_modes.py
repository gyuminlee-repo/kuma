"""Validate BuildEvolveproInputParams rank-mode / reports-mode XOR contract.

The model accepts EITHER rank mode (gc_data_xlsx + rep_batch_xlsx +
prev_evolvepro_xlsx) OR reports mode (round1_report_xlsx +
remeasure_report_xlsx). Providing both modes or neither is rejected by the
mode_xor model_validator.

_check_input_xlsx only verifies suffix + existence + traversal, so empty .xlsx
files created via openpyxl are sufficient for these validation tests.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sidecar_mame.models import BuildEvolveproInputParams


def _touch_xlsx(path):
    import openpyxl

    wb = openpyxl.Workbook()
    wb.save(path)
    return str(path)


@pytest.fixture
def files(tmp_path):
    return {
        "layout": _touch_xlsx(tmp_path / "layout.xlsx"),
        "gc": _touch_xlsx(tmp_path / "gc.xlsx"),
        "rep": _touch_xlsx(tmp_path / "rep.xlsx"),
        "prev": _touch_xlsx(tmp_path / "prev.xlsx"),
        "round1": _touch_xlsx(tmp_path / "round1.xlsx"),
        "remeasure": _touch_xlsx(tmp_path / "remeasure.xlsx"),
        "out": str(tmp_path / "out.xlsx"),
    }


# M1: rank mode validates.
def test_m1_rank_mode_validates(files):
    p = BuildEvolveproInputParams.model_validate(
        {
            "layout_xlsx": files["layout"],
            "gc_data_xlsx": files["gc"],
            "rep_batch_xlsx": files["rep"],
            "prev_evolvepro_xlsx": files["prev"],
            "output_xlsx": files["out"],
        }
    )
    assert p.gc_data_xlsx == files["gc"]
    assert p.round1_report_xlsx is None
    assert p.remeasure_report_xlsx is None


# M2: reports mode validates.
def test_m2_reports_mode_validates(files):
    p = BuildEvolveproInputParams.model_validate(
        {
            "layout_xlsx": files["layout"],
            "round1_report_xlsx": files["round1"],
            "remeasure_report_xlsx": files["remeasure"],
            "output_xlsx": files["out"],
        }
    )
    assert p.round1_report_xlsx == files["round1"]
    assert p.remeasure_report_xlsx == files["remeasure"]
    assert p.gc_data_xlsx is None
    assert p.rep_batch_xlsx is None
    assert p.prev_evolvepro_xlsx is None


# M3a: both modes provided -> rejected.
def test_m3a_both_modes_rejected(files):
    with pytest.raises(ValidationError):
        BuildEvolveproInputParams.model_validate(
            {
                "layout_xlsx": files["layout"],
                "gc_data_xlsx": files["gc"],
                "rep_batch_xlsx": files["rep"],
                "prev_evolvepro_xlsx": files["prev"],
                "round1_report_xlsx": files["round1"],
                "remeasure_report_xlsx": files["remeasure"],
                "output_xlsx": files["out"],
            }
        )


# M3b: neither mode provided -> rejected.
def test_m3b_neither_mode_rejected(files):
    with pytest.raises(ValidationError):
        BuildEvolveproInputParams.model_validate(
            {
                "layout_xlsx": files["layout"],
                "output_xlsx": files["out"],
            }
        )
