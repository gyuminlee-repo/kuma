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
    PreviewRow,
    _judge_build,  # pyright: ignore[reportPrivateUsage]
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
    "one_and_three_replicates": lambda tmp: {
        "round1_report_xlsx": _blocks(tmp / "p.xlsx", [("WT_1", 10.0), ("A1", 20.0), ("B1", 5.0), ("C1", 12.0)]),
        "remeasure_well_xlsx": _blocks(tmp / "c.xlsx", [
            ("H12-1", 10.0), ("H12-2", 11.0), ("H12-3", 9.0),
            ("A1-1", 20.0), ("A1-2", 22.0), ("A1-3", 21.0),
            ("B1-1", 5.0), ("B1-2", 5.5), ("B1-3", 4.5), ("BLANK", 0.1),
        ]),
    },
    "numeric_one_and_three_replicates": lambda tmp: {
        "numeric_report_xlsx": _blocks(tmp / "p.xlsx", ALL_ABOVE_WT),
        "remeasure_numeric_xlsx": _blocks(tmp / "c.xlsx", [
            ("WT1", 10.0), ("WT2", 10.5), ("WT3", 9.5),
            ("1", 20.0), ("1-2", 21.0), ("1-3", 19.0), ("2", 15.0), ("2-2", 16.0), ("2-3", 14.0),
            ("3", 12.0), ("3-2", 13.0), ("3-3", 11.0),
        ]),
    },
    "well_confirmation": lambda tmp: {
        "round1_report_xlsx": _blocks(tmp / "p.xlsx", [("WT_1", 10.0), ("A1", 20.0), ("B1", 5.0), ("C1", 12.0)]),
        "remeasure_well_xlsx": _blocks(tmp / "c.xlsx", [("H12-1", 10.0), ("A1-1", 20.0), ("A1-2", 22.0), ("BLANK", 0.1), ("E5-1", 3.0)]),
    },
}


def _positions(rows: Sequence[PreviewRow], *, statuses: set[str] | None = None) -> set[tuple[Any, ...]]:
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
    assert _positions(preview.rows, statuses={"used"}) == _build_used(plate, sources)
    assert _positions(preview.rows, statuses={"used"})


def _build_used(plate: dict[str, Path], sources: dict[str, Any]) -> set[tuple[Any, ...]]:
    """The rows a build (not the preview) uses: its own ledger, in build mode."""
    kwargs: dict[str, Any] = dict.fromkeys(
        ("activity_path", "gc_data_xlsx", "round1_report_xlsx", "numeric_report_xlsx", "remeasure_report_xlsx",
         "remeasure_numeric_xlsx", "remeasure_well_xlsx", "expected_xlsx", "gc_export_xlsx",
         "resequence_evidence", "excluded_rows", "output_xlsx"),
    )
    kwargs.update(sources)
    judged = _judge_build(
        activity_scale="raw", layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"],
        mismatch_threshold=0.1, allow_label_mismatch=False, **kwargs,
    )
    aside = {(r.source, r.block_index, r.row_index) for r in judged.ledger.rows if not r.kept}
    return {
        (source, row.block_index, row.row_index, row.sample_name)
        for source, row, _area, status, _detail in judged.ledger.events
        if status == "used" and (source, row.block_index, row.row_index) not in aside
    }


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


def _exclusion(row: PreviewRow) -> OperatorExclusion:
    return OperatorExclusion(
        source=row["source"], row_index=row["row_index"], block_index=row["block_index"],
        sample_name=row["sample_name"], area=row["area"],
    )


def test_no_selection_no_selection_refusal(tmp_path: Path, plate: dict[str, Path]) -> None:
    sources = CASES["block"](tmp_path)
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], **sources)
    assert preview.selection_refusal is None
    a1 = next(row for row in preview.rows if row["sample_name"] == "A1")
    again = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], excluded_rows=[_exclusion(a1)], **sources)
    assert again.selection_refusal is None
    # The defaults do not move with the selection.
    assert again.rows == preview.rows


def test_the_selection_refusal_is_the_one_the_build_gives(tmp_path: Path, plate: dict[str, Path]) -> None:
    sources = CASES["block"](tmp_path)
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], **sources)
    wt = [_exclusion(row) for row in preview.rows if row["status"] == "wt"]
    selected = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], excluded_rows=wt, **sources)
    assert selected.selection_refusal is not None
    with pytest.raises(ValueError) as refused:
        build_evolvepro_input(tmp_path / "out.xlsx", layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], excluded_rows=wt, **sources)
    assert str(refused.value) == selected.selection_refusal


def test_unticking_every_measurement_is_refused_by_the_build_not_the_screen(tmp_path: Path, plate: dict[str, Path]) -> None:
    sources = CASES["flat"](tmp_path)
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], **sources)
    used = [_exclusion(row) for row in preview.rows if row["status"] == "used"]
    selected = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], excluded_rows=used, **sources)
    assert selected.selection_refusal is not None
    with pytest.raises(ValueError) as refused:
        build_evolvepro_input(tmp_path / "out.xlsx", layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], excluded_rows=used, **sources)
    assert str(refused.value) == selected.selection_refusal


def test_a_refusal_the_files_give_anyway_is_not_the_selections(tmp_path: Path, plate: dict[str, Path]) -> None:
    report = _blocks(tmp_path / "r.xlsx", [("WT1", 10.0), ("A1", 20.0), ("B1", 5.0), ("11I", 9.0)])
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], round1_report_xlsx=report)
    assert preview.refusal is not None
    a1 = next(row for row in preview.rows if row["sample_name"] == "A1")
    selected = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], round1_report_xlsx=report, excluded_rows=[_exclusion(a1)])
    assert selected.selection_refusal is None


def test_a_stale_untick_is_a_selection_refusal(tmp_path: Path, plate: dict[str, Path]) -> None:
    sources = CASES["block"](tmp_path)
    stale = OperatorExclusion(source="round1_report_xlsx", row_index=999, block_index=40, sample_name="A1", area=20.0)
    selected = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], excluded_rows=[stale], **sources)
    assert selected.selection_refusal is not None and "no input of this build holds" in selected.selection_refusal


def _long(path: Path, rows: Sequence[tuple[str, str, float]]) -> Path:
    import pandas as pd

    pd.DataFrame([{"plate_id": p, "variant": v, "value": x} for p, v, x in rows]).to_csv(path, index=False)
    return path


LONG = [("P1", "WT_1", 1.0), ("P1", "5F", 2.0), ("P2", "WT_1", 1.0), ("P2", "10L", 3.0)]


def test_relative_scale_needs_no_wt_so_unticking_it_is_not_refused(tmp_path: Path, plate: dict[str, Path]) -> None:
    """1a: a file-level 'every WT unticked' rule would block this build; the build does not refuse it."""
    activity = _long(tmp_path / "a.csv", LONG)
    kwargs: dict[str, Any] = {"activity_path": activity, "activity_scale": "relative_to_wt", "verdict_xlsx": plate["verdict"]}
    preview = preview_gc_rows(**kwargs)
    wt = [_exclusion(row) for row in preview.rows if row["sample_name"] == "WT_1" and row["status"] in {"wt", "used"}]
    if not wt:
        pytest.skip("relative_to_wt lists no WT row an operator can untick")
    selected = preview_gc_rows(excluded_rows=wt, **kwargs)
    assert selected.selection_refusal is None
    build_evolvepro_input(tmp_path / "out.xlsx", excluded_rows=wt, **kwargs)


def test_raw_scale_refuses_one_plate_losing_its_wt(tmp_path: Path, plate: dict[str, Path]) -> None:
    """1b: P1 keeps its WT, so a file-level rule passes; the build refuses cohort P2."""
    activity = _long(tmp_path / "a.csv", LONG)
    kwargs: dict[str, Any] = {"activity_path": activity, "activity_scale": "raw", "verdict_xlsx": plate["verdict"]}
    preview = preview_gc_rows(**kwargs)
    assert preview.refusal is None and preview.selection_refusal is None
    p2_wt = [_exclusion(row) for row in preview.rows if row["status"] == "wt" and row["row_index"] == 4]
    assert len(p2_wt) == 1
    selected = preview_gc_rows(excluded_rows=p2_wt, **kwargs)
    assert selected.selection_refusal is not None
    assert "no WT/WT_1/WT1 rows for cohort(s): P2" in selected.selection_refusal
    with pytest.raises(ValueError, match="cohort.*P2"):
        build_evolvepro_input(tmp_path / "out.xlsx", excluded_rows=p2_wt, **kwargs)


def test_overwrite_check_follows_the_verdict_check(tmp_path: Path) -> None:
    """A direct call without verdict_xlsx is refused for that, not a TypeError."""
    from kuma_core.mame.activity.resequence_evidence import ResequenceEvidence

    evidence = ResequenceEvidence.model_construct(verdict_xlsx=str(tmp_path / "v2.xlsx"), links=[])
    with pytest.raises(ValueError, match="verdict_xlsx is required"):
        build_evolvepro_input(tmp_path / "out.xlsx", round1_report_xlsx=tmp_path / "r.xlsx", verdict_xlsx=None, resequence_evidence=evidence)  # pyright: ignore[reportArgumentType]


def test_a_numeric_refusal_keeps_the_rows_set_aside_before_it(tmp_path: Path, plate: dict[str, Path]) -> None:
    """The ID count check refuses after BLANK was judged; BLANK stays set aside, not unjudged."""
    report = _blocks(tmp_path / "n.xlsx", [("WT1", 10.0), ("BLANK", 0.1), ("1", 20.0), ("2", 15.0)])
    preview = preview_gc_rows(layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"], numeric_report_xlsx=report)
    assert preview.refusal is not None and "line up one to one" in preview.refusal
    blank = next(row for row in preview.rows if row["sample_name"] == "BLANK")
    assert blank["status"] == "set_aside"


def test_a_refused_long_format_file_uses_no_row(tmp_path: Path, plate: dict[str, Path]) -> None:
    import pandas as pd

    activity = tmp_path / "a.csv"
    pd.DataFrame([
        {"plate_id": "P1", "well": "A1", "value": 2.0},
        {"plate_id": "P2", "well": "B1", "value": 3.0},
    ]).to_csv(activity, index=False)
    preview = preview_gc_rows(activity_path=activity, activity_scale="relative_to_wt", layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"])
    assert preview.refusal is not None and "multi-plate" in preview.refusal
    assert "used" not in {row["status"] for row in preview.rows}


def test_a_refused_confirmation_uses_no_row(tmp_path: Path, plate: dict[str, Path]) -> None:
    primary = _blocks(tmp_path / "p.xlsx", [("WT_1", 10.0), ("A1", 20.0), ("B1", 5.0), ("C1", 12.0)])
    remeasure = _blocks(tmp_path / "c.xlsx", [("WT1", 10.0), ("5F", 20.0), ("V10L", 5.0)])
    preview = preview_gc_rows(
        layout_xlsx=plate["layout"], verdict_xlsx=plate["verdict"],
        round1_report_xlsx=primary, remeasure_report_xlsx=remeasure,
    )
    assert preview.refusal is not None and "conflicts with declared identity" in preview.refusal
    assert not [row for row in preview.rows if row["source"] == "remeasure_report_xlsx" and row["status"] == "used"]
