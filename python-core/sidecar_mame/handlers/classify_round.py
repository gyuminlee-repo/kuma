"""``strategy.classify_round`` JSON-RPC handler -- Fork D (v0.4).

Reads per-round xlsx files (Variant + activity columns), computes cross-round
metrics, and calls ``kuma_core.strategy.classify.classify()``.

RPC contract
------------
Method: ``strategy.classify_round``
Params::

    {
        "round_files": [
            {"n": 1, "path": "<abs xlsx path>"},
            {"n": 2, "path": "..."},
            ...
        ],
        "c_next": 96   # optional; default 96 if absent
    }

    round_files must be ordered by round number (ascending).
    c_next: capacity of the next combinatorial plate (used to derive K_throughput).

Returns (on success)::

    {
        "advisory": "decision",
        "label": str,       # DecisionLabel value
        "reason": str,
        "confidence": float | null,
    }

Raises (via dispatcher error codes):
    ValueError  -> -32602: missing/empty round_files, bad column headers,
                           non-parseable Variant, activity <= 0.
    RuntimeError -> -32002: xlsx file not found.

Data availability
-----------------
sigma_assay = None  (purified xlsx files contain no WT replicates).
T2 and T_model are NA as a consequence.  T3 operates on hit_rates derived
from the imported rounds.  The decision engine runs on T1/T3 only.

sigma/T2 is deferred until WT replicate import is wired.
current_round_activities (log2_fc) is populated for bootstrap
readiness but bootstrap is only entered for switch/stop labels,
which require wt_values != None (never reached without WT import).

EMA_2 definition: exponential moving average with span=2 (alpha = 2/3).
  EMA_0 = delta_0 (first inter-round delta treated as initialisation).
  EMA_t = alpha * delta_t + (1 - alpha) * EMA_{t-1}.

top-K size: K_throughput (T4 is informational and does not drive decisions).

anti-fallback: missing columns, unparseable Variant rows, or activity <= 0
raise explicit errors rather than silently skipping or defaulting.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

_VARIANT_RE = re.compile(r"^(\d+)")


# ---------------------------------------------------------------------------
# xlsx parsing
# ---------------------------------------------------------------------------

def _load_xlsx(path: str) -> list[dict]:
    """Read Variant+activity from an xlsx file.

    Returns a list of dicts with keys ``position`` (int) and
    ``activity`` (float).

    Raises
    ------
    RuntimeError
        File not found.
    ValueError
        Columns ``Variant`` or ``activity`` absent.
        Variant cell has no leading integer (position).
        activity value cannot be cast to float.
        activity value <= 0 (log2 undefined).
    """
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openpyxl is required for xlsx import") from exc

    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"xlsx file not found: {path}") from exc

    ws = wb.active
    rows = ws.iter_rows(values_only=True)

    # Header row
    try:
        header_row = next(rows)
    except StopIteration:
        wb.close()
        raise ValueError(f"xlsx is empty (no rows): {path}")

    headers = [str(h).strip() if h is not None else "" for h in header_row]
    if "Variant" not in headers:
        wb.close()
        raise ValueError(
            f"Column 'Variant' not found in {path}. Headers: {headers!r}"
        )
    if "activity" not in headers:
        wb.close()
        raise ValueError(
            f"Column 'activity' not found in {path}. Headers: {headers!r}"
        )

    var_idx = headers.index("Variant")
    act_idx = headers.index("activity")

    records: list[dict] = []
    for row_num, row in enumerate(rows, start=2):
        variant_raw = row[var_idx]
        activity_raw = row[act_idx]

        if variant_raw is None and activity_raw is None:
            continue  # skip blank trailing rows

        # Parse position from Variant (leading integer)
        if variant_raw is None:
            wb.close()
            raise ValueError(
                f"Row {row_num}: Variant is None in {path}"
            )
        m = _VARIANT_RE.match(str(variant_raw).strip())
        if m is None:
            wb.close()
            raise ValueError(
                f"Row {row_num}: Variant {variant_raw!r} has no leading integer "
                f"(position) in {path}"
            )
        position = int(m.group(1))

        # Parse activity
        if activity_raw is None:
            wb.close()
            raise ValueError(
                f"Row {row_num}: activity is None for Variant={variant_raw!r} in {path}"
            )
        try:
            activity = float(activity_raw)
        except (TypeError, ValueError) as exc:
            wb.close()
            raise ValueError(
                f"Row {row_num}: activity value {activity_raw!r} cannot be cast to "
                f"float for Variant={variant_raw!r} in {path}"
            ) from exc

        if activity <= 0.0:
            wb.close()
            raise ValueError(
                f"Row {row_num}: activity={activity!r} <= 0 for Variant={variant_raw!r} "
                f"in {path}; log2 is undefined"
            )

        records.append({"position": position, "activity": activity})

    wb.close()

    if not records:
        raise ValueError(f"xlsx contains no data rows: {path}")

    return records


# ---------------------------------------------------------------------------
# Per-round metrics
# ---------------------------------------------------------------------------

def _round_metrics(records: list[dict]) -> dict:
    """Compute per-round aggregate metrics from parsed xlsx records.

    Returns
    -------
    dict with:
        beneficial_count: int       number of variants with activity > 1.0
        hit_rate: float             beneficial_count / n_variants
        round_best: float           max(activity)
        log2_activities: list[float]   log2 of each activity (current_round_activities)
        positions: list[int]        position integers for all variants
    """
    n = len(records)
    beneficial_count = sum(1 for r in records if r["activity"] > 1.0)
    hit_rate = beneficial_count / n
    round_best = max(r["activity"] for r in records)
    log2_activities = [math.log2(r["activity"]) for r in records]
    positions = [r["position"] for r in records]
    return {
        "beneficial_count": beneficial_count,
        "hit_rate": hit_rate,
        "round_best": round_best,
        "log2_activities": log2_activities,
        "positions": positions,
    }


# ---------------------------------------------------------------------------
# EMA_2 helper
# ---------------------------------------------------------------------------

_EMA_ALPHA = 2.0 / 3.0  # EMA_2: span=2, alpha=2/(2+1)=2/3


def _compute_delta_best_ema(round_bests: list[float]) -> float:
    """Compute EMA_2 of inter-round deltas of best activity.

    EMA_2 uses alpha=2/3 (span=2).
    The first delta initialises the EMA (no prior value).
    Returns 0.0 when fewer than 2 rounds are available.

    Parameters
    ----------
    round_bests : list[float]
        Max activity per round, ordered ascending by round index.
    """
    if len(round_bests) < 2:
        return 0.0
    ema = round_bests[1] - round_bests[0]  # first delta initialises EMA
    for i in range(2, len(round_bests)):
        delta = round_bests[i] - round_bests[i - 1]
        ema = _EMA_ALPHA * delta + (1.0 - _EMA_ALPHA) * ema
    return ema


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

_DEFAULT_C_NEXT = 96
_DEFAULT_REGISTERED: dict = {
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


def handle_classify_round(params: dict) -> dict:
    """Advisory classify() call from round xlsx files.

    Parameters
    ----------
    params : dict
        round_files : list[{"n": int, "path": str}]
            Rounds ordered ascending by n.  All paths must be absolute.
        c_next : int, optional
            Capacity of the next combinatorial plate.  Default: 96.

    Returns
    -------
    On success::

        {
            "advisory": "decision",
            "label": str,
            "reason": str,
            "confidence": float | null,
        }

    Raises
    ------
    ValueError: round_files absent/empty, column mismatch, parse errors.
    RuntimeError: xlsx file not found.
    """
    from kuma_core.strategy.classify import RoundState, Signals, classify, compute_signals
    from kuma_core.strategy.signals import compute_K_throughput

    round_files = params.get("round_files")
    if not round_files:
        raise ValueError("round_files is required and must be non-empty")

    c_next = params.get("c_next", _DEFAULT_C_NEXT)
    try:
        c_next = int(c_next)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"c_next must be an integer, got {c_next!r}") from exc

    # Sort by round number (ascending) to ensure cross-round order
    try:
        sorted_files = sorted(round_files, key=lambda rf: int(rf["n"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Each round_file must have integer 'n' and 'path'. Error: {exc}"
        ) from exc

    # K_throughput: derived once from c_next (same for all rounds)
    K_throughput = compute_K_throughput(c_next)

    # Load and compute per-round metrics
    per_round_records: list[list[dict]] = []
    per_round_metrics: list[dict] = []
    for rf in sorted_files:
        path = rf.get("path")
        if not path:
            raise ValueError(f"round_file entry missing 'path': {rf!r}")
        records = _load_xlsx(str(path))
        metrics = _round_metrics(records)
        per_round_records.append(records)
        per_round_metrics.append(metrics)

    n_rounds = len(sorted_files)

    # Cross-round aggregation
    hit_rates = [m["hit_rate"] for m in per_round_metrics]
    cumulative_beneficial = sum(m["beneficial_count"] for m in per_round_metrics)
    round_bests = [m["round_best"] for m in per_round_metrics]
    delta_best_ema = _compute_delta_best_ema(round_bests)
    log2_activities_last = per_round_metrics[-1]["log2_activities"]

    # top-K positions for T4 (informational only; K=K_throughput)
    # Positions deduplicated; T4 does not drive decisions (backtest-demoted).
    def _top_k_pos_set(records: list[dict], k: int) -> set[int]:
        sorted_recs = sorted(records, key=lambda r: r["activity"], reverse=True)
        seen: set[int] = set()
        for rec in sorted_recs:
            seen.add(rec["position"])
            if len(seen) >= k:
                break
        return seen

    top_k_pos_n = _top_k_pos_set(per_round_records[-1], K_throughput)
    top_k_pos_n1 = (
        _top_k_pos_set(per_round_records[-2], K_throughput)
        if n_rounds >= 2 else set()
    )
    top_k_positions_list = sorted(top_k_pos_n)

    # previous_signals: chain Signals for all rounds except the last.
    # Builds an incremental RoundState per prior round and calls compute_signals().
    # sigma_assay=None throughout because purified xlsx contains no WT replicates.
    # sigma/T2 is deferred: T2/T_model=NA, T3 is the only active saturation signal.
    registered = _DEFAULT_REGISTERED.copy()
    previous_signals: Optional[Signals] = None

    if n_rounds >= 2:
        cum_so_far = 0
        ema_so_far: Optional[float] = None
        bests_so_far: list[float] = []
        hr_so_far: list[float] = []

        for i in range(n_rounds - 1):
            m = per_round_metrics[i]
            cum_so_far += m["beneficial_count"]
            bests_so_far.append(m["round_best"])
            hr_so_far.append(m["hit_rate"])
            ema_i = _compute_delta_best_ema(bests_so_far)

            # top-K for this interim round
            tk_n = _top_k_pos_set(per_round_records[i], K_throughput)
            tk_n1 = (
                _top_k_pos_set(per_round_records[i - 1], K_throughput)
                if i >= 1 else set()
            )

            interim_state = RoundState(
                n=i + 1,
                previous_signals=previous_signals,
                cumulative_beneficial=cum_so_far,
                K_throughput=K_throughput,
                delta_best_ema=ema_i,
                # sigma_assay=None: sigma/T2 deferred until WT replicate import wired.
                # With sigma=None, T2=NA and T_model=NA.  T3 is the active signal.
                sigma_assay=None,
                r=1,
                hit_rates=list(hr_so_far),
                top_k_positions_n=tk_n,
                top_k_positions_n1=tk_n1,
                top_k_positions=sorted(tk_n),
                # active_residues=[] and unused_beneficial_count=0: both demoted
                # (T_active=None, T_unused=False); neither gates the decision.
                active_residues=[],
                unused_beneficial_count=0,
                wt_values=None,
                current_round_activities=m["log2_activities"],
            )
            previous_signals = compute_signals(interim_state, registered)

    # Assemble final RoundState
    round_state = RoundState(
        n=n_rounds,
        previous_signals=previous_signals,
        cumulative_beneficial=cumulative_beneficial,
        K_throughput=K_throughput,
        delta_best_ema=delta_best_ema,
        # sigma_assay=None: sigma/T2 deferred until WT replicate import is wired.
        # When WT replicates are available, compute_sigma_assay(wt_values) activates T2.
        # T_model is also NA (requires sigma_assay).
        # With sigma=None, T3 is the sole noise-bearing saturation signal operative.
        sigma_assay=None,
        r=1,  # no replicate info in purified xlsx; r=1 is safe (T2=NA anyway)
        hit_rates=hit_rates,
        top_k_positions_n=top_k_pos_n,
        top_k_positions_n1=top_k_pos_n1,
        top_k_positions=top_k_positions_list,
        # active_residues=[]: demoted (T_active=None, does not gate decision)
        active_residues=[],
        # unused_beneficial_count=0: demoted (T_unused=False, does not gate decision)
        unused_beneficial_count=0,
        wt_values=None,  # no WT in purified xlsx; bootstrap deferred
        # current_round_activities is log2_fc so that tau_pos=0.0 -> beneficial
        # = log2_fc > 0 = activity > 1.0.  This ensures hit_star in bootstrap
        # (if ever activated) is consistent with the beneficial definition used
        # to compute hit_rates above.
        current_round_activities=log2_activities_last,
    )

    decision = classify(round_state, registered)

    return {
        "advisory": "decision",
        "label": decision.label,
        "reason": decision.reason,
        "confidence": decision.confidence,
    }


__all__ = ["handle_classify_round"]
