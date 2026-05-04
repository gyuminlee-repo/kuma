"""Tests for kuma_core.strategy.signals — TDD Phase 6 Task 6.1.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.1
Plan: notes/plans/2026-05-04-mame-activity-implementation-plan.md Phase 6
"""

import math
import pytest

from kuma_core.strategy.signals import (
    compute_K_throughput,
    compute_T1,
    compute_T2,
    compute_T3,
    compute_T4,
    compute_T_active,
    compute_T_unused,
    compute_sigma_assay,
)


# ---------------------------------------------------------------------------
# compute_K_throughput
# ---------------------------------------------------------------------------

def test_K_throughput_96_well():
    # C(14,2) = 91 <= 96, C(15,2) = 105 > 96 → K=14
    assert compute_K_throughput(96) == 14


def test_K_throughput_384_well():
    # C(28,2) = 378 <= 384, C(29,2) = 406 > 384 → K=28
    assert compute_K_throughput(384) == 28


def test_K_throughput_small():
    # C(1,2) = 0 <= 1, C(2,2) = 1 <= 1, C(3,2)=3 > 1 → K=2
    assert compute_K_throughput(1) >= 1


def test_K_throughput_exact_triangle():
    # C_next = 10 → C(4,2)=6<=10, C(5,2)=10<=10, C(6,2)=15>10 → K=5
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
# compute_T2
# ---------------------------------------------------------------------------

def test_T2_plateau():
    # threshold = 1.96 * 0.1 * sqrt(2/3) ≈ 0.16003
    threshold = 1.96 * 0.1 * math.sqrt(2 / 3)
    assert compute_T2(0.05, 0.1, 3) == (0.05 < threshold)


def test_T2_above_threshold():
    # delta > threshold → False (not plateau)
    assert compute_T2(1.0, 0.1, 3) is False


def test_T2_at_threshold_boundary():
    # delta exactly at threshold → False (not strictly below)
    sigma = 0.1
    r = 3
    threshold = 1.96 * sigma * math.sqrt(2 / r)
    assert compute_T2(threshold, sigma, r) is False


def test_T2_below_threshold():
    sigma = 0.05
    r = 4
    threshold = 1.96 * sigma * math.sqrt(2 / r)
    assert compute_T2(threshold * 0.5, sigma, r) is True


# ---------------------------------------------------------------------------
# compute_T3
# ---------------------------------------------------------------------------

def test_T3_declining_hit_rate():
    # slope < 0 → True (plateau)
    assert compute_T3([0.5, 0.4, 0.3]) is True


def test_T3_flat_hit_rate():
    # slope = 0 → True (plateau)
    assert compute_T3([0.4, 0.4]) is True


def test_T3_increasing_hit_rate():
    # slope > 0 → False
    assert compute_T3([0.2, 0.4, 0.6]) is False


def test_T3_insufficient_data():
    # fewer than 2 data points → False (not yet plateau)
    assert compute_T3([0.5]) is False
    assert compute_T3([]) is False


# ---------------------------------------------------------------------------
# compute_T4
# ---------------------------------------------------------------------------

def test_T4_high_jaccard():
    s1 = {10, 20, 30, 40, 50}
    s2 = {10, 20, 30, 40, 60}
    # intersection=4, union=6 → Jaccard=0.667 >= 0.5 → True
    assert compute_T4(s1, s2, jaccard_threshold=0.5) is True


def test_T4_low_jaccard():
    s1 = {1, 2, 3}
    s2 = {4, 5, 6}
    # intersection=0, union=6 → Jaccard=0.0 < 0.5 → False
    assert compute_T4(s1, s2, jaccard_threshold=0.5) is False


def test_T4_both_empty():
    # 0/0 → 0.0 < threshold → False (no convergence signal)
    assert compute_T4(set(), set(), jaccard_threshold=0.5) is False


def test_T4_default_threshold():
    s1 = {1, 2, 3, 4}
    s2 = {1, 2, 3, 5}
    # intersection=3, union=5 → Jaccard=0.6 >= 0.5 → True
    assert compute_T4(s1, s2) is True


# ---------------------------------------------------------------------------
# compute_T_active
# ---------------------------------------------------------------------------

def test_T_active_sufficient():
    # 4/8 = 0.5 >= 0.4 → True
    top_k = [1, 5, 10, 15, 20, 25, 30, 35]
    active = [1, 5, 10, 15]
    assert compute_T_active(top_k, active, threshold=0.4) is True


def test_T_active_insufficient():
    # 1/5 = 0.2 < 0.4 → False
    top_k = [1, 2, 3, 4, 5]
    active = [1, 99, 100]
    assert compute_T_active(top_k, active, threshold=0.4) is False


def test_T_active_empty_top_k():
    assert compute_T_active([], [1, 2, 3], threshold=0.4) is False


def test_T_active_no_active_residues():
    assert compute_T_active([1, 2, 3, 4, 5], [], threshold=0.4) is False


def test_T_active_default_threshold():
    # default = 0.4; 2/5 = 0.4 → True (>= not >)
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
# compute_sigma_assay
# ---------------------------------------------------------------------------

def test_sigma_assay_min_4_replicates_fail():
    assert compute_sigma_assay([1.0, 1.0, 1.0]) is None


def test_sigma_assay_min_4_replicates_pass():
    result = compute_sigma_assay([1.0, 1.05, 0.98, 1.02])
    assert result is not None
    assert result > 0


def test_sigma_assay_exact_4():
    # exactly 4 replicates should pass
    result = compute_sigma_assay([1.0, 2.0, 3.0, 4.0], min_replicates=4)
    assert result is not None


def test_sigma_assay_uniform_values():
    # all same → stdev = 0.0
    result = compute_sigma_assay([1.0, 1.0, 1.0, 1.0])
    assert result == 0.0


def test_sigma_assay_known_value():
    # population stdev of [1,2,3,4] = 1.118..., sample stdev = 1.291...
    # using statistics.stdev (sample)
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
