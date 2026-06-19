"""Tests for al.stats (paired comparison, effect size, bootstrap, Holm, headline)."""

from __future__ import annotations

import numpy as np

from al.stats import (
    bootstrap_ci,
    cliffs_delta,
    holm_correction,
    paired_comparison,
    paired_wilcoxon_p,
    pivotal_headline,
)


def test_cliffs_delta_extremes():
    assert cliffs_delta([3, 4, 5], [0, 1, 2]) == 1.0
    assert cliffs_delta([0, 1, 2], [3, 4, 5]) == -1.0
    assert abs(cliffs_delta([1, 2, 3], [1, 2, 3])) == 0.0


def test_wilcoxon_and_bootstrap():
    # consistent positive deltas -> small p; CI strictly above 0
    deltas = [0.2, 0.3, 0.25, 0.4, 0.15, 0.35, 0.22, 0.28]
    assert paired_wilcoxon_p(deltas) < 0.05
    lo, hi = bootstrap_ci(deltas, seed=1)
    assert lo > 0
    # all-zero deltas -> p == 1.0
    assert paired_wilcoxon_p([0, 0, 0]) == 1.0


def test_paired_comparison_bundle():
    a = [0.8, 0.7, 0.9, 0.85, 0.75]
    b = [0.5, 0.55, 0.6, 0.5, 0.58]
    c = paired_comparison(a, b, seed=2)
    assert c["n_pairs"] == 5
    assert c["median_delta"] > 0
    assert c["cliffs_delta"] > 0
    assert c["bootstrap_ci_median"][0] <= c["median_delta"] <= c["bootstrap_ci_median"][1]


def test_holm_monotonic():
    adj = holm_correction({"s1": 0.01, "s2": 0.04, "s3": 0.5})
    # Holm: sorted 0.01,0.04,0.5 with m=3 -> 0.03, 0.08, 0.5 (monotone non-decreasing)
    assert adj["s1"] <= adj["s2"] <= adj["s3"]
    assert adj["s1"] == np.float64(0.03) or abs(adj["s1"] - 0.03) < 1e-9


def test_pivotal_headline_rule():
    # benefit: median>0, p<0.05, |delta|>=0.2
    benefit = pivotal_headline(
        {"median_delta": 0.1, "wilcoxon_p": 0.01, "cliffs_delta": 0.3}
    )
    assert benefit["benefit"] is True
    # fails effect-size gate
    weak = pivotal_headline(
        {"median_delta": 0.1, "wilcoxon_p": 0.01, "cliffs_delta": 0.1}
    )
    assert weak["benefit"] is False
    # fails significance gate
    ns = pivotal_headline(
        {"median_delta": 0.1, "wilcoxon_p": 0.2, "cliffs_delta": 0.3}
    )
    assert ns["benefit"] is False
