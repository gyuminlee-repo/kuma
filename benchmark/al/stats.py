"""Paired statistics for arm comparison (plan Phase 2 stats).

Track-1 compares arms PAIRED across (assay, seed): for a metric (e.g.
recall@1%@budget), each pairing yields delta = metric(arm_a) - metric(arm_b).
We summarize the distribution of deltas with:

- median paired difference,
- paired Wilcoxon signed-rank p-value (scipy),
- Cliff's delta effect size,
- bootstrap CI of the median paired difference,

and apply Holm-Bonferroni correction across strata. Ported in spirit from
foldcrit benchmark.compare_regret (paired test + effect size + a_wins flag).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def cliffs_delta(a: Sequence[float], b: Sequence[float]) -> float:
    """Cliff's delta in [-1, 1]: P(a>b) - P(a<b). Positive => a tends to exceed b.

    This is an UNPAIRED stochastic-dominance effect size (all-pairs), used here as a
    magnitude gate ALONGSIDE the paired location tests (median paired delta + paired
    Wilcoxon). The pairing lives in those location statistics; Cliff's delta
    intentionally measures between-arm dominance over the full seed distributions.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.size == 0 or b.size == 0:
        return 0.0
    gt = np.sum(a[:, None] > b[None, :])
    lt = np.sum(a[:, None] < b[None, :])
    return float((gt - lt) / (a.size * b.size))


def bootstrap_ci(
    deltas: Sequence[float], stat=np.median, n_boot: int = 10000, ci: float = 0.95, seed: int = 0
) -> tuple[float, float]:
    """Percentile bootstrap CI for `stat` of the paired deltas."""
    d = np.asarray(deltas, dtype=float)
    if d.size == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        boots[i] = stat(rng.choice(d, size=d.size, replace=True))
    lo = float(np.percentile(boots, (1 - ci) / 2 * 100))
    hi = float(np.percentile(boots, (1 + ci) / 2 * 100))
    return (lo, hi)


def paired_wilcoxon_p(deltas: Sequence[float]) -> float:
    """Two-sided paired Wilcoxon signed-rank p-value on the deltas (vs 0)."""
    d = np.asarray(deltas, dtype=float)
    d = d[~np.isnan(d)]
    if d.size == 0 or np.allclose(d, 0):
        return 1.0
    from scipy.stats import wilcoxon

    try:
        return float(wilcoxon(d, zero_method="wilcox", alternative="two-sided").pvalue)
    except ValueError:
        # all-zero differences after dropping zeros, etc.
        return 1.0


def paired_comparison(
    metric_a: Sequence[float], metric_b: Sequence[float], *, seed: int = 0
) -> dict:
    """Paired comparison of arm A vs arm B on one metric across pairings.

    `metric_a[i]` and `metric_b[i]` are the same (assay, seed) pairing.
    """
    a = np.asarray(metric_a, dtype=float)
    b = np.asarray(metric_b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("paired metric arrays must have equal length")
    deltas = a - b
    lo, hi = bootstrap_ci(deltas, seed=seed)
    return {
        "n_pairs": int(deltas.size),
        "median_delta": float(np.median(deltas)) if deltas.size else float("nan"),
        "mean_delta": float(np.mean(deltas)) if deltas.size else float("nan"),
        "wilcoxon_p": paired_wilcoxon_p(deltas),
        "cliffs_delta": cliffs_delta(a, b),
        "bootstrap_ci_median": (lo, hi),
    }


def holm_correction(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values, keyed the same as the input."""
    items = sorted(pvalues.items(), key=lambda kv: kv[1])
    m = len(items)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (key, p) in enumerate(items):
        adj = min(1.0, (m - rank) * p)
        running = max(running, adj)  # enforce monotonicity
        adjusted[key] = running
    return adjusted


def pivotal_headline(
    comparison: dict, *, median_delta_min: float = 0.0, p_max: float = 0.05, cliffs_min: float = 0.2
) -> dict:
    """Apply the single pivotal headline rule to a paired comparison (FOR direction).

    Benefit declared iff median_delta > median_delta_min AND wilcoxon (Holm) p <=
    p_max AND Cliff's delta >= +cliffs_min (DIRECTIONAL, signed — closes plan F4;
    a negative effect is never a FOR-benefit). Caller must pass a Holm-adjusted p in
    ``comparison['wilcoxon_p']`` for the headline stratum.
    """
    benefit = (
        comparison["median_delta"] > median_delta_min
        and comparison["wilcoxon_p"] <= p_max
        and comparison["cliffs_delta"] >= cliffs_min
    )
    return {
        "benefit": bool(benefit),
        "verdict": "domain benefit" if benefit else "no/again context-dependent benefit",
        "median_delta": comparison["median_delta"],
        "p": comparison["wilcoxon_p"],
        "cliffs_delta": comparison["cliffs_delta"],
    }


# ---------------------------------------------------------------------------
# Pre-registered decision table (plan F1/F1a/F1b/F4) — complete 9-cell partition
# ---------------------------------------------------------------------------
# MEAN verdict (WIN/TIE/LOSE) over the primary metric, paired arm_a vs arm_b, with
# DIRECTIONAL signed bounds; TIE := NOT WIN AND NOT LOSE (pure complement, F1b).
# TAIL verdict (ADV/NULL/WORSE) from the CVaR bootstrap CI of (arm_b - arm_a) i.e.
# greedy-minus-KURO, so a KURO-favoring tail = CI strictly above 0.

# Pre-registered thresholds (plan §"Pre-registered DECISION thresholds").
MEDIAN_DELTA_MIN = 0.03
CLIFFS_MIN = 0.15
P_MAX = 0.05


def mean_verdict(
    comparison: dict,
    *,
    median_delta_min: float = MEDIAN_DELTA_MIN,
    cliffs_min: float = CLIFFS_MIN,
    p_max: float = P_MAX,
) -> str:
    """WIN / TIE / LOSE for arm_a vs arm_b on the primary metric (F1b partition).

    WIN  := median_delta >= +median_delta_min AND cliffs_delta >= +cliffs_min AND p <= p_max
    LOSE := median_delta <= -median_delta_min AND cliffs_delta <= -cliffs_min AND p <= p_max
    TIE  := NOT WIN AND NOT LOSE (covers large-but-nonsignificant / partial-criterion)
    Caller must pass a Holm-adjusted p in ``comparison['wilcoxon_p']``.
    """
    md = comparison["median_delta"]
    cd = comparison["cliffs_delta"]
    p = comparison["wilcoxon_p"]
    win = md >= median_delta_min and cd >= cliffs_min and p <= p_max
    lose = md <= -median_delta_min and cd <= -cliffs_min and p <= p_max
    if win and lose:  # impossible (opposite signs) but guard explicitly
        return "TIE"
    if win:
        return "WIN"
    if lose:
        return "LOSE"
    return "TIE"


def tail_outcome(ci_lo: float, ci_hi: float) -> str:
    """Three-valued tail verdict from the CVaR bootstrap CI of (arm_b - arm_a).

    The CI is on greedy-minus-KURO CVaR (Top-N minus KURO), so KURO has a tail
    advantage when KURO's worst-case is HIGHER, i.e. (Top-N - KURO) CI is strictly
    BELOW 0. Convention: pass ``ci`` of (arm_b_cvar - arm_a_cvar) where arm_a=KURO.
      TAIL-ADV   := CI excludes 0 in KURO favor (hi < 0  ->  KURO worst-case higher)
      TAIL-WORSE := CI excludes 0 against KURO (lo > 0)
      TAIL-NULL  := CI includes 0
    """
    if ci_hi < 0:
        return "TAIL-ADV"
    if ci_lo > 0:
        return "TAIL-WORSE"
    return "TAIL-NULL"


# Authoritative 9-cell partition (plan F1a). Keys: (MEAN, TAIL).
DECISION_TABLE = {
    ("WIN", "TAIL-ADV"): "FOR-STRONG",
    ("WIN", "TAIL-NULL"): "FOR-STRONG",
    ("WIN", "TAIL-WORSE"): "MIXED",
    ("TIE", "TAIL-ADV"): "FOR-QUALIFIED",
    ("TIE", "TAIL-NULL"): "INCONCLUSIVE",
    ("TIE", "TAIL-WORSE"): "AGAINST",
    ("LOSE", "TAIL-ADV"): "MIXED",
    ("LOSE", "TAIL-NULL"): "AGAINST/REFUTE",
    ("LOSE", "TAIL-WORSE"): "AGAINST/REFUTE-STRONG",
}


def decision_cell(mean: str, tail: str) -> str:
    """Map a (MEAN, TAIL) outcome to its pre-registered verdict cell (F1a)."""
    try:
        return DECISION_TABLE[(mean, tail)]
    except KeyError as exc:
        raise ValueError(f"undefined decision cell: mean={mean!r} tail={tail!r}") from exc