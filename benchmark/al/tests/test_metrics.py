"""Tests for al.metrics (recall@budget primary metric + secondaries)."""

from __future__ import annotations

from al.metrics import (
    campaign_metrics,
    max_fitness_found,
    recall_auc,
    recall_trajectory,
    rounds_to_recall,
    topx_recall_at_budget,
    true_topx_set,
)

# 20 variants, oracle = value 20..1 (v20 best). Top-10% = top 2 = {v20, v19}.
_ORACLE = {f"v{i}": float(i) for i in range(1, 21)}


def test_true_topx_set():
    assert true_topx_set(_ORACLE, 10.0) == {"v20", "v19"}
    assert true_topx_set(_ORACLE, 5.0) == {"v20"}  # ceil(20*0.05)=1


def test_recall_at_budget_monotone():
    # reveal best first
    order = ["v20", "v1", "v19", "v2"]
    assert topx_recall_at_budget(order, _ORACLE, 10.0, budget=1) == 0.5  # v20 of {v20,v19}
    assert topx_recall_at_budget(order, _ORACLE, 10.0, budget=3) == 1.0  # v20+v19
    # trajectory is non-decreasing and ends at full recall
    traj = recall_trajectory(order, _ORACLE, 10.0)
    assert traj == sorted(traj)
    assert traj[-1] == 1.0


def test_recall_auc_orders_strategies():
    top = ["v20", "v19", "v1", "v2"]   # finds both top hits immediately
    bot = ["v1", "v2", "v20", "v19"]   # finds them last
    assert recall_auc(top, _ORACLE, 10.0) > recall_auc(bot, _ORACLE, 10.0)


def test_max_fitness_and_rounds_to_recall():
    assert max_fitness_found(["v5", "v20", "v1"], _ORACLE) == 20.0
    # per-round: round0 misses, round1 gets both top -> reaches 90% at round 1
    round_revealed = [["v1", "v2"], ["v20", "v19"]]
    assert rounds_to_recall(round_revealed, _ORACLE, 10.0, 0.9) == 1
    # never reached
    assert rounds_to_recall([["v1"], ["v2"]], _ORACLE, 10.0, 0.9) is None


def test_campaign_metrics_bundle():
    order = ["v20", "v19", "v1", "v2"]
    rounds = [["v20", "v19"], ["v1", "v2"]]
    m = campaign_metrics(order, rounds, _ORACLE, x_list=(1.0, 5.0))
    assert m["budget"] == 4
    assert m["max_fitness"] == 20.0
    assert m["recall@5.0pct"] == 1.0  # v20 found
    assert 0.0 <= m["recall_auc@1.0pct"] <= 1.0
    assert m["rounds_to_90pct_recall@5.0pct"] == 0
