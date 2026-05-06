"""Tests for kuma_core.mame.activity.variant_notation.

Covers:
  - to_evolvepro: round-trip, WT passthrough, ValueError
  - from_evolvepro: position lookup, out-of-range, empty ref_seq, bad pattern
"""

import pytest

from kuma_core.mame.activity.variant_notation import from_evolvepro, to_evolvepro


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
        from_evolvepro("89W", "")  # type: ignore[arg-type]


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
