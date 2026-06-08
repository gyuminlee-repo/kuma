"""``strategy.classify_round`` JSON-RPC handler.

Read-only advisory slice (v0.3).  Assembles a ``RoundState`` from whatever
is available in the sidecar ``_rounds`` store and calls
``kuma_core.strategy.classify.classify()``.

Data availability contract
--------------------------
The following ``RoundState`` required scalars have no plumbing into the
sidecar store yet.  When ANY of them is absent the handler returns
``{advisory: "unavailable", missing: [...]}``.  No fabricated or defaulted
values are substituted.

  Scalars that require cross-round plumbing (reported as "plumbing needed"):
    - cumulative_beneficial  (cross-round beneficial count, threshold needed)
    - K_throughput           (combinatorial design knowledge needed)
    - delta_best_ema         (cross-round EMA calculation needed)
    - unused_beneficial_count (cross-round beneficial tracking needed)

  List/set fields that require mutation-position data or cross-round tracking:
    - hit_rates              (per-round beneficial fraction, threshold needed)
    - top_k_positions_n      (KURO mutation position data needed)
    - top_k_positions_n1     (prior-round position data needed)
    - top_k_positions        (KURO mutation position data needed)
    - active_residues        (structural annotation needed)
    - previous_signals       (prior-round Signals snapshot needed)

Fields that CAN be assembled from the current sidecar store
-----------------------------------------------------------
    - n                      (rd["n"])
    - current_round_activities  (merged_table non-WT activity_raw_mean)
    - wt_values              (merged_table is_wt activity_raw_mean)
    - r                      (most common replicate_n in merged_table)
    - sigma_assay            (compute_sigma_assay(wt_values), None if WT < 4)
"""

from __future__ import annotations

from typing import Any

from sidecar_mame.handlers.activity import _rounds, _rounds_lock


# Required scalar field names (RoundState fields that cannot be None).
# If ANY of these is absent from the round dict, return "unavailable".
_REQUIRED_PLUMBING_FIELDS: tuple[str, ...] = (
    "cumulative_beneficial",
    "K_throughput",
    "delta_best_ema",
    "unused_beneficial_count",
)

# Required list/set fields that also need plumbing.  An empty list is a
# *valid* value for hit_rates/active_residues/top_k_*; absence (None) is not.
# We gate on None only, not empty lists.
_REQUIRED_LIST_FIELDS: tuple[str, ...] = (
    "hit_rates",
    "top_k_positions_n",
    "top_k_positions_n1",
    "top_k_positions",
    "active_residues",
)


def _derive_wt_and_activity(
    merged_table: list[dict[str, Any]],
) -> tuple[list[float] | None, list[float] | None]:
    """Extract wt_values and current_round_activities from merged_table rows.

    Returns (wt_values, current_round_activities).  Either may be None if no
    matching rows exist.
    """
    wt: list[float] = []
    non_wt: list[float] = []
    for row in merged_table:
        val = row.get("activity_raw_mean")
        if val is None:
            continue
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        if row.get("is_wt"):
            wt.append(fval)
        else:
            non_wt.append(fval)
    return (wt if wt else None), (non_wt if non_wt else None)


def _derive_r(merged_table: list[dict[str, Any]]) -> int | None:
    """Return the modal replicate_n from merged_table rows, or None."""
    counts: dict[int, int] = {}
    for row in merged_table:
        rn = row.get("replicate_n")
        if rn is None:
            continue
        try:
            rn_int = int(rn)
        except (TypeError, ValueError):
            continue
        if rn_int > 0:
            counts[rn_int] = counts.get(rn_int, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def handle_classify_round(params: dict) -> dict:
    """Advisory classify() call for one round.

    Parameters
    ----------
    params : dict
        round_id (str): must match an existing sidecar round.

    Returns
    -------
    On success (all required scalars available + classify() runs):
        {
            "advisory": "decision",
            "label": str,       # DecisionLabel value
            "reason": str,
            "confidence": float | null,
        }

    When required scalars are missing (expected path for real data today):
        {
            "advisory": "unavailable",
            "missing": [str, ...],
        }

    Raises
    ------
    ValueError: round_id absent or empty (-> -32602 in dispatcher).
    RuntimeError: round not found (-> -32002 in dispatcher).
    """
    round_id = params.get("round_id")
    if not round_id:
        raise ValueError("round_id is required")

    # Acquire read lock; raise RuntimeError if round absent.
    with _rounds_lock:
        rd = _rounds.get(round_id)
    if rd is None:
        raise RuntimeError(f"Round not found: {round_id}")

    # 1. Check required scalar plumbing fields.
    missing: list[str] = []
    for field in _REQUIRED_PLUMBING_FIELDS:
        if rd.get(field) is None:
            missing.append(field)

    # 2. Check required list/set plumbing fields.
    for field in _REQUIRED_LIST_FIELDS:
        if rd.get(field) is None:
            missing.append(field)

    if missing:
        return {
            "advisory": "unavailable",
            "missing": missing,
        }

    # 3. All required scalars present: assemble RoundState.
    # (This path is exercised by synthetic test payload; real rounds always
    # trigger the unavailable branch until plumbing is wired.)
    from kuma_core.strategy.classify import RoundState, classify
    from kuma_core.strategy.signals import compute_sigma_assay

    merged_table: list[dict[str, Any]] = rd.get("merged_table") or []
    wt_values, current_round_activities = _derive_wt_and_activity(merged_table)

    # r: prefer explicit plumbing key; fall back to replicate_n derivation.
    r_val = rd.get("r")
    if r_val is None:
        r_val = _derive_r(merged_table)
    if r_val is None:
        r_val = 1  # last-resort safe minimum (prevents ZeroDivisionError in T2)

    sigma_assay: float | None = None
    if wt_values and len(wt_values) >= 4:
        sigma_assay = compute_sigma_assay(wt_values)

    round_state = RoundState(
        n=int(rd["n"]),
        previous_signals=rd.get("previous_signals"),
        cumulative_beneficial=int(rd["cumulative_beneficial"]),
        K_throughput=int(rd["K_throughput"]),
        delta_best_ema=float(rd["delta_best_ema"]),
        sigma_assay=sigma_assay,
        r=int(r_val),
        hit_rates=[float(v) for v in rd["hit_rates"]],
        top_k_positions_n=set(int(v) for v in rd["top_k_positions_n"]),
        top_k_positions_n1=set(int(v) for v in rd["top_k_positions_n1"]),
        top_k_positions=[int(v) for v in rd["top_k_positions"]],
        active_residues=[int(v) for v in rd["active_residues"]],
        unused_beneficial_count=int(rd["unused_beneficial_count"]),
        n_designed=rd.get("n_designed"),
        predicted_top_untested_gain=rd.get("predicted_top_untested_gain"),
        wt_values=wt_values,
        current_round_activities=current_round_activities,
        round_id=round_id,
    )

    # 4. Default registered config (matches test suite defaults).
    # Future: expose via sidecar params or workspace config.
    registered: dict = rd.get("registered") or {
        "N_min": 3,
        "bootstrap_n": 1000,
        "bootstrap_seed": 42,
        "confidence_threshold": 0.7,
        "t2_null_method": "legacy",
        "t3_window_rounds": 2,
        "jaccard_threshold": 0.5,
        "active_concentration_threshold": 0.4,
        "M_min_unused_beneficials": 5,
        "tau_pos": 0.0,
        "wt_replicate_min": 4,
    }

    decision = classify(round_state, registered)

    return {
        "advisory": "decision",
        "label": decision.label,
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


__all__ = ["handle_classify_round"]
