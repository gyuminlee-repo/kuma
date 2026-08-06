"""Golden equivalence tests for NB label / ordering helpers.

The NB_LABEL_CASES table is kept in lockstep with the JS suite in
src/lib/mame/nbLabel.test.ts so both languages produce identical labels.
"""

import pytest

from kuma_core.mame.export import nb_label, nb_order_key, well_sort_key
from kuma_core.mame.export.well_mapper import seq_to_well

NB_LABEL_CASES = [
    ("sort_barcode06", "NB06"),
    ("sort_barcode6", "NB6"),
    ("sort_barcode12", "NB12"),
    ("NB01", "NB01"),
    ("consensus", "consensus"),
    ("sorted_barcode09", "NB09"),
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


def test_well_sort_key_matches_seq_to_well_order():
    """Sorting a full plate by the key reproduces seq_to_well seq order 1..96."""
    # seq = (F - 1) * 8 + R, so seq n <-> custom barcode below.
    by_seq = [f"{(n - 1) % 8 + 1}_{(n - 1) // 8 + 1}" for n in range(1, 97)]
    assert sorted(reversed(by_seq), key=well_sort_key) == by_seq
    wells = [seq_to_well(n) for n in range(1, 97)]
    assert wells[:3] == ["A1", "B1", "C1"]
    assert wells[8] == "A2"
