from kuma_core.mame.activity.normalize import compute_fold_change, compute_log2_fc
import math


def test_fold_change_2x():
    assert abs(compute_fold_change(2.0, 1.0) - 2.0) < 1e-6


def test_fold_change_wt_zero_returns_none():
    assert compute_fold_change(2.0, 0.0) is None


def test_fold_change_none_input():
    assert compute_fold_change(None, 1.0) is None
    assert compute_fold_change(2.0, None) is None


def test_log2_fc():
    assert abs(compute_log2_fc(2.0) - 1.0) < 1e-6
    assert abs(compute_log2_fc(0.5) - (-1.0)) < 1e-6


def test_log2_fc_wt_returns_zero():
    assert compute_log2_fc(1.0, is_wt=True) == 0.0


def test_log2_fc_negative_or_zero_returns_none():
    assert compute_log2_fc(0.0) is None
    assert compute_log2_fc(-1.0) is None
