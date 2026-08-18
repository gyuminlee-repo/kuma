"""Axis and traversal discrimination for :mod:`kuma_core.mame.plate_geometry`.

Every fixture here is chosen so the two candidate rules disagree on it.

* ``row_axis`` needs an OFF-DIAGONAL token. ``3_3`` reads the same either way,
  so a diagonal case proves nothing about which half of ``{R}_{F}`` is the row,
  and neither does a list holding one index constant.
* ``traversal`` needs the SEQUENCE INDEX. Both fill orders put ``2_5`` in well
  ``B5``, they only disagree about the index in between (34 against 17), so a
  test that asserts well labels alone passes under both. That is exactly how a
  row-major ``well_sort_key`` survived from June to August 2026: all four of its
  ordering fixtures held the row index at 1.
"""

import pytest

from kuma_core.mame.plate_geometry import (
    PLATE_CAPACITY,
    PLATE_COLS,
    PLATE_ROWS,
    DEFAULT_ADDRESSING,
    PlateAddressing,
)

#: Off-diagonal probe: R=2, F=5. Reused everywhere so a change to one rule shows
#: up in every assertion that depends on it.
PROBE = "2_5"

#: (row_axis, traversal) -> (seq of PROBE, well of that seq).
#:
#: Read the four rows against each other rather than one at a time:
#: - the two ``reverse`` rows share a well (B5) and differ in seq -> traversal
#: - the two ``column`` rows differ in both -> row_axis
PROBE_TABLE = {
    ("reverse", "column"): (34, "B5"),
    ("reverse", "row"): (17, "B5"),
    ("forward", "column"): (13, "E2"),
    ("forward", "row"): (50, "E2"),
}


def _seq(addressing: PlateAddressing, token: str) -> int:
    """``token_to_seq`` narrowed: every token used here is placeable."""
    seq = addressing.token_to_seq(token)
    assert seq is not None, token
    return seq


@pytest.mark.parametrize("combo,expected", sorted(PROBE_TABLE.items()))
def test_probe_token_resolves_per_addressing(combo, expected):
    row_axis, traversal = combo
    expected_seq, expected_well = expected
    addressing = PlateAddressing(row_axis=row_axis, traversal=traversal)

    assert addressing.token_to_seq(PROBE) == expected_seq
    assert addressing.seq_to_well(expected_seq) == expected_well


def test_row_axis_is_discriminated_by_the_seq_and_the_well():
    """Swapping which half of the token is the row changes both answers."""
    reverse = PlateAddressing(row_axis="reverse")
    forward = PlateAddressing(row_axis="forward")

    assert reverse.token_to_seq(PROBE) == 34
    assert forward.token_to_seq(PROBE) == 13
    assert reverse.seq_to_well(_seq(reverse, PROBE)) == "B5"
    assert forward.seq_to_well(_seq(forward, PROBE)) == "E2"


def test_traversal_is_discriminated_by_the_seq_alone():
    """The well label agrees under both fill orders; only the index tells them apart."""
    column = PlateAddressing(traversal="column")
    row = PlateAddressing(traversal="row")

    assert column.token_to_seq(PROBE) == 34
    assert row.token_to_seq(PROBE) == 17
    # The trap this test exists for: asserting only these two lines would pass
    # whichever traversal the code implements.
    assert column.seq_to_well(_seq(column, PROBE)) == "B5"
    assert row.seq_to_well(_seq(row, PROBE)) == "B5"


def _all_tokens(addressing: PlateAddressing) -> list[str]:
    return [
        addressing.rc_to_token(r, c)
        for r in range(1, addressing.rows + 1)
        for c in range(1, addressing.cols + 1)
    ]


@pytest.mark.parametrize("combo", sorted(PROBE_TABLE))
def test_sort_key_is_monotonic_in_seq(combo):
    """Sorting every token by the display key reproduces the sequence order."""
    row_axis, traversal = combo
    addressing = PlateAddressing(row_axis=row_axis, traversal=traversal)
    tokens = _all_tokens(addressing)

    by_key = sorted(tokens, key=addressing.sort_key)
    by_seq = sorted(tokens, key=lambda t: _seq(addressing, t))

    assert by_key == by_seq
    assert [addressing.token_to_seq(t) for t in by_key] == list(
        range(1, PLATE_CAPACITY + 1)
    )


@pytest.mark.parametrize("combo", sorted(PROBE_TABLE))
def test_every_token_names_a_distinct_well_and_the_set_is_the_plate(combo):
    row_axis, traversal = combo
    addressing = PlateAddressing(row_axis=row_axis, traversal=traversal)
    tokens = _all_tokens(addressing)

    wells = {addressing.seq_to_well(_seq(addressing, t)) for t in tokens}
    plate = {
        f"{chr(ord('A') + r)}{c}"
        for r in range(PLATE_ROWS)
        for c in range(1, PLATE_COLS + 1)
    }

    assert len(tokens) == PLATE_CAPACITY
    assert wells == plate
    assert len(wells) == PLATE_CAPACITY


@pytest.mark.parametrize("combo", sorted(PROBE_TABLE))
def test_well_to_seq_inverts_seq_to_well(combo):
    row_axis, traversal = combo
    addressing = PlateAddressing(row_axis=row_axis, traversal=traversal)

    for seq in range(1, PLATE_CAPACITY + 1):
        assert addressing.well_to_seq(addressing.seq_to_well(seq)) == seq


def test_default_addressing_is_the_convention_mame_uses():
    assert DEFAULT_ADDRESSING.row_axis == "reverse"
    assert DEFAULT_ADDRESSING.traversal == "column"
    assert DEFAULT_ADDRESSING.rows == PLATE_ROWS
    assert DEFAULT_ADDRESSING.cols == PLATE_COLS
    assert DEFAULT_ADDRESSING.capacity == PLATE_CAPACITY
    assert DEFAULT_ADDRESSING.token_to_seq(PROBE) == 34


def test_axis_sizes_follow_the_row_axis():
    reverse = PlateAddressing(row_axis="reverse")
    forward = PlateAddressing(row_axis="forward")

    assert (reverse.forward_axis_size, reverse.reverse_axis_size) == (12, 8)
    assert (forward.forward_axis_size, forward.reverse_axis_size) == (8, 12)


@pytest.mark.parametrize(
    "token",
    ["UNKNOWN_BC", "1_2_3", "WT", "0_1", "1_13", "9_1", "", "5"],
)
def test_unplaceable_tokens_return_none(token):
    assert DEFAULT_ADDRESSING.token_to_seq(token) is None


def test_sort_key_is_more_forgiving_than_token_to_seq():
    """A token the plate cannot place still sorts, so its row stays on the sheet."""
    assert DEFAULT_ADDRESSING.token_to_seq("UNKNOWN_BC") is None
    assert DEFAULT_ADDRESSING.sort_key("UNKNOWN_BC") == (0, 0)
    assert DEFAULT_ADDRESSING.sort_key("1_10") == (10, 1)


@pytest.mark.parametrize(
    "kwargs", [{"row_axis": "diagonal"}, {"traversal": "spiral"}]
)
def test_unknown_convention_is_refused(kwargs):
    with pytest.raises(ValueError):
        PlateAddressing(**kwargs)


def test_norm_well_pads_independently_of_the_addressing():
    from kuma_core.mame.plate_geometry import norm_well

    assert norm_well("A1") == "A01"
    assert norm_well("A01") == "A01"
    assert norm_well("b3") == "B03"
    assert norm_well("H12") == "H12"
