"""Pydantic models for strategy decision logging and round metrics.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.4
Phase 6 Task 6.2 -- schema only.

5/12 scope: schema definition and persistence.
Classifier body, bootstrap computation, and advisory/auto modes are v0.3+.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal, Optional, TypeVar

from pydantic import BaseModel, field_validator


_FloatT = TypeVar("_FloatT", bound=Optional[float])


def _reject_non_finite(name: str, value: _FloatT) -> _FloatT:
    """Refuse NaN and infinity on a field whose docstring declares a range.

    A non-finite float is not a value in any declared range, and it does not
    survive the audit log: json has no NaN literal, so model_dump_json writes
    null and the reader can no longer tell "could not be computed" from
    "never recorded".
    """
    if value is None:
        return None
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return value


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
        decision_confidence: Scalar confidence from bootstrap, in [0.0, 1.0],
            or None when no bootstrap ran (calibration period, deferred on
            missing inputs). Both halves of that contract are enforced.

            The field is Optional because the absent state has to be
            representable: json has no NaN literal, so a NaN written here came
            back out of model_dump_json as null and model_validate_json then
            rejected its own output against the non-optional float. An audit
            log that cannot be read back is not an audit log. Non-finite values
            are refused at construction as well, so "not computed" has exactly
            one spelling (None) instead of two that serialise alike.
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
    decision_confidence: Optional[float] = None
    reason: str
    overridden_by_user: bool
    override_note: Optional[str] = None
    seed: int
    bootstrap_n: int = 1000
    prev_signals_digest: Optional[str] = None
    effective_seed: Optional[int] = None

    @field_validator("decision_confidence")
    @classmethod
    def _check_confidence(cls, v: Optional[float]) -> Optional[float]:
        v = _reject_non_finite("decision_confidence", v)
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError(f"decision_confidence must lie in [0, 1], got {v!r}")
        return v

    @field_validator("bootstrap_n")
    @classmethod
    def _check_bootstrap_n(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"bootstrap_n must be >= 1, got {v!r}")
        return v


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

    # The rules below were stated only in the field docstrings above, which
    # meant hit_rates=[-5.0, 2.0, nan], sigma_assay=-1.0, r=0 and negative
    # counts all constructed successfully and then produced either a wrong
    # signal or a ZeroDivisionError further downstream.

    @field_validator("delta_best_ema")
    @classmethod
    def _check_delta(cls, v: float) -> float:
        return _reject_non_finite("delta_best_ema", v)

    @field_validator("sigma_assay")
    @classmethod
    def _check_sigma(cls, v: Optional[float]) -> Optional[float]:
        v = _reject_non_finite("sigma_assay", v)
        if v is not None and v < 0:
            raise ValueError(f"sigma_assay is a standard deviation and cannot be negative, got {v!r}")
        return v

    @field_validator("hit_rates")
    @classmethod
    def _check_hit_rates(cls, v: list[float]) -> list[float]:
        for index, rate in enumerate(v):
            _reject_non_finite(f"hit_rates[{index}]", rate)
            if not 0.0 <= rate <= 1.0:
                raise ValueError(
                    f"hit_rates[{index}] is a ratio and must lie in [0, 1], got {rate!r}"
                )
        return v

    @field_validator("r")
    @classmethod
    def _check_r(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"r (replicates per well) must be >= 1, got {v!r}")
        return v

    @field_validator("cumulative_beneficial", "K_throughput", "unused_beneficial_count")
    @classmethod
    def _check_counts(cls, v: int, info) -> int:
        if v < 0:
            raise ValueError(f"{info.field_name} is a count and cannot be negative, got {v!r}")
        return v
