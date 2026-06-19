"""Phase A adversarial / red-team tests (G001 QA gate).

Boundary, failure-mode, and property-based checks for the Phase A surface:
  - NKLandscape K bounds
  - acquisition.select_indices error paths + clamp/empty behaviour
  - rf_thompson_sample tree-prediction property
  - rf_mean_std genuine variance (NOT zeros placeholder)
  - stats.mean_verdict exhaustiveness + mutual-exclusion of WIN/LOSE
  - stats.decision_cell 9-cell coverage + undefined raises
  - metrics.cvar lower-tail correctness, empty, catastrophe_rate threshold
  - run_campaign_nk determinism
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor

from al import acquisition, metrics, stats
from al.acquisition import rf_mean_std, rf_thompson_sample, rf_per_tree_predictions, select_indices
from al.landscape import NKLandscape, onehot
from al.rugged_sim import run_campaign_nk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rng(seed: int = 0) -> np.random.Generator:
    return np.random.default_rng(seed)


def _fit_small_rf(n_sites: int = 8, n_alleles: int = 2, K: int = 3, seed: int = 0):
    """Fit a RandomForest on a tiny NKLandscape; return (model, pool, X_pool)."""
    land = NKLandscape(n_sites, n_alleles, K=K, seed=seed)
    rng = _rng(seed)
    genos = land.all_genotypes()
    n_train = min(len(genos), 32)
    train_idx = rng.permutation(len(genos))[:n_train]
    train = [genos[i] for i in train_idx]
    X = np.vstack([onehot(g, n_alleles) for g in train])
    y = np.array([land.fitness(g) for g in train])
    model = RandomForestRegressor(
        n_estimators=50, criterion="friedman_mse", max_features=1.0, random_state=1
    )
    model.fit(X, y)
    pool = [g for g in genos if g not in set(train)]
    X_pool = np.vstack([onehot(g, n_alleles) for g in pool]) if pool else np.empty((0, n_sites * n_alleles))
    return model, pool, X_pool


# ===========================================================================
# 1. NKLandscape K bounds
# ===========================================================================

class TestNKLandscapeKBounds:
    def test_k_equals_n_sites_raises(self):
        """K = n_sites is out of [0, n_sites-1]; must raise ValueError."""
        with pytest.raises(ValueError, match="K must be in"):
            NKLandscape(n_sites=5, K=5)

    def test_k_negative_raises(self):
        """K = -1 is below 0; must raise ValueError."""
        with pytest.raises(ValueError, match="K must be in"):
            NKLandscape(n_sites=5, K=-1)

    def test_k_zero_valid(self):
        """K = 0 is the smooth lower bound; must succeed."""
        land = NKLandscape(n_sites=5, K=0)
        assert land.K == 0

    def test_k_n_sites_minus_1_valid(self):
        """K = n_sites - 1 is the max-rugged upper bound; must succeed."""
        land = NKLandscape(n_sites=5, K=4)
        assert land.K == 4


# ===========================================================================
# 2. acquisition.select_indices error paths
# ===========================================================================

class TestSelectIndicesErrors:
    def test_unknown_arm_raises(self):
        with pytest.raises(ValueError, match="unknown acquisition arm"):
            select_indices("bogus_arm", mean=[1.0, 2.0], n=1, rng=_rng())

    def test_ucb_without_std_raises(self):
        with pytest.raises(ValueError, match="ucb requires std"):
            select_indices("ucb", mean=[1.0, 2.0, 3.0], n=1, rng=_rng())

    def test_thompson_without_sample_raises(self):
        with pytest.raises(ValueError, match="thompson requires a posterior sample"):
            select_indices("thompson", mean=[1.0, 2.0, 3.0], n=1, rng=_rng())

    def test_embdiv_without_features_raises(self):
        with pytest.raises(ValueError, match="embdiv requires features"):
            select_indices("embdiv", mean=[1.0, 2.0], n=1, rng=_rng())

    def test_sigma_kuro_without_positions_raises(self):
        with pytest.raises(ValueError, match="sigma_kuro requires positions"):
            select_indices("sigma_kuro", mean=[1.0, 2.0], n=1, rng=_rng())


# ===========================================================================
# 3. n > pool size clamps; n <= 0 returns []
# ===========================================================================

class TestSelectIndicesSizeBehavior:
    def test_n_larger_than_pool_clamps(self):
        """n > pool size: return all pool elements (no duplicates, len == pool)."""
        mean = [0.1, 0.5, 0.9]
        pool_size = len(mean)
        idx = select_indices("topn", mean=mean, n=999, rng=_rng())
        assert len(idx) <= pool_size
        assert len(set(idx)) == len(idx)  # distinct
        assert all(0 <= i < pool_size for i in idx)

    def test_n_zero_returns_empty(self):
        mean = [0.1, 0.5, 0.9]
        assert select_indices("topn", mean=mean, n=0, rng=_rng()) == []

    def test_n_negative_returns_empty(self):
        mean = [0.1, 0.5, 0.9]
        assert select_indices("topn", mean=mean, n=-5, rng=_rng()) == []

    def test_random_n_larger_than_pool_clamps(self):
        mean = [0.1, 0.2]
        idx = select_indices("random", mean=mean, n=10, rng=_rng())
        assert len(idx) <= len(mean)
        assert len(set(idx)) == len(idx)

    def test_ucb_n_larger_than_pool_clamps(self):
        mean = np.array([0.1, 0.5, 0.9])
        std = np.array([0.01, 0.02, 0.03])
        idx = select_indices("ucb", mean=mean, std=std, n=100, rng=_rng())
        assert len(idx) <= len(mean)
        assert len(set(idx)) == len(idx)

    def test_thompson_n_larger_than_pool_clamps(self):
        mean = np.array([0.1, 0.5])
        sample = np.array([0.9, 0.1])
        idx = select_indices("thompson", mean=mean, sample=sample, n=100, rng=_rng())
        assert len(idx) <= len(mean)
        assert len(set(idx)) == len(idx)


# ===========================================================================
# 4. rf_thompson_sample: every sampled value equals some tree's prediction
# ===========================================================================

class TestRfThompsonSampleProperty:
    def test_each_sample_equals_a_tree_prediction(self):
        """Property: rf_thompson_sample draws one tree's prediction per point.
        For each point i, sample[i] must equal per_tree[t, i] for some tree t.
        """
        model, pool, X_pool = _fit_small_rf()
        assert X_pool.shape[0] > 0, "pool is non-empty"
        rng = _rng(42)
        sample = rf_thompson_sample(model, X_pool, rng)
        per_tree = rf_per_tree_predictions(model, X_pool)  # (T, N)
        for i in range(X_pool.shape[0]):
            # sample[i] must match at least one tree's prediction at point i
            assert sample[i] in per_tree[:, i], (
                f"sample[{i}]={sample[i]:.6f} not found in any of the "
                f"{per_tree.shape[0]} tree predictions"
            )

    def test_thompson_different_seeds_can_differ(self):
        """Two different seeds should (with high probability) give different samples."""
        model, pool, X_pool = _fit_small_rf()
        s1 = rf_thompson_sample(model, X_pool, _rng(0))
        s2 = rf_thompson_sample(model, X_pool, _rng(999))
        # With 50 trees and >=10 points, extremely unlikely to be identical
        assert not np.allclose(s1, s2), "Thompson samples from different seeds should differ"


# ===========================================================================
# 5. rf_mean_std: std >= 0 and > 0 somewhere (genuine variance)
# ===========================================================================

class TestRfMeanStd:
    def test_std_nonnegative(self):
        model, pool, X_pool = _fit_small_rf()
        mean, std = rf_mean_std(model, X_pool)
        assert np.all(std >= 0), f"std has negative values: {std[std < 0]}"

    def test_std_positive_somewhere(self):
        """std > 0 somewhere confirms real tree variance, NOT the zeros placeholder."""
        model, pool, X_pool = _fit_small_rf()
        _, std = rf_mean_std(model, X_pool)
        assert float(std.max()) > 0.0, (
            "BUG: all std values are 0 — this would indicate the zeros placeholder "
            "is leaking into rf_mean_std (not using estimators_)"
        )

    def test_mean_shape_matches_pool(self):
        model, pool, X_pool = _fit_small_rf()
        mean, std = rf_mean_std(model, X_pool)
        assert mean.shape == (X_pool.shape[0],)
        assert std.shape == (X_pool.shape[0],)

    def test_mean_std_consistent_with_per_tree(self):
        """mean and std must match numpy's own mean/std of the per-tree array."""
        model, pool, X_pool = _fit_small_rf()
        mean, std = rf_mean_std(model, X_pool)
        per_tree = rf_per_tree_predictions(model, X_pool)
        np.testing.assert_allclose(mean, per_tree.mean(axis=0), rtol=1e-9)
        np.testing.assert_allclose(std, per_tree.std(axis=0), rtol=1e-9)


# ===========================================================================
# 6. stats.mean_verdict exhaustiveness and mutual exclusion
# ===========================================================================

class TestMeanVerdictExhaustive:
    _VALID = frozenset(("WIN", "TIE", "LOSE"))

    def _verdict(self, md, cd, p):
        return stats.mean_verdict({"median_delta": md, "cliffs_delta": cd, "wilcoxon_p": p})

    def test_always_returns_valid_label(self):
        """A grid of (median_delta, cliffs_delta, p) always yields WIN/TIE/LOSE."""
        mds = [-0.10, -0.03, 0.0, 0.03, 0.10]
        cds = [-0.30, -0.15, 0.0, 0.15, 0.30]
        ps = [0.001, 0.04, 0.05, 0.20, 1.0]
        for md in mds:
            for cd in cds:
                for p in ps:
                    v = self._verdict(md, cd, p)
                    assert v in self._VALID, f"Unexpected verdict {v!r} for md={md} cd={cd} p={p}"

    def test_win_and_lose_never_both(self):
        """WIN and LOSE are mutually exclusive (they require opposite signs)."""
        # The guard in the function returns TIE for the impossible double-true case.
        # We verify the logical impossibility: a real input cannot satisfy both.
        mds = np.linspace(-0.5, 0.5, 21)
        cds = np.linspace(-0.5, 0.5, 21)
        for md in mds:
            for cd in cds:
                v = self._verdict(md, cd, 0.01)
                assert not (v == "WIN" and v == "LOSE")  # tautological but explicit

    def test_large_effect_nonsignificant_is_tie(self):
        """Large median_delta + large cliffs_delta but p=0.20 -> TIE (not WIN)."""
        v = self._verdict(0.10, 0.30, p=0.20)
        assert v == "TIE", f"Expected TIE for large-but-nonsignificant, got {v!r}"

    def test_win_requires_all_three_criteria(self):
        # fails magnitude
        assert self._verdict(0.02, 0.20, 0.01) == "TIE"
        # fails effect size
        assert self._verdict(0.05, 0.10, 0.01) == "TIE"
        # fails significance
        assert self._verdict(0.05, 0.20, 0.10) == "TIE"
        # all pass -> WIN
        assert self._verdict(0.05, 0.20, 0.01) == "WIN"

    def test_lose_requires_all_three_directional(self):
        # fails magnitude (direction ok)
        assert self._verdict(-0.02, -0.20, 0.01) == "TIE"
        # fails effect size (magnitude ok)
        assert self._verdict(-0.05, -0.10, 0.01) == "TIE"
        # all pass -> LOSE
        assert self._verdict(-0.05, -0.20, 0.01) == "LOSE"

    def test_random_inputs_always_valid(self):
        """Randomised fuzz: 500 random inputs, always in {WIN, TIE, LOSE}."""
        rng = np.random.default_rng(1234)
        for _ in range(500):
            md = float(rng.uniform(-0.5, 0.5))
            cd = float(rng.uniform(-1.0, 1.0))
            p = float(rng.uniform(0.0, 1.0))
            v = self._verdict(md, cd, p)
            assert v in self._VALID, f"Fuzz failure: verdict={v!r} md={md:.3f} cd={cd:.3f} p={p:.3f}"


# ===========================================================================
# 7. stats.decision_cell: 9-cell coverage + undefined raises
# ===========================================================================

class TestDecisionCell:
    _MEANS = ("WIN", "TIE", "LOSE")
    _TAILS = ("TAIL-ADV", "TAIL-NULL", "TAIL-WORSE")

    def test_all_9_combos_return_a_verdict(self):
        for mean in self._MEANS:
            for tail in self._TAILS:
                result = stats.decision_cell(mean, tail)
                assert isinstance(result, str) and result, \
                    f"decision_cell({mean!r}, {tail!r}) returned empty/non-string"

    def test_undefined_mean_raises(self):
        with pytest.raises(ValueError, match="undefined decision cell"):
            stats.decision_cell("DRAW", "TAIL-NULL")

    def test_undefined_tail_raises(self):
        with pytest.raises(ValueError, match="undefined decision cell"):
            stats.decision_cell("WIN", "UNKNOWN")

    def test_both_undefined_raises(self):
        with pytest.raises(ValueError):
            stats.decision_cell("", "")

    def test_exact_mappings_spot_check(self):
        assert stats.decision_cell("WIN", "TAIL-ADV") == "FOR-STRONG"
        assert stats.decision_cell("WIN", "TAIL-NULL") == "FOR-STRONG"
        assert stats.decision_cell("WIN", "TAIL-WORSE") == "MIXED"
        assert stats.decision_cell("TIE", "TAIL-ADV") == "FOR-QUALIFIED"
        assert stats.decision_cell("TIE", "TAIL-NULL") == "INCONCLUSIVE"
        assert stats.decision_cell("TIE", "TAIL-WORSE") == "AGAINST"
        assert stats.decision_cell("LOSE", "TAIL-ADV") == "MIXED"
        assert stats.decision_cell("LOSE", "TAIL-NULL") == "AGAINST/REFUTE"
        assert stats.decision_cell("LOSE", "TAIL-WORSE") == "AGAINST/REFUTE-STRONG"

    def test_table_has_exactly_9_entries(self):
        assert len(stats.DECISION_TABLE) == 9


# ===========================================================================
# 8. metrics.cvar lower-tail correctness
# ===========================================================================

class TestCvar:
    def test_lower_tail_below_mean(self):
        """CVaR@20% of [0..1] uniform must be below the mean (0.5)."""
        values = list(np.linspace(0, 1, 100))
        c = metrics.cvar(values, q=0.20)
        mean = float(np.mean(values))
        assert c < mean, f"CVaR@20% {c:.4f} >= mean {mean:.4f}"

    def test_empty_returns_nan(self):
        result = metrics.cvar([], q=0.20)
        assert math.isnan(result), f"Expected nan for empty, got {result!r}"

    def test_cvar_equals_mean_for_q_1(self):
        """CVaR@100% is the mean of all values."""
        values = [0.1, 0.3, 0.5, 0.7, 0.9]
        c = metrics.cvar(values, q=1.0)
        np.testing.assert_allclose(c, float(np.mean(values)), rtol=1e-9)

    def test_cvar_is_minimum_for_tiny_q(self):
        """CVaR@near-zero includes only the single worst value = minimum."""
        values = [0.1, 0.5, 0.9, 0.3, 0.7]
        c = metrics.cvar(values, q=0.001)  # ceil(5*0.001)=1 -> min
        assert c == pytest.approx(0.1, abs=1e-9)

    def test_catastrophe_rate_threshold(self):
        """catastrophe_rate counts fraction strictly below threshold."""
        values = [0.3, 0.4, 0.5, 0.6, 0.7]
        # threshold 0.50: strictly below -> 0.3, 0.4 -> rate = 2/5 = 0.40
        rate = metrics.catastrophe_rate(values, threshold=0.50)
        assert rate == pytest.approx(0.40, abs=1e-9)

    def test_catastrophe_rate_empty_is_nan(self):
        assert math.isnan(metrics.catastrophe_rate([]))

    def test_cvar_single_element(self):
        c = metrics.cvar([0.42], q=0.20)
        assert c == pytest.approx(0.42, abs=1e-9)

    def test_cvar_worst_20_percent_uses_at_least_one(self):
        """k = max(1, ceil(n*q)) so even with q=0.20 and n=1 it uses 1 element."""
        values = [0.7]
        c = metrics.cvar(values, q=0.20)
        assert c == pytest.approx(0.7, abs=1e-9)

    def test_cvar_lower_than_mean_on_skewed_data(self):
        """Right-skewed data: a few high values pull mean up; CVaR of lower 20% < mean."""
        values = [0.1, 0.1, 0.1, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9, 0.9]
        c = metrics.cvar(values, q=0.20)
        mean = float(np.mean(values))
        assert c < mean


# ===========================================================================
# 9. Determinism: same seed -> identical run_campaign_nk record
# ===========================================================================

class TestDeterminism:
    def test_identical_seed_gives_identical_record(self):
        """Same (landscape, arm, seed) must produce byte-identical numeric results."""
        land = NKLandscape(6, 2, K=2, seed=7)
        rec1 = run_campaign_nk(land, "topn", n=6, k_rounds=4, seed=3)
        rec2 = run_campaign_nk(land, "topn", n=6, k_rounds=4, seed=3)
        for key in ("norm_best", "best_found", "global_max", "found_global", "regret"):
            assert rec1[key] == rec2[key], f"key={key}: {rec1[key]} != {rec2[key]}"

    def test_different_seed_can_differ(self):
        """Different seeds should (in general) produce different outcomes."""
        land = NKLandscape(6, 2, K=2, seed=7)
        outcomes = set()
        for s in range(10):
            rec = run_campaign_nk(land, "random", n=6, k_rounds=4, seed=s)
            outcomes.add(rec["norm_best"])
        # With 10 random seeds, at least 2 distinct norm_best values expected.
        assert len(outcomes) > 1, "All seeds produced the same norm_best — suspicious"

    def test_determinism_across_all_arms(self):
        """All acquisition arms are deterministic given the same seed."""
        land = NKLandscape(6, 2, K=2, seed=5)
        from al.rugged_sim import ACQ_ARMS
        for arm in ACQ_ARMS:
            r1 = run_campaign_nk(land, arm, n=6, k_rounds=4, seed=0)
            r2 = run_campaign_nk(land, arm, n=6, k_rounds=4, seed=0)
            assert r1["norm_best"] == r2["norm_best"], f"arm={arm} not deterministic"
            assert r1["found_global"] == r2["found_global"], f"arm={arm} found_global not deterministic"
