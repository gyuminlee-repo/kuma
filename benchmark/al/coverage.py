"""Embedding-space coverage diagnostic (plan F2 / Gate G1(b)).

The domain quota acts on the SEQUENCE-POSITION axis, but the EVOLVEpro RF
generalizes over MEAN-POOLED ESM-2 embeddings. So a null/negative fitness result
is only interpretable WITH evidence about whether domain diversification actually
moved coverage in embedding space:

- "axis-relevant null"  : domain arm materially increased embedding-space coverage
  vs Top-N (by the pre-registered margin) yet found no extra fitness -> diversity
  genuinely does not help here.
- "axis-mismatch"        : domain arm's embedding coverage ~ Top-N -> the positional
  quota barely changed the RF's input distribution, so the test is uninformative
  about diversity (we diversified along the wrong axis).

Metrics on the 480-dim mean-pooled space (selected set S vs full pool P):
- ``kcenter_radius``   : max over P of min distance to S (smaller = better covered).
- ``mean_nn_distance`` : mean over P of min distance to S.
- ``variance_spanned`` : trace(cov(S)) / trace(cov(P)) — fraction of pool total
  variance the selected set spreads over.

Pre-registered axis-relevance margin (frozen at pilot end, NOT tuned post-hoc):
  domain arm is "axis-relevant" iff its k-center radius is >= 10% SMALLER than
  Top-N's AND its variance_spanned is >= 0.05 LARGER than Top-N's, at matched budget.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

# Pre-registered margins (Gate G1(b)). Freeze after pilot validation; do not tune.
KCENTER_RADIUS_REDUCTION_MIN = 0.10  # domain radius <= 0.90 * topn radius
VARIANCE_SPANNED_DELTA_MIN = 0.05    # domain variance_spanned >= topn + 0.05


def _emb(df: pd.DataFrame, variants: Sequence[str]) -> np.ndarray:
    return df.loc[list(variants)].to_numpy(dtype=np.float64)


def kcenter_radius(selected: np.ndarray, pool: np.ndarray) -> float:
    """max_{p in pool} min_{s in selected} ||p - s||  (the k-center objective)."""
    if selected.size == 0 or pool.size == 0:
        return float("inf")
    # pairwise distances pool x selected, take min over selected, max over pool
    d = np.linalg.norm(pool[:, None, :] - selected[None, :, :], axis=2)
    return float(d.min(axis=1).max())


def mean_nn_distance(selected: np.ndarray, pool: np.ndarray) -> float:
    if selected.size == 0 or pool.size == 0:
        return float("inf")
    d = np.linalg.norm(pool[:, None, :] - selected[None, :, :], axis=2)
    return float(d.min(axis=1).mean())


def variance_spanned(selected: np.ndarray, pool: np.ndarray) -> float:
    """trace(cov(selected)) / trace(cov(pool)); fraction of pool spread covered."""
    if selected.shape[0] < 2 or pool.shape[0] < 2:
        return 0.0
    tr_pool = float(np.var(pool, axis=0, ddof=1).sum())
    if tr_pool <= 0:
        return 0.0
    tr_sel = float(np.var(selected, axis=0, ddof=1).sum())
    return tr_sel / tr_pool


def coverage_metrics(
    embeddings_df: pd.DataFrame, selected_variants: Sequence[str], pool_variants: Sequence[str]
) -> dict:
    """Coverage of `selected` against the full `pool` in embedding space."""
    sel = _emb(embeddings_df, selected_variants)
    pool = _emb(embeddings_df, pool_variants)
    return {
        "kcenter_radius": kcenter_radius(sel, pool),
        "mean_nn_distance": mean_nn_distance(sel, pool),
        "variance_spanned": variance_spanned(sel, pool),
        "n_selected": len(selected_variants),
        "n_pool": len(pool_variants),
    }


def classify_axis_relevance(domain_cov: dict, topn_cov: dict) -> dict:
    """Apply the pre-registered margin to decide axis-relevant vs axis-mismatch.

    Returns {radius_reduction, variance_delta, axis_relevant: bool, label}.
    """
    tr = topn_cov["kcenter_radius"]
    radius_reduction = (tr - domain_cov["kcenter_radius"]) / tr if tr > 0 else 0.0
    variance_delta = domain_cov["variance_spanned"] - topn_cov["variance_spanned"]
    axis_relevant = (
        radius_reduction >= KCENTER_RADIUS_REDUCTION_MIN
        and variance_delta >= VARIANCE_SPANNED_DELTA_MIN
    )
    return {
        "radius_reduction": radius_reduction,
        "variance_delta": variance_delta,
        "axis_relevant": bool(axis_relevant),
        "label": "axis-relevant" if axis_relevant else "axis-mismatch",
    }
