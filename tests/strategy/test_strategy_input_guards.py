"""Regression tests for the strategy engine input guards and confidence semantics.

One test (or one parametrised group) per defect from the 2026 strategy audit,
each failing before the corresponding fix and passing after:

- B1 a confidence that could not be computed selected the confident branch,
     and a non-finite confidence_threshold opened the gate entirely
- B2 the bootstrap input guard was weaker than the computation it protected
- B3 a single non-finite activity made the decision depend on list order
- B4 t3_window_rounds of 0 silently meant the whole history, 1 meant "insufficient"
- B5 models.py carried no validators and the audit log did not round-trip
- B6 unhandled exceptions on ordinary input
- B7 a docstring defined a set and the code divided by list length
- B8 the point estimate and the bootstrap draws ran on different signal sets
"""

from __future__ import annotations

import importlib
import math
from typing import Any

import pytest
from pydantic import ValidationError

from kuma_core.strategy.classify import (
    RoundState,
    Signals,
    _decide_core,
    bootstrap_confidence,
    classify,
    compute_signals,
)

# kuma_core.strategy re-exports the classify *function* under that name, so the
# module object has to be fetched explicitly for monkeypatching.
classify_module = importlib.import_module("kuma_core.strategy.classify")
from kuma_core.strategy.models import RoundMetrics, StrategyDecisionLog
from kuma_core.strategy.signals import (
    compute_sigma_assay,
    compute_sigma_assay_ci,
    compute_T2,
    compute_T2_threshold,
    compute_T3,
    compute_T3_magnitude,
    compute_T_active,
    compute_T_model,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

#: Twenty log2 activities, ten of them positive, so the resampled hit rate
#: varies around 0.5 and T3* is the only signal that can move.
ACTIVITIES = [
    -1.0, -0.9, -0.8, -0.7, -0.6, -0.5, -0.4, -0.3, -0.2, -0.1,
    0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0,
]

WT_VALUES = [1.0, 1.05, 0.95, 1.02]

#: Previous round saturated through T3, which satisfies the hysteresis clause.
PREV_SATURATED = Signals(
    T1=False, T2=None, T3=True, T4=None, T_active=None, T_model=None, T_unused=False
)


def _registered(**overrides) -> dict:
    base = {
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
    base.update(overrides)
    return base


def _round_state(**overrides) -> RoundState:
    """A round that lands on the `stop` branch: saturated, no throughput."""
    base: dict[str, Any] = dict(
        n=4,
        previous_signals=PREV_SATURATED,
        cumulative_beneficial=1,      # below K_throughput -> T1 False -> stop
        K_throughput=5,
        delta_best_ema=0.01,
        sigma_assay=None,
        r=3,
        hit_rates=[0.6, 0.52, 0.50],
        top_k_positions_n=set(),
        top_k_positions_n1=set(),
        top_k_positions=[],
        active_residues=[],
        unused_beneficial_count=0,
        n_designed=None,
        predicted_top_untested_gain=None,
        wt_values=list(WT_VALUES),
        current_round_activities=list(ACTIVITIES),
        round_id="r4",
    )
    base.update(overrides)
    return RoundState(**base)


# ---------------------------------------------------------------------------
# B1 -- a confidence that could not be computed must not select a branch
# ---------------------------------------------------------------------------

class TestNonFiniteConfidence:
    @pytest.mark.parametrize(
        "cumulative_beneficial, gated_label",
        [(1, "stop"), (10, "switch_combinatorial")],
    )
    def test_non_finite_confidence_defers_on_both_gated_labels(
        self, monkeypatch, cumulative_beneficial, gated_label
    ):
        """NaN < thr is False, which used to select the confident branch.

        Both gated labels were affected, so the low-confidence safety net ran
        backwards on exactly the input it exists to catch.
        """
        state = _round_state(cumulative_beneficial=cumulative_beneficial)
        # The undecorated tree really does reach the gated branch under test,
        # so the gate below is the only thing that can move the label.
        label0, _ = _decide_core(compute_signals(state, _registered()), state.previous_signals)
        assert label0 == gated_label

        monkeypatch.setattr(
            classify_module,
            "bootstrap_confidence",
            lambda *a, **k: (float("nan"), {}),
        )
        decision = classify(state, _registered())
        assert decision.label == "deferred"
        assert decision.reason == "bootstrap_inputs_missing"
        assert decision.confidence is None or math.isfinite(decision.confidence)

    @pytest.mark.parametrize("thr", [float("nan"), float("inf"), None, "0.7", -0.1, 1.5])
    def test_unusable_confidence_threshold_is_refused(self, thr):
        """A NaN threshold made both comparisons False and opened the gate."""
        with pytest.raises(ValueError, match="confidence_threshold"):
            classify(_round_state(), _registered(confidence_threshold=thr))


# ---------------------------------------------------------------------------
# B2 -- the guard must be as strong as the computation it protects
# ---------------------------------------------------------------------------

class TestBootstrapInputGuard:
    @pytest.mark.parametrize(
        "wt_values",
        [None, [], [1.0, 1.05, 0.95]],
        ids=["missing", "empty", "below_wt_replicate_min"],
    )
    def test_unusable_wt_values_all_defer(self, wt_values):
        """Empty failed open (stop at NaN) and short failed closed (conf 0.0).

        One replicate more or less flipped stop into continue_walking. All
        three regimes now reach the same deferral.
        """
        decision = classify(_round_state(wt_values=wt_values), _registered())
        assert decision.label == "deferred"
        assert decision.reason == "bootstrap_inputs_missing"
        assert decision.confidence is None

    def test_empty_activities_defer(self):
        decision = classify(_round_state(current_round_activities=[]), _registered())
        assert decision.label == "deferred"
        assert decision.reason == "bootstrap_inputs_missing"

    def test_enough_replicates_still_produces_a_measured_confidence(self):
        decision = classify(_round_state(), _registered())
        assert decision.confidence is not None
        assert math.isfinite(decision.confidence)


# ---------------------------------------------------------------------------
# B3 -- one non-finite activity must not make the decision order-dependent
# ---------------------------------------------------------------------------

class TestNonFiniteActivities:
    def test_same_multiset_in_either_order_is_refused_identically(self):
        """max([nan, 5.0]) is nan and max([5.0, nan]) is 5.0.

        The same measurements in a different row order used to produce
        opposite labels. Neither was correct, so both are refused.
        """
        nan = float("nan")
        first = _round_state(current_round_activities=[nan] + list(ACTIVITIES))
        last = _round_state(current_round_activities=list(ACTIVITIES) + [nan])

        with pytest.raises(ValueError, match="current_round_activities"):
            classify(first, _registered())
        with pytest.raises(ValueError, match="current_round_activities"):
            classify(last, _registered())

    def test_infinity_in_activities_is_refused(self):
        state = _round_state(current_round_activities=list(ACTIVITIES) + [float("inf")])
        with pytest.raises(ValueError, match="current_round_activities"):
            classify(state, _registered())

    def test_non_finite_wt_value_names_the_parameter(self):
        """Previously: AttributeError: 'float' object has no attribute 'numerator'."""
        state = _round_state(wt_values=[1.0, 1.05, float("nan"), 1.02])
        with pytest.raises(ValueError, match="wt_values"):
            classify(state, _registered())


# ---------------------------------------------------------------------------
# B4 -- a window below 2 is not a meaningful configuration
# ---------------------------------------------------------------------------

class TestT3Window:
    HIT_RATES = [0.9, 0.1, 0.2, 0.3]

    @pytest.mark.parametrize("window", [0, 1, -1])
    def test_window_below_two_is_refused(self, window):
        """window=0 meant the whole history (hit_rates[-0:] is hit_rates[0:])
        and window=1 reported "fewer than 2 data points" with four present.
        Window 0 and window 2 returned opposite verdicts on the same input.
        """
        with pytest.raises(ValueError, match="window"):
            compute_T3_magnitude(self.HIT_RATES, window)
        with pytest.raises(ValueError, match="window"):
            compute_T3(self.HIT_RATES, window)

    def test_window_below_two_is_refused_through_classify(self):
        with pytest.raises(ValueError, match="t3_window_rounds"):
            classify(_round_state(), _registered(t3_window_rounds=0))

    def test_window_two_still_reads_the_two_most_recent_rounds(self):
        assert compute_T3_magnitude(self.HIT_RATES, 2) == pytest.approx(0.1)
        assert compute_T3(self.HIT_RATES, 2) is False

    def test_short_history_still_reports_insufficient_rather_than_raising(self):
        assert compute_T3_magnitude([0.3], 2) is None
        assert compute_T3([0.3], 2) is None


# ---------------------------------------------------------------------------
# B5 -- the rules lived in docstrings and nowhere in code
# ---------------------------------------------------------------------------

class TestModelValidators:
    @staticmethod
    def _metrics(**overrides) -> RoundMetrics:
        base: dict[str, Any] = dict(
            round_id="r1",
            computed_at="2026-01-01T00:00:00Z",
            cumulative_beneficial=10,
            K_throughput=5,
            delta_best_ema=0.05,
            sigma_assay=0.1,
            r=3,
            hit_rates=[0.5, 0.4],
            top_k_positions_n=set(),
            top_k_positions_n1=set(),
            top_k_positions=[],
            active_residues=[],
            unused_beneficial_count=0,
            T1=True,
            T_unused=False,
        )
        base.update(overrides)
        return RoundMetrics(**base)

    @pytest.mark.parametrize(
        "field, value",
        [
            ("hit_rates", [-5.0, 2.0, float("nan")]),
            ("hit_rates", [0.5, 1.5]),
            ("hit_rates", [0.5, float("nan")]),
            ("sigma_assay", -1.0),
            ("sigma_assay", float("nan")),
            ("r", 0),
            ("K_throughput", -3),
            ("cumulative_beneficial", -9),
            ("unused_beneficial_count", -1),
            ("delta_best_ema", float("inf")),
        ],
    )
    def test_round_metrics_refuses_values_its_docstring_excludes(self, field, value):
        with pytest.raises(ValidationError):
            self._metrics(**{field: value})

    def test_round_metrics_still_accepts_a_valid_round(self):
        m = self._metrics()
        assert m.r == 3
        assert m.sigma_assay == 0.1

    @staticmethod
    def _log(**overrides) -> StrategyDecisionLog:
        base: dict[str, Any] = dict(
            round_id="r1",
            decided_at="2026-01-01T00:00:00Z",
            activation_mode="advisory",
            pre_registered_thresholds={},
            signal_inputs={},
            signal_scores={},
            bootstrap_distribution={},
            decision="stop",
            decision_confidence=0.8,
            reason="saturated_no_throughput",
            overridden_by_user=False,
            seed=1,
        )
        base.update(overrides)
        return StrategyDecisionLog(**base)

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.5])
    def test_log_refuses_a_confidence_outside_its_declared_range(self, value):
        with pytest.raises(ValidationError):
            self._log(decision_confidence=value)

    def test_audit_log_round_trips_when_no_bootstrap_ran(self):
        """A NaN confidence serialised to null and the model then rejected its
        own output, because the field was typed non-optional float. The absent
        state is now spelled None, which survives the round trip.
        """
        log = self._log(decision_confidence=None)
        restored = StrategyDecisionLog.model_validate_json(log.model_dump_json())
        assert restored.decision_confidence is None
        assert restored == log

    def test_audit_log_round_trips_with_a_measured_confidence(self):
        log = self._log(decision_confidence=0.8)
        restored = StrategyDecisionLog.model_validate_json(log.model_dump_json())
        assert restored.decision_confidence == 0.8


# ---------------------------------------------------------------------------
# B6 -- refuse ordinary bad input deliberately, naming the parameter
# ---------------------------------------------------------------------------

class TestDeliberateRefusals:
    def test_bootstrap_n_zero(self):
        """Previously ZeroDivisionError from the distribution denominator."""
        with pytest.raises(ValueError, match="bootstrap_n"):
            classify(_round_state(), _registered(bootstrap_n=0))

    @pytest.mark.parametrize(
        "call",
        [
            lambda: compute_T2_threshold(0.5, 0),
            lambda: compute_T2(0.1, 0.5, 0),
            lambda: compute_T_model(0.1, 0.5, 0),
        ],
        ids=["threshold", "T2", "T_model"],
    )
    def test_zero_replicates(self, call):
        """Previously ZeroDivisionError from inside a sqrt."""
        with pytest.raises(ValueError, match="r "):
            call()

    def test_sigma_unavailable_still_short_circuits_before_the_replicate_check(self):
        """NA on a missing sigma takes precedence, as it did before."""
        assert compute_T2(0.1, None, 0) is None
        assert compute_T_model(0.1, None, 0) is None

    @pytest.mark.parametrize("min_replicates", [0, 1])
    def test_wt_replicate_min_below_two(self, min_replicates):
        """Previously statistics.StatisticsError."""
        with pytest.raises(ValueError, match="min_replicates"):
            compute_sigma_assay([1.0, 2.0], min_replicates=min_replicates)
        with pytest.raises(ValueError, match="min_replicates"):
            compute_sigma_assay_ci([1.0, 2.0], min_replicates=min_replicates)

    def test_wt_replicate_min_below_two_through_classify(self):
        with pytest.raises(ValueError, match="wt_replicate_min"):
            classify(_round_state(), _registered(wt_replicate_min=1))

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_non_finite_wt_values_reach_a_named_error(self, bad):
        """Previously AttributeError: 'float' object has no attribute 'numerator'."""
        with pytest.raises(ValueError, match="wt_values"):
            compute_sigma_assay([1.0, 2.0, bad, 3.0])
        with pytest.raises(ValueError, match="wt_values"):
            compute_sigma_assay_ci([1.0, 2.0, bad, 3.0])


# ---------------------------------------------------------------------------
# B7 -- the docstring defines a set, so the code must divide by set size
# ---------------------------------------------------------------------------

class TestActiveFractionIsOverSets:
    def test_repeated_position_is_counted_once(self):
        """Fraction = |set(top_k) & set(active)| / |set(top_k)|.

        [1, 1, 1, 2] against active [1] is 0.5, not 0.75. top_k_positions is
        list[int] and repeats are ordinary input, so the two forms straddle a
        threshold of 0.6 in opposite directions.
        """
        assert compute_T_active([1, 1, 1, 2], [1], threshold=0.6) is False
        assert compute_T_active([1, 1, 1, 2], [1], threshold=0.4) is True

    def test_duplicate_free_input_is_unchanged(self):
        assert compute_T_active([1, 2, 3, 4], [1, 2], threshold=0.4) is True
        assert compute_T_active([1, 2, 3, 4], [1], threshold=0.4) is False

    def test_empty_inputs_still_report_insufficient_data(self):
        assert compute_T_active([], [1], threshold=0.4) is None
        assert compute_T_active([1], [], threshold=0.4) is None


# ---------------------------------------------------------------------------
# B8 -- the draws must run on the point-estimate signal set
# ---------------------------------------------------------------------------

class TestConfidenceSignalSetAlignment:
    def test_draws_cannot_use_a_sigma_the_point_estimate_lacked(self):
        """With sigma_assay None at the point estimate, T2* and T_model* are NA
        in every draw, so wt_values cannot influence the confidence at all.

        Before the fix the point estimate ran with T2 NA while every draw ran
        with T2 live, and because sat_now is an OR over (T2, T3, T_model),
        adding a signal to the draws could only inflate agreement.
        """
        registered = _registered()
        tight = _round_state(sigma_assay=None, wt_values=[1.0, 1.0, 1.0, 1.0])
        wide = _round_state(sigma_assay=None, wt_values=[0.1, 5.0, 0.2, 9.0])

        conf_tight, dist_tight = bootstrap_confidence(
            tight, registered, n_boot=500, seed=7
        )
        conf_wide, dist_wide = bootstrap_confidence(
            wide, registered, n_boot=500, seed=7
        )

        assert conf_tight == conf_wide
        assert dist_tight == dist_wide

    def test_a_sigma_the_point_estimate_had_still_drives_the_draws(self):
        """The alignment removes evidence the point estimate lacked; it does
        not stop the bootstrap from resampling evidence the point estimate had.
        """
        registered = _registered()
        tight = _round_state(sigma_assay=0.05, wt_values=[1.0, 1.0, 1.0, 1.0])
        wide = _round_state(sigma_assay=0.05, wt_values=[0.1, 5.0, 0.2, 9.0])

        _, dist_tight = bootstrap_confidence(tight, registered, n_boot=500, seed=7)
        _, dist_wide = bootstrap_confidence(wide, registered, n_boot=500, seed=7)

        assert dist_tight != dist_wide

    @pytest.mark.parametrize(
        "hit_rates",
        [[0.6, 0.52, 0.50], [0.6, 0.505, 0.50], [0.6, 0.51, 0.50], [0.6, 0.53, 0.50]],
    )
    def test_the_shipping_configuration_now_defers_instead_of_switching(self, hit_rates):
        """The handler forwards wt_values while passing sigma_assay=None, so
        this is the configuration that reaches the researcher. The inflated
        confidence cleared the 0.7 gate and printed a strategy switch; the
        aligned confidence falls below it and the decision is a deferral.
        """
        state = _round_state(hit_rates=hit_rates, cumulative_beneficial=10)
        decision = classify(state, _registered())

        assert decision.label == "deferred"
        assert decision.reason == "low_confidence"
        assert decision.confidence is not None
        assert decision.confidence < 0.7

    def test_confidence_counts_only_signals_the_point_estimate_carried(self):
        """T3 is the only live saturation signal here, so the confidence must
        equal the share of draws whose resampled T3 keeps the point label.
        """
        state = _round_state(hit_rates=[0.6, 0.52, 0.50], cumulative_beneficial=10)
        registered = _registered()
        conf, dist = bootstrap_confidence(state, registered, n_boot=2000, seed=11)

        assert 0.0 < conf < 0.7
        assert dist["switch_combinatorial"] == pytest.approx(conf)
        # A signal that is NA at the point estimate is NA in every draw, so no
        # draw may land on a label that needs T2 or T_model to be live.
        assert dist["stop"] == 0.0
