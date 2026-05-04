"""Combinatorial switching signal computations.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.1
Phase 6 Task 6.1 — 5/12 scope: signal calculation only.
Classifier body (advisory/auto mode, bootstrap) is v0.3+.

Dependencies: math, statistics (stdlib only).
"""

from __future__ import annotations

import math
import statistics
from typing import Optional


# ---------------------------------------------------------------------------
# K_throughput helper
# ---------------------------------------------------------------------------

def compute_K_throughput(C_next: int) -> int:
    """Return the largest K such that C(K, 2) <= C_next.

    K_throughput = floor((1 + sqrt(1 + 8 * C_next)) / 2)

    This satisfies: C(K, 2) = K*(K-1)/2 <= C_next.

    Args:
        C_next: Capacity of the next combinatorial plate (number of wells).

    Returns:
        Maximum K such that all pairwise combinations fit within C_next wells.

    Raises:
        ValueError: If C_next <= 0.
    """
    if C_next <= 0:
        raise ValueError(f"C_next must be a positive integer, got {C_next!r}")
    k = int(math.floor((1 + math.sqrt(1 + 8 * C_next)) / 2))
    # Guard: ensure C(k, 2) <= C_next (floating-point rounding correction)
    while k * (k - 1) // 2 > C_next:
        k -= 1
    return k


# ---------------------------------------------------------------------------
# Signal T1 — Combinatorial throughput
# ---------------------------------------------------------------------------

def compute_T1(cumulative_beneficial: int, K_throughput: int) -> bool:
    """Return True when enough beneficial singles have accumulated.

    Spec: cumulative_beneficial >= K_throughput.
    Sufficient building blocks to fill pairwise combinations in the next plate.

    Args:
        cumulative_beneficial: Total beneficial single mutations found so far.
        K_throughput: Required number of singles (from compute_K_throughput).

    Returns:
        True if the throughput threshold is met.
    """
    return cumulative_beneficial >= K_throughput


# ---------------------------------------------------------------------------
# Signal T2 — Baseline improvement plateau
# ---------------------------------------------------------------------------

def compute_T2(delta_best_ema: float, sigma_assay: float, r: int) -> bool:
    """Return True when the EMA of best-baseline delta is within noise bounds.

    Plateau criterion: delta < 1.96 * sigma_assay * sqrt(2 / r).

    This implements the statistical 95% MDE (minimum detectable effect).
    If delta is below the noise confidence interval, no statistically
    meaningful improvement is occurring.

    Args:
        delta_best_ema: EMA_2(best_n - best_{n-1}), the smoothed improvement.
        sigma_assay: Assay noise (from compute_sigma_assay).
        r: Number of replicates per well.

    Returns:
        True if improvement is within noise (plateau detected).
    """
    threshold = 1.96 * sigma_assay * math.sqrt(2 / r)
    return delta_best_ema < threshold


# ---------------------------------------------------------------------------
# Signal T3 — Hit rate trend
# ---------------------------------------------------------------------------

def compute_T3(hit_rates: list[float]) -> bool:
    """Return True when the hit rate trend is flat or declining.

    Uses linear regression slope over the provided hit rates.
    Fewer than 2 data points returns False (not enough data to call plateau).

    Args:
        hit_rates: Sequence of per-round hit rates (n_positive / n_designed).

    Returns:
        True if slope <= 0 (convergence / saturation signal).
    """
    if len(hit_rates) < 2:
        return False
    x = list(range(len(hit_rates)))
    slope, _ = statistics.linear_regression(x, hit_rates)
    return slope <= 0


# ---------------------------------------------------------------------------
# Signal T4 — Position convergence (Jaccard)
# ---------------------------------------------------------------------------

def compute_T4(
    top_k_positions_n: set[int],
    top_k_positions_n1: set[int],
    jaccard_threshold: float = 0.5,
) -> bool:
    """Return True when top-K mutation positions converge across rounds.

    Jaccard = |intersection| / |union|. Both empty sets yield 0.0 (no signal).

    Args:
        top_k_positions_n: Residue positions in top-K variants of round n.
        top_k_positions_n1: Residue positions in top-K variants of round n-1.
        jaccard_threshold: Minimum Jaccard similarity to flag convergence.

    Returns:
        True if Jaccard >= jaccard_threshold.
    """
    union = top_k_positions_n | top_k_positions_n1
    if not union:
        return False
    intersection = top_k_positions_n & top_k_positions_n1
    jaccard = len(intersection) / len(union)
    return jaccard >= jaccard_threshold


# ---------------------------------------------------------------------------
# Signal T_active — Active site mutation fraction
# ---------------------------------------------------------------------------

def compute_T_active(
    top_k_positions: list[int],
    active_residues: list[int],
    threshold: float = 0.4,
) -> bool:
    """Return True when a sufficient fraction of top-K positions are active-site.

    Fraction = |top_k ∩ active| / |top_k|.

    Spec: Lind et al. 2024, PNAS (sign epistasis at active site).
    Empty top_k_positions or empty active_residues returns False.

    Args:
        top_k_positions: Residue positions of the current top-K mutations.
        active_residues: Known active-site residues (e.g., within 6 Å of catalytic center).
        threshold: Minimum fraction for combinatorial value signal.

    Returns:
        True if active-site fraction >= threshold.
    """
    if not top_k_positions or not active_residues:
        return False
    active_set = set(active_residues)
    fraction = sum(1 for pos in top_k_positions if pos in active_set) / len(top_k_positions)
    return fraction >= threshold


# ---------------------------------------------------------------------------
# Signal T_unused — Unused beneficial count
# ---------------------------------------------------------------------------

def compute_T_unused(unused_beneficial_count: int, M_min: int = 5) -> bool:
    """Return True when enough beneficial mutations were left unexplored.

    Baseline-walking uses only the single best mutation as the next baseline,
    leaving information about other beneficial mutations' epistatic interactions
    uncollected. T_unused signals this opportunity.

    Args:
        unused_beneficial_count: Count of beneficial singles from rounds 1..n
            that were never incorporated into a subsequent baseline.
        M_min: Minimum count to trigger the signal (default 5).

    Returns:
        True if unused_beneficial_count >= M_min.
    """
    return unused_beneficial_count >= M_min


# ---------------------------------------------------------------------------
# sigma_assay estimation
# ---------------------------------------------------------------------------

def compute_sigma_assay(
    wt_values: list[float],
    min_replicates: int = 4,
) -> Optional[float]:
    """Estimate assay noise from wild-type replicate measurements.

    Returns the sample standard deviation of wt_values.
    Returns None if fewer than min_replicates values are provided,
    disabling T2 computation (spec §12-A.8).

    Args:
        wt_values: Activity measurements of WT-control wells.
        min_replicates: Minimum number of replicates required (default 4).

    Returns:
        Sample stdev if len(wt_values) >= min_replicates, else None.
    """
    if len(wt_values) < min_replicates:
        return None
    return statistics.stdev(wt_values)
