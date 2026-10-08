"""Golden equivalence tests for NB label / ordering helpers.

The NB_LABEL_CASES and WELL_ADDRESS_CASES tables are kept in lockstep with the
JS suite in src/lib/mame/nbLabel.test.ts, literal for literal, so editing one
language alone breaks the other.

WELL_ADDRESS_CASES carries the sequence index as well as the well label. The
label alone cannot tell a column-major plate from a row-major one (both put
``2_5`` in ``B5``), and it takes an off-diagonal pair such as ``2_5`` against
``5_2`` to tell which half of ``{R}_{F}`` is the row.
"""

import pytest

from kuma_core.mame.export import nb_label, nb_order_key, well_sort_key
from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.plate_geometry import DEFAULT_ADDRESSING

NB_LABEL_CASES = [
    ("sort_barcode06", "NB06"),
    ("sort_barcode6", "NB6"),
    ("sort_barcode12", "NB12"),
    ("NB01", "NB01"),
    ("consensus", "consensus"),
    ("sorted_barcode09", "NB09"),
]

#: (custom barcode, sequence index, well label) under DEFAULT_ADDRESSING.
#: 2_5 and 5_2 are the row_axis discriminator; the seq column is the traversal
#: discriminator. Both plate corners are included so an off-by-one in either
#: direction shows up.
WELL_ADDRESS_CASES = [
    ("1_1", 1, "A1"),
    ("2_1", 2, "B1"),
    ("1_2", 9, "A2"),
    ("2_5", 34, "B5"),
    ("5_2", 13, "E2"),
    ("1_10", 73, "A10"),
    ("8_12", 96, "H12"),
]


@pytest.mark.parametrize("raw,expected", NB_LABEL_CASES)
def test_nb_label(raw, expected):
    assert nb_label(raw) == expected


def test_nb_order_key_parses_first_digit_run():
    assert nb_order_key("sort_barcode06") == 6


def test_nb_order_key_sorts_non_numeric_last():
    assert nb_order_key("consensus") == 10**9


def test_well_sort_key_splits_numeric_parts():
    # "{R}_{F}" -> (F, R): column first, row second (column-major axis).
    assert well_sort_key("1_10") == (10, 1)
    assert well_sort_key("1_2") == (2, 1)


def test_well_sort_key_orders_naturally():
    assert sorted(["1_10", "1_2"], key=well_sort_key) == ["1_2", "1_10"]


def test_well_sort_key_is_column_major():
    """Axis discriminator: B1 (2_1) must precede A2 (1_2), not follow it.

    Off-diagonal cases are required here, a row-major key (R, F) also passes
    any all-same-R fixture, so only mixed R/F inputs tell the axes apart.
    """
    assert sorted(["1_2", "2_1", "1_1"], key=well_sort_key) == ["1_1", "2_1", "1_2"]


@pytest.mark.parametrize("custom,seq,well", WELL_ADDRESS_CASES)
def test_well_address_golden_table(custom, seq, well):
    """The literal table, asserted against the canonical addressing.

    Pinned to DEFAULT_ADDRESSING rather than to seq_to_well alone: the point of
    this table is that changing the convention has to change these numbers, and
    a helper that quietly disagrees with the convention would still satisfy an
    assertion written against itself.
    """
    assert DEFAULT_ADDRESSING.token_to_seq(custom) == seq
    assert DEFAULT_ADDRESSING.seq_to_well(seq) == well
    assert seq_to_well(seq) == well


def test_well_sort_key_matches_seq_to_well_order():
    """Sorting a full plate by the key reproduces the canonical seq order 1..96.

    The plate is enumerated through DEFAULT_ADDRESSING instead of a hand-written
    ``(n - 1) % 8`` so this test moves with the convention rather than freezing a
    second copy of it, which is what let the key run row-major for two months
    while its fixtures still passed.
    """
    capacity = DEFAULT_ADDRESSING.capacity
    by_seq = [
        DEFAULT_ADDRESSING.rc_to_token(*DEFAULT_ADDRESSING.seq_to_rc(n))
        for n in range(1, capacity + 1)
    ]
    assert sorted(reversed(by_seq), key=well_sort_key) == by_seq
    assert by_seq[:3] == ["1_1", "2_1", "3_1"]
    assert by_seq[8] == "1_2"

    wells = [seq_to_well(n) for n in range(1, capacity + 1)]
    assert wells[:3] == ["A1", "B1", "C1"]
    assert wells[8] == "A2"
    assert wells[-1] == "H12"
