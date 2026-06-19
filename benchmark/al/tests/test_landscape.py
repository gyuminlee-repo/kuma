"""Tests for al.landscape (NK rugged landscape) + al.rugged_sim AL campaign."""

from __future__ import annotations

import numpy as np

from al.landscape import NKLandscape, hamming, onehot
from al.rugged_sim import ARMS, run_campaign_nk, run_rugged_sweep


def test_nk_deterministic_and_bounds():
    l1 = NKLandscape(5, 4, K=2, seed=7)
    l2 = NKLandscape(5, 4, K=2, seed=7)
    g = (0, 1, 2, 3, 0)
    assert l1.fitness(g) == l2.fitness(g)  # deterministic
    assert 0.0 <= l1.fitness(g) <= 1.0
    gopt, gmax = l1.global_optimum()
    assert l1.fitness(gopt) == gmax
    assert all(l1.fitness(g) <= gmax for g in l1.all_genotypes())


def test_ruggedness_increases_local_optima():
    # K=0 (smooth) should have far fewer local optima than high K (rugged).
    smooth = NKLandscape(6, 4, K=0, seed=3).ruggedness()
    rugged = NKLandscape(6, 4, K=4, seed=3).ruggedness()
    assert rugged["n_local_optima"] > smooth["n_local_optima"]
    assert smooth["n_genotypes"] == 4 ** 6


def test_onehot_hamming():
    assert hamming((0, 1, 2), (0, 2, 2)) == 1
    v = onehot((0, 1), 3)
    assert list(v) == [1, 0, 0, 0, 1, 0]


def test_campaign_returns_valid_record():
    land = NKLandscape(5, 4, K=2, seed=1)
    rec = run_campaign_nk(land, "greedy", n=6, k_rounds=4, seed=0)
    assert rec["best_found"] <= rec["global_max"]
    assert 0 < rec["norm_best"] <= 1.0
    assert isinstance(rec["found_global"], bool)
    assert rec["arm"] == "greedy"


def test_sweep_small():
    recs = run_rugged_sweep(n_sites=4, n_alleles=3, k_values=(0, 2), n=4, k_rounds=3, seeds=range(2))
    # 2 K-values x 2 seeds x 3 arms = 12 records
    assert len(recs) == 12
    assert {r["arm"] for r in recs} == set(ARMS)
    assert all(0 < r["norm_best"] <= 1.0 for r in recs)
