"""Handler coverage for raw Agilent primary and optional confirmation."""
from __future__ import annotations

from pathlib import Path
import importlib

import pytest

openpyxl = pytest.importorskip("openpyxl")

from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows
from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
build_module = importlib.import_module("kuma_core.mame.activity.build_evolvepro_input")
from sidecar_mame.handlers.activity import handle_build_evolvepro_input


def _fid(path: Path, rows: list[tuple[str, float]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for sample, area in rows:
        ws.append(["Signal:", "FID1B"])
        ws.append(["Area", "Sample Name"])
        ws.append([area, sample])
        ws.append(["Sum", area])
        ws.append([])
    wb.save(path)
    return path


def _inputs(tmp_path: Path) -> dict[str, Path]:
    layout = tmp_path / "layout.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    ws.append(["V5F", "A1"])
    ws.append(["V10L", "B1"])
    wb.save(layout)

    verdict = tmp_path / "verdict.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["well_id", "mutant_id", "verdict"])
    ws.append(["A01", "V5F", "PASS"])
    ws.append(["B01", "V10L", "PASS"])
    wb.save(verdict)
    return {
        "layout": layout,
        "verdict": verdict,
        "round1": _fid(tmp_path / "round1.xlsx", [("WT_1", 0.5), ("WT_2", 0.5), ("A1", 0.8), ("B1", 0.4)]),
        "remeasure": _fid(tmp_path / "remeasure.xlsx", [("WT_1", 0.5), ("WT_2", 0.5), ("V5F", 0.75)]),
    }


def test_confirmation_overrides_raw_primary_and_retains_mismatch_diagnostic(tmp_path: Path):
    files = _inputs(tmp_path)
    out = tmp_path / "out.xlsx"
    response = handle_build_evolvepro_input({
        "round1_report_xlsx": str(files["round1"]),
        "remeasure_report_xlsx": str(files["remeasure"]),
        "layout_xlsx": str(files["layout"]),
        "verdict_xlsx": str(files["verdict"]),
        "output_xlsx": str(out),
    })

    assert response["n_authoritative"] == 1
    assert response["n_fallback_only"] == 1
    assert response["mismatched"] == [{"variant": "5F", "authoritative": 1.5, "fallback": 1.6}]
    assert dict(read_evolvepro_rows(out)) == pytest.approx({"5F": 1.5, "10L": 0.8})


def test_raw_primary_writes_requested_relative_gc_review_export(tmp_path: Path):
    files = _inputs(tmp_path)
    out = tmp_path / "out.xlsx"
    review = tmp_path / "relative_gc.xlsx"
    response = handle_build_evolvepro_input({
        "round1_report_xlsx": str(files["round1"]),
        "layout_xlsx": str(files["layout"]),
        "verdict_xlsx": str(files["verdict"]),
        "output_xlsx": str(out),
        "gc_export_xlsx": str(review),
    })

    assert response["gc_export_path"] == str(review)
    assert review.exists()
    assert dict(read_evolvepro_rows(out)) == pytest.approx({"5F": 1.6, "10L": 0.8})


def test_artifact_bundle_preserves_existing_outputs_when_staging_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    files = _inputs(tmp_path)
    out = tmp_path / "out.xlsx"
    review = tmp_path / "relative_gc.xlsx"
    out.write_bytes(b"existing-output")
    review.write_bytes(b"existing-review")

    def fail_output(_rows: object, _path: Path) -> None:
        raise RuntimeError("simulated output writer failure")

    monkeypatch.setattr(build_module, "write_evolvepro_xlsx", fail_output)

    with pytest.raises(RuntimeError, match="simulated output writer failure"):
        build_evolvepro_input(
            out,
            round1_report_xlsx=files["round1"],
            layout_xlsx=files["layout"],
            verdict_xlsx=files["verdict"],
            gc_export_xlsx=review,
        )

    assert out.read_bytes() == b"existing-output"
    assert review.read_bytes() == b"existing-review"
    assert not list(tmp_path.glob(".*.tmp.xlsx"))

def test_handler_reports_exclusions_and_written_output_count(tmp_path: Path):
    files = _inputs(tmp_path)
    workbook = openpyxl.load_workbook(files["verdict"])
    worksheet = workbook.active
    worksheet["C3"] = "WRONG_AA"
    workbook.save(files["verdict"])
    out = tmp_path / "out.xlsx"

    response = handle_build_evolvepro_input({
        "round1_report_xlsx": str(files["round1"]),
        "layout_xlsx": str(files["layout"]),
        "verdict_xlsx": str(files["verdict"]),
        "output_xlsx": str(out),
    })

    assert response["n_ngs_excluded"] == 1
    assert response["ngs_excluded"] == ["10L"]
    assert response["n_variants"] == 1
    assert dict(read_evolvepro_rows(out)) == pytest.approx({"5F": 1.6})
    assert response["n_authoritative"] + response["n_fallback_only"] == response["n_variants"]
