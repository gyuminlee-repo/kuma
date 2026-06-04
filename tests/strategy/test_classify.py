"""Truth-table tests for classify() v0.3 engine.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.2 / §12-A.2b

Key regression tests:
- P0-a: First plateau (sat_now=True, p=None) -> continue_walking(hysteresis_pending)
         NOT deferred -- validates prev=None path in _decide_core.
- P0-b: Stop gate symmetry -- bootstrap conf<0.7 -> continue_walking(stop_low_confidence)
         NOT unconditional stop -- validates stop branch confidence gate.

Bootstrap fixture design notes (see advisor guidance):
- Only T2 and T3 vary across resamples; T4/T_model/T_active/T_unused are frozen.
- For low-confidence cases: route saturation through T2 only (T4=None, T_model=None),
  set delta_best_ema borderline so ~half of T2 resamples flip False.
  Keep T3 borderline too so neither T2 nor T3 alone pins sat_now=True.
- For high-confidence cases: set T2 solidly True (delta far below threshold) AND T3=True.
- sat_prev must be True (via p.T2=True or similar) for saturation to be achievable.
- If T4 or T_model is True at point, sat_now is True in every resample
  (frozen) -> confidence pins near 1.0 -> low-confidence path unreachable.
"""

from __future__ import annotations

import math

import pytest

from kuma_core.strategy.classify import (
    RoundState,
    Signals,
    _decide_core,
    all_na,
    any_true,
    bootstrap_confidence,
    classify,
    compute_signals,
    effective_seed,
)
from kuma_core.strategy.signals import compute_sigma_assay, compute_T2_threshold


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registered(**overrides) -> dict:
    """Return a minimal registered dict with safe defaults."""
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


def _make_round_state(**overrides) -> RoundState:
    """Return a base RoundState suitable for most tests."""
    base = dict(
        n=4,
        previous_signals=None,
        cumulative_beneficial=10,
        K_throughput=5,
        delta_best_ema=0.01,
        sigma_assay=None,
        r=3,
        hit_rates=[0.4, 0.3],
        top_k_positions_n=set(),
        top_k_positions_n1=set(),
        top_k_positions=[],
        active_residues=[],
        unused_beneficial_count=0,
        n_designed=None,
        predicted_top_untested_gain=None,
        wt_values=None,
        current_round_activities=None,
        round_id=None,
    )
    base.update(overrides)
    return RoundState(**base)


# ---------------------------------------------------------------------------
# any_true / all_na unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_any_true_basic(self):
        assert any_true(True, False) is True

    def test_any_true_none_skipped(self):
        # None does not count as True or False
        assert any_true(None, None) is False

    def test_any_true_none_plus_true(self):
        assert any_true(None, True) is True

    def test_any_true_none_plus_false(self):
        assert any_true(None, False) is False

    def test_any_true_all_false(self):
        assert any_true(False, False) is False

    def test_all_na_all_none(self):
        assert all_na(None, None, None) is True

    def test_all_na_one_value(self):
        assert all_na(None, False) is False

    def test_all_na_true_present(self):
        assert all_na(None, True) is False

    def test_all_na_empty(self):
        # Edge: no args -> vacuously True
        assert all_na() is True


# ---------------------------------------------------------------------------
# _decide_core truth table
# ---------------------------------------------------------------------------

class TestDecideCore:
    def _s(self, **kw) -> Signals:
        defaults = dict(
            T1=False, T2=None, T3=None, T4=None,
            T_active=None, T_model=None, T_unused=False,
        )
        defaults.update(kw)
        return Signals(**defaults)

    def test_insufficient_data_all_na(self):
        s = self._s(T2=None, T3=None, T4=None, T_model=None)
        label, reason = _decide_core(s, None)
        assert label == "deferred"
        assert reason == "insufficient_data"

    # --- P0-a regression: first plateau (prev=None) -> hysteresis_pending ---
    def test_first_plateau_prev_none(self):
        """P0-a: sat_now=True but p=None -> sat_prev=False -> hysteresis_pending.

        Must NOT return deferred. This is the key first-plateau regression.
        """
        s = self._s(T2=True)
        label, reason = _decide_core(s, None)
        assert label == "continue_walking"
        assert reason == "hysteresis_pending"

    def test_hysteresis_pending_prev_no_sat(self):
        """sat_now=True, p defined but p has no saturation -> hysteresis_pending."""
        s = self._s(T2=True)
        p = self._s(T2=False, T3=False)
        label, reason = _decide_core(s, p)
        assert label == "continue_walking"
        assert reason == "hysteresis_pending"

    def test_no_saturation_signal(self):
        s = self._s(T2=False, T3=False, T4=False)
        p = self._s(T2=True)
        label, reason = _decide_core(s, p)
        assert label == "continue_walking"
        assert reason == "no_saturation_signal"

    def test_switch_combinatorial_core(self):
        s = self._s(T1=True, T2=True, T_unused=True)
        p = self._s(T2=True)
        label, reason = _decide_core(s, p)
        assert label == "switch_combinatorial"
        assert reason == "saturated_with_combinatorial_value"

    def test_stop_core(self):
        """Saturation + no combinatorial value -> stop."""
        s = self._s(T1=False, T2=True, T_unused=False, T_active=None)
        p = self._s(T2=True)
        label, reason = _decide_core(s, p)
        assert label == "stop"
        assert reason == "saturated_no_combinatorial_value"

    def test_t3_triggers_saturation(self):
        s = self._s(T1=True, T3=True, T_unused=True)
        p = self._s(T3=True)
        label, reason = _decide_core(s, p)
        assert label == "switch_combinatorial"

    def test_t_active_triggers_combinatorial_value(self):
        """T_active=True gives combinatorial value even when T_unused=False."""
        s = self._s(T1=True, T2=True, T_active=True, T_unused=False)
        p = self._s(T2=True)
        label, reason = _decide_core(s, p)
        assert label == "switch_combinatorial"

    def test_t1_false_kills_combinatorial_value(self):
        """T_unused=True but T1=False -> no combinatorial value -> stop path."""
        s = self._s(T1=False, T2=True, T_unused=True)
        p = self._s(T2=True)
        label, reason = _decide_core(s, p)
        assert label == "stop"

    def test_na_not_coerced_to_false_in_sat(self):
        """T2=None, T3=True -> sat_now=True (None skipped, T3 counts)."""
        s = self._s(T2=None, T3=True, T1=False)
        p = self._s(T3=True)
        label, reason = _decide_core(s, p)
        # saturation=True, combinatorial_value=False -> stop (before gate)
        assert label == "stop"


# ---------------------------------------------------------------------------
# classify calibration gate
# ---------------------------------------------------------------------------

class TestClassifyCalibration:
    def test_n_below_n_min(self):
        rs = _make_round_state(n=2)
        reg = _make_registered(N_min=3)
        d = classify(rs, reg)
        assert d.label == "continue_walking"
        assert d.reason == "calibration_period"

    def test_n_equals_n_min_not_calibration(self):
        """n == N_min: calibration gate does NOT fire (n < N_min required)."""
        # All saturation signals None -> deferred(insufficient_data)
        rs = _make_round_state(n=3, sigma_assay=None)
        reg = _make_registered(N_min=3)
        d = classify(rs, reg)
        assert d.reason != "calibration_period"

    def test_n_zero(self):
        rs = _make_round_state(n=0)
        reg = _make_registered(N_min=3)
        d = classify(rs, reg)
        assert d.label == "continue_walking"
        assert d.reason == "calibration_period"


# ---------------------------------------------------------------------------
# classify: deferred paths
# ---------------------------------------------------------------------------

class TestClassifyDeferred:
    def test_insufficient_data_no_saturation_signals(self):
        rs = _make_round_state(n=4, sigma_assay=None, hit_rates=[0.4])
        reg = _make_registered()
        d = classify(rs, reg)
        assert d.label == "deferred"
        assert d.reason == "insufficient_data"

    def test_bootstrap_inputs_missing_switch_path(self):
        """Gated branch (switch) without bootstrap inputs -> deferred."""
        p = Signals(T1=True, T2=True, T3=None, T4=None,
                    T_active=None, T_model=None, T_unused=True)
        rs = _make_round_state(
            n=4,
            previous_signals=p,
            cumulative_beneficial=10,
            K_throughput=5,
            unused_beneficial_count=6,
            # sigma_assay fixed so T2 can fire via legacy method
            sigma_assay=0.1,
            r=3,
            delta_best_ema=0.0001,  # well below legacy threshold
            hit_rates=[0.4, 0.3],
            wt_values=None,               # bootstrap unavailable
            current_round_activities=None,
        )
        reg = _make_registered(t2_null_method="legacy")
        d = classify(rs, reg)
        assert d.label == "deferred"
        assert d.reason == "bootstrap_inputs_missing"

    def test_bootstrap_inputs_missing_stop_path(self):
        """Gated branch (stop) without bootstrap inputs -> deferred."""
        p = Signals(T1=False, T2=True, T3=None, T4=None,
                    T_active=None, T_model=None, T_unused=False)
        rs = _make_round_state(
            n=4,
            previous_signals=p,
            cumulative_beneficial=2,
            K_throughput=5,
            unused_beneficial_count=0,
            sigma_assay=0.1,
            r=3,
            delta_best_ema=0.0001,
            hit_rates=[0.4, 0.3],
            wt_values=None,
            current_round_activities=None,
        )
        reg = _make_registered(t2_null_method="legacy")
        d = classify(rs, reg)
        assert d.label == "deferred"
        assert d.reason == "bootstrap_inputs_missing"


# ---------------------------------------------------------------------------
# Bootstrap fixture helpers
# ---------------------------------------------------------------------------

def _make_switch_state(*, delta_borderline: bool) -> tuple[RoundState, dict]:
    """Build a switch_combinatorial fixture.

    Bootstrap design:
    - Only T2 and T3 vary across resamples (T4=None, T_model=None, T_active=None).
    - sat_prev = True via p.T2=True.
    - combinatorial_value = True via T1=True, T_unused=True (frozen).
    - wt_values: 4 replicates with sigma computed from them.
    - r=3, method="legacy": legacy threshold = 1.96 * sigma * sqrt(2/3).
    - For HIGH confidence: delta well below threshold -> T2=True in almost all resamples.
    - For LOW confidence: delta = thr * 0.98 (just below), hit_rates borderline
      so resampled sigma fluctuations flip T2, resampled hit_rates flip T3.
    """
    wt_values = [1.0, 1.0, 1.5, 0.5]
    sigma = compute_sigma_assay(wt_values, min_replicates=4)
    assert sigma is not None
    thr = compute_T2_threshold(sigma, r=3, method="legacy")

    if not delta_borderline:
        delta = thr * 0.02
        hit_rates = [0.8, 0.3]  # clearly declining -> T3=True
    else:
        delta = thr * 0.98  # just below -> T2=True at point, flips in resamples
        hit_rates = [0.55, 0.52]  # nearly flat -> T3 flips easily

    p = Signals(
        T1=True, T2=True, T3=None, T4=None,
        T_active=None, T_model=None, T_unused=True,
    )

    activities = [0.5, 0.8, 1.2, 0.3, 0.9, 1.5]

    rs = RoundState(
        n=5,
        previous_signals=p,
        cumulative_beneficial=10,
        K_throughput=5,
        delta_best_ema=delta,
        sigma_assay=sigma,
        r=3,
        hit_rates=hit_rates,
        top_k_positions_n=set(),
        top_k_positions_n1=set(),
        top_k_positions=[],
        active_residues=[],
        unused_beneficial_count=6,
        n_designed=None,
        predicted_top_untested_gain=None,
        wt_values=wt_values,
        current_round_activities=activities,
        round_id="round_5",
    )
    reg = _make_registered(
        t2_null_method="legacy",
        t3_window_rounds=2,
        tau_pos=0.0,
        confidence_threshold=0.7,
        bootstrap_n=2000,
    )
    return rs, reg


def _make_stop_state(*, delta_borderline: bool) -> tuple[RoundState, dict]:
    """Build a stop fixture (saturation + no combinatorial value).

    cumulative_beneficial < K_throughput so T1=False.
    T_unused=False (unused_beneficial_count=0), T_active=None (empty lists).
    """
    wt_values = [1.0, 1.0, 1.5, 0.5]
    sigma = compute_sigma_assay(wt_values, min_replicates=4)
    assert sigma is not None
    thr = compute_T2_threshold(sigma, r=3, method="legacy")

    if not delta_borderline:
        delta = thr * 0.02
        hit_rates = [0.8, 0.3]
    else:
        delta = thr * 0.98
        hit_rates = [0.55, 0.52]

    p = Signals(
        T1=False, T2=True, T3=None, T4=None,
        T_active=None, T_model=None, T_unused=False,
    )

    activities = [0.5, 0.8, 1.2, 0.3, 0.9, 1.5]

    rs = RoundState(
        n=5,
        previous_signals=p,
        cumulative_beneficial=2,
        K_throughput=5,
        delta_best_ema=delta,
        sigma_assay=sigma,
        r=3,
        hit_rates=hit_rates,
        top_k_positions_n=set(),
        top_k_positions_n1=set(),
        top_k_positions=[],
        active_residues=[],
        unused_beneficial_count=0,
        n_designed=None,
        predicted_top_untested_gain=None,
        wt_values=wt_values,
        current_round_activities=activities,
        round_id="round_5",
    )
    reg = _make_registered(
        t2_null_method="legacy",
        t3_window_rounds=2,
        tau_pos=0.0,
        confidence_threshold=0.7,
        bootstrap_n=2000,
    )
    return rs, reg


# ---------------------------------------------------------------------------
# classify: switch_combinatorial with confidence gate
# ---------------------------------------------------------------------------

class TestClassifySwitch:
    def test_switch_high_confidence(self):
        """Solid saturation -> switch_combinatorial with conf >= 0.7."""
        rs, reg = _make_switch_state(delta_borderline=False)
        d = classify(rs, reg)
        assert d.label == "switch_combinatorial"
        assert d.reason == "saturated_with_combinatorial_value"
        assert d.confidence is not None
        assert d.confidence >= 0.7
        assert d.bootstrap_distribution is not None
        assert set(d.bootstrap_distribution.keys()) == {
            "continue_walking", "switch_combinatorial", "stop", "deferred"
        }

    def test_switch_low_confidence(self):
        """Borderline saturation: gate must fire correctly per confidence level."""
        rs, reg = _make_switch_state(delta_borderline=True)
        d = classify(rs, reg)
        if d.confidence is not None and d.confidence < 0.7:
            assert d.label == "deferred"
            assert d.reason == "low_confidence"
        elif d.label == "switch_combinatorial":
            assert d.confidence is not None and d.confidence >= 0.7
        else:
            pytest.fail(f"Unexpected result: label={d.label} reason={d.reason} conf={d.confidence}")

    def test_switch_returns_distribution(self):
        """switch_combinatorial decision includes bootstrap_distribution."""
        rs, reg = _make_switch_state(delta_borderline=False)
        d = classify(rs, reg)
        assert d.bootstrap_distribution is not None
        total = sum(d.bootstrap_distribution.values())
        assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# classify: stop gate symmetry (P0-b regression)
# ---------------------------------------------------------------------------

class TestClassifyStopGate:
    """P0-b: stop branch uses the SAME confidence gate as switch_combinatorial.

    Below threshold -> continue_walking(stop_low_confidence), NOT deferred.
    """

    def test_stop_high_confidence(self):
        """Solid saturation + no value -> stop with conf >= 0.7."""
        rs, reg = _make_stop_state(delta_borderline=False)
        d = classify(rs, reg)
        assert d.label == "stop"
        assert d.reason == "saturated_no_combinatorial_value"
        assert d.confidence is not None
        assert d.confidence >= 0.7

    def test_stop_low_confidence_falls_back_to_continue(self):
        """P0-b regression: stop + conf < 0.7 -> continue_walking(stop_low_confidence).

        This is the key symmetry assertion: stop is NOT unconditional,
        and it does NOT fall back to deferred (unlike switch).
        """
        rs, reg = _make_stop_state(delta_borderline=True)
        d = classify(rs, reg)
        if d.confidence is not None and d.confidence < 0.7:
            assert d.label == "continue_walking"
            assert d.reason == "stop_low_confidence"
        elif d.label == "stop":
            assert d.confidence is not None and d.confidence >= 0.7
        else:
            pytest.fail(f"Unexpected: label={d.label} reason={d.reason} conf={d.confidence}")

    def test_stop_does_not_return_deferred_on_low_conf(self):
        """stop branch must NEVER return deferred regardless of confidence.

        Forcibly check the asymmetry: deferred is the fallback for switch,
        continue_walking is the fallback for stop.
        """
        rs, reg = _make_stop_state(delta_borderline=True)
        reg["confidence_threshold"] = 0.999  # force low confidence path
        d = classify(rs, reg)
        # With threshold=0.999, almost certainly conf < threshold.
        # The stop fallback must be continue_walking, not deferred.
        assert d.label in ("continue_walking", "stop")
        assert d.label != "deferred"


# ---------------------------------------------------------------------------
# P0-a regression: first plateau
# ---------------------------------------------------------------------------

class TestFirstPlateau:
    """P0-a: When previous_signals is None, sat_prev=False.

    sat_now=True but saturation=False -> hysteresis_pending.
    Must NOT return deferred(insufficient_data).
    """

    def test_first_plateau_via_classify(self):
        wt_values = [1.0, 1.2, 0.8, 1.1]
        sigma = compute_sigma_assay(wt_values, min_replicates=4)
        assert sigma is not None
        thr = compute_T2_threshold(sigma, r=3, method="legacy")

        rs = RoundState(
            n=3,
            previous_signals=None,   # No prior round
            cumulative_beneficial=10,
            K_throughput=5,
            delta_best_ema=thr * 0.5,   # T2=True (plateau detected)
            sigma_assay=sigma,
            r=3,
            hit_rates=[0.5, 0.3],       # T3=True
            top_k_positions_n=set(),
            top_k_positions_n1=set(),
            top_k_positions=[],
            active_residues=[],
            unused_beneficial_count=0,
            n_designed=None,
            predicted_top_untested_gain=None,
            wt_values=None,
            current_round_activities=None,
        )
        reg = _make_registered(t2_null_method="legacy", N_min=3)
        d = classify(rs, reg)
        # sat_now=True but prev=None -> sat_prev=False -> hysteresis_pending
        assert d.label == "continue_walking"
        assert d.reason == "hysteresis_pending"


# ---------------------------------------------------------------------------
# effective_seed determinism
# ---------------------------------------------------------------------------

class TestEffectiveSeed:
    def test_same_inputs_same_seed(self):
        rs = _make_round_state(n=5, round_id="round_5")
        reg = _make_registered()
        s1 = effective_seed(rs, reg)
        s2 = effective_seed(rs, reg)
        assert s1 == s2

    def test_different_thresholds_different_seed(self):
        rs = _make_round_state(n=5, round_id="round_5")
        reg_a = _make_registered(confidence_threshold=0.7)
        reg_b = _make_registered(confidence_threshold=0.8)
        assert effective_seed(rs, reg_a) != effective_seed(rs, reg_b)

    def test_different_round_id_different_seed(self):
        rs_a = _make_round_state(n=5, round_id="round_5")
        rs_b = _make_round_state(n=5, round_id="round_6")
        reg = _make_registered()
        assert effective_seed(rs_a, reg) != effective_seed(rs_b, reg)

    def test_fallback_round_id_uses_n(self):
        """round_id=None falls back to str(n). Same result as round_id=str(n)."""
        rs_none = _make_round_state(n=7, round_id=None)
        rs_str = _make_round_state(n=7, round_id="7")
        reg = _make_registered()
        assert effective_seed(rs_none, reg) == effective_seed(rs_str, reg)


# ---------------------------------------------------------------------------
# Bootstrap reproducibility
# ---------------------------------------------------------------------------

class TestBootstrapReproducibility:
    def test_same_seed_same_distribution(self):
        rs, reg = _make_switch_state(delta_borderline=False)
        reg["bootstrap_n"] = 500
        fixed_seed = 9999

        conf1, dist1 = bootstrap_confidence(rs, reg, n_boot=500, seed=fixed_seed)
        conf2, dist2 = bootstrap_confidence(rs, reg, n_boot=500, seed=fixed_seed)

        assert conf1 == conf2
        assert dist1 == dist2

    def test_different_seed_distribution_still_valid(self):
        """Both seeds produce valid probability distributions summing to 1."""
        rs, reg = _make_switch_state(delta_borderline=True)
        reg["bootstrap_n"] = 200

        _, dist1 = bootstrap_confidence(rs, reg, n_boot=200, seed=1)
        _, dist2 = bootstrap_confidence(rs, reg, n_boot=200, seed=99999)

        total1 = sum(dist1.values())
        total2 = sum(dist2.values())
        assert abs(total1 - 1.0) < 1e-9
        assert abs(total2 - 1.0) < 1e-9

    def test_missing_wt_values_returns_nan(self):
        rs = _make_round_state(wt_values=None, current_round_activities=[1.0, 2.0])
        reg = _make_registered()
        conf, dist = bootstrap_confidence(rs, reg, n_boot=100, seed=1)
        assert math.isnan(conf)
        assert dist == {}

    def test_missing_activities_returns_nan(self):
        rs = _make_round_state(wt_values=[1.0, 1.2, 0.8, 1.1], current_round_activities=None)
        reg = _make_registered()
        conf, dist = bootstrap_confidence(rs, reg, n_boot=100, seed=1)
        assert math.isnan(conf)
        assert dist == {}


# ---------------------------------------------------------------------------
# compute_signals integration (basic wiring check)
# ---------------------------------------------------------------------------

class TestComputeSignals:
    def test_signals_types(self):
        """compute_signals returns a Signals with correct types."""
        rs = _make_round_state(
            n=4,
            cumulative_beneficial=10,
            K_throughput=5,
            sigma_assay=0.5,
            r=3,
            delta_best_ema=0.01,
            hit_rates=[0.5, 0.4],
            unused_beneficial_count=6,
        )
        reg = _make_registered(t2_null_method="legacy")
        s = compute_signals(rs, reg)
        assert isinstance(s.T1, bool)
        assert isinstance(s.T_unused, bool)
        assert s.T2 is None or isinstance(s.T2, bool)

    def test_t_model_none_when_no_gain_input(self):
        rs = _make_round_state(predicted_top_untested_gain=None, sigma_assay=0.5, r=3)
        reg = _make_registered()
        s = compute_signals(rs, reg)
        assert s.T_model is None

    def test_t1_true_when_beneficial_exceeds_k(self):
        rs = _make_round_state(cumulative_beneficial=10, K_throughput=5)
        reg = _make_registered()
        s = compute_signals(rs, reg)
        assert s.T1 is True

    def test_t1_false_when_beneficial_below_k(self):
        rs = _make_round_state(cumulative_beneficial=3, K_throughput=10)
        reg = _make_registered()
        s = compute_signals(rs, reg)
        assert s.T1 is False
