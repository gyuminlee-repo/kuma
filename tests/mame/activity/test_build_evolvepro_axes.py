"""Scientific behavior of the unified Step 3 activity builder."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

openpyxl = pytest.importorskip("openpyxl")

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows


def _layout(path: Path, rows: list[tuple[str, str]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _verdict(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["well_id", "mutant_id", "verdict"])
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _agilent(path: Path, rows: list[tuple[str, float]]) -> Path:
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


def _rows(path: Path) -> dict[str, float]:
    return dict(read_evolvepro_rows(path))


def test_generic_variant_aliases_and_raw_cohort_normalization(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    pd.DataFrame([
        {"plate_id": "P1", "mutation": "WT_1", "activity": 10},
        {"plate_id": "P1", "mutation": "V5F", "activity": 20},
        {"plate_id": "P2", "mutation": "WT1", "activity": 20},
        {"plate_id": "P2", "mutation": "5F", "activity": 20},
    ]).to_csv(activity, index=False)
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS")])
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(out, activity_path=activity, verdict_xlsx=verdict)

    assert result.n_variants == 1
    assert _rows(out) == pytest.approx({"5F": 1.5})


def test_generic_well_alias_requires_layout_and_maps_to_variant(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    pd.DataFrame([{"well_id": "WT_1", "area": 2}, {"well_id": "A1", "area": 3}]).to_csv(activity, index=False)
    layout = _layout(tmp_path / "layout.xlsx", [("V5F", "A1"), ("WT", "H12")])
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "PASS")])
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(out, activity_path=activity, layout_xlsx=layout, verdict_xlsx=verdict)

    assert result.well_by_variant == {"5F": "A01"}
    assert _rows(out) == pytest.approx({"5F": 1.5})


def test_generic_mixed_well_and_variant_namespaces_are_rejected(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    pd.DataFrame([{"well": "A1", "value": 1}, {"well": "5F", "value": 1}]).to_csv(activity, index=False)
    layout = _layout(tmp_path / "layout.xlsx", [("V5F", "A1")])
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "PASS")])

    with pytest.raises(ValueError, match="cannot mix well and variant"):
        build_evolvepro_input(tmp_path / "out.xlsx", activity_path=activity, layout_xlsx=layout, verdict_xlsx=verdict)


def test_raw_generic_data_requires_wt_in_every_plate_cohort(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    pd.DataFrame([
        {"plate_id": "P1", "variant": "WT_1", "value": 1},
        {"plate_id": "P1", "variant": "5F", "value": 1},
        {"plate_id": "P2", "variant": "5F", "value": 1},
    ]).to_csv(activity, index=False)
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS")])

    with pytest.raises(ValueError, match="no WT_1/WT1 rows for cohort.*P2"):
        build_evolvepro_input(tmp_path / "out.xlsx", activity_path=activity, verdict_xlsx=verdict)


def test_relative_to_wt_generic_values_are_not_normalized_twice(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    pd.DataFrame([{"variant": "V5F", "value": 0.75}]).to_csv(activity, index=False)
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS")])
    out = tmp_path / "out.xlsx"

    build_evolvepro_input(out, activity_path=activity, activity_scale="relative_to_wt", verdict_xlsx=verdict)

    assert _rows(out) == pytest.approx({"5F": 0.75})


def test_variant_labeled_confirmation_overrides_primary_and_reports_mismatch(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    pd.DataFrame([{"variant": "5F", "value": 1.0}]).to_csv(activity, index=False)
    remeasure = _agilent(tmp_path / "remeasure.xlsx", [("WT_1", 0.5), ("WT_2", 0.5), ("V5F", 0.75)])
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS")])
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(out, activity_path=activity, activity_scale="relative_to_wt", remeasure_report_xlsx=remeasure, verdict_xlsx=verdict)

    assert result.n_authoritative == 1
    assert result.n_fallback_only == 0
    assert result.mismatched == [{"variant": "5F", "authoritative": 1.5, "fallback": 1.0}]
    assert _rows(out) == pytest.approx({"5F": 1.5})


def test_confirmation_must_use_variant_labels(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    pd.DataFrame([{"variant": "5F", "value": 1.0}]).to_csv(activity, index=False)
    remeasure = _agilent(tmp_path / "remeasure.xlsx", [("WT_1", 1), ("A1", 1)])
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS")])

    with pytest.raises(ValueError, match="not a canonical variant label"):
        build_evolvepro_input(tmp_path / "out.xlsx", activity_path=activity, activity_scale="relative_to_wt", remeasure_report_xlsx=remeasure, verdict_xlsx=verdict)


def test_well_labeled_multi_plate_input_fails_closed_when_evidence_is_unscoped(
    tmp_path: Path,
):
    activity = tmp_path / "activity.csv"
    pd.DataFrame(
        [
            {"well": "WT_1", "value": 1.0, "plate_id": "plate-1"},
            {"well": "A1", "value": 1.2, "plate_id": "plate-1"},
            {"well": "WT_1", "value": 2.0, "plate_id": "plate-2"},
            {"well": "A1", "value": 2.4, "plate_id": "plate-2"},
        ],
    ).to_csv(activity, index=False)
    layout = _layout(tmp_path / "layout.xlsx", [("V5F", "A1")])
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "PASS")])

    with pytest.raises(ValueError, match="multi-plate.*unscoped"):
        build_evolvepro_input(
            tmp_path / "out.xlsx",
            activity_path=activity,
            layout_xlsx=layout,
            verdict_xlsx=verdict,
        )


def test_activity_file_without_measurement_rows_reports_the_real_cause(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    activity.write_text("variant,value\nWT_1,1.0\n", encoding="utf-8")
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "PASS")])

    with pytest.raises(ValueError, match="no measurement rows outside WT records"):
        build_evolvepro_input(
            tmp_path / "out.xlsx",
            activity_path=activity,
            verdict_xlsx=verdict,
        )
