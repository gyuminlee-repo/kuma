"""Golden equivalence tests for NB label / ordering helpers.

The NB_LABEL_CASES table is kept in lockstep with the JS suite in
src/lib/mame/nbLabel.test.ts so both languages produce identical labels.
"""

import pytest

from kuma_core.mame.export import nb_label, nb_order_key, well_sort_key

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
    assert well_sort_key("1_10") == (1, 10)
    assert well_sort_key("1_2") == (1, 2)


def test_well_sort_key_orders_naturally():
    assert sorted(["1_10", "1_2"], key=well_sort_key) == ["1_2", "1_10"]
