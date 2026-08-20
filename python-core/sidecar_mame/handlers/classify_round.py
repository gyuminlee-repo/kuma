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
            {"n": 2, "path": "...", "wt_values": [1.02, 0.97, ...]},
            ...
        ],
        "c_next": 96   # optional; default 96 if absent
    }

    round_files must be ordered by round number (ascending).
    c_next: capacity of the next combinatorial plate (used to derive K_throughput).
    wt_values: optional wild-type replicates step 4.1 recorded for that round,
        on the scale of the activity column in the same file.  Only the entry
        with the highest n is read: the bootstrap tests the current round.

Returns one of two shapes, discriminated by ``advisory``.

The classifier answered::

    {
        "advisory": "decision",
        "label": str,       # DecisionLabel value
        "reason": str,
        "confidence": float | null,
        "missing_inputs": [str],     # inputs this call could not supply
    }

The classifier was never asked::

    {
        "advisory": "not_assessable",
        "reason": str,               # which input is absent or short
        "missing_inputs": [str],
        "blocked_decisions": [str],  # labels unreachable without it
        "wt_replicate_count": int,   # replicates this round handed over
        "wt_replicate_min": int,     # replicates the noise estimate needs
    }

Raises (via dispatcher error codes):
    ValueError  -> -32602: missing/empty round_files, bad column headers,
                           non-parseable Variant, activity <= 0, wt_values
                           that is not a list of finite numbers.
    RuntimeError -> -32002: xlsx file not found.

Data availability
-----------------
sigma_assay = None  (the xlsx holds one activity per designed variant and no WT
column).  T2 and T_model are NA as a consequence.  T3 operates on hit_rates
derived from the imported rounds.  The point decision runs on T1/T3 only.

The WT replicates arrive beside the file rather than inside it.  Step 4.1 keeps
them on the round it built (``Round.evolvepro_input.wt_values``) because the
workbook itself cannot carry them, and the caller forwards them on the matching
``round_files`` entry.  They enter the bootstrap, which resamples them into a
sigma per draw; the point sigma_assay stays None, so which branch the decision
tree proposes is unchanged and only the confidence test behind switch/stop can
now run.  ``missing_inputs`` therefore still names wt_replicates on an answered
decision: the verdict itself was reached with T2 and T_model NA either way.

Two limits of that confidence, both since addressed, kept here because the
confidence values recorded on rounds judged before those fixes carry them:

- The draws computed a sigma and a T2 while the point estimate had neither.
  ``sat_now`` is any_true over T2/T3/T_model (classify.py), which only ever
  turns more True as signals arrive, so a draw could agree with a switch/stop
  point label for a reason the point label did not have, and agreement was
  biased upward for exactly the two labels the gate guards.  bootstrap_confidence
  now gates every draw on ``point_sigma_available``, so a draw carries a sigma
  only where the point estimate does.
- ``delta_best_ema`` was in activity units (round_best is max activity) while
  ``current_round_activities`` is log2, and classify.py adjusts the former by a
  difference of the latter before comparing it against a threshold.  The mixture
  predates this handler and was inert while the bootstrap never ran; both are on
  the log2 scale since v0.16.29.02.

What r means, and why the replicate counts recorded since v0.16.30.01 are not
it, is docs/2026-08-19-mame-assay-noise-model.md.  The short of it: the repeats
a variant can carry on the Agilent path are repeat injections of one well, and
averaging those does not reduce the well-to-well spread the round bests differ
by.

Read the confidence as "the resampled decision kept agreeing", not as a
calibrated probability.

Below ``wt_replicate_min`` the replicates are not forwarded at all.
compute_sigma_assay returns None under that count, so every bootstrap draw
carries sigma=None and its T2 comes back NA, while T_model is frozen at its
point value and is NA too.  The resampled decision then rests on the same lone
T3 that proposed the branch.  The gate would confirm a one-signal call, and it confirms it
emphatically: a T3 that is stable under resampling returns confidence 1.0, so
a switch_combinatorial backed by nothing but a hit-rate trend would be drawn at
full confidence.  Confidence measures agreement between the point decision and
its resamples, not the sufficiency of the evidence behind it.  Withholding the
replicates keeps the answer at "not assessable" and names the shortfall, which
is the honest output; a maximally confident single-signal verdict is worse than
none.

current_round_activities (log2_fc) is what the bootstrap resamples alongside
the replicates, but the bootstrap is only entered for switch/stop labels, and
those need wt_values.
When none were forwarded classify() answers that case with
deferred("bootstrap_inputs_missing").  Passing that through as-is would report
a withheld judgement, since deferred otherwise means the classifier weighed the
evidence and declined (insufficient_data, low_confidence).  It never got the
question.  This handler converts that one case into the separate
"not_assessable" shape above and leaves every genuine deferred untouched.

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

# Inputs the caller did not supply.  The per-round xlsx holds one measured
# activity per designed variant and no wild-type replicate column, so this list
# is what the call is missing whenever the replicates do not arrive beside the
# file.  It describes the inputs of one call, not a judgement the classifier
# made; a call that carries enough replicates reports nothing missing.
_MISSING_INPUTS = ["wt_replicates"]

# No wild-type replicate reached this call at all.
_REASON_WT_MISSING = "wt_replicates_missing"

# Replicates arrived but too few to estimate assay noise from.
_REASON_WT_INSUFFICIENT = "wt_replicates_insufficient"

# Labels classify() gates behind the bootstrap confidence test, which needs
# wt_values.  A call that carries too few replicates cannot reach either one,
# which is what the not_assessable shape reports; every other label is still
# answered normally.
_BOOTSTRAP_GATED_LABELS = ["switch_combinatorial", "stop"]


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
    if ws is None:
        wb.close()
        raise ValueError(f"xlsx has no readable sheet: {path}")
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
            # openpyxl types a cell value as a broad union; anything that is not
            # castable is reported per row by the handler below.
            activity = float(activity_raw)  # type: ignore[arg-type]
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
# WT replicates carried beside the file
# ---------------------------------------------------------------------------

def _wt_values(round_file: dict) -> list[float]:
    """Read the wild-type replicates a round_file entry carries.

    Absent or empty means the round recorded none, which every round built
    before step 4.1 kept them reports and which a hand-picked file from outside
    this workspace also reports.  That is a fact about the input, so it returns
    an empty list rather than raising.

    A present but unreadable value is a different matter and raises, in line
    with the anti-fallback rule the rest of this handler follows: a wt_values
    that cannot be parsed would otherwise silently become "no WT on record" and
    the answer would name the wrong reason.

    Raises
    ------
    ValueError
        wt_values is not a list, or holds a value that is not a finite number.
    """
    raw = round_file.get("wt_values")
    if raw is None:
        return []
    if not isinstance(raw, (list, tuple)):
        raise ValueError(
            f"round_file wt_values must be a list of numbers, got {raw!r}"
        )
    values: list[float] = []
    for item in raw:
        if isinstance(item, bool):
            raise ValueError(f"round_file wt_values holds a non-numeric entry: {item!r}")
        try:
            value = float(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"round_file wt_values holds a non-numeric entry: {item!r}"
            ) from exc
        if not math.isfinite(value):
            raise ValueError(
                f"round_file wt_values holds a non-finite entry: {item!r}"
            )
        values.append(value)
    return values


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
        round_best: float           max(activity), reported as measured
        round_best_log2: float      log2 of that same maximum
        log2_activities: list[float]   log2 of each activity (current_round_activities)
        positions: list[int]        position integers for all variants
    """
    n = len(records)
    beneficial_count = sum(1 for r in records if r["activity"] > 1.0)
    hit_rate = beneficial_count / n
    round_best = max(r["activity"] for r in records)
    log2_activities = [math.log2(r["activity"]) for r in records]
    # log2 is monotone, so this is log2(round_best). Taking it off the list the
    # classifier is handed keeps the two from drifting if either definition
    # moves later.
    round_best_log2 = max(log2_activities)
    positions = [r["position"] for r in records]
    return {
        "beneficial_count": beneficial_count,
        "hit_rate": hit_rate,
        "round_best": round_best,
        "round_best_log2": round_best_log2,
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
        log2 of the max activity per round, ordered ascending by round index.

    The scale matters and is not free. classify.py forms
    ``delta* = delta_best_ema + (best_n* - max(current_round_activities))``
    and ``current_round_activities`` is log2, so a linear EMA here added a
    linear quantity to a log2 one and then compared the sum against a threshold
    built from sigma_assay. Everything on this path is log2 fold change: the
    exported activity is already a ratio to the WT block mean, which makes it a
    multiplicative quantity, and ``tau_pos=0.0`` downstream only means
    "beneficial" because the activities reaching it are log2.
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
    # Three, because three is what a plate carries: the WT block is WT_1,
    # WT_2 and WT_3. Four disabled the signal permanently rather than guarding
    # it, since no run ever reached the count. Three leaves two degrees of
    # freedom, so the estimate is loose, and that looseness is real rather than
    # hidden: it widens the threshold and makes plateau harder to call, not
    # easier. docs/2026-08-19-mame-assay-noise-model.md carries the derivation.
    "wt_replicate_min": 3,
}


def handle_classify_round(params: dict) -> dict:
    """Advisory classify() call from round xlsx files.

    Parameters
    ----------
    params : dict
        round_files : list[{"n": int, "path": str, "wt_values": list[float]}]
            Rounds ordered ascending by n.  All paths must be absolute.
            wt_values is optional and only read on the highest-numbered entry.
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
            "missing_inputs": [str],
        }

    or, when the bootstrap gate was reached with too few WT replicates to run
    on, the "not_assessable" shape documented in the module docstring.

    Raises
    ------
    ValueError: round_files absent/empty, column mismatch, parse errors,
        unreadable wt_values.
    RuntimeError: xlsx file not found.
    """
    from kuma_core.strategy.classify import RoundState, Signals, classify, compute_signals
    from kuma_core.strategy.signals import compute_K_throughput, compute_sigma_assay

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

    # WT replicates of the round being judged.  Only the highest-numbered entry
    # is read: the bootstrap resamples the noise of the current measurement, and
    # the earlier rounds are in the list to supply the hit-rate trend.
    wt_values = _wt_values(sorted_files[-1])
    wt_min = _DEFAULT_REGISTERED["wt_replicate_min"]

    # On the log2 scale, because that is the scale everything it meets is on.
    # delta_best_ema is an EMA of log2 round bests and current_round_activities
    # is log2, so a sigma taken on the linear values would be compared against
    # quantities in another unit. For a small spread the two differ by 1/ln2,
    # about 1.44, which is the whole width of the threshold.
    #
    # A zero or negative replicate has no logarithm. The builder already
    # refuses a negative activity, so this catches a WT well that measured
    # exactly zero, which is a failed injection rather than a measurement of
    # no activity, and one of those would otherwise become negative infinity
    # and take the whole estimate with it.
    wt_log2 = [math.log2(v) for v in wt_values if v > 0.0]
    usable_wt = len(wt_log2) == len(wt_values) and len(wt_log2) >= wt_min

    # Below the minimum nothing is handed over.  compute_sigma_assay returns
    # None under that count, so every draw would resample into T2=NA and
    # T_model=NA and the confirmation would land back on the same lone T3 that
    # proposed the branch.  A T3 that holds up under resampling scores that as
    # confidence 1.0, which would print a single-signal switch as a certainty.
    bootstrap_wt = wt_log2 if usable_wt else None

    # The point estimate reads the same replicates the draws do. Held apart,
    # a draw could carry a signal the decision never had, and sat_now is an OR
    # over T2/T3/T_model, so agreement could only be biased upward for exactly
    # the two labels the confidence gate guards.
    sigma_assay = compute_sigma_assay(wt_log2, min_replicates=wt_min) if usable_wt else None

    # Cross-round aggregation
    hit_rates = [m["hit_rate"] for m in per_round_metrics]
    cumulative_beneficial = sum(m["beneficial_count"] for m in per_round_metrics)
    round_bests = [m["round_best_log2"] for m in per_round_metrics]
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
    # sigma_assay=None throughout: compute_signals reads sigma_assay and never
    # wt_values, and no sigma is estimated anywhere in this handler, so T2 and
    # T_model are NA here and T3 is the only active saturation signal.
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
            bests_so_far.append(m["round_best_log2"])
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
                # The count the maximum was taken over. Absent it, compute_T2
                # drops to the legacy null, which asks whether one nominated
                # variant improved. The question here is whether the best of a
                # plate did, and the best of many is high even when none of them
                # is: the order statistic is what accounts for that.
                n_designed=len(per_round_records[i]),
                # sigma_assay=None: sigma/T2 deferred until WT replicate import wired.
                # With sigma=None, T2=NA and T_model=NA.  T3 is the active signal.
                sigma_assay=None,
                # r=1: the file states one activity per variant and nothing
                # about how many measurements produced it.  T2 is NA here for
                # want of a sigma, so r does not act on these interim signals.
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
        # Rows in the round file rather than variants designed: gating drops
        # some of the designed set before it reaches this file, and the null
        # needs the number of draws the maximum was actually taken over.
        n_designed=len(per_round_records[-1]),
        # The spread of the wild-type block on the log2 scale, or None when
        # the round recorded too few wells to estimate one from. This is what
        # answers T2 rather than leaving it NA, and the same list feeds the
        # bootstrap, so the point estimate and its draws carry the same signal
        # set.
        sigma_assay=sigma_assay,
        # r=1 is the measurement, not a placeholder for one the file withholds.
        # A mutant well on the Agilent path carries a single measurement
        # (AgilentRecord, evolvepro_xlsx.py:44-56), so the exported activity is
        # one reading of one well.  A wild-type replicate is also one well read
        # once, which is why the WT spread estimates the variance of exactly
        # that quantity and why sqrt(2/r) at r=1 is the right standard error for
        # a difference of two of them.
        #
        # The replicate counts recorded since v0.16.30.01 do not raise it.  What
        # a variant can carry more than one of is repeat injections of the same
        # prepared well, and averaging those leaves the preparation and
        # well-to-well terms untouched while the round bests this compares
        # differ by well and by plate.  Feeding that count in as r would claim a
        # precision the repeats did not buy.
        #
        # Measured on campaign data rather than argued: on the rep-batch plate
        # every one of 34 variants carries exactly three measurements, and the
        # within-variant spread puts the injection term at 20 percent of the
        # variance against 80 for preparation.  Supplying r=3 naively would
        # narrow the threshold 42 percent when the honest narrowing is 7, and a
        # threshold too narrow refuses to call plateau.  So r=1 here is 7
        # percent wide rather than 42 percent tight, which is the safe
        # direction.  Note that r is genuinely 3 on the AGILENT_REP_BATCH route,
        # so anything that starts consuming r has to handle that route on its
        # own terms.  The derivation and the figures are in
        # docs/2026-08-19-mame-assay-noise-model.md.
        #
        # sigma_assay stays None above regardless, so this value reaches only
        # the bootstrap's own threshold rather than the decision.
        r=1,
        hit_rates=hit_rates,
        top_k_positions_n=top_k_pos_n,
        top_k_positions_n1=top_k_pos_n1,
        top_k_positions=top_k_positions_list,
        # active_residues=[]: demoted (T_active=None, does not gate decision)
        active_residues=[],
        # unused_beneficial_count=0: demoted (T_unused=False, does not gate decision)
        unused_beneficial_count=0,
        # What step 4.1 recorded for this round, or None when it recorded too
        # few to estimate noise from.  None keeps the bootstrap gate shut and
        # the answer becomes not_assessable below.
        wt_values=bootstrap_wt,
        # current_round_activities is log2_fc so that tau_pos=0.0 -> beneficial
        # = log2_fc > 0 = activity > 1.0.  This ensures hit_star in bootstrap
        # (if ever activated) is consistent with the beneficial definition used
        # to compute hit_rates above.
        current_round_activities=log2_activities_last,
    )

    decision = classify(round_state, registered)

    if decision.label == "deferred" and decision.reason == "bootstrap_inputs_missing":
        # classify() only reaches this reason after the core decision tree has
        # already proposed switch_combinatorial or stop and then found no
        # bootstrap inputs to confirm it with.  Two facts are worth reporting
        # and neither survives the "deferred" label: the signals did point at a
        # transition, and the confirming question was never put to the
        # classifier.  Report them as their own state.
        #
        # Which of the two shortfalls it was matters to whoever reads it: a
        # round that recorded no wild-type wells needs a different remedy than
        # one that recorded three, and the counts say which.
        return {
            "advisory": "not_assessable",
            "reason": _REASON_WT_MISSING if not wt_values else _REASON_WT_INSUFFICIENT,
            "missing_inputs": list(_MISSING_INPUTS),
            "blocked_decisions": list(_BOOTSTRAP_GATED_LABELS),
            "wt_replicate_count": len(wt_values),
            "wt_replicate_min": wt_min,
        }

    return {
        "advisory": "decision",
        "label": decision.label,
        "reason": decision.reason,
        "confidence": decision.confidence,
        # Reported whether or not the replicates arrived.  They reach the
        # bootstrap, not the point signals: sigma_assay stays None above, so the
        # decision on screen was still reached with T2 and T_model NA and
        # saturation resting on the hit-rate trend alone.  That is exactly what
        # the note this field draws says, so emptying it on a supplied round
        # would delete a true caveat from a verdict that still depends on it.
        "missing_inputs": list(_MISSING_INPUTS),
    }


__all__ = ["handle_classify_round"]
