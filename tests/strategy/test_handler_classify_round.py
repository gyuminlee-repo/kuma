"""Tests for the ``strategy.classify_round`` JSON-RPC handler -- Fork D (v0.4).

Contract change: params are now ``{round_files, c_next}`` (xlsx paths).
The old ``{round_id}`` param and sidecar _rounds store are no longer used.

Test structure:
  TestValidation     -- missing/invalid params raise ValueError
  TestXlsxParsing    -- column validation and anti-fallback (bad xlsx)
  TestMultiRound     -- 2-3 round fixtures produce non-deferred Decision
  TestLog2Fc         -- current_round_activities == log2(activity) (AC2)
  TestMissingColumns -- missing Variant/activity columns raise ValueError
  TestZeroActivity   -- activity <= 0 raises ValueError (anti-fallback)

Fixture design (AC3 rationale):
  sigma_assay=None (no WT) -> T2=NA, T_model=NA.
  Decision engine uses T1 and T3 only.
  For non-deferred result without WT:
    - n_rounds >= N_min=3 to pass calibration gate
    - hit_rate rising -> T3=False -> no saturation -> continue_walking
  switch_combinatorial/stop require wt_values (bootstrap gate); unreachable
  without WT import -- this is correct per spec (sigma deferred).

anti-fallback: missing columns, bad Variant, activity<=0 all raise;
  no fabricated defaults.
"""

from __future__ import annotations

import math

import openpyxl
import pytest

from sidecar_mame.handlers.classify_round import (
    _compute_delta_best_ema,
    _load_xlsx,
    _round_metrics,
    handle_classify_round,
)


# ---------------------------------------------------------------------------
# Helpers to build synthetic xlsx fixtures
# ---------------------------------------------------------------------------

def _make_xlsx(path, rows):
    """Write a minimal xlsx with Variant + activity columns."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Variant", "activity"])
    for variant, activity in rows:
        ws.append([variant, activity])
    wb.save(path)


# ---------------------------------------------------------------------------
# TestValidation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_round_files_raises_value_error(self):
        with pytest.raises(ValueError, match="round_files"):
            handle_classify_round({})

    def test_empty_round_files_raises_value_error(self):
        with pytest.raises(ValueError, match="round_files"):
            handle_classify_round({"round_files": []})

    def test_bad_c_next_raises_value_error(self):
        with pytest.raises(ValueError, match="c_next"):
            handle_classify_round(
                {"round_files": [{"n": 1, "path": "/tmp/x.xlsx"}], "c_next": "bad"}
            )

    def test_missing_path_in_round_file_raises_value_error(self):
        with pytest.raises(ValueError, match="missing"):
            handle_classify_round({"round_files": [{"n": 1}]})


# ---------------------------------------------------------------------------
# TestXlsxParsing
# ---------------------------------------------------------------------------

class TestXlsxParsing:
    def test_file_not_found_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="not found"):
            handle_classify_round(
                {"round_files": [{"n": 1, "path": "/nonexistent/path/round.xlsx"}]}
            )

    def test_missing_variant_column_raises_value_error(self, tmp_path):
        bad_xlsx = tmp_path / "bad.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["SomeCol", "activity"])
        ws.append(["A100", 1.2])
        wb.save(str(bad_xlsx))
        with pytest.raises(ValueError, match="Variant"):
            handle_classify_round(
                {"round_files": [{"n": 1, "path": str(bad_xlsx)}]}
            )

    def test_missing_activity_column_raises_value_error(self, tmp_path):
        bad_xlsx = tmp_path / "bad.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Variant", "Score"])
        ws.append(["100A", 1.2])
        wb.save(str(bad_xlsx))
        with pytest.raises(ValueError, match="activity"):
            handle_classify_round(
                {"round_files": [{"n": 1, "path": str(bad_xlsx)}]}
            )

    def test_variant_without_leading_integer_raises_value_error(self, tmp_path):
        bad_xlsx = tmp_path / "bad.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Variant", "activity"])
        ws.append(["NoPosition", 1.5])
        wb.save(str(bad_xlsx))
        with pytest.raises(ValueError, match="no leading integer"):
            handle_classify_round(
                {"round_files": [{"n": 1, "path": str(bad_xlsx)}]}
            )

    def test_activity_zero_raises_value_error(self, tmp_path):
        bad_xlsx = tmp_path / "bad.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Variant", "activity"])
        ws.append(["100A", 0.0])
        wb.save(str(bad_xlsx))
        with pytest.raises(ValueError, match="<= 0"):
            handle_classify_round(
                {"round_files": [{"n": 1, "path": str(bad_xlsx)}]}
            )

    def test_activity_negative_raises_value_error(self, tmp_path):
        bad_xlsx = tmp_path / "bad.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Variant", "activity"])
        ws.append(["100A", -0.5])
        wb.save(str(bad_xlsx))
        with pytest.raises(ValueError, match="<= 0"):
            handle_classify_round(
                {"round_files": [{"n": 1, "path": str(bad_xlsx)}]}
            )


# ---------------------------------------------------------------------------
# TestLog2Fc -- AC2: current_round_activities == log2(activity)
# ---------------------------------------------------------------------------

class TestLog2Fc:
    def test_round_metrics_log2_activities(self, tmp_path):
        activities = [1.0, 2.0, 0.5, 4.0]
        rows = [(f"{100+i}A", a) for i, a in enumerate(activities)]
        xlsx = tmp_path / "r1.xlsx"
        _make_xlsx(str(xlsx), rows)
        records = _load_xlsx(str(xlsx))
        metrics = _round_metrics(records)
        expected_log2 = [math.log2(a) for a in activities]
        assert metrics["log2_activities"] == pytest.approx(expected_log2)

    def test_beneficial_uses_activity_gt_1_strictly(self, tmp_path):
        """activity=1.0 is NOT beneficial; must be strictly > 1.0."""
        activities = [0.5, 1.0, 1.5, 2.0]
        rows = [(f"{100+i}A", a) for i, a in enumerate(activities)]
        xlsx = tmp_path / "r1.xlsx"
        _make_xlsx(str(xlsx), rows)
        records = _load_xlsx(str(xlsx))
        metrics = _round_metrics(records)
        assert metrics["beneficial_count"] == 2

    def test_hit_rate_matches_beneficial_fraction(self, tmp_path):
        activities = [0.5, 0.8, 1.2, 1.5]
        rows = [(f"{100+i}A", a) for i, a in enumerate(activities)]
        xlsx = tmp_path / "r1.xlsx"
        _make_xlsx(str(xlsx), rows)
        records = _load_xlsx(str(xlsx))
        metrics = _round_metrics(records)
        assert metrics["hit_rate"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TestEmaHelper
# ---------------------------------------------------------------------------

class TestEmaHelper:
    def test_single_round_returns_zero(self):
        assert _compute_delta_best_ema([2.0]) == pytest.approx(0.0)

    def test_two_rounds_ema_is_first_delta(self):
        assert _compute_delta_best_ema([1.0, 1.5]) == pytest.approx(0.5)

    def test_three_rounds_ema_value(self):
        # delta_0=0.5, delta_1=0.3; EMA_1 = 2/3*0.3 + 1/3*0.5
        expected = 2 / 3 * 0.3 + 1 / 3 * 0.5
        assert _compute_delta_best_ema([1.0, 1.5, 1.8]) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# TestMultiRound -- AC3: non-deferred Decision
# ---------------------------------------------------------------------------

_VALID_LABELS = frozenset({"continue_walking", "switch_combinatorial", "stop", "deferred"})
_NON_DEFERRED = frozenset({"continue_walking", "switch_combinatorial", "stop"})


class TestMultiRound:
    """Fixture design rationale:
    sigma=None -> T2=NA, T_model=NA.
    n_rounds=3 -> clears N_min=3 calibration gate (n >= N_min required).
    hit_rates rising across 3 rounds -> T3=False -> no saturation.
    Decision: continue_walking("no_saturation_signal") -- non-deferred.

    cumulative_beneficial varies; K_throughput=14 (c_next=96 default).
    T1=False (not enough beneficials) -- throughput not met.
    T3=False (rising trend) -> no saturation -> continue_walking.
    """

    def _make_3round_files(self, tmp_path):
        r1 = tmp_path / "r1.xlsx"
        _make_xlsx(
            str(r1),
            [(f"{100+i}A", 1.5 if i < 2 else 0.7) for i in range(10)],
        )
        r2 = tmp_path / "r2.xlsx"
        _make_xlsx(
            str(r2),
            [(f"{200+i}A", 1.5 if i < 4 else 0.7) for i in range(10)],
        )
        r3 = tmp_path / "r3.xlsx"
        _make_xlsx(
            str(r3),
            [(f"{300+i}A", 1.5 if i < 6 else 0.7) for i in range(10)],
        )
        return [
            {"n": 1, "path": str(r1)},
            {"n": 2, "path": str(r2)},
            {"n": 3, "path": str(r3)},
        ]

    def test_3round_returns_advisory_decision(self, tmp_path):
        result = handle_classify_round({"round_files": self._make_3round_files(tmp_path)})
        assert result["advisory"] == "decision"

    def test_3round_label_is_valid(self, tmp_path):
        result = handle_classify_round({"round_files": self._make_3round_files(tmp_path)})
        assert result["label"] in _VALID_LABELS

    def test_3round_non_deferred(self, tmp_path):
        """Rising hit_rate -> T3=False -> continue_walking (non-deferred).

        T3=False: slope > 0 (0.2->0.4->0.6 = positive slope).
        all_na(T2=NA, T3=False, T_model=NA) = False (T3 evaluated).
        sat_now = any_true(T2=NA, T3=False, T_model=NA) = False.
        => continue_walking(no_saturation_signal). Not deferred.
        """
        result = handle_classify_round({"round_files": self._make_3round_files(tmp_path)})
        assert result["label"] in _NON_DEFERRED, (
            f"Got {result['label']!r} reason={result.get('reason')!r}"
        )

    def test_3round_reason_non_empty(self, tmp_path):
        result = handle_classify_round({"round_files": self._make_3round_files(tmp_path)})
        assert isinstance(result["reason"], str) and result["reason"]

    def test_3round_confidence_none_or_float(self, tmp_path):
        result = handle_classify_round({"round_files": self._make_3round_files(tmp_path)})
        conf = result["confidence"]
        if conf is not None:
            assert isinstance(conf, float)
            assert 0.0 <= conf <= 1.0

    def test_2round_returns_advisory_decision(self, tmp_path):
        r1 = tmp_path / "r1.xlsx"
        r2 = tmp_path / "r2.xlsx"
        _make_xlsx(str(r1), [(f"{100+i}A", 1.3 if i < 3 else 0.6) for i in range(10)])
        _make_xlsx(str(r2), [(f"{200+i}A", 1.3 if i < 5 else 0.6) for i in range(10)])
        result = handle_classify_round(
            {"round_files": [{"n": 1, "path": str(r1)}, {"n": 2, "path": str(r2)}]}
        )
        assert result["advisory"] == "decision"

    def test_c_next_custom(self, tmp_path):
        """c_next=10 -> K=5; small throughput bar."""
        r1 = tmp_path / "r1.xlsx"
        r2 = tmp_path / "r2.xlsx"
        r3 = tmp_path / "r3.xlsx"
        _make_xlsx(str(r1), [(f"{100+i}A", 1.5 if i < 3 else 0.7) for i in range(10)])
        _make_xlsx(str(r2), [(f"{200+i}A", 1.5 if i < 5 else 0.7) for i in range(10)])
        _make_xlsx(str(r3), [(f"{300+i}A", 1.5 if i < 7 else 0.7) for i in range(10)])
        result = handle_classify_round(
            {
                "round_files": [
                    {"n": 1, "path": str(r1)},
                    {"n": 2, "path": str(r2)},
                    {"n": 3, "path": str(r3)},
                ],
                "c_next": 10,
            }
        )
        assert result["advisory"] == "decision"
        assert result["label"] in _VALID_LABELS

    def test_round_files_out_of_order_accepted(self, tmp_path):
        """round_files provided in wrong n-order are sorted correctly."""
        r1 = tmp_path / "r1.xlsx"
        r2 = tmp_path / "r2.xlsx"
        r3 = tmp_path / "r3.xlsx"
        _make_xlsx(str(r1), [(f"{100+i}A", 1.2 if i < 2 else 0.8) for i in range(8)])
        _make_xlsx(str(r2), [(f"{200+i}A", 1.2 if i < 4 else 0.8) for i in range(8)])
        _make_xlsx(str(r3), [(f"{300+i}A", 1.2 if i < 6 else 0.8) for i in range(8)])
        result = handle_classify_round(
            {
                "round_files": [
                    {"n": 3, "path": str(r3)},
                    {"n": 1, "path": str(r1)},
                    {"n": 2, "path": str(r2)},
                ]
            }
        )
        assert result["advisory"] == "decision"


# ---------------------------------------------------------------------------
# TestSingleRound -- calibration period degenerate case
# ---------------------------------------------------------------------------

class TestSingleRound:
    def test_1round_returns_calibration_period(self, tmp_path):
        """Single round (n=1 < N_min=3) returns continue_walking(calibration_period)."""
        r1 = tmp_path / "r1.xlsx"
        _make_xlsx(str(r1), [(f"{100+i}A", 1.5 if i < 3 else 0.7) for i in range(10)])
        result = handle_classify_round(
            {"round_files": [{"n": 1, "path": str(r1)}]}
        )
        assert result["advisory"] == "decision"
        assert result["label"] == "continue_walking"
        assert result["reason"] == "calibration_period"


# ---------------------------------------------------------------------------
# TestDecliningSaturation -- T3=True path -> deferred(bootstrap_inputs_missing)
# ---------------------------------------------------------------------------

class TestDecliningSaturation:
    """Fixture: 3 rounds with declining hit_rates [0.6, 0.4, 0.2].

    T3 uses a 2-round sliding window of hit_rates.  Negative slope
    (0.4->0.2 in window 2-3) signals saturation.  classify() enters
    switch/stop evaluation.  wt_values=None triggers the bootstrap gate:
      Decision(label="deferred", reason="bootstrap_inputs_missing").

    This test proves:
      (a) previous_signals chaining fires correctly (T3 reads prior signals).
      (b) saturated-looking data yields deferred rather than a fabricated label.
    """

    def _make_declining_3round(self, tmp_path):
        # Round 1: hit_rate=6/10=0.6, best=2.0
        r1 = tmp_path / "r1.xlsx"
        _make_xlsx(str(r1), [(f"{100+i}A", 2.0 if i < 6 else 0.5) for i in range(10)])
        # Round 2: hit_rate=4/10=0.4, best=1.8
        r2 = tmp_path / "r2.xlsx"
        _make_xlsx(str(r2), [(f"{200+i}A", 1.8 if i < 4 else 0.5) for i in range(10)])
        # Round 3: hit_rate=2/10=0.2, best=1.5
        r3 = tmp_path / "r3.xlsx"
        _make_xlsx(str(r3), [(f"{300+i}A", 1.5 if i < 2 else 0.5) for i in range(10)])
        return [
            {"n": 1, "path": str(r1)},
            {"n": 2, "path": str(r2)},
            {"n": 3, "path": str(r3)},
        ]

    def test_declining_hit_rate_returns_deferred(self, tmp_path):
        """T3 saturation signal -> bootstrap gate -> deferred."""
        result = handle_classify_round(
            {"round_files": self._make_declining_3round(tmp_path)}
        )
        assert result["advisory"] == "decision"
        assert result["label"] == "deferred", (
            f"Expected 'deferred' from saturation path; got {result['label']!r} "
            f"reason={result.get('reason')!r}"
        )
        assert result["reason"] == "bootstrap_inputs_missing", (
            f"Expected bootstrap_inputs_missing; got {result['reason']!r}"
        )

    def test_declining_confidence_is_none(self, tmp_path):
        """Deferred decisions carry no confidence score."""
        result = handle_classify_round(
            {"round_files": self._make_declining_3round(tmp_path)}
        )
        assert result["confidence"] is None

