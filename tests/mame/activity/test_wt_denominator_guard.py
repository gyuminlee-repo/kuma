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
    # A negative WT block is refused by the mean check, a negative mutant by
    # the per-row measurement rule.
    with pytest.raises(ValueError, match="negative|WT mean area must be > 0"):
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


# --- The rule applies to rows the build adopts, not to rows it sets aside. ---

from kuma_core.mame.activity.build_evolvepro_input import OperatorExclusion  # noqa: E402
from kuma_core.mame.activity.evolvepro_xlsx import (  # noqa: E402
    parse_agilent_block_rep_batch,
    read_block_report,
)


def _exclusion(source: str, path: Path, name: str) -> OperatorExclusion:
    row = next(r for r in read_block_report(path) if r.sample_name == name)
    return OperatorExclusion(
        source=source, row_index=row.row_index, block_index=row.block_index,
        sample_name=name, area=float(row.area_raw),
    )


def test_unmapped_negative_well_does_not_refuse_the_report(tmp_path: Path):
    raw = _report(tmp_path / "raw.xlsx", [("WT_1", 10), ("A1", 20), ("H12", -1)])
    result = build_evolvepro_input(tmp_path / "out.xlsx", round1_report_xlsx=raw, verdict_xlsx=_verdict(tmp_path))
    assert result.variant_replicates == {"89W": [2.0]}
    # The set-aside row keeps the area the file holds, not None.
    h12 = [row for row in result.excluded_rows if row["sample_name"] == "H12"]
    assert [row["area"] for row in h12] == [-1.0]


def test_excluded_negative_row_does_not_refuse_the_report(tmp_path: Path):
    raw = _report(tmp_path / "raw.xlsx", [("WT_1", 10), ("WT_2", -3), ("A1", 20)])
    result = build_evolvepro_input(
        tmp_path / "out.xlsx", round1_report_xlsx=raw, verdict_xlsx=_verdict(tmp_path),
        excluded_rows=[_exclusion("round1_report_xlsx", raw, "WT_2")],
    )
    assert result.variant_replicates == {"89W": [2.0]}


def test_adopted_negative_row_is_still_refused(tmp_path: Path):
    raw = _report(tmp_path / "raw.xlsx", [("WT_1", 10), ("A1", -20), ("H12", -1)])
    with pytest.raises(ValueError, match="negative"):
        build_evolvepro_input(tmp_path / "out.xlsx", round1_report_xlsx=raw, verdict_xlsx=_verdict(tmp_path))


def test_gc_sheet_unmapped_negative_well_is_set_aside(tmp_path: Path):
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Sample Name", "Area"])
    sheet.append(["A1", 1.5])
    sheet.append(["H12", -0.5])
    gc = tmp_path / "gc.xlsx"
    book.save(gc)
    result = build_evolvepro_input(tmp_path / "out.xlsx", gc_data_xlsx=gc, verdict_xlsx=_verdict(tmp_path))
    assert result.variant_replicates == {"89W": [1.5]}


def test_label_confirmation_skips_unmapped_negative_and_refuses_member(tmp_path: Path):
    primary = tmp_path / "primary.csv"
    primary.write_text("variant,value\n89W,2\n")
    ok = _report(tmp_path / "ok.xlsx", [("WT1", 10), ("A1-1", 30), ("H12-1", -5)])
    result = build_evolvepro_input(
        tmp_path / "out.xlsx", activity_path=primary, activity_scale="relative_to_wt",
        remeasure_report_xlsx=ok, verdict_xlsx=_verdict(tmp_path),
    )
    assert result.variant_replicates == {"89W": [3.0]}
    bad = _report(tmp_path / "bad.xlsx", [("WT1", 10), ("A1-1", -30)])
    with pytest.raises(ValueError, match="negative"):
        build_evolvepro_input(
            tmp_path / "out2.xlsx", activity_path=primary, activity_scale="relative_to_wt",
            remeasure_report_xlsx=bad, verdict_xlsx=_verdict(tmp_path),
        )


def test_long_reader_excluded_negative_row_does_not_refuse(tmp_path: Path):
    primary = tmp_path / "primary.csv"
    primary.write_text("variant,value\nWT_1,10\nWT_2,-4\nF89W,20\n")
    result = build_evolvepro_input(
        tmp_path / "out.xlsx", activity_path=primary, verdict_xlsx=_verdict(tmp_path),
        excluded_rows=[OperatorExclusion(source="activity_path", row_index=3, sample_name="WT_2", area=-4.0)],
    )
    assert result.variant_replicates == {"89W": [2.0]}


def test_numeric_block_excluded_negative_row_is_not_read(tmp_path: Path):
    report = _report(tmp_path / "num.xlsx", [("WT1", 10), ("1", 10), ("1-2", -5)])
    block = parse_agilent_block_rep_batch(report, skip=lambda row, _area: row.sample_name == "1-2")
    assert block.reps == {1: [10.0]}
    # The excluded row keeps its area for the operator.
    assert [area for row, _s, area, _n in block.others if row.sample_name == "1-2"] == [-5.0]


def test_numeric_decode_refuses_an_adopted_negative_id(tmp_path: Path):
    from kuma_core.mame.activity.numeric_id_decode import decode_primary_screen

    layout = tmp_path / "layout.xlsx"
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Mutant", "Well Pos."])
    sheet.append(["F89W", "A1"])
    sheet.append(["WT", "H12"])
    book.save(layout)
    report = _report(tmp_path / "num.xlsx", [("WT1", 10), ("1", 10), ("1-2", -5)])
    with pytest.raises(ValueError, match="negative"):
        decode_primary_screen(report, layout)


def test_wt_mean_overflow_is_refused():
    with pytest.raises(ValueError, match="WT mean area must be > 0"):
        wt_denominator([1e308, 1e308], "src")


def test_relative_activity_refuses_a_negative_numerator():
    with pytest.raises(ValueError, match="negative"):
        compute_relative_activity(-20.0, [10.0])


def test_join_fallback_wt_mean_follows_the_dedicated_guard():
    from kuma_core.mame.activity.join import merge_activity_with_genotype
    from kuma_core.mame.activity.models import ActivityRecord, PlateConfig, PlateMeta

    def run(wt_value: float):
        activity = [
            ActivityRecord(plate_id="P01", well_id="B03", value=2.0, replicate_idx=1, is_wt=False, source_file="t.csv"),
            ActivityRecord(plate_id="P01", well_id="A01", value=wt_value, replicate_idx=1, is_wt=True, source_file="t.csv"),
        ]
        meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
        rows, _ = merge_activity_with_genotype({("P01", "B03"): "F89W"}, {("P01", "B03"): "F89W"}, activity, meta)
        return next(r for r in rows if r.well_id == "B03").fold_change

    assert run(1.0) == 2.0
    assert run(0.0) is None  # zero keeps the "no usable WT" contract
    assert run(-1.0) is None  # a negative mean is not a denominator
