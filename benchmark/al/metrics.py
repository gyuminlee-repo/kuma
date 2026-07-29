"""Evaluation metrics for an AL campaign.

Two metric families live here:

DE-outcome metrics (HEADLINE — plan Phase A/B). The pre-registered primary metric
is ``norm_best`` (normalized best-fitness-found@final, computed per campaign in
``rugged_sim``); the SECONDARY confirmatory tail is ``cvar``@20% with
``catastrophe_rate``/``escape_rate``. These replace recall@budget as the headline
because the benchmark measures a directed-evolution OUTCOME, not retrieval recall.

Recall@budget metrics (LEGACY/SECONDARY — retained for the single-mutant Track-1
oracle). ``topx_recall_at_budget`` / ``recall_auc`` measure how fast the true
top-X% set is revealed. These are exploitation/retrieval metrics and are NOT the
headline for the rugged/cold-start regime the KURO design targets; they remain for
backward compatibility and single-mutant cross-checks only.

All recall figures are "of the true top-X%", directly comparable across arms at a
matched budget; all DE-outcome figures are normalized within the candidate pool.
"""

from __future__ import annotations

import math

import numpy as np
from collections.abc import Mapping, Sequence


def true_topx_set(oracle: Mapping[str, float], x_percent: float) -> set[str]:
    """Return the set of variants in the true top-X% by oracle value (ties included)."""
    if not 0 < x_percent <= 100:
        raise ValueError("x_percent must be in (0, 100]")
    n = len(oracle)
    k = max(1, math.ceil(n * x_percent / 100.0))
    ordered = sorted(oracle, key=lambda v: (-oracle[v], v))
    cutoff = oracle[ordered[k - 1]]
    # include ties at the cutoff value
    return {v for v in oracle if oracle[v] >= cutoff}


def topx_recall_at_budget(
    revealed_order: Sequence[str],
    oracle: Mapping[str, float],
    x_percent: float,
    budget: int,
) -> float:
    """Fraction of the true top-X% set revealed within the first `budget` picks."""
    top = true_topx_set(oracle, x_percent)
    if not top:
        return 0.0
    seen = set(revealed_order[:budget])
    return len(seen & top) / len(top)


def recall_trajectory(
    revealed_order: Sequence[str], oracle: Mapping[str, float], x_percent: float
) -> list[float]:
    """Recall of the true top-X% after each cumulative pick (length == len(revealed))."""
    top = true_topx_set(oracle, x_percent)
    if not top:
        return [0.0] * len(revealed_order)
    traj = []
    seen_hits = 0
    seen: set[str] = set()
    for v in revealed_order:
        if v not in seen:
            seen.add(v)
            if v in top:
                seen_hits += 1
        traj.append(seen_hits / len(top))
    return traj


def recall_auc(
    revealed_order: Sequence[str], oracle: Mapping[str, float], x_percent: float
) -> float:
    """Normalized area under the recall-vs-budget curve (0..1; higher = faster recall)."""
    traj = recall_trajectory(revealed_order, oracle, x_percent)
    if not traj:
        return 0.0
    return sum(traj) / len(traj)


def max_fitness_found(
    revealed_order: Sequence[str], oracle: Mapping[str, float], budget: int | None = None
) -> float:
    picks = revealed_order if budget is None else revealed_order[:budget]
    return max((oracle[v] for v in picks), default=float("-inf"))


def rounds_to_recall(
    round_revealed: Sequence[Sequence[str]],
    oracle: Mapping[str, float],
    x_percent: float,
    target_fraction: float = 0.9,
) -> int | None:
    """First round index (0-based) whose cumulative recall >= target_fraction of 1.0.

    `round_revealed` is the list of per-round selected variant lists. Returns None
    if the target is never reached.
    """
    top = true_topx_set(oracle, x_percent)
    if not top:
        return None
    seen: set[str] = set()
    for r, picks in enumerate(round_revealed):
        seen.update(picks)
        if len(seen & top) / len(top) >= target_fraction:
            return r
    return None


def campaign_metrics(
    revealed_order: Sequence[str],
    round_revealed: Sequence[Sequence[str]],
    oracle: Mapping[str, float],
    x_list: Sequence[float] = (1.0, 5.0),
) -> dict:
    """Bundle the primary + secondary metrics for one campaign."""
    budget = len(revealed_order)
    out: dict = {"budget": budget, "max_fitness": max_fitness_found(revealed_order, oracle)}
    for x in x_list:
        out[f"recall@{x}pct"] = topx_recall_at_budget(revealed_order, oracle, x, budget)
        out[f"recall_auc@{x}pct"] = recall_auc(revealed_order, oracle, x)
        out[f"rounds_to_90pct_recall@{x}pct"] = rounds_to_recall(round_revealed, oracle, x, 0.9)
    return out

# ---------------------------------------------------------------------------
# DE-outcome metrics (plan headline + asymmetric-risk; replace recall@budget)
# ---------------------------------------------------------------------------
# The plan's headline is a directed-evolution OUTCOME, not retrieval recall:
#   - norm_best@final : normalized best fitness found at the final round (primary)
#   - CVaR@20%        : mean of the worst-20% norm_best across seeds (SECONDARY
#                       confirmatory tail; widened from @10% for bootstrap power)
#   - catastrophe rate: fraction of seeds with norm_best < 0.50
#   - escape rate     : fraction of seeds that found the global optimum
#   - regret          : global_max - best_found (per campaign)


def cvar(values: Sequence[float], q: float = 0.20) -> float:
    """Conditional Value-at-Risk of the LOWER tail: mean of the worst ``q`` fraction.

    Higher norm_best is better, so the risky tail is the LOW values. CVaR@20% is the
    mean of the lowest 20% of values (at least one element). NaN for empty input.
    """
    v = np.sort(np.asarray(list(values), dtype=float))
    if v.size == 0:
        return float("nan")
    k = max(1, int(np.ceil(v.size * q)))
    return float(v[:k].mean())


def catastrophe_rate(values: Sequence[float], threshold: float = 0.50) -> float:
    """Fraction of values strictly below the catastrophe threshold (default 0.50)."""
    v = np.asarray(list(values), dtype=float)
    return float(np.mean(v < threshold)) if v.size else float("nan")


def escape_rate(found_global_flags: Sequence[bool]) -> float:
    """Fraction of campaigns that escaped to the global optimum."""
    f = np.asarray(list(found_global_flags), dtype=bool)
    return float(np.mean(f)) if f.size else float("nan")


def de_outcome_summary(records: Sequence[Mapping], *, q: float = 0.20) -> dict:
    """Aggregate DE-outcome metrics over a set of campaign records (one arm, one K).

    Each record must carry ``norm_best``, ``found_global``, and ``regret``.
    """
    nb = [float(r["norm_best"]) for r in records]
    fg = [bool(r["found_global"]) for r in records]
    rg = [float(r["regret"]) for r in records]
    return {
        "n_seeds": len(nb),
        "mean_norm_best": float(np.mean(nb)) if nb else float("nan"),
        "median_norm_best": float(np.median(nb)) if nb else float("nan"),
        "cvar_norm_best": cvar(nb, q=q),
        "cvar_q": q,
        "catastrophe_rate": catastrophe_rate(nb),
        "escape_rate": escape_rate(fg),
        "mean_regret": float(np.mean(rg)) if rg else float("nan"),
    }
