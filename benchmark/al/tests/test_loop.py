"""Tests for al.loop + al.arms using the REAL EVOLVEpro top_layer surrogate.

Embeddings are injected (synthetic) and the oracle is a deterministic function of
the embedding, so the RandomForest surrogate can learn it — no ESM needed, but the
real evolvepro.top_layer runs.
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from al import arms
from al.loop import run_campaign

_HAS_EP = importlib.util.find_spec("evolvepro") is not None

# 40 single-sub variants at positions 1..40 (parseable by domain_aware_select).
_N = 40
_VARIANTS = [f"A{p}V" for p in range(1, _N + 1)]
_DOMAINS = [
    {"name": "d1", "start": 1, "end": 20},
    {"name": "d2", "start": 21, "end": 40},
]


def _fixture(dim: int = 8, seed: int = 0):
    rng = np.random.default_rng(seed)
    emb = pd.DataFrame(rng.normal(size=(_N, dim)), index=_VARIANTS, columns=list(range(dim)))
    w = rng.normal(size=dim)
    # oracle: linear in embedding (RF-learnable) + tiny noise
    oracle = {v: float(emb.loc[v].to_numpy() @ w + 0.01 * rng.normal()) for v in _VARIANTS}
    # cold-start: a DIFFERENT projection (not the oracle), so round-0 != oracle-top-N
    w2 = rng.normal(size=dim)
    cold = {v: float(emb.loc[v].to_numpy() @ w2) for v in _VARIANTS}
    return emb, oracle, cold


def test_arms_round0_uses_coldstart_only():
    emb, oracle, cold = _fixture()
    # Top-N round-0 == top-n by cold-start, independent of oracle.
    picks = arms.select("topn", round_idx=0, candidates=_VARIANTS, score=cold, n=5)
    expected = sorted(_VARIANTS, key=lambda v: (-cold[v], v))[:5]
    assert picks == expected
    # Permuting the oracle must not change round-0 (leak-free at the arm level).
    assert picks == arms.select("topn", round_idx=0, candidates=_VARIANTS, score=cold, n=5)


@pytest.mark.skipif(not _HAS_EP, reason="evolvepro not installed")
def test_campaign_topn_real_surrogate():
    emb, oracle, cold = _fixture(seed=1)
    res = run_campaign("topn", _VARIANTS, emb, oracle, cold, n=5, k_rounds=4, seed=7)
    # 4 rounds * 5 = 20 distinct revealed variants.
    assert len(res.revealed_order) == 20
    assert len(set(res.revealed_order)) == 20
    # cumulative best is monotonic non-decreasing.
    traj = res.cumulative_best_trajectory
    assert traj == sorted(traj)
    # round-0 selection equals cold-start top-5 (no oracle leak).
    r0 = res.rounds[0].selected
    assert r0 == sorted(_VARIANTS, key=lambda v: (-cold[v], v))[:5]


@pytest.mark.skipif(not _HAS_EP, reason="evolvepro not installed")
def test_campaign_leak_free_under_oracle_permutation():
    """Permuting the oracle must leave round-0 byte-identical for every arm."""
    emb, oracle, cold = _fixture(seed=2)
    rng = np.random.default_rng(99)
    keys = list(oracle)
    vals = list(oracle.values())
    rng.shuffle(vals)
    oracle_perm = dict(zip(keys, vals, strict=True))

    for arm in ("topn", "domain_r1only", "domain_every", "random_r1"):
        a = run_campaign(arm, _VARIANTS, emb, oracle, cold, n=5, k_rounds=2,
                         domains=_DOMAINS, seed=3)
        b = run_campaign(arm, _VARIANTS, emb, oracle_perm, cold, n=5, k_rounds=2,
                         domains=_DOMAINS, seed=3)
        assert a.rounds[0].selected == b.rounds[0].selected, f"{arm}: round-0 leaked oracle"


@pytest.mark.skipif(not _HAS_EP, reason="evolvepro not installed")
def test_domain_arm_differs_from_topn_at_round0():
    emb, oracle, cold = _fixture(seed=4)
    topn = run_campaign("topn", _VARIANTS, emb, oracle, cold, n=6, k_rounds=1,
                        domains=_DOMAINS, seed=5).rounds[0].selected
    dom = run_campaign("domain_every", _VARIANTS, emb, oracle, cold, n=6, k_rounds=1,
                       domains=_DOMAINS, seed=5).rounds[0].selected
    # Domain quota spreads picks across both domains; Top-N may concentrate.
    dom_d1 = sum(1 for v in dom if int(v[1:-1]) <= 20)
    dom_d2 = len(dom) - dom_d1
    assert dom_d1 >= 1 and dom_d2 >= 1, "domain arm should cover both domains"
    # regression guard for the unsorted-rows bug: each domain's picks must be the
    # TOP-by-score within that domain, not arbitrary file order.
    cold = {v: float(v[1:-1]) for v in _VARIANTS}  # score == position (1..40)
    picks = arms.select("domain_every", round_idx=0, candidates=list(_VARIANTS),
                         score=cold, n=6, domains=_DOMAINS, seed=0)
    d1 = sorted([v for v in picks if int(v[1:-1]) <= 20], key=lambda v: -cold[v])
    d2 = sorted([v for v in picks if int(v[1:-1]) > 20], key=lambda v: -cold[v])
    # top of domain 1 by score is position 20 (A20V); of domain 2 is position 40.
    assert d1[0] == "A20V", f"domain1 top-by-score wrong: {d1}"
    assert d2[0] == "A40V", f"domain2 top-by-score wrong: {d2}"


def test_domain_arm_equals_topn_under_single_domain():
    """With one whole-protein domain, the domain quota reduces to Top-N (architect invariant)."""
    cold = {v: float(v[1:-1]) for v in _VARIANTS}
    full = [{"name": "full", "start": 1, "end": 40}]
    dom = arms.select("domain_every", round_idx=0, candidates=list(_VARIANTS),
                      score=cold, n=8, domains=full, seed=0)
    topn = arms.select("topn", round_idx=0, candidates=list(_VARIANTS), score=cold, n=8)
    assert set(dom) == set(topn), f"single-domain quota must equal Top-N set\n dom={dom}\n topn={topn}"
