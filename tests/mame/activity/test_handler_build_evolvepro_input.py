"""Unified Step 3 RPC integration tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from sidecar_mame.handlers.activity import handle_build_evolvepro_input


_RESULT_KEYS = {
    "output_path", "n_variants", "n_authoritative", "n_fallback_only",
    "warnings", "mismatched", "n_ngs_excluded", "ngs_excluded",
    "gc_export_path", "label_audit", "manifest_path", "primary_format",
    "input_count", "evaluable_count", "exclusion_reason_counts",
    "normalization_sources", "evidence_hash", "artifact_hashes",
}


def _layout(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    ws.append(["V5F", "A1"])
    ws.append(["V10L", "B1"])
    wb.save(path)
    return path


def _verdict(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["well_id", "mutant_id", "verdict"])
    ws.append(["A01", "V5F", "PASS"])
    ws.append(["B01", "V10L", "PASS"])
    wb.save(path)
    return path


def _gc(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    ws.append(["A1", 1.25])
    ws.append(["B1", 0.75])
    wb.save(path)
    return path


def _agilent(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for sample, area in (("WT_1", 2.0), ("WT_2", 2.0), ("A1", 3.0), ("B1", 1.0)):
        ws.append(["Signal:", "FID1B"])
        ws.append(["Area", "Sample Name"])
        ws.append([area, sample])
        ws.append(["Sum", area])
        ws.append([])
    wb.save(path)
    return path


def _assert_domain_response(response: dict, output: Path, count: int) -> None:
    assert set(response) == _RESULT_KEYS
    assert response["output_path"] == str(output)
    assert response["n_variants"] == count
    assert response["n_authoritative"] == 0
    assert response["n_fallback_only"] == count
    assert response["n_ngs_excluded"] == 0
    assert response["ngs_excluded"] == []
    assert response["gc_export_path"] == ""
    assert response["label_audit"] is not None
    assert Path(response["manifest_path"]).exists()
    assert response["input_count"] == count
    assert response["evaluable_count"] == count
    assert response["evidence_hash"].startswith("sha256:")
    assert response["artifact_hashes"][str(output)].startswith("sha256:")
    json.dumps(response)


def test_handler_builds_well_mapped_gc_primary_with_domain_shape(tmp_path: Path):
    output = tmp_path / "out.xlsx"
    response = handle_build_evolvepro_input({
        "gc_data_xlsx": str(_gc(tmp_path / "gc.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
        "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
        "output_xlsx": str(output),
    })

    _assert_domain_response(response, output, 2)


def test_handler_builds_raw_agilent_primary_with_layout_mapping(tmp_path: Path):
    output = tmp_path / "out.xlsx"
    response = handle_build_evolvepro_input({
        "round1_report_xlsx": str(_agilent(tmp_path / "round1.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
        "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
        "output_xlsx": str(output),
    })

    _assert_domain_response(response, output, 2)
    assert output.exists()


def test_handler_rejects_missing_required_verdict(tmp_path: Path):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        handle_build_evolvepro_input({
            "gc_data_xlsx": str(_gc(tmp_path / "gc.xlsx")),
            "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
            "output_xlsx": str(tmp_path / "out.xlsx"),
        })


def test_method_registered_in_dispatcher():
    from sidecar_mame.dispatcher import _METHODS

    assert _METHODS["mame.activity.build_evolvepro_input"] is handle_build_evolvepro_input
