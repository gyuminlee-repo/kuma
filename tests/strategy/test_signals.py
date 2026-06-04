"""Tests for kuma_core.strategy.signals -- TDD Phase 6 Task 6.1.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.1
Plan: notes/plans/2026-05-04-mame-activity-implementation-plan.md Phase 6
"""

import math
import pytest

from kuma_core.strategy.signals import (
    compute_K_throughput,
    compute_T1,
    compute_T2,
    compute_T2_threshold,
    compute_T3,
    compute_T3_magnitude,
    compute_T4,
    compute_T_active,
    compute_T_model,
    compute_T_unused,
    compute_sigma_assay,
    compute_sigma_assay_ci,
    compute_stability_viable_count,
)


# ---------------------------------------------------------------------------
# compute_K_throughput
# ---------------------------------------------------------------------------

def test_K_throughput_96_well():
    # C(14,2) = 91 <= 96, C(15,2) = 105 > 96 -> K=14
    assert compute_K_throughput(96) == 14


def test_K_throughput_384_well():
    # C(28,2) = 378 <= 384, C(29,2) = 406 > 384 -> K=28
    assert compute_K_throughput(384) == 28


def test_K_throughput_small():
    # C(1,2) = 0 <= 1, C(2,2) = 1 <= 1, C(3,2)=3 > 1 -> K=2
    assert compute_K_throughput(1) >= 1


def test_K_throughput_exact_triangle():
    # C_next = 10 -> C(4,2)=6<=10, C(5,2)=10<=10, C(6,2)=15>10 -> K=5
    assert compute_K_throughput(10) == 5


def test_K_throughput_invalid():
    with pytest.raises(ValueError):
        compute_K_throughput(0)
    with pytest.raises(ValueError):
        compute_K_throughput(-1)


# ---------------------------------------------------------------------------
# compute_T1
# ---------------------------------------------------------------------------

def test_T1_sufficient_beneficials():
    assert compute_T1(cumulative_beneficial=14, K_throughput=14) is True


def test_T1_insufficient_beneficials():
    assert compute_T1(cumulative_beneficial=10, K_throughput=14) is False


def test_T1_exact_threshold():
    assert compute_T1(cumulative_beneficial=14, K_throughput=14) is True


# ---------------------------------------------------------------------------
# compute_T2 / compute_T2_threshold
# ---------------------------------------------------------------------------

def test_T2_plateau():
    # threshold = 1.96 * 0.1 * sqrt(2/3) ~= 0.16003 (legacy, n_designed=None)
    threshold = 1.96 * 0.1 * math.sqrt(2 / 3)
    # n_designed=None -> falls back to legacy formula regardless of method
    result = compute_T2(0.05, 0.1, 3, n_designed=None)
    assert result == (0.05 < threshold)


def test_T2_above_threshold():
    # delta > threshold -> False (not plateau); n_designed=None -> legacy
    assert compute_T2(1.0, 0.1, 3, n_designed=None) is False


def test_T2_at_threshold_boundary():
    # delta exactly at threshold -> False (not strictly below); n_designed=None
    sigma = 0.1
    r = 3
    threshold = 1.96 * sigma * math.sqrt(2 / r)
    assert compute_T2(threshold, sigma, r, n_designed=None) is False


def test_T2_below_threshold():
    sigma = 0.05
    r = 4
    threshold = 1.96 * sigma * math.sqrt(2 / r)
    assert compute_T2(threshold * 0.5, sigma, r, n_designed=None) is True


def test_T2_sigma_none_returns_none():
    # S2 [P0]: sigma_assay=None -> None (not False)
    assert compute_T2(0.05, None, 3) is None
    assert compute_T2(0.05, None, 3, n_designed=24) is None


def test_T2_order_statistic_threshold_less_than_legacy_for_small_n():
    # order_statistic threshold < legacy when n_designed is small (< e^(1.96^2) ~47)
    # Using n=24: order = sigma*sqrt(2*ln(24)/r), legacy = 1.96*sigma*sqrt(2/r)
    sigma = 0.1
    r = 4
    n = 24
    order_thresh = compute_T2_threshold(sigma, r, n_designed=n, method="order_statistic")
    legacy_thresh = compute_T2_threshold(sigma, r, n_designed=None, method="legacy")
    assert order_thresh < legacy_thresh, (
        f"order={order_thresh:.6f} should be < legacy={legacy_thresh:.6f} for n={n}"
    )


def test_T2_threshold_legacy_method():
    sigma = 0.1
    r = 4
    expected = 1.96 * sigma * math.sqrt(2 / r)
    assert abs(compute_T2_threshold(sigma, r, method="legacy") - expected) < 1e-12


def test_T2_threshold_n_designed_clamp():
    # n_designed=1 should clamp to 2
    sigma = 0.1
    r = 4
    t1 = compute_T2_threshold(sigma, r, n_designed=1)
    t2 = compute_T2_threshold(sigma, r, n_designed=2)
    assert abs(t1 - t2) < 1e-12


# ---------------------------------------------------------------------------
# compute_T3 / compute_T3_magnitude
# ---------------------------------------------------------------------------

def test_T3_declining_hit_rate():
    # slope < 0 -> True (plateau); uses last 2 points by default
    assert compute_T3([0.5, 0.4, 0.3]) is True


def test_T3_flat_hit_rate():
    # slope = 0 -> True (plateau)
    assert compute_T3([0.4, 0.4]) is True


def test_T3_increasing_hit_rate():
    # slope > 0 -> False
    assert compute_T3([0.2, 0.4, 0.6]) is False


def test_T3_insufficient_data_returns_none():
    # S1 [P1]: fewer than 2 points -> None (not False)
    assert compute_T3([0.5]) is None
    assert compute_T3([]) is None


def test_T3_window_bug_regression():
    # Regression for full-history bug: hit_rates=[0.5,0.1,0.2,0.3].
    # Full-history slope is negative (T3 would fire incorrectly).
    # Last 2 points [0.2, 0.3] have positive slope -> should be False.
    assert compute_T3([0.5, 0.1, 0.2, 0.3]) is False


def test_T3_window_2_declining():
    # Last 2 points declining -> True even if earlier points rose
    assert compute_T3([0.1, 0.5, 0.4]) is True


def test_T3_window_custom():
    # window=3: last 3 of [0.1, 0.5, 0.4, 0.2] -> [0.5, 0.4, 0.2], slope < 0 -> True
    assert compute_T3([0.1, 0.5, 0.4, 0.2], window=3) is True


def test_T3_magnitude_returns_slope():
    mag = compute_T3_magnitude([0.2, 0.3])
    assert mag is not None
    assert mag > 0  # 0.3 > 0.2, positive slope


def test_T3_magnitude_insufficient_data():
    assert compute_T3_magnitude([0.5]) is None
    assert compute_T3_magnitude([]) is None


# ---------------------------------------------------------------------------
# compute_T4
# ---------------------------------------------------------------------------

def test_T4_high_jaccard():
    s1 = {10, 20, 30, 40, 50}
    s2 = {10, 20, 30, 40, 60}
    # intersection=4, union=6 -> Jaccard=0.667 >= 0.5 -> True
    assert compute_T4(s1, s2, jaccard_threshold=0.5) is True


def test_T4_low_jaccard():
    s1 = {1, 2, 3}
    s2 = {4, 5, 6}
    # intersection=0, union=6 -> Jaccard=0.0 < 0.5 -> False
    assert compute_T4(s1, s2, jaccard_threshold=0.5) is False


def test_T4_both_empty_returns_none():
    # S2 [P0]: both sets empty -> None (not False)
    assert compute_T4(set(), set(), jaccard_threshold=0.5) is None


def test_T4_default_threshold():
    s1 = {1, 2, 3, 4}
    s2 = {1, 2, 3, 5}
    # intersection=3, union=5 -> Jaccard=0.6 >= 0.5 -> True
    assert compute_T4(s1, s2) is True


# ---------------------------------------------------------------------------
# compute_T_active
# ---------------------------------------------------------------------------

def test_T_active_sufficient():
    # 4/8 = 0.5 >= 0.4 -> True
    top_k = [1, 5, 10, 15, 20, 25, 30, 35]
    active = [1, 5, 10, 15]
    assert compute_T_active(top_k, active, threshold=0.4) is True


def test_T_active_insufficient():
    # 1/5 = 0.2 < 0.4 -> False
    top_k = [1, 2, 3, 4, 5]
    active = [1, 99, 100]
    assert compute_T_active(top_k, active, threshold=0.4) is False


def test_T_active_empty_top_k_returns_none():
    # S3 [P0]: empty top_k -> None (not False)
    assert compute_T_active([], [1, 2, 3], threshold=0.4) is None


def test_T_active_no_active_residues_returns_none():
    # S3 [P0]: empty active_residues -> None (not False)
    assert compute_T_active([1, 2, 3, 4, 5], [], threshold=0.4) is None


def test_T_active_default_threshold():
    # default = 0.4; 2/5 = 0.4 -> True (>= not >)
    top_k = [1, 2, 3, 4, 5]
    active = [1, 2]
    assert compute_T_active(top_k, active) is True


# ---------------------------------------------------------------------------
# compute_T_unused
# ---------------------------------------------------------------------------

def test_T_unused_above_m_min():
    assert compute_T_unused(unused_beneficial_count=7, M_min=5) is True


def test_T_unused_exactly_m_min():
    assert compute_T_unused(unused_beneficial_count=5, M_min=5) is True


def test_T_unused_below_m_min():
    assert compute_T_unused(unused_beneficial_count=3, M_min=5) is False


def test_T_unused_default_m_min():
    assert compute_T_unused(unused_beneficial_count=5) is True
    assert compute_T_unused(unused_beneficial_count=4) is False


# ---------------------------------------------------------------------------
# compute_T_model
# ---------------------------------------------------------------------------

def test_T_model_sigma_none_returns_none():
    # S5 [P2]: sigma_assay=None -> None
    assert compute_T_model(0.05, None, 4) is None


def test_T_model_below_threshold_returns_true():
    # gain < z * sigma * sqrt(2/r) -> True (single space exhausted)
    sigma = 0.1
    r = 4
    threshold = 1.96 * sigma * math.sqrt(2 / r)
    assert compute_T_model(threshold * 0.5, sigma, r) is True


def test_T_model_above_threshold_returns_false():
    # gain > threshold -> False (untested single may be worthwhile)
    sigma = 0.1
    r = 4
    threshold = 1.96 * sigma * math.sqrt(2 / r)
    assert compute_T_model(threshold * 2.0, sigma, r) is False


def test_T_model_custom_z():
    sigma = 0.1
    r = 4
    z = 1.645
    threshold = z * sigma * math.sqrt(2 / r)
    assert compute_T_model(threshold * 0.5, sigma, r, z_model=z) is True
    assert compute_T_model(threshold * 1.5, sigma, r, z_model=z) is False


# ---------------------------------------------------------------------------
# compute_sigma_assay
# ---------------------------------------------------------------------------

def test_sigma_assay_min_4_replicates_fail():
    assert compute_sigma_assay([1.0, 1.0, 1.0]) is None


def test_sigma_assay_min_4_replicates_pass():
    result = compute_sigma_assay([1.0, 1.05, 0.98, 1.02])
    assert result is not None
    assert result > 0


def test_sigma_assay_exact_4():
    result = compute_sigma_assay([1.0, 2.0, 3.0, 4.0], min_replicates=4)
    assert result is not None


def test_sigma_assay_uniform_values():
    # all same -> stdev = 0.0
    result = compute_sigma_assay([1.0, 1.0, 1.0, 1.0])
    assert result == 0.0


def test_sigma_assay_known_value():
    import statistics
    vals = [1.0, 2.0, 3.0, 4.0]
    expected = statistics.stdev(vals)
    result = compute_sigma_assay(vals)
    assert result is not None
    assert abs(result - expected) < 1e-10


def test_sigma_assay_custom_min_replicates():
    assert compute_sigma_assay([1.0, 2.0], min_replicates=3) is None
    result = compute_sigma_assay([1.0, 2.0, 3.0], min_replicates=3)
    assert result is not None


# ---------------------------------------------------------------------------
# compute_sigma_assay_ci
# ---------------------------------------------------------------------------

def test_sigma_assay_ci_insufficient_returns_none():
    # S6 [P1]: fewer than min_replicates -> None
    assert compute_sigma_assay_ci([1.0, 1.0, 1.0]) is None


def test_sigma_assay_ci_n4_ordering():
    # n=4 (df=3): lo < s < hi
    import statistics
    vals = [1.0, 1.05, 0.98, 1.02]
    s = statistics.stdev(vals)
    result = compute_sigma_assay_ci(vals)
    assert result is not None
    lo, hi = result
    assert lo < s < hi, f"Expected lo={lo:.4f} < s={s:.4f} < hi={hi:.4f}"


def test_sigma_assay_ci_n4_approximate_bounds():
    # df=3: exact chi2 95% CI ~[0.566s, 3.729s]
    # Wilson-Hilferty approximation: lo ~0.567s (tight), hi ~4.07s (wider than exact)
    # Use loose bounds to accommodate W-H approximation error
    import statistics
    vals = [1.0, 2.0, 3.0, 4.0]
    s = statistics.stdev(vals)
    result = compute_sigma_assay_ci(vals)
    assert result is not None
    lo, hi = result
    lo_ratio = lo / s
    hi_ratio = hi / s
    # lo: W-H is accurate (~0.567), tight check
    assert 0.50 < lo_ratio < 0.65, f"lo/s={lo_ratio:.4f}, expected ~0.567"
    # hi: W-H is ~9% wider than exact 3.73, use loose upper bound
    assert 3.5 < hi_ratio < 4.5, f"hi/s={hi_ratio:.4f}, expected ~4.07 (W-H approx)"


def test_sigma_assay_ci_n8_tighter():
    # Larger n should give tighter CI
    import statistics
    vals = [1.0, 1.1, 0.9, 1.05, 0.95, 1.02, 0.98, 1.01]
    s = statistics.stdev(vals)
    result = compute_sigma_assay_ci(vals)
    assert result is not None
    lo, hi = result
    assert lo < s < hi  # CI brackets the point estimate
    # With n=8 (df=7), CI ratio should be tighter than df=3
    assert hi / s < 3.1, f"hi/s={hi/s:.4f}, expected < 3.1 for n=8"


def test_sigma_assay_ci_returns_tuple():
    result = compute_sigma_assay_ci([1.0, 2.0, 3.0, 4.0])
    assert isinstance(result, tuple)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# compute_stability_viable_count
# ---------------------------------------------------------------------------

def test_stability_viable_count_no_max():
    # S7 [P2]: per_single_ddg_max=None -> all beneficials counted
    ddgs = [0.5, 1.0, 2.0, -0.3]
    assert compute_stability_viable_count(ddgs) == 4
    assert compute_stability_viable_count(ddgs, per_single_ddg_max=None) == 4


def test_stability_viable_count_with_max():
    # Only ddG <= max are counted
    ddgs = [0.5, 1.0, 2.0, -0.3]
    assert compute_stability_viable_count(ddgs, per_single_ddg_max=1.0) == 3
    # 0.5, 1.0, -0.3 are <= 1.0; 2.0 is not


def test_stability_viable_count_strict_max():
    ddgs = [0.5, 1.0, 2.0, 3.0]
    assert compute_stability_viable_count(ddgs, per_single_ddg_max=0.9) == 1


def test_stability_viable_count_all_filtered():
    ddgs = [2.0, 3.0, 5.0]
    assert compute_stability_viable_count(ddgs, per_single_ddg_max=1.0) == 0


def test_stability_viable_count_empty():
    assert compute_stability_viable_count([]) == 0
    assert compute_stability_viable_count([], per_single_ddg_max=1.0) == 0
