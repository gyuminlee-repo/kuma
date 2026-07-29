"""Tests for al.proxy_rf — faithful proxy must match real EVOLVEpro top_layer (Gate G1(c))."""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from al.proxy_rf import proxy_surrogate, proxy_vs_real_spearman, spearman

_HAS_EP = importlib.util.find_spec("evolvepro") is not None


def _synthetic(n=60, dim=12, revealed=30, seed=0):
    rng = np.random.default_rng(seed)
    variants = [f"A{i}V" for i in range(1, n + 1)]
    emb = pd.DataFrame(rng.normal(size=(n, dim)), index=variants, columns=list(range(dim)))
    w = rng.normal(size=dim)
    acts = emb.to_numpy() @ w + 0.01 * rng.normal(size=n)
    rows = []
    for i, v in enumerate(variants):
        rev = i < revealed
        rows.append({
            "variant": v,
            "activity": float(acts[i]) if rev else float("nan"),
            "iteration": 0.0 if rev else float("nan"),
            "activity_scaled": 0.0 if rev else float("nan"),
            "activity_binary": 0 if rev else float("nan"),
        })
    return emb, pd.DataFrame(rows)


def test_spearman_basics():
    assert spearman([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)


def test_proxy_surrogate_scores_pool():
    emb, lab = _synthetic()
    scores = proxy_surrogate(emb, lab, n_revealed_rounds=1)
    assert len(scores) == 30  # the un-revealed pool
    assert all(np.isfinite(v) for v in scores.values())


@pytest.mark.skipif(not _HAS_EP, reason="evolvepro not installed")
def test_proxy_matches_real_top_layer():
    """Identical RF + random_state => Spearman >= 0.99 (Gate G1(c))."""
    emb, lab = _synthetic(seed=3)
    rho = proxy_vs_real_spearman(emb, lab, n_revealed_rounds=1)
    assert rho >= 0.99, f"proxy<->real Spearman {rho} < 0.99 (plumbing bug)"
