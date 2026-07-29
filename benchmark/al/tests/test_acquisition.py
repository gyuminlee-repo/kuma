"""Tests for al.acquisition (round-2+ acquisition arms) + the decision table.

Covers each arm's selection behavior, the RandomForest per-tree variance that feeds
UCB/Thompson (std_predictions is a zeros placeholder, so variance must come from
estimators_), the REAL sigma-adaptive KURO schedule (decreasing exploration), and
the pre-registered directional decision table (F1a/F1b/F4).
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from al import acquisition, stats
from al.acquisition import ACQUISITION_ARMS, rf_mean_std, rf_thompson_sample, select_indices
from al.landscape import NKLandscape, onehot
from al.rugged_sim import ACQ_ARMS, regime_decision_table, run_campaign_nk, run_rugged_sweep


def _rng(seed=0):
    return np.random.default_rng(seed)


def _fit_rf_on_nk(land, n_train=24, seed=0):
    rng = _rng(seed)
    genos = land.all_genotypes()
    idx = rng.permutation(len(genos))[:n_train]
    train = [genos[i] for i in idx]
    X = np.vstack([onehot(g, land.n_alleles) for g in train])
    y = np.array([land.fitness(g) for g in train])
    model = RandomForestRegressor(
        n_estimators=100, criterion="friedman_mse", max_features=1.0, random_state=1
    )
    model.fit(X, y)
    pool = [g for g in genos if g not in set(train)]
    X_pool = np.vstack([onehot(g, land.n_alleles) for g in pool])
    return model, pool, X_pool


def test_acquisition_arm_set():
    assert ACQUISITION_ARMS == ("topn", "random", "ucb", "thompson", "embdiv", "sigma_kuro")
    assert set(ACQ_ARMS) == set(ACQUISITION_ARMS)


def test_topn_selects_highest_mean():
    mean = [0.1, 0.9, 0.5, 0.7, 0.2]
    idx = select_indices("topn", mean=mean, n=2, rng=_rng())
    assert idx == [1, 3]  # the two highest means, in descending order


def test_random_selects_n_distinct():
    mean = list(range(10))
    idx = select_indices("random", mean=mean, n=4, rng=_rng(3))
    assert len(idx) == 4
    assert len(set(idx)) == 4
    assert all(0 <= i < 10 for i in idx)


def test_ucb_uses_std_not_just_mean():
    # mean favors index 0; a large std on index 4 makes UCB prefer 4 at kappa=2.
    mean = np.array([0.90, 0.10, 0.10, 0.10, 0.80])
    std = np.array([0.00, 0.00, 0.00, 0.00, 0.50])
    greedy = select_indices("topn", mean=mean, n=1, rng=_rng())
    ucb = select_indices("ucb", mean=mean, std=std, n=1, rng=_rng(), kappa=2.0)
    assert greedy == [0]
    assert ucb == [4]  # 0.80 + 2*0.50 = 1.80 > 0.90


def test_ucb_requires_std():
    try:
        select_indices("ucb", mean=[1.0, 2.0], n=1, rng=_rng())
    except ValueError:
        return
    raise AssertionError("ucb without std must raise")


def test_thompson_selects_by_sample():
    mean = [0.0, 0.0, 0.0]
    sample = [0.1, 0.9, 0.2]
    idx = select_indices("thompson", mean=mean, sample=sample, n=1, rng=_rng())
    assert idx == [1]


def test_rf_per_tree_variance_nondegenerate():
    # The forest must expose REAL per-tree variance (std>0 somewhere); EVOLVEpro's
    # std_predictions placeholder is zeros, so UCB/Thompson rely on this.
    land = NKLandscape(8, 2, K=3, seed=2)
    model, _pool, X_pool = _fit_rf_on_nk(land)
    mean, std = rf_mean_std(model, X_pool)
    assert mean.shape == std.shape == (len(X_pool),)
    assert float(std.max()) > 0.0  # genuine tree disagreement
    sample = rf_thompson_sample(model, X_pool, _rng(1))
    assert sample.shape == (len(X_pool),)
    # each sampled value must equal some tree's prediction at that point
    per_tree = acquisition.rf_per_tree_predictions(model, X_pool)
    assert np.all([sample[i] in set(per_tree[:, i]) for i in range(len(sample))])


def test_embdiv_spreads_in_feature_space():
    # 4 points on a line; maximin from anchor at 0 should pick the far end first.
    feats = np.array([[0.0], [1.0], [2.0], [9.0]])
    anchor = np.array([[0.0]])
    mean = np.array([0.0, 0.0, 0.0, 0.0])
    idx = select_indices(
        "embdiv", mean=mean, features=feats, anchor_features=anchor, n=1, rng=_rng()
    )
    assert idx == [3]  # farthest from the anchor


def test_sigma_kuro_schedule_decreases_over_rounds():
    # The deployed KURO uses the REAL sigma_adaptive_params schedule: exploration
    # (entropy_weight, pool K) must DECREASE as cumulative revealed data grows.
    from kuma_core.kuro.evolvepro import sigma_adaptive_params

    k1, ew1 = sigma_adaptive_params(1, 96)   # cumulative 96  -> rho 0.40
    k2, ew2 = sigma_adaptive_params(5, 96)   # cumulative 480 -> rho 0.70
    assert ew1 == 0.30 and ew2 == 0.15
    assert k1 > k2  # exploration pool shrinks


def test_position_entropy_varies_per_candidate():
    # Regression guard: the sigma_kuro entropy bonus must VARY per candidate (else
    # entropy_weight is inert). Candidates carrying minority alleles at uncertain
    # sites must score higher than the majority-allele candidates.
    from al.acquisition import _position_entropy

    # site 0: allele 1 is rare (1/4); site 1: balanced. The (1, x) candidate carries
    # the rare allele at site 0 and must get a strictly higher bonus.
    positions = [(0, 0), (0, 1), (0, 1), (1, 0)]
    ent = _position_entropy(positions, n_alleles=2)
    assert ent.shape == (4,)
    assert float(ent.max()) > float(ent.min())  # NOT a constant (the no-op bug)
    assert ent[3] == float(ent.max())  # the rare-allele candidate scores highest


def test_sigma_kuro_entropy_weight_can_change_selection():
    # With a non-degenerate pool, raising entropy_weight (early round) vs a near-zero
    # exploration regime should be able to change which candidates sigma_kuro picks,
    # proving the entropy blend is behaviorally active (not inert).
    from al.acquisition import _greedy_maximin

    # 4 candidates, identical pairwise distance to anchor (so diversity is a tie),
    # distinct entropy bonuses -> entropy_weight must break the tie by entropy.
    cand = [0, 1, 2, 3]
    ent = np.array([0.0, 0.1, 0.5, 0.9])
    tiebreak = np.zeros(4)

    def zero_dist(i, j):
        return 1.0  # constant distance -> diversity term identical for all

    pick_explore = _greedy_maximin(
        cand, zero_dist, [], 1, tiebreak, entropy=ent, entropy_weight=0.9
    )
    pick_greedy = _greedy_maximin(cand, zero_dist, [], 1, tiebreak, entropy=ent, entropy_weight=0.0)
    assert pick_explore == [3]  # highest entropy wins when exploration weighted
    assert pick_greedy != pick_explore or len(set(ent)) == 1  # weight changed the pick


def test_sigma_kuro_selects_valid_subset():
    land = NKLandscape(8, 2, K=3, seed=4)
    model, pool, X_pool = _fit_rf_on_nk(land)
    mean, _std = rf_mean_std(model, X_pool)
    idx = select_indices(
        "sigma_kuro", mean=mean, positions=pool, anchor_positions=[], n=5,
        n_alleles=2, evolvepro_round=1, round_size=5, rng=_rng(),
    )
    assert len(idx) == 5
    assert len(set(idx)) == 5
    assert all(0 <= i < len(pool) for i in idx)


def test_mean_verdict_partition_is_exhaustive():
    # WIN
    assert stats.mean_verdict(
        {"median_delta": 0.05, "cliffs_delta": 0.20, "wilcoxon_p": 0.01}
    ) == "WIN"
    # LOSE (directional mirror)
    assert stats.mean_verdict(
        {"median_delta": -0.05, "cliffs_delta": -0.20, "wilcoxon_p": 0.01}
    ) == "LOSE"
    # large-but-nonsignificant -> TIE (the F1b sliver that must be covered)
    assert stats.mean_verdict(
        {"median_delta": 0.05, "cliffs_delta": 0.20, "wilcoxon_p": 0.20}
    ) == "TIE"
    # partial criterion (effect ok, magnitude below bound) -> TIE
    assert stats.mean_verdict(
        {"median_delta": 0.05, "cliffs_delta": 0.05, "wilcoxon_p": 0.01}
    ) == "TIE"


def test_tail_outcome_three_valued():
    assert stats.tail_outcome(-0.3, -0.1) == "TAIL-ADV"   # KURO worst-case higher
    assert stats.tail_outcome(0.1, 0.3) == "TAIL-WORSE"
    assert stats.tail_outcome(-0.1, 0.2) == "TAIL-NULL"


def test_decision_table_is_complete_9_cell_partition():
    means = ("WIN", "TIE", "LOSE")
    tails = ("TAIL-ADV", "TAIL-NULL", "TAIL-WORSE")
    cells = {(m, t): stats.decision_cell(m, t) for m in means for t in tails}
    assert len(cells) == 9  # every combination assigned exactly one verdict
    assert cells[("TIE", "TAIL-ADV")] == "FOR-QUALIFIED"  # the diversity-as-hedge cell
    assert cells[("LOSE", "TAIL-WORSE")] == "AGAINST/REFUTE-STRONG"
    assert cells[("WIN", "TAIL-NULL")] == "FOR-STRONG"


def test_campaign_runs_every_acquisition_arm():
    land = NKLandscape(6, 2, K=2, seed=1)
    for arm in ACQ_ARMS:
        rec = run_campaign_nk(land, arm, n=6, k_rounds=4, seed=0)
        assert rec["arm"] == arm
        assert 0.0 < rec["norm_best"] <= 1.0
        assert rec["regret"] >= 0.0


def test_regime_table_cells_are_valid_verdicts():
    recs = run_rugged_sweep(
        n_sites=6, n_alleles=2, k_values=(0, 2), n=6, k_rounds=4, seeds=range(5), arms=ACQ_ARMS
    )
    table = regime_decision_table(recs)
    assert {row["K"] for row in table} == {0, 2}
    valid = set(stats.DECISION_TABLE.values())
    assert all(row["decision_cell"] in valid for row in table)
    assert all(row["mean_verdict"] in ("WIN", "TIE", "LOSE") for row in table)
