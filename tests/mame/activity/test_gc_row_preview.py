"""The row preview states the build's own judgement, row by row.

For each shape (block report, flat sheet, numeric-ID report) the rows the
preview marks set aside must be exactly the rows the build lists in its
manifest, its flags the build's kept flags, and its WT rows the build's
wt_rows. A preview that disagreed with the build would show an operator one
outcome and produce another. All fixtures are synthetic.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from kuma_core.mame.activity.build_evolvepro_input import (
    OperatorExclusion,
    build_evolvepro_input,
    preview_gc_rows,
)

PLATE = [("V5F", "A1"), ("K10L", "B1"), ("S11I", "C1"), ("WT", "H12")]


def _sheet(path: Path, rows: Sequence[Sequence[object]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(list(row))
    wb.save(path)
    return path


def _blocks(path: Path, samples: Sequence[tuple[str, object]]) -> Path:
    rows: list[list[object]] = []
    for name, area in samples:
        rows += [["Signal:", "FID1B"], ["Area", "Sample Name"], [area, name], ["Sum", area], []]
    return _sheet(path, rows)


@pytest.fixture
def plate(tmp_path: Path) -> dict[str, Path]:
    return {
        "layout": _sheet(tmp_path / "layout.xlsx", [["Mutant", "Well Pos."], *[list(row) for row in PLATE]]),
        "verdict": _sheet(
            tmp_path / "verdict.xlsx",
            [["well_id", "mutant_id", "verdict"], *[[f"{w[0]}{int(w[1:]):02d}", m, "PASS"] for m, w in PLATE]],
        ),
    }


SHARED = [("BLANK", 0.2), ("ISTD", 50.0), ("", 3.0), ("WT1", 10.0)]
ALL_ABOVE_WT = [("WT1", 10.0), ("1", 20.0), ("2", 15.0), ("3", 12.0)]

CASES: dict[str, Any] = {
    "block": lambda tmp: {"round1_report_xlsx": _blocks(tmp / "r.xlsx", [
        ("WT1", 10.0), ("WT2", 10.0), ("A1", 20.0), ("5", 4.0), ("B1", 5.0), ("C1", None), ("C1", 12.0), ("H12", 9.0), ("G7", 1.0),
    ] + SHARED)},
    "flat": lambda tmp: {"gc_data_xlsx": _sheet(tmp / "gc.xlsx", [
        ["Sample Name", "Area"], ["A1", 2.0], ["BLANK", 0.1], ["10", 0.5], ["", 1.0], ["B1", 0.5], ["B1", 0.6], ["C1", None], ["H12", 1.0],
    ])},
    "numeric": lambda tmp: {"numeric_report_xlsx": _blocks(tmp / "n.xlsx", [
        ("WT1", 10.0), ("1", 20.0), ("2", 5.0), ("2", 6.0), ("3", 12.0), ("1.5", 4.0), ("3-2", None), ("G7", 2.0),
    ] + SHARED), "expected_xlsx": None},
    "numeric_confirmation": lambda tmp: {
        "numeric_report_xlsx": _blocks(tmp / "p.xlsx", ALL_ABOVE_WT),
        "remeasure_numeric_xlsx": _blocks(tmp / "c.xlsx", ALL_ABOVE_WT + [("1-2", 21.0), ("BLANK", 0.1)]),
    },
    "well_confirmation": lambda tmp: {
        "round1_report_xlsx": _blocks(tmp / "p.xlsx", [("WT_1", 10.0), ("A1", 20.0), ("B1", 5.0), ("C1", 12.0)]),
        "remeasure_well_xlsx": _blocks(tmp / "c.xlsx", [("H12-1", 10.0), ("A1-1", 20.0), ("A1-2", 22.0), ("BLANK", 0.1), ("E5-1", 3.0)]),
    },
}


def _positions(rows: Sequence[dict[str, Any]], *, statuses: set[str] | None = None) -> set[tuple[Any, ...]]:
    return {
        (row["source"], row["block_index"], row["row_index"], row["sample_name"])
        for row in rows
        if statuses is None or row["status"] in statuses
    }


@pytest.mark.parametrize("case", sorted(CASES))
def test_the_preview_states_the_builds_judgement(tmp_path: Path, plate: dict[str, Path], case: str) -> None:
    sources = {key: value for key, value in CASES[case](tmp_path).items() if value is not None}
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], **sources)
    assert preview.refusal is None
    result = build_evolvepro_input(tmp_path / "out.xlsx", layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], **sources)
    assert result.manifest_path is not None
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    set_aside = {(r["source"], r["block_index"], r["row_index"], r["sample_name"], r["reason"]) for r in manifest["excluded_rows"] if not r["kept"]}
    assert {
        (row["source"], row["block_index"], row["row_index"], row["sample_name"], row["reason"])
        for row in preview.rows if row["status"] == "set_aside"
    } == set_aside
    flags = {(r["source"], r["block_index"], r["row_index"], r["reason"]) for r in manifest["excluded_rows"] if r["kept"]}
    assert {
        (row["source"], row["block_index"], row["row_index"], flag)
        for row in preview.rows for flag in row["flags"]
    } == flags
    assert _positions(preview.rows, statuses={"wt"}) == {
        (r["source"], r["block_index"], r["row_index"], r["sample_name"]) for r in result.wt_rows
    }
    assert not [row for row in preview.rows if row["status"] == "unjudged"]
    assert [row for row in preview.rows if row["status"] == "used"]


def test_every_row_of_the_file_is_listed(tmp_path: Path, plate: dict[str, Path]) -> None:
    sources = CASES["block"](tmp_path)
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], **sources)
    # 9 named rows and 4 shared ones (one of them with no name).
    assert len(preview.rows) == 13
    by_name = {row["sample_name"]: row for row in preview.rows if row["sample_name"]}
    assert by_name["BLANK"]["status"] == "set_aside" and by_name["BLANK"]["reason"] == "non_well_sample"
    assert by_name["H12"]["status"] == "ignored" and by_name["H12"]["reason"] == "declared_wt_well"
    assert by_name["A1"]["status"] == "used"


def test_excluding_what_the_preview_marks_used_is_what_the_build_reports(tmp_path: Path, plate: dict[str, Path]) -> None:
    sources = CASES["block"](tmp_path)
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], **sources)
    wt2 = next(row for row in preview.rows if row["sample_name"] == "WT2")
    assert wt2["status"] == "wt"
    exclusion = OperatorExclusion(
        source=wt2["source"], row_index=wt2["row_index"], block_index=wt2["block_index"],
        sample_name=wt2["sample_name"], area=wt2["area"],
    )
    result = build_evolvepro_input(
        tmp_path / "out.xlsx", layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"],
        excluded_rows=[exclusion], **sources,
    )
    assert result.exclusion_reason_counts["operator_excluded"] == 1


def test_rows_of_this_run_in_the_other_notation_are_locked_and_all_listed(tmp_path: Path, plate: dict[str, Path]) -> None:
    report = _blocks(tmp_path / "r.xlsx", [("WT1", 10.0), ("A1", 20.0), ("11I", 9.0), ("10L", 8.0)])
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], round1_report_xlsx=report)
    locked = [row["sample_name"] for row in preview.rows if row["status"] == "locked"]
    assert locked == ["11I", "10L"]
    assert preview.refusal is not None and "names variant 11I of this run" in preview.refusal
    with pytest.raises(ValueError, match="names variant 11I of this run"):
        build_evolvepro_input(tmp_path / "out.xlsx", layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], round1_report_xlsx=report)


def test_a_numeric_report_locks_wells_of_the_plate(tmp_path: Path, plate: dict[str, Path]) -> None:
    report = _blocks(tmp_path / "n.xlsx", ALL_ABOVE_WT + [("C1", 9.0)])
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], numeric_report_xlsx=report)
    assert [row["sample_name"] for row in preview.rows if row["status"] == "locked"] == ["C1"]
    assert preview.refusal is not None


def test_a_refused_file_lists_its_rows_unjudged_beyond_where_reading_stopped(tmp_path: Path, plate: dict[str, Path]) -> None:
    report = _blocks(tmp_path / "r.xlsx", [("A1", 20.0), ("B1", 5.0)])
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], round1_report_xlsx=report)
    assert preview.refusal == "round1_report_xlsx has no WT block areas"
    assert {row["status"] for row in preview.rows} == {"unjudged"}
    assert len(preview.rows) == 2
