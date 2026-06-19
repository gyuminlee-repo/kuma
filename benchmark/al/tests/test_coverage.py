"""Tests for al.coverage (embedding-space coverage + axis-relevance margin)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from al.coverage import (
    classify_axis_relevance,
    coverage_metrics,
    kcenter_radius,
    variance_spanned,
)


def _pool_df():
    # 2-D pool on a grid so coverage is easy to reason about.
    pts = [(x, y) for x in range(5) for y in range(5)]  # 25 points
    idx = [f"v{i}" for i in range(len(pts))]
    return pd.DataFrame(pts, index=idx, columns=[0, 1]), idx


def test_spread_covers_better_than_clustered():
    df, idx = _pool_df()
    pool = idx
    # spread: 4 corners + center -> low k-center radius, high variance
    spread = ["v0", "v4", "v20", "v24", "v12"]  # (0,0)(0,4)(4,0)(4,4)(2,2)
    # clustered: 5 points in one corner -> high radius, low variance
    clustered = ["v0", "v1", "v5", "v6", "v2"]
    cov_s = coverage_metrics(df, spread, pool)
    cov_c = coverage_metrics(df, clustered, pool)
    assert cov_s["kcenter_radius"] < cov_c["kcenter_radius"]
    assert cov_s["variance_spanned"] > cov_c["variance_spanned"]


def test_axis_relevance_margin():
    df, idx = _pool_df()
    pool = idx
    spread = ["v0", "v4", "v20", "v24", "v12"]
    clustered = ["v0", "v1", "v5", "v6", "v2"]
    dom = coverage_metrics(df, spread, pool)      # "domain" arm = spread
    topn = coverage_metrics(df, clustered, pool)  # "topn" arm = clustered
    rel = classify_axis_relevance(dom, topn)
    assert rel["axis_relevant"] is True
    assert rel["radius_reduction"] >= 0.10
    assert rel["variance_delta"] >= 0.05
    # near-identical selections -> axis-mismatch (no material coverage change)
    same = coverage_metrics(df, spread, pool)
    rel2 = classify_axis_relevance(same, dom)
    assert rel2["axis_relevant"] is False
    assert rel2["label"] == "axis-mismatch"


def test_variance_spanned_bounds():
    df, idx = _pool_df()
    # selecting the whole pool spans 100% of pool variance
    assert variance_spanned(df.to_numpy(float), df.to_numpy(float)) == 1.0
    # a single point spans ~0
    one = df.loc[["v0"]].to_numpy(float)
    assert variance_spanned(one, df.to_numpy(float)) == 0.0
