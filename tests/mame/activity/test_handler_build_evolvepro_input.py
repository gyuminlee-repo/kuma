"""Tests for the ``mame.activity.build_evolvepro_input`` RPC handler.

Synthetic xlsx fixtures only (no external absolute paths). Verifies that the
handler validates params, returns the documented response shape, and that the
method is registered in the dispatcher.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from sidecar_mame.handlers.activity import handle_build_evolvepro_input


def _make_layout(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    ws.append(["V5F", "A1"])
    ws.append(["V10L", "B1"])
    ws.append(["WT", "H12"])
    wb.save(str(tmp_path / "layout.xlsx"))
    return tmp_path / "layout.xlsx"


def _make_gc(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    ws.append(["A1", 1.0])
    ws.append(["B1", 1.1])
    wb.save(str(tmp_path / "gc.xlsx"))
    return tmp_path / "gc.xlsx"


def _block(ws, name: str, area: float) -> None:
    ws.append(["Signal:", "FID1B"])
    ws.append(["Area", "Sample Name"])
    ws.append([area, name])
    ws.append(["Sum", area])
    ws.append([])


def _make_rep_batch(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    # rep1 for IDs 1,2; WT1; rep2; WT2; rep3; WT3
    for rep in range(3):
        for base_id in (1, 2):
            suffix = "" if rep == 0 else f"-{rep + 1}"
            _block(ws, f"{base_id}{suffix}", 1.0 + 0.1 * rep)
        _block(ws, f"WT{rep + 1}", 1.0)
    wb.save(str(tmp_path / "rep.xlsx"))
    return tmp_path / "rep.xlsx"


def _make_prev(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Variant", "activity"])
    ws.append(["5F", 1.8])
    ws.append(["10L", 1.4])
    ws.append(["WT", 1.0])
    wb.save(str(tmp_path / "prev.xlsx"))
    return tmp_path / "prev.xlsx"


def _make_expected(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "expected_mutations"
    ws.append([
        "mutant_id",
        "position",
        "wt_aa",
        "mt_aa",
        "wt_codon",
        "mt_codon",
        "group_id",
        "primer_set_ref",
        "notation_type",
        "status",
    ])
    ws.append(["V5F", 5, "V", "F", "", "", "", "V5F", "substitution", "DESIGNED"])
    ws.append(["V10L", 10, "V", "L", "", "", "", "V10L", "substitution", "DESIGNED"])
    wb.save(str(tmp_path / "expected.xlsx"))
    return tmp_path / "expected.xlsx"


def test_handler_returns_documented_shape(tmp_path: Path):
    out = tmp_path / "out.xlsx"
    res = handle_build_evolvepro_input({
        "layout_xlsx": str(_make_layout(tmp_path)),
        "gc_data_xlsx": str(_make_gc(tmp_path)),
        "rep_batch_xlsx": str(_make_rep_batch(tmp_path)),
        "prev_evolvepro_xlsx": str(_make_prev(tmp_path)),
        "output_xlsx": str(out),
    })

    for key in (
        "output_path",
        "n_variants",
        "n_authoritative",
        "n_fallback_only",
        "mapping_audit",
        "mapping_audit_path",
        "prev_descending",
        "warnings",
        "swap_warnings",
    ):
        assert key in res, f"missing response key: {key}"

    assert res["output_path"] == str(out)
    assert Path(res["output_path"]).exists()
    assert res["n_variants"] == 2
    assert res["n_authoritative"] == 2
    assert isinstance(res["mapping_audit"], list)
    assert res["mapping_audit"][0] == {"id": 1, "variant": "5F", "well": "A01"}
    assert isinstance(res["warnings"], list)
    assert isinstance(res["swap_warnings"], list)
    assert Path(res["mapping_audit_path"]).exists()


def test_handler_numeric_primary_writes_mapping_audit_in_decode_order(tmp_path: Path):
    out = tmp_path / "numeric.xlsx"

    res = handle_build_evolvepro_input({
        "round1_rep_batch_xlsx": str(_make_rep_batch(tmp_path)),
        "expected_mutations_xlsx": str(_make_expected(tmp_path)),
        "remeasure_rep_batch_xlsx": str(_make_rep_batch(tmp_path)),
        "output_xlsx": str(out),
    })

    expected_rows = [
        {"id": 1, "variant": "5F", "well": "A1"},
        {"id": 2, "variant": "10L", "well": "B1"},
    ]
    assert res["primary_source"] == "numeric_report"
    assert res["confirmation_source"] == "numeric_subset"
    assert res["mapping_audit"] == expected_rows
    audit_path = Path(res["mapping_audit_path"])
    assert audit_path.exists()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["mapping"] == expected_rows


def test_handler_rejects_missing_input(tmp_path: Path):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        handle_build_evolvepro_input({
            "layout_xlsx": str(tmp_path / "does_not_exist.xlsx"),
            "gc_data_xlsx": str(_make_gc(tmp_path)),
            "rep_batch_xlsx": str(_make_rep_batch(tmp_path)),
            "prev_evolvepro_xlsx": str(_make_prev(tmp_path)),
            "output_xlsx": str(tmp_path / "out.xlsx"),
        })


def test_method_registered_in_dispatcher():
    from sidecar_mame.dispatcher import _METHODS

    assert "mame.activity.build_evolvepro_input" in _METHODS
    assert _METHODS["mame.activity.build_evolvepro_input"] is (
        handle_build_evolvepro_input
    )


def test_handler_rank_mode_two_files_is_provisional(tmp_path: Path):
    """layout + GC data alone must build, flagged provisional (no confirmation)."""
    out = tmp_path / "out.xlsx"
    res = handle_build_evolvepro_input({
        "layout_xlsx": str(_make_layout(tmp_path)),
        "gc_data_xlsx": str(_make_gc(tmp_path)),
        "output_xlsx": str(out),
    })

    assert res["mode"] == "rank"
    assert res["confidence"] == "provisional"
    assert res["output_path"] == str(out)
    assert Path(res["output_path"]).exists()
    assert res["n_variants"] == 2
    assert res["n_authoritative"] == 0
    assert res["n_fallback_only"] == 2
