"""Combinatorial switching classifier (v0.3 engine).

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.2 / §12-A.2b
Phase 6 Task 6.3 -- classify() body, bootstrap, hysteresis gate.

Dependencies: stdlib only (math, statistics, hashlib, json, dataclasses).
Imports signals.py functions; does NOT rewrite them.

Bootstrap simplifications (documented per §12-A.2b):
- Structural signals T1/T4/T_active/T_model/T_unused are frozen at point values
  (selection/design outputs, not measurement noise).
- Noise-bearing signals T2 and T3 are resampled.
- best_{n-1} baseline is held fixed; only best_n* varies from resampling
  current_round_activities, so delta* = delta_best_ema + (best_n* - max(current_round_activities)).
- sat_prev is frozen (previous_signals not resampled).

Backtest revision (report_final.md, 2026-06-08):
- 전환 동력은 단일소진(T2/T3/T_model) + throughput(T1).
- T4/T_active/T_unused는 informational 신호로 유지되며 결정에서 demote.
- additive-headroom(B)는 약한 필요조건 필터로 권장되나 per-position
  single-effect 데이터 plumbing 필요(현재 RoundState에 없음).
  데이터 확보 시 switch의 weak filter로 추가 예정.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Optional

from kuma_core.strategy.signals import (
    compute_sigma_assay,
    compute_T1,
    compute_T2,
    compute_T3,
    compute_T4,
    compute_T_active,
    compute_T_model,
    compute_T_unused,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Signals:
    """Computed signal snapshot for a single round.

    T1 and T_unused are always bool.
    T2, T3, T4, T_active, T_model may be None (insufficient data).
    """
    T1: bool
    T2: Optional[bool]
    T3: Optional[bool]
    T4: Optional[bool]
    T_active: Optional[bool]
    T_model: Optional[bool]
    T_unused: bool


DecisionLabel = Literal["continue_walking", "switch_combinatorial", "stop", "deferred"]


@dataclass(frozen=True)
class Decision:
    """Classifier output for one round."""
    label: DecisionLabel
    reason: str
    confidence: Optional[float] = None
    bootstrap_distribution: Optional[dict[str, float]] = None


@dataclass
class RoundState:
    """All inputs needed for one classify() call.

    Fields mirror RoundMetrics plus bootstrap raw data.
    round_id is optional; falls back to str(n) for effective_seed.
    """
    n: int
    previous_signals: Optional[Signals]

    # Signal inputs (same meaning as RoundMetrics)
    cumulative_beneficial: int
    K_throughput: int
    delta_best_ema: float
    sigma_assay: Optional[float]
    r: int
    hit_rates: list[float]
    top_k_positions_n: set[int]
    top_k_positions_n1: set[int]
    top_k_positions: list[int]
    active_residues: list[int]
    unused_beneficial_count: int

    # Optional EVOLVEpro surrogate output
    n_designed: Optional[int] = None
    predicted_top_untested_gain: Optional[float] = None

    # Bootstrap raw inputs (absence triggers deferred fail-safe)
    wt_values: Optional[list[float]] = None
    current_round_activities: Optional[list[float]] = None

    # Optional round identifier for effective_seed
    round_id: Optional[str] = None


# ---------------------------------------------------------------------------
# NA-aware helpers
# ---------------------------------------------------------------------------

def any_true(*vals: Optional[bool]) -> bool:
    """Return True if at least one value is True (skipping None).

    Returns False when all values are None.
    None values are excluded; they are NOT coerced to False.
    """
    return any(v is True for v in vals)


def all_na(*vals: Optional[bool]) -> bool:
    """Return True if every value is None."""
    return all(v is None for v in vals)


# ---------------------------------------------------------------------------
# Deterministic seed
# ---------------------------------------------------------------------------

def effective_seed(round_state: RoundState, registered: dict) -> int:
    """Derive a deterministic RNG seed from round identity and thresholds.

    effective_seed = registered["bootstrap_seed"]
                     XOR (int.from_bytes(sha256(round_id + canonical_json(registered))[:8], "big")
                          & 0x7FFFFFFF)

    Uses hashlib.sha256 -- builtin hash() is forbidden (PYTHONHASHSEED
    makes it non-deterministic across processes).

    round_id falls back to str(n) if not set on round_state.
    """
    base_seed = registered.get("bootstrap_seed", 20260504)
    round_id = round_state.round_id if round_state.round_id is not None else str(round_state.n)
    canonical = json.dumps(registered, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256((round_id + canonical).encode()).digest()
    offset = int.from_bytes(digest[:8], "big") & 0x7FFFFFFF
    return base_seed ^ offset


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

def compute_signals(round_state: RoundState, registered: dict) -> Signals:
    """Compute all 7 signals from round_state using registered parameters.

    Calls signals.py functions; does not reimplement them.
    """
    t2_method = registered.get("t2_null_method", "order_statistic")
    t3_window = registered.get("t3_window_rounds", 2)
    jaccard_thr = registered.get("jaccard_threshold", 0.5)
    active_thr = registered.get("active_concentration_threshold", 0.4)
    m_min = registered.get("M_min_unused_beneficials", 5)

    T1 = compute_T1(round_state.cumulative_beneficial, round_state.K_throughput)

    T2 = compute_T2(
        round_state.delta_best_ema,
        round_state.sigma_assay,
        round_state.r,
        n_designed=round_state.n_designed,
        method=t2_method,
    )

    T3 = compute_T3(round_state.hit_rates, window=t3_window)

    T4 = compute_T4(
        round_state.top_k_positions_n,
        round_state.top_k_positions_n1,
        jaccard_threshold=jaccard_thr,
    )

    T_active = compute_T_active(
        round_state.top_k_positions,
        round_state.active_residues,
        threshold=active_thr,
    )

    if round_state.predicted_top_untested_gain is not None:
        T_model = compute_T_model(
            round_state.predicted_top_untested_gain,
            round_state.sigma_assay,
            round_state.r,
        )
    else:
        T_model = None

    T_unused = compute_T_unused(
        round_state.unused_beneficial_count,
        M_min=m_min,
    )

    return Signals(
        T1=T1,
        T2=T2,
        T3=T3,
        T4=T4,
        T_active=T_active,
        T_model=T_model,
        T_unused=T_unused,
    )


# ---------------------------------------------------------------------------
# Decision core (no confidence gate, no recursion)
# ---------------------------------------------------------------------------

def _decide_core(
    s: Signals, p: Optional[Signals]
) -> tuple[DecisionLabel, str]:
    """Apply the backtest-revised decision tree without bootstrap confidence gating.

    Returns (label, reason).

    Callers: _decide_core is pure; classify() wraps the confidence gate for
    switch_combinatorial and stop branches.

    Backtest revision (report_final.md): saturation is determined by T2/T3/T_model
    only (T4 demoted to informational). has_throughput = T1 alone (T_active/T_unused
    demoted to informational). Hysteresis (sat_now AND sat_prev) is unchanged.
    T4/T_active/T_unused continue to be computed and stored in Signals for display.
    """
    # 1. All saturation signals NA -> cannot decide
    # T4 excluded: informational only (backtest shows it is not a decision driver)
    if all_na(s.T2, s.T3, s.T_model):
        return ("deferred", "insufficient_data")

    sat_now = any_true(s.T2, s.T3, s.T_model)

    # sat_prev from previous round; None when no prior round
    if p is not None:
        sat_prev = any_true(p.T2, p.T3, p.T_model)
    else:
        sat_prev = False

    saturation = sat_now and sat_prev
    # has_throughput: T1 alone (T_unused/T_active demoted per backtest; label: "throughput")
    has_throughput = bool(s.T1)

    if saturation and has_throughput:
        return ("switch_combinatorial", "saturated_with_throughput")

    if saturation and not has_throughput:
        return ("stop", "saturated_no_throughput")

    if not sat_now:
        return ("continue_walking", "no_saturation_signal")

    if not saturation:
        # sat_now True but sat_prev False -> hysteresis not yet met
        return ("continue_walking", "hysteresis_pending")

    # Defensive guard: logically unreachable given above branches
    return ("deferred", "mixed_signals")


# ---------------------------------------------------------------------------
# Bootstrap confidence
# ---------------------------------------------------------------------------

def bootstrap_confidence(
    round_state: RoundState,
    registered: dict,
    n_boot: int,
    seed: int,
) -> tuple[float, dict[str, float]]:
    """Estimate decision confidence by resampling noise-bearing signals T2 and T3.

    Bootstrap simplifications (see module docstring):
    - Only T2 and T3 are resampled (measurement noise sources).
    - T1, T4, T_active, T_model, T_unused are frozen at their point values.
    - sat_prev is frozen (previous_signals not resampled).
    - best_{n-1} is held fixed; delta* = delta_ema + (best_n* - max(activities)).

    Returns:
        (confidence, distribution) where confidence is the fraction of bootstrap
        samples that agree with the point decision label, and distribution is the
        full label-frequency dict.
        Returns (float("nan"), {}) when bootstrap inputs are unavailable.
    """
    wt_values = round_state.wt_values
    current_round_activities = round_state.current_round_activities

    if not wt_values or not current_round_activities:
        return (float("nan"), {})

    # Parameters from registered
    t2_method = registered.get("t2_null_method", "order_statistic")
    t3_window = registered.get("t3_window_rounds", 2)
    tau_pos = registered.get("tau_pos", 0.0)
    wt_min = registered.get("wt_replicate_min", 4)

    # Precompute point values for frozen signals
    point_signals = compute_signals(round_state, registered)
    p = round_state.previous_signals

    # Best_n from original activities (used as reference for delta adjustment)
    best_n_point = max(current_round_activities)

    tally: dict[str, int] = {
        "continue_walking": 0,
        "switch_combinatorial": 0,
        "stop": 0,
        "deferred": 0,
    }

    def _det_index(counter: int, n: int) -> int:
        """Deterministic, version-independent index in [0, n) from sha256(seed||counter).

        Used for reproducible bootstrap resampling (pre-registration / audit contract).
        Version-independent determinism via sha256 (no PRNG module). Not cryptographic.
        """
        digest = hashlib.sha256(f"{seed}:{counter}".encode()).digest()
        return int.from_bytes(digest[:8], "big") % n

    counter = 0
    for _ in range(n_boot):
        # Resample wt -> sigma*
        wt_star = [wt_values[_det_index(counter + i, len(wt_values))] for i in range(len(wt_values))]
        counter += len(wt_values)
        sigma_star = compute_sigma_assay(wt_star, min_replicates=wt_min)

        # Resample activities -> best_n* and hit*
        act_star = [current_round_activities[_det_index(counter + i, len(current_round_activities))] for i in range(len(current_round_activities))]
        counter += len(current_round_activities)
        best_n_star = max(act_star)
        n_act = len(act_star)
        hit_star = sum(1 for a in act_star if a > tau_pos) / n_act

        # delta* = point delta_best_ema adjusted for best_n* deviation
        delta_star = round_state.delta_best_ema + (best_n_star - best_n_point)

        # hit_rates* = replace last round's hit rate with resampled value
        hit_rates_star = list(round_state.hit_rates[:-1]) + [hit_star]

        # Recompute noise-bearing signals
        T2_star = compute_T2(
            delta_star,
            sigma_star,
            round_state.r,
            n_designed=round_state.n_designed,
            method=t2_method,
        )
        T3_star = compute_T3(hit_rates_star, window=t3_window)

        # Construct bootstrap signal snapshot (structural signals frozen)
        s_star = Signals(
            T1=point_signals.T1,
            T2=T2_star,
            T3=T3_star,
            T4=point_signals.T4,
            T_active=point_signals.T_active,
            T_model=point_signals.T_model,
            T_unused=point_signals.T_unused,
        )

        label_star, _ = _decide_core(s_star, p)
        tally[label_star] += 1

    distribution = {label: cnt / n_boot for label, cnt in tally.items()}

    # Point label for confidence extraction
    point_label, _ = _decide_core(point_signals, p)
    confidence = distribution.get(point_label, 0.0)

    return (confidence, distribution)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify(round_state: RoundState, registered: dict) -> Decision:
    """Classify one ALE round as per §12-A.2 decision tree (v0.3 engine).

    Args:
        round_state: All signal inputs and bootstrap raw data for this round.
        registered: Pre-registered threshold dict (§12-A.3). Keys are read with
            .get() so only non-default values need to be supplied.

    Returns:
        Decision with label, reason, and (for gated branches) confidence and
        bootstrap_distribution.

    Confidence gate applies symmetrically to switch_combinatorial and stop:
        switch + conf < threshold -> deferred("low_confidence")
        stop   + conf < threshold -> continue_walking("stop_low_confidence")
    """
    n_min = registered.get("N_min", 3)
    if round_state.n < n_min:
        return Decision(label="continue_walking", reason="calibration_period")

    s = compute_signals(round_state, registered)
    p = round_state.previous_signals

    label0, reason0 = _decide_core(s, p)

    if label0 in ("switch_combinatorial", "stop"):
        # Bootstrap inputs are required for gated branches
        if round_state.wt_values is None or round_state.current_round_activities is None:
            return Decision(label="deferred", reason="bootstrap_inputs_missing")

        seed = effective_seed(round_state, registered)
        n_boot = registered.get("bootstrap_n", 1000)
        conf, dist = bootstrap_confidence(round_state, registered, n_boot=n_boot, seed=seed)

        thr = registered.get("confidence_threshold", 0.7)

        if label0 == "switch_combinatorial":
            if conf < thr:
                return Decision(
                    label="deferred",
                    reason="low_confidence",
                    confidence=conf,
                    bootstrap_distribution=dist,
                )
            return Decision(
                label="switch_combinatorial",
                reason="saturated_with_throughput",
                confidence=conf,
                bootstrap_distribution=dist,
            )
        else:  # label0 == "stop"
            if conf < thr:
                return Decision(
                    label="continue_walking",
                    reason="stop_low_confidence",
                    confidence=conf,
                    bootstrap_distribution=dist,
                )
            return Decision(
                label="stop",
                reason="saturated_no_throughput",
                confidence=conf,
                bootstrap_distribution=dist,
            )

    # continue_walking or deferred: no confidence gate
    return Decision(label=label0, reason=reason0)
