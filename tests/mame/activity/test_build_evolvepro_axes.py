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


# ---------------------------------------------------------------------------
# WT replicates carried out of the build
#
# The workbook holds one row per designed variant and the WT rows are filtered
# out on the way in, so the replicates behind the normalization only survive on
# the result. Step 4.2 reads them from there through the round record.
# ---------------------------------------------------------------------------

def test_raw_generic_wt_replicates_leave_on_the_exported_scale(tmp_path: Path):
    """Each WT over its own cohort mean, the division the variants went through."""
    activity = tmp_path / "activity.csv"
    pd.DataFrame([
        {"mutation": "WT_1", "activity": 8},
        {"mutation": "WT_2", "activity": 12},
        {"mutation": "WT_3", "activity": 10},
        {"mutation": "WT_4", "activity": 10},
        {"mutation": "V5F", "activity": 20},
    ]).to_csv(activity, index=False)
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS")])

    result = build_evolvepro_input(
        tmp_path / "out.xlsx", activity_path=activity, verdict_xlsx=verdict
    )

    assert result.wt_values == pytest.approx([0.8, 1.2, 1.0, 1.0])


def test_multi_cohort_wt_replicates_are_each_relative_to_their_own_plate(tmp_path: Path):
    activity = tmp_path / "activity.csv"
    pd.DataFrame([
        {"plate_id": "P1", "mutation": "WT_1", "activity": 10},
        {"plate_id": "P1", "mutation": "WT_2", "activity": 10},
        {"plate_id": "P1", "mutation": "V5F", "activity": 20},
        {"plate_id": "P2", "mutation": "WT_1", "activity": 40},
        {"plate_id": "P2", "mutation": "WT_2", "activity": 60},
        {"plate_id": "P2", "mutation": "V10L", "activity": 50},
    ]).to_csv(activity, index=False)
    verdict = _verdict(
        tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS"), ("B1", "V10L", "PASS")]
    )

    result = build_evolvepro_input(
        tmp_path / "out.xlsx", activity_path=activity, verdict_xlsx=verdict
    )

    assert result.wt_values == pytest.approx([1.0, 1.0, 0.8, 1.2])


def test_relative_generic_wt_rows_are_carried_without_a_second_division(tmp_path: Path):
    # The WT mean here is 1.1, not 1.0, so carrying the rows through and
    # dividing them by their own mean give different answers. A fixture whose
    # WT mean lands on 1.0 cannot tell the two apart.
    activity = tmp_path / "activity.csv"
    pd.DataFrame([
        {"variant": "WT_1", "value": 0.9},
        {"variant": "WT_2", "value": 1.3},
        {"variant": "5F", "value": 1.4},
    ]).to_csv(activity, index=False)
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS")])

    result = build_evolvepro_input(
        tmp_path / "out.xlsx",
        activity_path=activity,
        activity_scale="relative_to_wt",
        verdict_xlsx=verdict,
    )

    assert result.wt_values == pytest.approx([0.9, 1.3])


def test_raw_report_wt_block_areas_leave_relative_to_their_mean(tmp_path: Path):
    report = _agilent(
        tmp_path / "round1.xlsx",
        [("WT_1", 8.0), ("WT_2", 12.0), ("A1", 20.0)],
    )
    layout = _layout(tmp_path / "layout.xlsx", [("V5F", "A1")])
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "PASS")])

    result = build_evolvepro_input(
        tmp_path / "out.xlsx",
        round1_report_xlsx=report,
        layout_xlsx=layout,
        verdict_xlsx=verdict,
    )

    assert result.wt_values == pytest.approx([0.8, 1.2])


def test_wt_of_a_cohort_that_measured_nothing_is_left_out(tmp_path: Path):
    """A WT block whose plate produced no variant row normalized nothing here."""
    activity = tmp_path / "activity.csv"
    pd.DataFrame([
        {"plate_id": "P1", "mutation": "WT_1", "activity": 8},
        {"plate_id": "P1", "mutation": "WT_2", "activity": 12},
        {"plate_id": "P1", "mutation": "V5F", "activity": 20},
        {"plate_id": "P2", "mutation": "WT_1", "activity": 100},
        {"plate_id": "P2", "mutation": "WT_2", "activity": 300},
    ]).to_csv(activity, index=False)
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A1", "V5F", "PASS")])

    result = build_evolvepro_input(
        tmp_path / "out.xlsx", activity_path=activity, verdict_xlsx=verdict
    )

    # P2 would have contributed [0.5, 1.5], a spread three times P1 own.
    assert result.wt_values == pytest.approx([0.8, 1.2])


def test_prenormalized_gc_sheet_records_no_replicates(tmp_path: Path):
    """The WT mean was taken upstream, so no replicate ever reaches this app."""
    gc = tmp_path / "gc.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    ws.append(["A1", 1.25])
    wb.save(gc)
    layout = _layout(tmp_path / "layout.xlsx", [("V5F", "A1")])
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "PASS")])

    result = build_evolvepro_input(
        tmp_path / "out.xlsx",
        gc_data_xlsx=gc,
        layout_xlsx=layout,
        verdict_xlsx=verdict,
    )

    assert result.wt_values == []
