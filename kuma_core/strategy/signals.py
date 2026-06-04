"""Combinatorial switching signal computations.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.1
Phase 6 Task 6.1 -- 5/12 scope: signal calculation only.
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
# Signal T1 -- Combinatorial throughput
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
# Signal T2 -- Baseline improvement plateau
# ---------------------------------------------------------------------------

def compute_T2_threshold(
    sigma_assay: float,
    r: int,
    n_designed: Optional[int] = None,
    method: str = "order_statistic",
) -> float:
    """Compute the T2 plateau threshold.

    method="order_statistic" and n_designed given:
        threshold = sigma_assay * sqrt(2 * ln(n_designed) / r)
        Best-of-N order-statistic approximation. n_designed is clamped to >= 2.
        Reference: review §3.2 (best-of-N null for sequential maxima).

    method="legacy" or n_designed is None:
        threshold = 1.96 * sigma_assay * sqrt(2 / r)
        Two-replicate-average 95% MDE (backward-compatible default).

    Args:
        sigma_assay: Assay noise (from compute_sigma_assay).
        r: Number of replicates per well.
        n_designed: Number of variants designed per round (for order_statistic).
        method: "order_statistic" | "legacy".

    Returns:
        Float threshold value.
    """
    if method == "order_statistic" and n_designed is not None:
        n = max(n_designed, 2)
        return sigma_assay * math.sqrt(2 * math.log(n) / r)
    # Legacy / fallback
    return 1.96 * sigma_assay * math.sqrt(2 / r)


def compute_T2(
    delta_best_ema: float,
    sigma_assay: Optional[float],
    r: int,
    n_designed: Optional[int] = None,
    method: str = "order_statistic",
) -> Optional[bool]:
    """Return True when the EMA of best-baseline delta is within noise bounds.

    Plateau criterion: delta < threshold (see compute_T2_threshold).

    When method="order_statistic" and n_designed is provided, uses the
    best-of-N order-statistic approximation (review §3.2). When
    n_designed is None or method="legacy", falls back to the 95% MDE
    two-replicate formulation for backward compatibility.

    Returns None if sigma_assay is None (WT replicates < 4, spec §12-A.8).

    Args:
        delta_best_ema: EMA_2(best_n - best_{n-1}), the smoothed improvement.
        sigma_assay: Assay noise (from compute_sigma_assay), or None.
        r: Number of replicates per well.
        n_designed: Number of variants designed per round (order_statistic only).
        method: "order_statistic" | "legacy".

    Returns:
        True if improvement is within noise (plateau detected), False otherwise,
        or None if sigma_assay is None (insufficient WT replicates).
    """
    if sigma_assay is None:
        return None
    threshold = compute_T2_threshold(sigma_assay, r, n_designed=n_designed, method=method)
    return delta_best_ema < threshold


# ---------------------------------------------------------------------------
# Signal T3 -- Hit rate trend
# ---------------------------------------------------------------------------

def compute_T3(hit_rates: list[float], window: int = 2) -> Optional[bool]:
    """Return True when the hit rate trend (most recent window) is flat or declining.

    Spec (§12-A.1 L617): computes slope over the most recent *window* rounds.
    Returns None if fewer than 2 total data points are provided
    (NA = "insufficient data", distinct from False = "signal absent").

    Args:
        hit_rates: Sequence of per-round hit rates (n_positive / n_designed).
        window: Number of most recent rounds to use for slope calculation (default 2).

    Returns:
        True if slope <= 0 (convergence / saturation signal),
        False if slope > 0,
        None if fewer than 2 data points.
    """
    if len(hit_rates) < 2:
        return None
    recent = hit_rates[-window:]
    if len(recent) < 2:
        return None
    x = list(range(len(recent)))
    slope, _ = statistics.linear_regression(x, recent)
    return slope <= 0


def compute_T3_magnitude(hit_rates: list[float], window: int = 2) -> Optional[float]:
    """Return the slope of the most recent window of hit rates (for audit logging).

    Args:
        hit_rates: Sequence of per-round hit rates.
        window: Number of most recent rounds (default 2).

    Returns:
        Float slope value, or None if fewer than 2 data points.
    """
    if len(hit_rates) < 2:
        return None
    recent = hit_rates[-window:]
    if len(recent) < 2:
        return None
    x = list(range(len(recent)))
    slope, _ = statistics.linear_regression(x, recent)
    return slope


# ---------------------------------------------------------------------------
# Signal T4 -- Position convergence (Jaccard)
# ---------------------------------------------------------------------------

def compute_T4(
    top_k_positions_n: set[int],
    top_k_positions_n1: set[int],
    jaccard_threshold: float = 0.5,
) -> Optional[bool]:
    """Return True when top-K mutation positions converge across rounds.

    Jaccard = |intersection| / |union|.
    Returns None if both sets are empty (insufficient data, not "no convergence").

    Args:
        top_k_positions_n: Residue positions in top-K variants of round n.
        top_k_positions_n1: Residue positions in top-K variants of round n-1.
        jaccard_threshold: Minimum Jaccard similarity to flag convergence.

    Returns:
        True if Jaccard >= jaccard_threshold,
        False if Jaccard < jaccard_threshold,
        None if union is empty (both sets empty).
    """
    union = top_k_positions_n | top_k_positions_n1
    if not union:
        return None
    intersection = top_k_positions_n & top_k_positions_n1
    jaccard = len(intersection) / len(union)
    return jaccard >= jaccard_threshold


# ---------------------------------------------------------------------------
# Signal T_active -- Active site mutation fraction
# ---------------------------------------------------------------------------

def compute_T_active(
    top_k_positions: list[int],
    active_residues: list[int],
    threshold: float = 0.4,
) -> Optional[bool]:
    """Return True when a sufficient fraction of top-K positions are active-site.

    Fraction = |top_k ∩ active| / |top_k|.

    Rationale: Active-site spatial proximity (within 6 A of catalytic centre)
    raises the probability of pairwise interactions, increasing the information
    value of all-pairwise measurements regardless of sign (synergistic or
    antagonistic). This signal does not predict additive stacking success.
    Sign epistasis cannot be predicted from single-mutant data alone, so
    measuring all pairs is justified. T_active is a tool-adoption signal based
    on observed clustering; it does not carry a direct prior-literature anchor
    predicting combinatorial superiority.

    References:
        Lind et al. 2024, PNAS 121(28):e2400439121
            (10.1073/pnas.2400439121) -- sign epistasis ~31-35% in active-site
            landscape; combinatorial characterisation navigates it.
        Wu et al. 2019, PNAS 116(18):8852-8857
            (10.1073/pnas.1901979116) -- a priori site selection by structural
            knowledge for epistatic site pairing.

    Returns None if top_k_positions or active_residues is empty
    (insufficient data, distinct from False = "no active-site signal").

    Args:
        top_k_positions: Residue positions of the current top-K mutations.
        active_residues: Known active-site residues (e.g. within 6 A of catalytic
            center).
        threshold: Minimum fraction for combinatorial value signal.

    Returns:
        True if active-site fraction >= threshold,
        False if fraction < threshold,
        None if top_k_positions or active_residues is empty.
    """
    if not top_k_positions or not active_residues:
        return None
    active_set = set(active_residues)
    fraction = sum(1 for pos in top_k_positions if pos in active_set) / len(top_k_positions)
    return fraction >= threshold


# ---------------------------------------------------------------------------
# Signal T_unused -- Unused beneficial count
# ---------------------------------------------------------------------------

def compute_T_unused(unused_beneficial_count: int, M_min: int = 5) -> bool:
    """Return True when enough beneficial mutations were left unexplored.

    Baseline-walking uses only the single best mutation as the next baseline,
    leaving information about other beneficial mutations epistatic interactions
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
# Signal T_model -- Surrogate single-exhaustion (EVOLVEpro y_pred)
# ---------------------------------------------------------------------------

def compute_T_model(
    predicted_top_untested_gain: float,
    sigma_assay: Optional[float],
    r: int,
    z_model: float = 1.96,
) -> Optional[bool]:
    """Return True when surrogate predicts no untested single exceeds assay noise.

    Predictive twin of T2: T2 checks measured improvement plateau; T_model checks
    whether the surrogate (EVOLVEpro y_pred) predicts any remaining untested single
    can exceed noise. Signals single-space exhaustion directly from surrogate output.

    Wiring (classify() v0.3+): belongs in the saturation clause alongside T2/T3/T4,
    NOT in combinatorial_value.
        saturation = (T2 or T3 or T4 or T_model) and prev_sat

    Reference: Jiang et al. 2024, Science, EVOLVEpro (10.1126/science.adr6006).

    Returns None if sigma_assay is None (mirrors T2 behaviour, spec §12-A.8).

    Args:
        predicted_top_untested_gain: max(y_pred over untested singles) minus
            current_best_baseline.
        sigma_assay: Assay noise, or None if WT replicates < 4.
        r: Number of replicates per well.
        z_model: Z-score multiplier (default 1.96).

    Returns:
        True if predicted gain < noise threshold (single space exhausted),
        False otherwise,
        None if sigma_assay is None.
    """
    if sigma_assay is None:
        return None
    threshold = z_model * sigma_assay * math.sqrt(2 / r)
    return predicted_top_untested_gain < threshold


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


# ---------------------------------------------------------------------------
# sigma_assay confidence interval (chi-square via Wilson-Hilferty)
# ---------------------------------------------------------------------------

def compute_sigma_assay_ci(
    wt_values: list[float],
    confidence: float = 0.95,
    min_replicates: int = 4,
) -> Optional[tuple[float, float]]:
    """Return chi-square CI for sigma_assay using Wilson-Hilferty approximation.

    Uses the Wilson-Hilferty normal approximation to chi-square quantiles
    (stdlib statistics.NormalDist only -- no scipy/numpy).

    NOTE: Wilson-Hilferty is an approximation. For df=3 (n=4), the upper bound
    may be ~9% wider than the exact chi-square value.

    Formula::

        s   = sample stdev
        df  = n - 1
        chi2_q(p, df) = df * (1 - 2/(9*df) + z_p * sqrt(2/(9*df)))^3
            where z_p = NormalDist().inv_cdf(p)
        lo  = s * sqrt(df / chi2_q(1 - alpha/2, df))
        hi  = s * sqrt(df / chi2_q(alpha/2, df))

    Args:
        wt_values: Activity measurements of WT-control wells.
        confidence: Confidence level (default 0.95).
        min_replicates: Minimum replicates required (default 4).

    Returns:
        (lo, hi) tuple, or None if fewer than min_replicates values.
    """
    if len(wt_values) < min_replicates:
        return None
    n = len(wt_values)
    df = n - 1
    s = statistics.stdev(wt_values)
    alpha = 1.0 - confidence
    nd = statistics.NormalDist()

    def chi2_q(p: float, df_: int) -> float:
        z = nd.inv_cdf(p)
        val = df_ * (1 - 2 / (9 * df_) + z * math.sqrt(2 / (9 * df_))) ** 3
        # Clamp to avoid sqrt of negative in extreme tails
        return max(val, 1e-12)

    q_hi = chi2_q(1 - alpha / 2, df)  # upper tail -> lower sigma bound
    q_lo = chi2_q(alpha / 2, df)      # lower tail -> upper sigma bound
    lo = s * math.sqrt(df / q_hi)
    hi = s * math.sqrt(df / q_lo)
    return (lo, hi)


# ---------------------------------------------------------------------------
# Stability building-block filter
# ---------------------------------------------------------------------------

def compute_stability_viable_count(
    beneficial_ddgs: list[float],
    per_single_ddg_max: Optional[float] = None,
) -> int:
    """Count stability-viable building blocks among beneficial singles.

    When per_single_ddg_max is None (default), all beneficial singles are
    considered viable (filter disabled). When set, only singles with
    ddG <= per_single_ddg_max are counted.

    Rationale: Beneficial-activity singles disproportionately destabilise the
    protein. Destabilisation is approximately additive, so combinatorial stacks
    can exhaust the fold budget and yield unfolded/inactive variants. Applying
    this filter to the cumulative_beneficial count fed into T1 ensures that
    fold-incompatible libraries naturally fail T1 without an additional AND gate
    (spec §5.3).

    References:
        Tokuriki & Tawfik 2009, Curr Opin Struct Biol
            (10.1016/j.sbi.2009.08.003)
        Bloom et al. 2006, PNAS
            (10.1073/pnas.0510098103)

    Args:
        beneficial_ddgs: ddG values of beneficial single mutations
            (consistent units with per_single_ddg_max, e.g. kcal/mol).
        per_single_ddg_max: Maximum allowed ddG per single mutation.
            None means filter disabled (returns full count).

    Returns:
        Integer count of stability-viable beneficial singles.
    """
    if per_single_ddg_max is None:
        return len(beneficial_ddgs)
    return sum(1 for ddg in beneficial_ddgs if ddg <= per_single_ddg_max)
