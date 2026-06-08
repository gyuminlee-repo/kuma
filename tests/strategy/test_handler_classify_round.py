"""Tests for the ``strategy.classify_round`` JSON-RPC handler.

Two cases prove reachability and correctness:

Case A (unavailable): round exists but lacks required scalar plumbing fields.
  Assert advisory=="unavailable" and the four required missing field names.

Case B (synthetic): round dict pre-populated with all required scalars.
  Assert advisory=="decision" and that a valid DecisionLabel is returned.
  This exercises the real classify() code path through the handler.

Anti-fallback discipline: no values are fabricated to make classify() run
in production.  The synthetic fixture is a legitimate test tool.

Isolation: _rounds is cleared before/after each test via autouse fixture
(same pattern as test_handler_activity.py).
"""

from __future__ import annotations

import pytest

from sidecar_mame.handlers.activity import _rounds
from sidecar_mame.handlers.classify_round import handle_classify_round


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_rounds():
    """Reset _rounds state before and after every test."""
    _rounds.clear()
    yield
    _rounds.clear()


def _seed_partial_round(round_id: str = "r1") -> None:
    """Seed a round that has only the basic activity fields (no plumbing scalars)."""
    _rounds[round_id] = {
        "n": 4,
        "status": "ngs_done",
        "plate_meta": {"plates": []},
        "merged_table": [
            {"is_wt": True, "activity_raw_mean": 1.0, "replicate_n": 3},
            {"is_wt": True, "activity_raw_mean": 1.1, "replicate_n": 3},
            {"is_wt": False, "activity_raw_mean": 2.5, "replicate_n": 3},
        ],
    }


def _seed_full_round(round_id: str = "r1") -> None:
    """Seed a round with all required RoundState fields present.

    Values are chosen to produce a deterministic classify() outcome.
    Matches defaults from _make_round_state() in test_classify.py:
    cumulative_beneficial=10, K_throughput=5, delta_best_ema=0.01,
    unused_beneficial_count=0, hit_rates=[0.4, 0.3], r=3.
    """
    _rounds[round_id] = {
        "n": 4,
        "status": "ngs_done",
        "plate_meta": {"plates": []},
        "merged_table": [
            {"is_wt": True, "activity_raw_mean": 1.0, "replicate_n": 3},
            {"is_wt": True, "activity_raw_mean": 1.1, "replicate_n": 3},
            {"is_wt": False, "activity_raw_mean": 2.5, "replicate_n": 3},
        ],
        # Plumbing scalars:
        "cumulative_beneficial": 10,
        "K_throughput": 5,
        "delta_best_ema": 0.01,
        "unused_beneficial_count": 0,
        # Plumbing lists (empty lists are valid):
        "hit_rates": [0.4, 0.3],
        "top_k_positions_n": [],
        "top_k_positions_n1": [],
        "top_k_positions": [],
        "active_residues": [],
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestHandleClassifyRoundValidation:
    def test_missing_round_id_raises_value_error(self):
        with pytest.raises(ValueError, match="round_id is required"):
            handle_classify_round({})

    def test_empty_round_id_raises_value_error(self):
        with pytest.raises(ValueError, match="round_id is required"):
            handle_classify_round({"round_id": ""})

    def test_unknown_round_id_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="Round not found"):
            handle_classify_round({"round_id": "nonexistent"})


# ---------------------------------------------------------------------------
# Case A: partial round -> unavailable
# ---------------------------------------------------------------------------

class TestHandleClassifyRoundUnavailable:
    def test_partial_round_returns_unavailable(self):
        """Round exists but lacks plumbing scalars; advisory should be unavailable."""
        _seed_partial_round()
        result = handle_classify_round({"round_id": "r1"})
        assert result["advisory"] == "unavailable"  # noqa: S101

    def test_missing_list_includes_required_scalars(self):
        """Missing list must include all four required scalar field names."""
        _seed_partial_round()
        result = handle_classify_round({"round_id": "r1"})
        missing = result["missing"]
        for field in (
            "cumulative_beneficial",
            "K_throughput",
            "delta_best_ema",
            "unused_beneficial_count",
        ):
            assert field in missing, f"Expected {field!r} in missing={missing!r}"  # noqa: S101

    def test_missing_list_includes_required_list_fields(self):
        """Missing list must include all required list/set field names."""
        _seed_partial_round()
        result = handle_classify_round({"round_id": "r1"})
        missing = result["missing"]
        for field in (
            "hit_rates",
            "top_k_positions_n",
            "top_k_positions_n1",
            "top_k_positions",
            "active_residues",
        ):
            assert field in missing, f"Expected {field!r} in missing={missing!r}"  # noqa: S101


# ---------------------------------------------------------------------------
# Case B: synthetic full round -> decision
# ---------------------------------------------------------------------------

_VALID_LABELS = frozenset(
    {"continue_walking", "switch_combinatorial", "stop", "deferred"}
)


class TestHandleClassifyRoundDecision:
    def test_full_round_returns_decision(self):
        """Synthetic round with all required scalars should reach classify() and return a Decision."""
        _seed_full_round()
        result = handle_classify_round({"round_id": "r1"})
        assert result["advisory"] == "decision"  # noqa: S101

    def test_label_is_valid_decision_label(self):
        """Returned label must be one of the four DecisionLabel literals."""
        _seed_full_round()
        result = handle_classify_round({"round_id": "r1"})
        assert result["label"] in _VALID_LABELS, f"Unexpected label: {result['label']!r}"  # noqa: S101

    def test_reason_is_non_empty_string(self):
        """Decision reason must be a non-empty string."""
        _seed_full_round()
        result = handle_classify_round({"round_id": "r1"})
        assert isinstance(result["reason"], str) and result["reason"]  # noqa: S101

    def test_confidence_is_none_or_float(self):
        """Confidence must be None or a float in [0.0, 1.0]."""
        _seed_full_round()
        result = handle_classify_round({"round_id": "r1"})
        conf = result["confidence"]
        if conf is not None:
            assert isinstance(conf, float)  # noqa: S101
            assert 0.0 <= conf <= 1.0, f"confidence out of range: {conf}"  # noqa: S101
