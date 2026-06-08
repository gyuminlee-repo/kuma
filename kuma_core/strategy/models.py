"""Pydantic models for strategy decision logging and round metrics.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.4
Phase 6 Task 6.2 -- schema only.

5/12 scope: schema definition and persistence.
Classifier body, bootstrap computation, and advisory/auto modes are v0.3+.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


class StrategyDecisionLog(BaseModel):
    """Audit log for a single strategy decision event.

    Persisted per-round in the workspace for PI reporting.
    Spec: §12-A.4.

    Fields:
        round_id: Identifier of the round for which the decision was made.
        decided_at: Timestamp of the decision (timezone-aware recommended).
        activation_mode: Current classifier activation phase.
        pre_registered_thresholds: Snapshot of §12-A.3 registered thresholds
            at decision time (immutable after workspace lock).
        signal_inputs: Raw inputs used to compute signals:
            sigma_assay, r, best_n, best_{n-1}, hit_rate_n, top_k_positions.
        signal_scores: Computed signal values, e.g. T1=True, T2=False, T3=True.
        signal_magnitudes: Parallel float magnitudes for audit (T4->jaccard,
            T_active->fraction, T_unused->count, T3->slope, T2->delta).
            Populated alongside signal_scores; empty dict if not computed.
        bootstrap_distribution: Probability distribution over decision labels
            from bootstrap sampling (v0.3+). Schema retained for future use.
        decision: The selected decision label.
        decision_confidence: Scalar confidence from bootstrap (0.0-1.0).
        reason: Short human-readable rationale code, e.g. "calibration_period".
        overridden_by_user: True if the user dismissed the classifier result.
        override_note: Optional free-text annotation for the override.
        seed: RNG seed used for bootstrap, for reproducibility.
        bootstrap_n: Number of bootstrap samples drawn (default 1000).
        prev_signals_digest: SHA-256 hex digest of the previous round signals
            snapshot used for hysteresis. Together with pre_registered_thresholds,
            fixing both ensures decision_confidence is reproducible.
            "(thresholds, prev_signals) tuple fixed -> reproducible; effective_seed =
            sha256(round_id+thresholds) XOR seed (implementation in classify() v0.3)"
        effective_seed: Derived RNG seed encoding round_id and threshold state.
            Ensures reproducibility when thresholds change between rounds
            (spec §12-A.2/A.4 reproducibility contract).
    """

    round_id: str
    decided_at: datetime
    activation_mode: Literal["calibration", "advisory", "auto"]
    pre_registered_thresholds: dict[str, Any]
    signal_inputs: dict[str, Any]
    signal_scores: dict[str, Any]  # bool | float values per signal
    signal_magnitudes: dict[str, float] = {}
    bootstrap_distribution: dict[str, float]
    decision: Literal["continue_walking", "switch_combinatorial", "stop", "deferred"]
    decision_confidence: float
    reason: str
    overridden_by_user: bool
    override_note: Optional[str] = None
    seed: int
    bootstrap_n: int = 1000
    prev_signals_digest: Optional[str] = None
    effective_seed: Optional[int] = None


class RoundMetrics(BaseModel):
    """Computed signal values and raw inputs for a single ALE round.

    Captures the full signal state for display (RoundSummaryPanel)
    and archival. No decision fields -- classification is v0.3+.

    Fields:
        round_id: Identifier of the ALE round.
        computed_at: Timestamp when signals were computed.
        cumulative_beneficial: Total beneficial single mutations found so far.
        K_throughput: Required number of singles (compute_K_throughput result).
        delta_best_ema: EMA_2 of (best_n - best_{n-1}).
        sigma_assay: Estimated assay noise (None if WT replicates < 4).
        r: Number of replicates per well used in T2 calculation.
        hit_rates: Per-round hit rate list (n_positive / n_designed).
        top_k_positions_n: Residue positions in top-K variants of round n.
        top_k_positions_n1: Residue positions in top-K variants of round n-1.
        top_k_positions: Flat list of residue positions in current top-K.
        active_residues: Known active-site residue positions.
        unused_beneficial_count: Beneficial mutations not used as next baseline.
        T1: Throughput threshold signal value.
        T2: Plateau signal value. None = sigma_assay unavailable (WT < 4).
        T3: Hit rate trend signal value. None = fewer than 2 data points.
        T4: Position convergence signal value. None = both position sets empty.
        T_active: Active site fraction signal value. None = empty inputs.
        T_model: Surrogate single-exhaustion signal (EVOLVEpro y_pred).
            None = sigma_assay unavailable. v0.3+ wiring in classify().
        T_unused: Unused beneficial count signal value.
        signal_magnitudes: Float magnitudes for audit display (T4->jaccard,
            T_active->fraction, T_unused->count, T3->slope, T2->delta).
    """

    round_id: str
    computed_at: datetime

    # Raw inputs
    cumulative_beneficial: int
    K_throughput: int
    delta_best_ema: float
    sigma_assay: Optional[float] = None
    r: int
    hit_rates: list[float]
    top_k_positions_n: set[int]
    top_k_positions_n1: set[int]
    top_k_positions: list[int]
    active_residues: list[int]
    unused_beneficial_count: int

    # Computed signal booleans (T1 and T_unused remain bool; others are Optional)
    T1: bool
    T2: Optional[bool] = None
    T3: Optional[bool] = None
    T4: Optional[bool] = None
    T_active: Optional[bool] = None
    T_model: Optional[bool] = None
    T_unused: bool

    # Audit magnitudes (display-only; not used by classifier logic)
    signal_magnitudes: dict[str, float] = {}

    model_config = {"arbitrary_types_allowed": True}
