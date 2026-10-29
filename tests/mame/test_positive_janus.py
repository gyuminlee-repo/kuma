"""Step 4.1 positive clone JANUS mapping: the round-1 clones above wild-type.

The fixture is the published table of slide 12 (one round-1 GC screen, peak
areas, H12 the wild-type well). The expected placement is the one the slide
states: positives in source column-major order fill the deep well plate from A1
down each column. The numbers are the slide's, not a lab data file.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from kuma_core.mame.activity.numeric_id_decode import (
    above_wt_subset,
    decode_primary_screen,
)
from kuma_core.mame.export.janus_mapping import DEFAULT_SAMPLE_TYPE, DEFAULT_VOLUME_UL
from kuma_core.mame.export.positive_janus import (
    DEFAULT_DEST_PLATE_NAME,
    DEFAULT_SOURCE_PLATE_NAME,
    export_positive_janus_csv,
    positive_candidates,
    positive_janus_rows,
    read_positive_screen,
)
from kuma_core.shared.janus_deck import JANUS_DEVICE_HEADER

# Slide 12: source well -> peak area. H12 is the wild-type well.
SLIDE_12 = {
    "C8": 1.4273, "H9": 1.0495, "D5": 1.019, "D11": 0.9772, "E10": 0.97,
    "D2": 0.9242, "D3": 0.8767, "G8": 0.8701, "B8": 0.8676, "F5": 0.8651,
    "H4": 0.8573, "B9": 0.8498, "F1": 0.8484, "E11": 0.8468, "F4": 0.8311,
    "E4": 0.8236, "H5": 0.823, "A3": 0.8205, "H1": 0.814, "F2": 0.8108,
    "G5": 0.7974, "D9": 0.7925, "E3": 0.7923,
}
SLIDE_12_WT = 0.8089

# Slide 12, destination well -> source well.
EXPECTED_PLACEMENT = [
    ("A1", "F1"), ("B1", "H1"), ("C1", "D2"), ("D1", "F2"), ("E1", "A3"),
    ("F1", "D3"), ("G1", "E4"), ("H1", "F4"), ("A2", "H4"), ("B2", "D5"),
    ("C2", "F5"), ("D2", "H5"), ("E2", "B8"), ("F2", "C8"), ("G2", "G8"),
    ("H2", "B9"), ("A3", "H9"), ("B3", "E10"), ("C3", "D11"), ("D3", "E11"),
]


def _seq(well: str) -> int:
    return (int(well[1:]) - 1) * 8 + (ord(well[0]) - ord("A")) + 1


# Column-major plate order of the slide wells, one synthetic mutant per well.
PLATE_ORDER = sorted(SLIDE_12, key=_seq)
MUTANT = {well: f"K{10 + index}R" for index, well in enumerate(PLATE_ORDER)}


def _blocks(path: Path, samples: list[tuple[str, float]]) -> Path:
    """One Agilent FID1B block per injection."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for name, area in samples:
        ws.append(["Signal:", "FID1B"])
        ws.append(["Area", "Sample Name"])
        ws.append([area, name])
        ws.append(["Sum", area])
        ws.append([])
    wb.save(path)
    return path


def _layout(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Mutant", "Well Pos."])
    for well in PLATE_ORDER:
        ws.append([MUTANT[well], well])
    ws.append(["WT", "H12"])
    wb.save(path)
    return path


def _verdict(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["well_id", "mutant_id", "verdict"])
    for well in PLATE_ORDER:
        ws.append([f"{well[0]}{int(well[1:]):02d}", MUTANT[well], "PASS"])
    ws.append(["H12", "WT", "PASS"])
    wb.save(path)
    return path


def _raw_report(path: Path) -> Path:
    # The raw report states WT as named rows; one row at the H12 area makes the
    # reference the slide's wild-type value.
    return _blocks(path, [("WT_1", SLIDE_12_WT), *SLIDE_12.items()])


def _selected(candidates) -> list[str]:
    return [c.well for c in candidates if c.above_wt]


def test_slide_12_raw_report_places_the_twenty_positives_column_major(tmp_path: Path):
    candidates, _warnings = positive_candidates(
        round1_report_xlsx=_raw_report(tmp_path / "round1.xlsx"),
        layout_xlsx=_layout(tmp_path / "layout.xlsx"),
    )
    rows = positive_janus_rows(candidates, _selected(candidates))

    assert [(row[6], row[4]) for row in rows] == EXPECTED_PLACEMENT
    assert [row[2] for row in rows] == list(range(1, 21))
    assert all(row[0] == MUTANT[str(row[4])] for row in rows)
    assert {row[1] for row in rows} == {DEFAULT_SAMPLE_TYPE}
    assert {row[3] for row in rows} == {DEFAULT_SOURCE_PLATE_NAME}
    assert {row[5] for row in rows} == {DEFAULT_DEST_PLATE_NAME}
    assert {row[7] for row in rows} == {DEFAULT_VOLUME_UL}


def test_every_measured_well_is_listed_and_wild_type_is_not(tmp_path: Path):
    candidates, _ = positive_candidates(
        round1_report_xlsx=_raw_report(tmp_path / "round1.xlsx"),
        layout_xlsx=_layout(tmp_path / "layout.xlsx"),
    )
    assert [c.well for c in candidates] == PLATE_ORDER
    assert "H12" not in {c.well for c in candidates}
    below = {c.well for c in candidates if not c.above_wt}
    assert below == {"G5", "D9", "E3"}


def test_verdict_workbook_alone_maps_the_same_set(tmp_path: Path):
    candidates, _ = positive_candidates(
        round1_report_xlsx=_raw_report(tmp_path / "round1.xlsx"),
        verdict_xlsx=_verdict(tmp_path / "verdict.xlsx"),
    )
    rows = positive_janus_rows(candidates, _selected(candidates))
    assert [(row[6], row[4]) for row in rows] == EXPECTED_PLACEMENT


def test_flat_relative_sheet_uses_the_same_rule(tmp_path: Path):
    sheet = tmp_path / "gc.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Sample Name", "Area"])
    for well, area in SLIDE_12.items():
        ws.append([well, area / SLIDE_12_WT])
    wb.save(sheet)
    candidates, _ = positive_candidates(
        gc_data_xlsx=sheet, layout_xlsx=_layout(tmp_path / "layout.xlsx")
    )
    rows = positive_janus_rows(candidates, _selected(candidates))
    assert [(row[6], row[4]) for row in rows] == EXPECTED_PLACEMENT


def test_area_equal_to_wild_type_is_not_a_positive(tmp_path: Path):
    report = _blocks(
        tmp_path / "round1.xlsx",
        [("WT_1", SLIDE_12_WT), *{**SLIDE_12, "F1": SLIDE_12_WT}.items()],
    )
    candidates, _ = positive_candidates(
        round1_report_xlsx=report, layout_xlsx=_layout(tmp_path / "layout.xlsx")
    )
    assert "F1" not in _selected(candidates)
    assert len(_selected(candidates)) == 19


def test_numeric_report_selects_the_set_the_confirmation_decoder_indexes(tmp_path: Path):
    layout = _layout(tmp_path / "layout.xlsx")
    report = _blocks(
        tmp_path / "numeric.xlsx",
        [("WT_1", SLIDE_12_WT)]
        + [(str(index), SLIDE_12[well]) for index, well in enumerate(PLATE_ORDER, start=1)],
    )
    candidates, _ = positive_candidates(numeric_report_xlsx=report, layout_xlsx=layout)

    decoder = above_wt_subset(decode_primary_screen(report, layout))
    assert _selected(candidates) == [
        f"{well[0]}{int(well[1:])}" for _, _, well in decoder
    ]
    rows = positive_janus_rows(candidates, _selected(candidates))
    assert [(row[6], row[4]) for row in rows] == EXPECTED_PLACEMENT


def test_operator_can_drop_a_positive_and_add_a_clone_below_wild_type(tmp_path: Path):
    candidates, _ = positive_candidates(
        round1_report_xlsx=_raw_report(tmp_path / "round1.xlsx"),
        layout_xlsx=_layout(tmp_path / "layout.xlsx"),
    )
    chosen = [w for w in _selected(candidates) if w != "D2"] + ["E3"]
    rows = positive_janus_rows(
        candidates, chosen, volume=50.0, source_rack="stock A", dest_rack="DW 1"
    )
    sources = [row[4] for row in rows]
    assert "D2" not in sources
    # E3 sits between D3 and E4 in column-major order.
    assert sources[4:7] == ["D3", "E3", "E4"]
    assert [row[6] for row in rows][:3] == ["A1", "B1", "C1"]
    assert {row[3] for row in rows} == {"stock A"}
    assert {row[5] for row in rows} == {"DW 1"}
    assert {row[7] for row in rows} == {50.0}


@pytest.mark.parametrize(
    "selection, kwargs, message",
    [
        ([], {}, "no clone"),
        (["A12"], {}, "not measured"),
        (["F1"], {"volume": 0.0}, "volume"),
        (["F1"], {"volume": float("nan")}, "volume"),
        (["F1"], {"source_rack": " "}, "plate name"),
        (["F1"], {"dest_rack": ""}, "plate name"),
    ],
)
def test_refusals(tmp_path: Path, selection, kwargs, message):
    candidates, _ = positive_candidates(
        round1_report_xlsx=_raw_report(tmp_path / "round1.xlsx"),
        layout_xlsx=_layout(tmp_path / "layout.xlsx"),
    )
    with pytest.raises(ValueError, match=message):
        positive_janus_rows(candidates, selection, **kwargs)


def test_csv_is_the_eight_column_device_sheet(tmp_path: Path):
    candidates, _ = positive_candidates(
        round1_report_xlsx=_raw_report(tmp_path / "round1.xlsx"),
        layout_xlsx=_layout(tmp_path / "layout.xlsx"),
    )
    out = tmp_path / "positive_janus.csv"
    export_positive_janus_csv(positive_janus_rows(candidates, _selected(candidates)), out)
    with out.open(newline="", encoding="utf-8") as fh:
        table = list(csv.reader(fh))
    assert table[0] == JANUS_DEVICE_HEADER
    assert len(table) == 21
    assert table[1] == [
        MUTANT["F1"], DEFAULT_SAMPLE_TYPE, "1", DEFAULT_SOURCE_PLATE_NAME, "F1",
        DEFAULT_DEST_PLATE_NAME, "A1", str(DEFAULT_VOLUME_UL),
    ]


def test_long_format_is_refused(tmp_path: Path):
    with pytest.raises(ValueError, match="exactly one"):
        positive_candidates(layout_xlsx=_layout(tmp_path / "layout.xlsx"))


def test_numeric_report_with_both_order_sources_follows_the_design_list(tmp_path: Path):
    """The build decodes a numeric-ID screen against expected_xlsx when both are
    given (``_numeric_primary`` drops the layout), so the export must number and
    place the clones the same way instead of refusing the pair."""
    layout = _layout(tmp_path / "layout.xlsx")
    # Design list without a Well column: the run is placed compactly from A1,
    # which differs from the slide wells the layout states.
    expected = tmp_path / "expected.csv"
    expected.write_text(
        "variant\n" + "\n".join(MUTANT[well] for well in PLATE_ORDER) + "\n",
        encoding="utf-8",
    )
    report = _blocks(
        tmp_path / "numeric.xlsx",
        [("WT_1", SLIDE_12_WT)]
        + [(str(index), SLIDE_12[well]) for index, well in enumerate(PLATE_ORDER, start=1)],
    )
    candidates, _ = positive_candidates(
        numeric_report_xlsx=report, expected_xlsx=expected, layout_xlsx=layout
    )

    # The build's decode of the same screen: expected first, layout ignored.
    build_decode = decode_primary_screen(report, None, expected_xlsx=expected)
    assert [(c.well, c.name) for c in candidates] == [
        (f"{slot.well[0]}{int(slot.well[1:])}", slot.mutant) for slot in build_decode.slots
    ]
    assert _selected(candidates) == [
        f"{well[0]}{int(well[1:])}" for _, _, well in above_wt_subset(build_decode)
    ]
    # And that is not the layout reading.
    assert [c.well for c in candidates] != PLATE_ORDER


# Rows a well-labelled screen carries that belong to no well: blanks and a
# bare number (a calibration standard under the well grammar). The build
# reports each one by name, block and row; the candidates read must too.
UNTIED_ROWS = [("BLANK", 0.01), ("BLANK2", 0.02), ("12", 0.5)]


def _report_with_untied_rows(path: Path) -> Path:
    return _blocks(path, [("WT_1", SLIDE_12_WT), *UNTIED_ROWS, *SLIDE_12.items()])


def test_rows_tied_to_no_well_are_reported_with_their_position(tmp_path: Path):
    screen = read_positive_screen(
        round1_report_xlsx=_report_with_untied_rows(tmp_path / "round1.xlsx"),
        layout_xlsx=_layout(tmp_path / "layout.xlsx"),
    )
    reported = {row.sample_name: row for row in screen.excluded_rows}
    assert set(reported) == {name for name, _ in UNTIED_ROWS}
    assert reported["BLANK"].reason == "non_well_sample"
    assert reported["BLANK2"].reason == "non_well_sample"
    assert reported["12"].reason == "numeric_calibration"
    # One block per injection, after the WT block, in file order.
    blocks = [reported[name].block_index for name, _ in UNTIED_ROWS]
    present = [block for block in blocks if block is not None]
    assert len(present) == 3
    assert present == sorted(present) and len(set(present)) == 3
    for name, _ in UNTIED_ROWS:
        assert any(repr(name) in warning and reported[name].location in warning for warning in screen.warnings)
    # Reporting them changes nothing about which clones move where.
    rows = positive_janus_rows(screen.candidates, _selected(screen.candidates))
    assert [(row[6], row[4]) for row in rows] == EXPECTED_PLACEMENT


def test_positive_candidates_warnings_name_the_untied_rows(tmp_path: Path):
    candidates, warnings = positive_candidates(
        round1_report_xlsx=_report_with_untied_rows(tmp_path / "round1.xlsx"),
        layout_xlsx=_layout(tmp_path / "layout.xlsx"),
    )
    assert any("'BLANK'" in warning for warning in warnings)
    assert [c.well for c in candidates] == PLATE_ORDER


def test_numeric_report_reports_a_blank_row(tmp_path: Path):
    layout = _layout(tmp_path / "layout.xlsx")
    report = _blocks(
        tmp_path / "numeric.xlsx",
        [("WT_1", SLIDE_12_WT), ("BLANK", 0.01)]
        + [(str(index), SLIDE_12[well]) for index, well in enumerate(PLATE_ORDER, start=1)],
    )
    screen = read_positive_screen(numeric_report_xlsx=report, layout_xlsx=layout)
    assert [row.sample_name for row in screen.excluded_rows] == ["BLANK"]
    assert screen.excluded_rows[0].block_index is not None
    rows = positive_janus_rows(screen.candidates, _selected(screen.candidates))
    assert [(row[6], row[4]) for row in rows] == EXPECTED_PLACEMENT


def test_unmapped_wells_are_reported_once(tmp_path: Path):
    # A measured well the mapping does not name keeps its own one-line warning,
    # and is listed among the rows like the build manifest lists it.
    report = _blocks(
        tmp_path / "round1.xlsx", [("WT_1", SLIDE_12_WT), *SLIDE_12.items(), ("A12", 0.9)]
    )
    screen = read_positive_screen(round1_report_xlsx=report, layout_xlsx=_layout(tmp_path / "layout.xlsx"))
    assert [(row.sample_name, row.reason) for row in screen.excluded_rows] == [("A12", "unmapped_well")]
    assert sum("A12" in warning for warning in screen.warnings) == 1
