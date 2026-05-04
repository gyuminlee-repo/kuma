"""Tests for kuma_core.strategy.models — TDD Phase 6 Task 6.2.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A.4
Plan: notes/plans/2026-05-04-mame-activity-implementation-plan.md Phase 6
"""

from datetime import datetime, timezone
import pytest

from kuma_core.strategy.models import StrategyDecisionLog, RoundMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_log(**overrides) -> StrategyDecisionLog:
    """Minimal valid StrategyDecisionLog factory."""
    defaults = dict(
        round_id="round-001",
        decided_at=datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc),
        activation_mode="calibration",
        pre_registered_thresholds={"jaccard_threshold": 0.5, "M_min": 5},
        signal_inputs={
            "sigma_assay": 0.1,
            "r": 4,
            "best_n": 1.5,
            "best_n1": 1.3,
            "hit_rate_n": 0.3,
            "top_k_positions": [10, 20, 30],
        },
        signal_scores={"T1": True, "T2": False, "T3": False, "T4": True},
        bootstrap_distribution={
            "continue_walking": 0.05,
            "switch_combinatorial": 0.87,
            "stop": 0.0,
            "deferred": 0.08,
        },
        decision="deferred",
        decision_confidence=0.87,
        reason="calibration_period",
        overridden_by_user=False,
        override_note=None,
        seed=20260504,
        bootstrap_n=1000,
    )
    defaults.update(overrides)
    return StrategyDecisionLog(**defaults)


def _make_metrics(**overrides) -> RoundMetrics:
    """Minimal valid RoundMetrics factory."""
    defaults = dict(
        round_id="round-001",
        computed_at=datetime(2026, 5, 4, 10, 0, 0, tzinfo=timezone.utc),
        cumulative_beneficial=14,
        K_throughput=14,
        delta_best_ema=0.05,
        sigma_assay=0.1,
        r=4,
        hit_rates=[0.5, 0.4, 0.3],
        top_k_positions_n={10, 20, 30, 40},
        top_k_positions_n1={10, 20, 30, 50},
        top_k_positions=[10, 20, 30],
        active_residues=[10, 20],
        unused_beneficial_count=6,
        T1=True,
        T2=False,
        T3=True,
        T4=True,
        T_active=True,
        T_unused=True,
    )
    defaults.update(overrides)
    return RoundMetrics(**defaults)


# ---------------------------------------------------------------------------
# StrategyDecisionLog — construction + literals
# ---------------------------------------------------------------------------

def test_StrategyDecisionLog_all_decision_labels():
    for label in ["continue_walking", "switch_combinatorial", "stop", "deferred"]:
        log = _make_log(decision=label)
        assert log.decision == label


def test_StrategyDecisionLog_all_activation_modes():
    for mode in ["calibration", "advisory", "auto"]:
        log = _make_log(activation_mode=mode)
        assert log.activation_mode == mode


def test_StrategyDecisionLog_invalid_decision():
    with pytest.raises(Exception):
        _make_log(decision="unknown_decision")


def test_StrategyDecisionLog_invalid_activation_mode():
    with pytest.raises(Exception):
        _make_log(activation_mode="fully_auto")


def test_StrategyDecisionLog_required_fields_present():
    log = _make_log()
    assert log.round_id == "round-001"
    assert isinstance(log.decided_at, datetime)
    assert isinstance(log.pre_registered_thresholds, dict)
    assert isinstance(log.signal_inputs, dict)
    assert isinstance(log.signal_scores, dict)
    assert isinstance(log.bootstrap_distribution, dict)
    assert isinstance(log.decision_confidence, float)
    assert isinstance(log.reason, str)
    assert isinstance(log.overridden_by_user, bool)
    assert isinstance(log.seed, int)
    assert isinstance(log.bootstrap_n, int)


def test_StrategyDecisionLog_override_note_optional():
    log_no_note = _make_log(override_note=None)
    assert log_no_note.override_note is None
    log_with_note = _make_log(override_note="PI override: early switch")
    assert log_with_note.override_note == "PI override: early switch"


def test_StrategyDecisionLog_bootstrap_distribution_keys():
    log = _make_log()
    keys = set(log.bootstrap_distribution.keys())
    expected = {"continue_walking", "switch_combinatorial", "stop", "deferred"}
    assert keys == expected


def test_StrategyDecisionLog_signal_scores_mixed_types():
    # signal_scores can hold bool or float values
    log = _make_log(signal_scores={"T1": True, "T2": False, "T3": 0.7})
    assert log.signal_scores["T1"] is True
    assert log.signal_scores["T3"] == 0.7


def test_StrategyDecisionLog_confidence_bounds():
    # confidence is a float — no validation on bounds in schema, just type
    log = _make_log(decision_confidence=0.0)
    assert log.decision_confidence == 0.0
    log2 = _make_log(decision_confidence=1.0)
    assert log2.decision_confidence == 1.0


# ---------------------------------------------------------------------------
# RoundMetrics — construction
# ---------------------------------------------------------------------------

def test_RoundMetrics_all_signal_booleans():
    m = _make_metrics()
    assert m.T1 is True
    assert m.T2 is False
    assert m.T3 is True
    assert m.T4 is True
    assert m.T_active is True
    assert m.T_unused is True


def test_RoundMetrics_required_raw_inputs():
    m = _make_metrics()
    assert m.round_id == "round-001"
    assert isinstance(m.computed_at, datetime)
    assert m.cumulative_beneficial == 14
    assert m.K_throughput == 14
    assert isinstance(m.delta_best_ema, float)
    assert isinstance(m.sigma_assay, float)
    assert m.r == 4
    assert isinstance(m.hit_rates, list)
    assert isinstance(m.top_k_positions, list)
    assert isinstance(m.active_residues, list)
    assert m.unused_beneficial_count == 6


def test_RoundMetrics_sigma_assay_optional_none():
    # sigma_assay can be None (WT replicates < 4)
    m = _make_metrics(sigma_assay=None)
    assert m.sigma_assay is None


def test_RoundMetrics_top_k_sets():
    m = _make_metrics()
    assert isinstance(m.top_k_positions_n, (set, frozenset))
    assert isinstance(m.top_k_positions_n1, (set, frozenset))


def test_RoundMetrics_no_decision_field():
    # RoundMetrics must not have decision or decision_confidence fields
    m = _make_metrics()
    assert not hasattr(m, "decision")
    assert not hasattr(m, "decision_confidence")
