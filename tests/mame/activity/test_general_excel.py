"""Synthetic GC final-result sheets, not the unavailable researcher workbook."""
from pathlib import Path

import pytest
from openpyxl import Workbook

from kuma_core.mame.activity.build_evolvepro_input import _read_long, build_evolvepro_input
from kuma_core.mame.activity.detect_measurement_source import detect_measurement_source
from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows
from sidecar_mame.handlers.activity import handle_build_evolvepro_input, handle_detect_measurement_source


def workbook(path: Path, rows: list[list[str | float]]) -> Path:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    book.save(path)
    return path


@pytest.fixture
def gc_final(tmp_path: Path) -> Path:
    return workbook(tmp_path / "GC_final.xlsx", [
        ["well", "Sample", "Peak area"],
        ["A1", "S11I", 20.0],
        ["A01", "S11I-1", 40.0],
        ["H11", "WT", 8.0],
        ["H12", "WT", 12.0],
    ])


@pytest.fixture
def verdict(tmp_path: Path) -> Path:
    return workbook(tmp_path / "verdict.xlsx", [
        ["well_id", "mutant_id", "verdict"],
        ["A1", "S11I", "PASS"],
        ["H11", "WT", "PASS"],
        ["H12", "WT", "PASS"],
    ])


def test_detects_exact_general_excel_columns(gc_final: Path):
    result = handle_detect_measurement_source({"measurement_path": str(gc_final)})
    assert result["candidates"] == ["longFormat"]
    assert result["ambiguous"] is False
    assert result["evidence"]["well_columns"] == ["well"]
    assert result["evidence"]["label_columns"] == ["sample"]
    assert result["evidence"]["value_columns"] == ["peak area"]


@pytest.mark.parametrize("header", [" PEAK  AREA ", "pEaKaReA", "Peak\tarea"])
def test_peak_area_header_ignores_case_and_spacing(tmp_path: Path, header: str):
    path = workbook(tmp_path / "spaced.xlsx", [["well", "Sample Name", header], ["A1", "S11I", 2.0]])
    assert detect_measurement_source(path).candidates == ["longFormat"]
    values, _, _, _ = _read_long(path, "relative_to_wt", {"A01": "11I"}, {}, [])
    assert values == {"11I": [2.0]}


@pytest.mark.parametrize("scale, expected, wt", [
    ("raw", 3.0, [0.8, 1.2]),
    ("relative_to_wt", 30.0, [8.0, 12.0]),
])
def test_build_folds_replicates_and_keeps_scale_user_choice(gc_final: Path, verdict: Path, tmp_path: Path, scale: str, expected: float, wt: list[float]):
    result = handle_build_evolvepro_input({
        "activity_path": str(gc_final), "activity_scale": scale,
        "verdict_xlsx": str(verdict), "output_xlsx": str(tmp_path / "output.xlsx"),
    })
    assert read_evolvepro_rows(result["output_path"]) == [("11I", expected)]
    assert result["wt_values"] == wt
    assert result["variant_replicates"]["11I"] == ([2.0, 4.0] if scale == "raw" else [20.0, 40.0])
    assert result["warnings"] == []


@pytest.mark.parametrize("with_layout", [False, True])
def test_conflict_rejects_all_rows_before_artifacts(verdict: Path, tmp_path: Path, with_layout: bool):
    path = workbook(tmp_path / "conflict.xlsx", [
        ["well", "Sample", "Peak area"],
        ["A1", "Q12V", 20.0],
        ["H11", "S11I-1", 30.0],
        ["A01", "WT", 10.0],
    ])
    layout = workbook(tmp_path / "layout.xlsx", [
        ["Mutant", "Well Pos."], ["S11I", "A1"], ["WT", "H11"], ["WT", "H12"],
    ]) if with_layout else None
    output = tmp_path / "output.xlsx"
    with pytest.raises(ValueError) as caught:
        build_evolvepro_input(output, activity_path=path, verdict_xlsx=verdict, layout_xlsx=layout)
    assert str(caught.value).startswith("errors.mame.measurementIdentityConflict|")
    assert "row 2: well=A01, sample=Q12V, layout_variant=11I" in str(caught.value)
    assert "row 3: well=H11, sample=S11I-1, layout_variant=WT" in str(caught.value)
    assert "row 4: well=A01, sample=WT, layout_variant=11I" in str(caught.value)
    assert not output.exists()
    assert not output.with_suffix(".xlsx.manifest.json").exists()


def test_without_mapping_uses_sample_and_reports_unchecked(gc_final: Path):
    values, wells, warnings, wt = _read_long(gc_final, "raw", {}, {}, [])
    assert values == {"11I": [2.0, 4.0]}
    assert wells == {}
    assert warnings == ["errors.mame.measurementWellsUnchecked|A01, H11, H12"]
    assert wt == [0.8, 1.2]


def test_verdict_without_measured_wells_does_not_invent_mapping(gc_final: Path, tmp_path: Path):
    verdict = workbook(tmp_path / "verdict.xlsx", [
        ["well_id", "mutant_id", "verdict"], ["B1", "S11I", "PASS"],
    ])
    result = build_evolvepro_input(tmp_path / "output.xlsx", activity_path=gc_final, verdict_xlsx=verdict)
    assert read_evolvepro_rows(result.output_path) == [("11I", 3.0)]
    assert result.warnings == ["errors.mame.measurementWellsUnchecked|A01, H11, H12"]
    assert result.well_by_variant == {"11I": "B01"}


def test_delimited_dual_columns_share_detector_and_reader(tmp_path: Path):
    path = tmp_path / "general.csv"
    path.write_text("well,Sample,Peak area\nA1,S11I-1,20\nH12,WT,10\n")
    assert detect_measurement_source(path).candidates == ["longFormat"]
    assert _read_long(path, "raw", {"A01": "11I"}, {}, [], {"H12"})[0] == {"11I": [2.0]}


def test_dual_sample_name_area_is_not_the_gc_well_label_format(tmp_path: Path):
    path = workbook(tmp_path / "sample_names.xlsx", [
        ["well", "Sample Name", "Area"], ["A1", "S11I-1", 2.0],
    ])
    assert detect_measurement_source(path).candidates == ["longFormat"]
    assert _read_long(path, "relative_to_wt", {"A01": "11I"}, {}, [])[0] == {"11I": [2.0]}
