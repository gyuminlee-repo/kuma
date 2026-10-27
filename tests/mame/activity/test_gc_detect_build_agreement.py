"""The detector and the build agree: a format the detector names is never refused as a format.

The detector judges what a file is from its names alone; the build judges
which rows belong to the run. When the detector offers format X, building with
X may still refuse, but only for a membership reason (no row of this run, the
run in two notations, an order that does not line up). A format-shaped refusal
("is not a well", "neither a canonical well nor variant") would mean the two
layers disagree about what a name is, which is the drift that sent shared-run
reports to manual selection.

Fixtures mix what a shared GC run carries: BLANK, internal standards,
calibration numbers, another experiment's WT1, rows without a name or area,
and repeated replicate numbers. All synthetic.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.detect_measurement_source import detect_measurement_source

PLATE = [("V5F", "A1"), ("K10L", "B1"), ("S11I", "C1"), ("WT", "H12")]

FIELD = {
    "rawReport": "round1_report_xlsx",
    "numericReport": "numeric_report_xlsx",
    "gcSheet": "gc_data_xlsx",
    "longFormat": "activity_path",
    "confirmationVariantLabels": "remeasure_report_xlsx",
    "confirmationNumericIds": "remeasure_numeric_xlsx",
    "confirmationWellLabels": "remeasure_well_xlsx",
}

FORMAT_REFUSALS = (
    "is not a well",
    "neither a canonical",
    "invalid 96-well",
    "is not a canonical",
    "carries no FID1B",
    "column not found",
)
MEMBERSHIP_REFUSALS = (
    "no row that belongs to this run",
    "in two notations",
    "cannot mix well and variant",
    "IDs must be",
    "line up one to one",
    "no measurement rows outside WT records",
    "No variants with explicit PASS",
    # A reference question rather than a format one: raw values need WT rows.
    "no WT",
)


def _sheet(path: Path, rows: list[list[object]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _blocks(path: Path, samples: list[tuple[str, object]]) -> Path:
    rows: list[list[object]] = []
    for name, area in samples:
        rows += [["Signal:", "FID1B"], ["Area", "Sample Name"], [area, name], ["Sum", area], []]
    return _sheet(path, rows)


SHARED = [("BLANK", 0.2), ("ISTD", 50.0), ("", 3.0), ("WT1", 30.0)]

FIXTURES = {
    "well_block": lambda tmp: _blocks(tmp / "well_block.xlsx", [
        ("WT1", 10.0), ("WT2", 10.0), ("A1", 20.0), ("5", 4.0), ("B1", 5.0), ("C1", None), ("C1", 12.0),
    ] + SHARED),
    "numeric_block": lambda tmp: _blocks(tmp / "numeric_block.xlsx", [
        ("WT1", 10.0), ("1", 20.0), ("2", 5.0), ("2", 6.0), ("3", 12.0), ("1.5", 4.0), ("3-2", None),
    ] + SHARED),
    "flat_sheet": lambda tmp: _sheet(tmp / "flat_sheet.xlsx", [
        ["Sample Name", "Area"], ["A1", 2.0], ["BLANK", 0.1], ["ISTD", 5.0], ["10", 0.5], ["", 1.0], ["B1", 0.5], ["C1", None],
    ]),
}


@pytest.mark.parametrize("fixture", sorted(FIXTURES))
@pytest.mark.parametrize("slot", ["primary", "confirmation"])
def test_every_offered_format_is_refused_only_for_membership(tmp_path: Path, fixture: str, slot: str) -> None:
    layout = _sheet(tmp_path / "layout.xlsx", [["Mutant", "Well Pos."], *[list(row) for row in PLATE]])
    verdict = _sheet(
        tmp_path / "verdict.xlsx",
        [["well_id", "mutant_id", "verdict"], *[[f"{w[0]}{int(w[1:]):02d}", m, "PASS"] for m, w in PLATE]],
    )
    # Every variant above WT, so a numeric confirmation indexes all three.
    primary = _blocks(tmp_path / "primary.xlsx", [("WT_1", 10.0), ("A1", 20.0), ("B1", 15.0), ("C1", 12.0)])
    path = FIXTURES[fixture](tmp_path)

    detected = detect_measurement_source(path, slot=slot)
    if fixture == "flat_sheet" and slot == "confirmation":
        assert detected.candidates == []
        return
    assert detected.candidates, detected.reason
    built = 0
    for candidate in detected.candidates:
        field = FIELD[candidate]
        sources: dict[str, object] = {field: path}
        if field.startswith("remeasure_"):
            sources["round1_report_xlsx"] = primary
        try:
            build_evolvepro_input(
                tmp_path / f"out_{candidate}.xlsx", layout_xlsx=layout, verdict_xlsx=verdict, **sources
            )
            built += 1
        except ValueError as exc:
            message = str(exc)
            assert not any(fragment in message for fragment in FORMAT_REFUSALS), (candidate, message)
            assert any(fragment in message for fragment in MEMBERSHIP_REFUSALS), (candidate, message)
    # Not vacuous: the reading meant for the file builds.
    assert built >= 1, detected.candidates


@pytest.mark.parametrize(
    ("samples", "expected"),
    [
        # A numeric report carrying ten times as many foreign well names (off
        # this layout) as IDs: the count reads it as a well report, and the
        # build finds no well of this run.
        ([("WT1", 10.0), ("1", 20.0)] + [(f"D{column}", 1.0) for column in range(2, 12)], "rawReport"),
        # A well report of this plate with ten times as many standards as
        # wells: the count reads it as numeric, and the build meets the plate's
        # own well.
        ([("WT1", 10.0), ("A1", 20.0)] + [(str(i), 1.0) for i in range(1, 11)], "numericReport"),
    ],
)
def test_a_wrong_count_guess_is_refused_for_membership(tmp_path: Path, samples: list[tuple[str, object]], expected: str) -> None:
    """The count rule may guess wrong; the build must then refuse loudly, never decode."""
    layout = _sheet(tmp_path / "layout.xlsx", [["Mutant", "Well Pos."], *[list(row) for row in PLATE]])
    verdict = _sheet(
        tmp_path / "verdict.xlsx",
        [["well_id", "mutant_id", "verdict"], *[[f"{w[0]}{int(w[1:]):02d}", m, "PASS"] for m, w in PLATE]],
    )
    path = _blocks(tmp_path / "guess.xlsx", samples)
    detected = detect_measurement_source(path)
    assert detected.candidates[0] == expected
    assert ("rawReport" in detected.candidates) != ("numericReport" in detected.candidates)
    with pytest.raises(ValueError) as caught:
        build_evolvepro_input(
            tmp_path / "out.xlsx", layout_xlsx=layout, verdict_xlsx=verdict, **{FIELD[expected]: path}
        )
    message = str(caught.value)
    assert not any(fragment in message for fragment in FORMAT_REFUSALS), message
    assert any(fragment in message for fragment in MEMBERSHIP_REFUSALS), message
