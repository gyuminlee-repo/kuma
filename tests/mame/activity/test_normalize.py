"""Tests for kuma_core.mame.activity.normalize.

Covers existing compute_fold_change / compute_log2_fc plus
v0.3 Phase B-3 additions: compute_relative_activity, WT_PATTERN.
"""

import pytest
from kuma_core.mame.activity.normalize import (
    compute_fold_change,
    compute_log2_fc,
    compute_relative_activity,
    WT_PATTERN,
)


# ---------------------------------------------------------------------------
# Existing tests (5/12 demo path — must not regress)
# ---------------------------------------------------------------------------

def test_fold_change_2x():
    result = compute_fold_change(2.0, 1.0)
    assert result is not None and abs(result - 2.0) < 1e-6


def test_fold_change_wt_zero_returns_none():
    assert compute_fold_change(2.0, 0.0) is None


def test_fold_change_none_input():
    assert compute_fold_change(None, 1.0) is None
    assert compute_fold_change(2.0, None) is None


def test_log2_fc():
    r1 = compute_log2_fc(2.0)
    r2 = compute_log2_fc(0.5)
    assert r1 is not None and abs(r1 - 1.0) < 1e-6
    assert r2 is not None and abs(r2 - (-1.0)) < 1e-6


def test_log2_fc_wt_returns_zero():
    assert compute_log2_fc(1.0, is_wt=True) == 0.0


def test_log2_fc_negative_or_zero_returns_none():
    assert compute_log2_fc(0.0) is None
    assert compute_log2_fc(-1.0) is None


# ---------------------------------------------------------------------------
# WT_PATTERN constant
# ---------------------------------------------------------------------------

def test_wt_pattern_matches_wt_with_underscore():
    assert WT_PATTERN.match("WT_1")
    assert WT_PATTERN.match("WT_2")
    assert WT_PATTERN.match("WT_10")


def test_wt_pattern_matches_wt_without_underscore():
    # 실데이터 §11-B: WT1 형식 (underscore 없음)
    assert WT_PATTERN.match("WT1")
    assert WT_PATTERN.match("WT3")


def test_wt_pattern_does_not_match_non_wt():
    assert not WT_PATTERN.match("F89W")
    assert not WT_PATTERN.match("WT")     # bare WT without number
    assert not WT_PATTERN.match("WT_")    # no digit
    assert not WT_PATTERN.match("wt_1")  # lowercase


# ---------------------------------------------------------------------------
# compute_relative_activity — Phase B-3
# ---------------------------------------------------------------------------

def test_relative_activity_basic():
    # 0.9 / mean([0.8, 0.9, 0.7]) = 0.9 / 0.8 = 1.125
    wt_areas = [0.8, 0.9, 0.7]
    result = compute_relative_activity(0.9, wt_areas)
    assert abs(result - 0.9 / (sum(wt_areas) / len(wt_areas))) < 1e-9


def test_relative_activity_single_wt_replicate():
    result = compute_relative_activity(1.5, [3.0])
    assert abs(result - 0.5) < 1e-9


def test_relative_activity_wt_itself_returns_one():
    # When area equals mean(wt_areas), result must be 1.0.
    wt_areas = [1.0, 1.0, 1.0]
    result = compute_relative_activity(1.0, wt_areas)
    assert abs(result - 1.0) < 1e-9


def test_relative_activity_empty_wt_raises():
    with pytest.raises(ValueError, match="wt_areas is empty"):
        compute_relative_activity(1.0, [])


def test_relative_activity_zero_wt_mean_raises():
    with pytest.raises(ValueError, match="WT mean area must be > 0"):
        compute_relative_activity(1.0, [0.0, 0.0])


def test_relative_activity_negative_wt_mean_raises():
    # Physically invalid — should raise.
    with pytest.raises(ValueError, match="WT mean area must be > 0"):
        compute_relative_activity(1.0, [-1.0, -2.0])


def test_relative_activity_error_message_contains_inputs():
    # Error message must include input information (anti-fallback rule).
    with pytest.raises(ValueError) as exc_info:
        compute_relative_activity(1.0, [0.0])
    msg = str(exc_info.value)
    assert "0" in msg  # wt_mean value appears in message
