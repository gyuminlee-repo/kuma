"""Tests for al.sweep aggregation + paired comparison logic (synthetic, no compute)."""

from __future__ import annotations

import pandas as pd

from al.sweep import paired_arm_comparison, summarize


def _synthetic_records():
    """3 assays x 4 seeds x {topn, domain_r1only}; multi stratum: topn beats domain."""
    rows = []
    for assay, stratum, base_topn, base_dom in [
        ("M1", "multi", 0.6, 0.3),
        ("M2", "multi", 0.5, 0.2),
        ("S1", "single", 0.4, 0.4),
    ]:
        for seed in range(4):
            rows.append({"assay": assay, "stratum": stratum, "arm": "topn",
                         "seed": seed, "recall@1.0pct": base_topn + 0.01 * seed})
            rows.append({"assay": assay, "stratum": stratum, "arm": "domain_r1only",
                         "seed": seed, "recall@1.0pct": base_dom + 0.01 * seed})
    return pd.DataFrame(rows)


def test_paired_comparison_pairs_by_assay_seed():
    df = _synthetic_records()
    comp = paired_arm_comparison(df[df["stratum"] == "multi"], "domain_r1only", "topn", "recall@1.0pct")
    assert comp["n_pairs"] == 8  # 2 multi assays x 4 seeds
    assert comp["median_delta"] < 0  # domain underperforms topn in multi
    assert comp["cliffs_delta"] < 0


def test_summarize_per_stratum_and_pivotal():
    df = _synthetic_records()
    summ = summarize(df, "recall@1.0pct")
    assert set(summ["strata"]) == {"multi", "single"}
    # single stratum: domain == topn -> median_delta ~ 0
    s = summ["strata"]["single"]["domain_r1only_vs_topn"]
    assert abs(s["median_delta"]) < 1e-9
    # pivotal headline evaluated on the multi stratum
    assert summ["pivotal"]["regime"].startswith("multi-domain")
    assert summ["pivotal"]["benefit"] is False  # domain underperforms here


def test_summarize_no_multi_stratum():
    df = _synthetic_records()
    df = df[df["stratum"] == "single"]
    summ = summarize(df, "recall@1.0pct")
    assert summ["pivotal"]["benefit"] is None
