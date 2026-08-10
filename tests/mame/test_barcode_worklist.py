"""Which barcode pair each occupied well is read under.

The fixtures are built so the two axes cannot be confused for one another. A
plate whose selection sits in one row, or one column, would pass under either
reading of ``{R}_{F}``; the wells here span both, and the expected tokens are
written out rather than computed, so a flipped axis fails instead of agreeing
with itself.
"""

from pathlib import Path

from kuma_core.mame.barcode_worklist import (
    WORKLIST_HEADER,
    build_barcode_worklist,
    write_barcode_worklist_csv,
)

#: Reverse seeds R1..R8 and forward seeds F1..F12, shaped the way
#: ``load_barcode_prefixes`` hands them over: ``(name, prefix)`` in index order.
REVERSE = [(f"ispS_r_{i}", "ACGT") for i in range(1, 9)]
FORWARD = [(f"ispS_f_{i}", "TGCA") for i in range(1, 13)]


def test_each_well_gets_the_token_the_demux_files_it_under() -> None:
    """Row picks the reverse seed, column the forward one, and A3 is not B3."""
    layout = {"A1": "M1", "B1": "M2", "B3": "M18"}

    worklist = build_barcode_worklist(layout, REVERSE, FORWARD)

    assert [(r.well, r.custom_barcode) for r in worklist.rows] == [
        ("A1", "1_1"),
        ("B1", "2_1"),
        ("B3", "2_3"),
    ]
    # The named seeds follow the indices, so an operator can pick tubes by name.
    assert [(r.reverse_name, r.forward_name) for r in worklist.rows] == [
        ("ispS_r_1", "ispS_f_1"),
        ("ispS_r_2", "ispS_f_1"),
        ("ispS_r_2", "ispS_f_3"),
    ]


def test_rows_come_back_in_plate_order_whatever_order_the_layout_had() -> None:
    """The sheet is read down a column, so it is written that way."""
    layout = {"B3": "M18", "A1": "M1", "B1": "M2"}

    worklist = build_barcode_worklist(layout, REVERSE, FORWARD)

    assert [r.well for r in worklist.rows] == ["A1", "B1", "B3"]


def test_the_seeds_actually_needed_are_the_distinct_ones_not_the_whole_set() -> None:
    """The point of the summary: a partial plate does not need all twenty.

    Three wells that between them use two reverse seeds and two forward ones.
    Reporting 8 and 12 would be reporting the workbook rather than the campaign.
    """
    layout = {"A1": "M1", "B1": "M2", "B3": "M18"}

    worklist = build_barcode_worklist(layout, REVERSE, FORWARD)

    assert worklist.reverse_indices == [1, 2]
    assert worklist.forward_indices == [1, 3]
    assert worklist.missing_seeds == []


def test_a_workbook_short_of_a_seed_is_named_rather_than_raised() -> None:
    """A worklist that names the wells is still worth having."""
    layout = {"A1": "M1", "A5": "M33"}

    worklist = build_barcode_worklist(layout, REVERSE, FORWARD[:3])

    assert [r.forward_name for r in worklist.rows] == ["ispS_f_1", None]
    assert worklist.missing_seeds == ["F5"]


def test_the_pairing_holds_without_a_workbook_at_all() -> None:
    """It comes from the plate, so the names are the only thing a workbook adds."""
    layout = {"A1": "M1", "H12": "WT"}

    worklist = build_barcode_worklist(layout)

    assert [(r.custom_barcode, r.reverse_name, r.forward_name) for r in worklist.rows] == [
        ("1_1", None, None),
        ("8_12", None, None),
    ]
    # Nothing was asked of a workbook, so nothing is missing from one.
    assert worklist.missing_seeds == []


def test_the_csv_states_the_header_and_one_row_per_well(tmp_path: Path) -> None:
    layout = {"A1": "M1", "B3": "M18"}
    worklist = build_barcode_worklist(layout, REVERSE, FORWARD)

    written = write_barcode_worklist_csv(worklist, tmp_path / "out" / "worklist.csv")

    lines = written.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(WORKLIST_HEADER)
    assert lines[1] == "A1,M1,1_1,1,ispS_r_1,1,ispS_f_1"
    assert lines[2] == "B3,M18,2_3,2,ispS_r_2,3,ispS_f_3"
    assert len(lines) == 3
