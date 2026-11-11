"""Tests for kuma_core.mame.activity.variant_notation.

Covers:
  - to_evolvepro: round-trip, WT passthrough, ValueError
  - from_evolvepro: position lookup, out-of-range, empty ref_seq, bad pattern
  - the combination-genotype helpers, and that they leave the single
    substitution functions answering exactly as before
"""

import json

import pytest

from kuma_core.mame.activity.variant_notation import (
    canonical_label,
    from_evolvepro,
    from_evolvepro_label,
    is_canonical_internal,
    is_canonical_label,
    is_combination_label,
    is_short_label,
    to_evolvepro,
    to_evolvepro_label,
)


REF = "MFLSIGKAFVIGILLLSVVQANDTAEQRHKNASLAERDYGKVSITLNLTPAGDFLFEAIPASQNLHQFFLRNNGTLKIQYEGERNFTYQIPDGQPNTNLSVTIPANQFLEFESPLTIQGGVAGSSNTYLHLQLLGDQTFNLTSVNVNGSVLQLPQPVTLGDTATFRCYVGYALPKEIGIWHHWNDVGHLYHDFAHQPYALGADSAVDGALNYLSQQLSNLTVPQNLVSFECTERYGDQAQLHGQSYNSAIVNCSLTPCHQSAPVDCDKFNWTGASCRYFGVSPTFAIWWIRQPRSGGGLYGSNAVPYYSWLPTTDPATGAVYSVGSSNTYLNLSVTMKGNTLQIPYEGERNFTYQIPDGQPNTNLSVTIPANQFLEFESPLTIQGGVAGSSNTYLHLQLLGDQTFNLTSVNVNGSVLQLPQPVTLGDTATFRCYVGYALPKEIG"


# ---------------------------------------------------------------------------
# to_evolvepro
# ---------------------------------------------------------------------------

def test_to_evolvepro_basic():
    assert to_evolvepro("F89W") == "89W"


def test_to_evolvepro_single_digit_pos():
    assert to_evolvepro("A1K") == "1K"


def test_to_evolvepro_three_digit_pos():
    assert to_evolvepro("G123A") == "123A"


def test_to_evolvepro_wt_passthrough():
    assert to_evolvepro("WT") == "WT"


def test_to_evolvepro_invalid_raises():
    with pytest.raises(ValueError, match="F89"):
        to_evolvepro("F89")


def test_to_evolvepro_lowercase_raises():
    with pytest.raises(ValueError):
        to_evolvepro("f89W")


def test_to_evolvepro_empty_raises():
    with pytest.raises(ValueError):
        to_evolvepro("")


def test_to_evolvepro_numeric_raises():
    with pytest.raises(ValueError):
        to_evolvepro("123")


# ---------------------------------------------------------------------------
# from_evolvepro
# ---------------------------------------------------------------------------

def test_from_evolvepro_basic():
    # REF[88] (0-indexed) should be the ref AA at position 89.
    ref_aa = REF[88]
    result = from_evolvepro("89W", REF)
    assert result == f"{ref_aa}89W"


def test_from_evolvepro_position_1():
    ref_aa = REF[0]
    result = from_evolvepro("1K", REF)
    assert result == f"{ref_aa}1K"


def test_from_evolvepro_empty_ref_raises():
    with pytest.raises(ValueError, match="ref_seq"):
        from_evolvepro("89W", "")


def test_from_evolvepro_none_ref_raises():
    with pytest.raises(ValueError, match="ref_seq"):
        from_evolvepro("89W", json.loads("null"))


def test_from_evolvepro_out_of_range_raises():
    with pytest.raises(ValueError, match="out of range"):
        from_evolvepro("9999K", REF)


def test_from_evolvepro_bad_pattern_raises():
    with pytest.raises(ValueError, match="cannot parse"):
        from_evolvepro("F89W", REF)  # internal notation passed — wrong format


def test_from_evolvepro_zero_pos_raises():
    with pytest.raises(ValueError):
        from_evolvepro("0K", REF)


# ---------------------------------------------------------------------------
# Round-trip: to_evolvepro → from_evolvepro
# ---------------------------------------------------------------------------

VARIANT_PAIRS = [
    "F89W", "A1K", "G123A", "D200N", "K45E",
]


@pytest.mark.parametrize("internal", VARIANT_PAIRS)
def test_round_trip(internal: str):
    short = to_evolvepro(internal)
    recovered = from_evolvepro(short, REF)
    # The recovered internal notation must match the original.
    # (ref AA comes from REF, so it matches as long as REF contains that AA.)
    assert recovered == internal or recovered[1:] == internal[1:], (
        f"Round-trip mismatch: {internal!r} → {short!r} → {recovered!r}"
    )


# ---------------------------------------------------------------------------
# is_canonical_internal
# ---------------------------------------------------------------------------

def test_is_canonical_internal_accepts_single_substitution():
    assert is_canonical_internal("F89W") is True
    assert is_canonical_internal("A1K") is True


def test_is_canonical_internal_rejects_wt():
    assert is_canonical_internal("WT") is False


def test_is_canonical_internal_rejects_multi_substitution():
    assert is_canonical_internal("F89W/L70V") is False


def test_is_canonical_internal_rejects_short_form():
    assert is_canonical_internal("89W") is False


# ---------------------------------------------------------------------------
# Combination genotypes
# ---------------------------------------------------------------------------

def test_is_combination_label_routes_on_the_separator():
    assert is_combination_label("F89W") is False
    assert is_combination_label("WT") is False
    assert is_combination_label("S304C:V547I") is True
    assert is_combination_label("A2V/A3G") is True


def test_is_canonical_label_accepts_a_single_substitution():
    assert is_canonical_label("F89W") is True
    assert is_canonical_label("WT") is False
    assert is_canonical_label("89W") is False


def test_is_canonical_label_accepts_a_combination():
    assert is_canonical_label("S304C:V547I") is True
    assert is_canonical_label("A2V/A3G") is True


def test_is_canonical_label_rejects_an_unparsable_component():
    assert is_canonical_label("S304C:547I") is False
    assert is_canonical_label("S304C:") is False
    assert is_canonical_label("A2V:WT") is False


def test_is_canonical_label_rejects_one_position_twice():
    assert is_canonical_label("A2V:A2G") is False


def test_canonical_label_orders_components_by_position():
    assert canonical_label("V547I:S304C") == "S304C:V547I"
    assert canonical_label("A3G/A2V") == "A2V:A3G"


def test_canonical_label_leaves_a_single_substitution_alone():
    assert canonical_label("F89W") == "F89W"
    assert canonical_label("WT") == "WT"


def test_to_evolvepro_label_matches_to_evolvepro_for_a_single():
    for internal in VARIANT_PAIRS + ["WT"]:
        assert to_evolvepro_label(internal) == to_evolvepro(internal)


def test_to_evolvepro_label_joins_short_components_in_position_order():
    assert to_evolvepro_label("S304C:V547I") == "304C:547I"
    assert to_evolvepro_label("V547I:S304C") == "304C:547I"
    assert to_evolvepro_label("A3G/A2V") == "2V:3G"


def test_to_evolvepro_label_raises_on_one_position_twice():
    with pytest.raises(ValueError, match="twice"):
        to_evolvepro_label("A2V:A2G")


def test_to_evolvepro_label_single_error_text_is_unchanged():
    with pytest.raises(ValueError) as combination_free:
        to_evolvepro_label("F89")
    with pytest.raises(ValueError) as direct:
        to_evolvepro("F89")
    assert str(combination_free.value) == str(direct.value)


def test_is_short_label():
    assert is_short_label("89W") is True
    assert is_short_label("304C:547I") is True
    assert is_short_label("F89W") is False
    assert is_short_label("304C:V547I") is False
    assert is_short_label("WT") is False


def test_from_evolvepro_label_round_trips_a_combination():
    internal = f"{REF[1]}2V:{REF[88]}89W"
    short = to_evolvepro_label(internal)
    assert short == "2V:89W"
    assert from_evolvepro_label(short, REF) == internal


def test_from_evolvepro_label_matches_from_evolvepro_for_a_single():
    assert from_evolvepro_label("89W", REF) == from_evolvepro("89W", REF)


def test_from_evolvepro_label_returns_position_order():
    assert from_evolvepro_label("89W:2V", REF) == f"{REF[1]}2V:{REF[88]}89W"
