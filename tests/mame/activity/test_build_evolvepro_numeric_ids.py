"""Numeric-ID reports as Step 4 sources.

From 2026-07 the lab exports both activity files in the Agilent block layout
with numeric sample names: the whole-plate screen numbers every variant of the
plate in order, and the replicated confirmation numbers the subset that beat
wild-type. Neither file carries a variant anywhere, so both are decoded against
the order the run was placed in.
"""
from __future__ import annotations

from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows

# Four wells in plate column-major order, which is the order a numeric ID walks.
PLATE = [("V5F", "A01"), ("V10L", "B01"), ("S11E", "C01"), ("N28T", "D01")]


def _layout(path: Path, rows: list[tuple[str, str]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _verdict(path: Path, rows: list[tuple[str, str]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["well_id", "mutant_id", "verdict"])
    for mutant, well in rows:
        ws.append([well, mutant, "PASS"])
    wb.save(path)
    return path


def _blocks(path: Path, samples: list[tuple[str, float]]) -> Path:
    """One Agilent FID1B block per injection, the shape both reports arrive in."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for name, area in samples:
        ws.append(["Signal:", "FID1B"])
        ws.append(["Area", "Sample Name"])
        ws.append([area, name])
        ws.append(["Sum", area])
        ws.append([])
    wb.save(path)
    return path


def _rows(path: Path) -> dict[str, float]:
    return dict(read_evolvepro_rows(path))


@pytest.fixture
def plate(tmp_path: Path) -> dict[str, Path]:
    return {
        "layout": _layout(tmp_path / "layout.xlsx", PLATE),
        "verdict": _verdict(tmp_path / "verdict.xlsx", PLATE),
    }


def test_numeric_primary_positions_decode_to_the_plate_order(tmp_path: Path, plate):
    """Sample name `i` is the `i`-th variant of the plate, not a label."""
    report = _blocks(
        tmp_path / "screen.xlsx",
        [("WT_1", 10.0), ("1", 20.0), ("2", 5.0), ("3", 12.0), ("4", 8.0)],
    )
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(
        out,
        numeric_report_xlsx=report,
        layout_xlsx=plate["layout"],
        verdict_xlsx=plate["verdict"],
    )

    assert result.primary_format == "numeric_report_xlsx"
    assert _rows(out) == pytest.approx({"5F": 2.0, "10L": 0.5, "11E": 1.2, "28T": 0.8})
    assert result.wt_values == pytest.approx([1.0])


def test_numeric_confirmation_indexes_the_above_wt_subset(tmp_path: Path, plate):
    """The replicated file numbers only the variants that beat wild-type.

    Two of the four wells are above WT here, so its IDs run 1..2 in plate order
    rather than 1..4, and the replicate means replace those two values while the
    other two keep the screen value.
    """
    screen = _blocks(
        tmp_path / "screen.xlsx",
        [("WT_1", 10.0), ("1", 20.0), ("2", 5.0), ("3", 12.0), ("4", 8.0)],
    )
    confirmation = _blocks(
        tmp_path / "confirm.xlsx",
        [
            ("WT1", 10.0),
            ("1", 18.0),
            ("1-2", 22.0),
            ("2", 11.0),
            ("2-2", 13.0),
        ],
    )
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(
        out,
        numeric_report_xlsx=screen,
        remeasure_numeric_xlsx=confirmation,
        layout_xlsx=plate["layout"],
        verdict_xlsx=plate["verdict"],
    )

    assert result.n_authoritative == 2
    assert result.n_fallback_only == 2
    # A01 and C01 were above WT, so they are subset positions 1 and 2.
    assert _rows(out) == pytest.approx(
        {"5F": 2.0, "11E": 1.2, "10L": 0.5, "28T": 0.8}
    )


def test_numeric_confirmation_runs_against_a_well_labeled_screen(tmp_path: Path, plate):
    """The screen does not have to be numeric for the confirmation to decode.

    A round whose whole-plate screen arrived as a well-labelled sheet states the
    same thing, one relative activity per well, so the subset is built from the
    plate order and the confirmation decodes against it unchanged.
    """
    gc = tmp_path / "gc.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    for (_mutant, well), value in zip(PLATE, [2.0, 0.5, 1.2, 0.8]):
        ws.append([well, value])
    wb.save(gc)
    confirmation = _blocks(
        tmp_path / "confirm.xlsx",
        [("WT1", 10.0), ("1", 18.0), ("1-2", 22.0), ("2", 11.0), ("2-2", 13.0)],
    )
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(
        out,
        gc_data_xlsx=gc,
        remeasure_numeric_xlsx=confirmation,
        layout_xlsx=plate["layout"],
        verdict_xlsx=plate["verdict"],
    )

    assert result.n_authoritative == 2
    assert _rows(out) == pytest.approx({"5F": 2.0, "11E": 1.2, "10L": 0.5, "28T": 0.8})


def test_a_confirmation_covering_a_different_set_is_refused(tmp_path: Path, plate):
    """A count that does not match the subset cannot be placed positionally.

    Guessing would attach a measurement to a neighbouring variant, and every
    consumer downstream reads the label as ground truth, so the build stops and
    says which two counts disagreed.
    """
    screen = _blocks(
        tmp_path / "screen.xlsx",
        [("WT_1", 10.0), ("1", 20.0), ("2", 5.0), ("3", 12.0), ("4", 8.0)],
    )
    # Three IDs against a two-member above-WT subset.
    confirmation = _blocks(
        tmp_path / "confirm.xlsx",
        [("WT1", 10.0), ("1", 18.0), ("2", 11.0), ("3", 9.0)],
    )

    with pytest.raises(ValueError, match="numeric IDs"):
        build_evolvepro_input(
            tmp_path / "out.xlsx",
            numeric_report_xlsx=screen,
            remeasure_numeric_xlsx=confirmation,
            layout_xlsx=plate["layout"],
            verdict_xlsx=plate["verdict"],
        )


def test_numeric_sources_need_exactly_one_order_source(tmp_path: Path, plate):
    report = _blocks(
        tmp_path / "screen.xlsx",
        [("WT_1", 10.0), ("1", 20.0), ("2", 5.0), ("3", 12.0), ("4", 8.0)],
    )

    with pytest.raises(ValueError, match="exactly one order source"):
        build_evolvepro_input(
            tmp_path / "out.xlsx",
            numeric_report_xlsx=report,
            verdict_xlsx=plate["verdict"],
        )


def test_two_confirmation_sources_are_refused(tmp_path: Path, plate):
    report = _blocks(
        tmp_path / "screen.xlsx",
        [("WT_1", 10.0), ("1", 20.0), ("2", 5.0), ("3", 12.0), ("4", 8.0)],
    )

    with pytest.raises(ValueError, match="at most one confirmation source"):
        build_evolvepro_input(
            tmp_path / "out.xlsx",
            numeric_report_xlsx=report,
            remeasure_numeric_xlsx=report,
            remeasure_report_xlsx=report,
            layout_xlsx=plate["layout"],
            verdict_xlsx=plate["verdict"],
        )
