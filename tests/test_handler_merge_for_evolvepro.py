"""Unit tests for handle_merge_for_evolvepro — Phase B replicate merge integration.

8 scenarios from design spec §5:
  1. legacy-path        — no replicate data → replicate_stats=null
  2. authoritative-only — authoritative only → stats.authoritative_count=1
  3. fallback-fill      — fallback only → merged value filled
  4. mismatch-flag      — both present with large diff → mismatched list populated
  5. empty-list-error   — empty list in authoritative → ValueError (-32602)
  6. bad-notation       — unparseable short variant → ValueError (-32602)
  7. no-ref_seq         — replicate data without ref_seq → ValueError (-32602)
  8. export-blocked     — closed swap cycle -> severity=error -> ExportBlockedError
                          (-32004). A single open (unclosed) mismatch is
                          severity=warning and does NOT raise (see
                          TestExportBlockedWithReplicates below).

Test structure: all tests use _rounds directly (no sidecar process needed).
"""

from __future__ import annotations

import pytest

from sidecar_mame.handlers.activity import (
    ExportBlockedError,
    _rounds,
    handle_merge_for_evolvepro,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# ref_seq: length 100, position 89 (1-based) = index 88 = 'F'.
# Used by from_evolvepro("89W", REF_SEQ) → "F89W".
REF_SEQ = "A" * 88 + "F" + "A" * 11  # length 100, [88]='F'


@pytest.fixture(autouse=True)
def clear_rounds():
    """Isolate _rounds state between tests."""
    _rounds.clear()
    yield
    _rounds.clear()


def _seed_round(
    round_id: str = "round_1",
    mutation: str = "F89W",
    activity_value: float = 2.0,
) -> None:
    """Seed a minimal round with one mutant well (B03=mutation) and one WT well (A01)."""
    _rounds[round_id] = {
        "n": 1,
        "plate_meta": {
            "plates": [
                {"plate_id": "P01", "wt_wells": ["A01"], "control_wells": []}
            ]
        },
        "design": {
            "plateMap": [
                {"plate_id": "P01", "well_id": "B03", "mutation": mutation},
            ]
        },
        "genotype": {
            "verdict": [
                {"plate_id": "P01", "well_id": "B03", "called_mutation": mutation},
            ]
        },
        "activity": {
            "raw_records": [
                {
                    "plate_id": "P01", "well_id": "A01",
                    "value": 1.0, "replicate_idx": 1,
                    "is_wt": True, "source_file": "act.csv",
                },
                {
                    "plate_id": "P01", "well_id": "B03",
                    "value": activity_value, "replicate_idx": 1,
                    "is_wt": False, "source_file": "act.csv",
                },
            ]
        },
        "merged_table": [],
        "status": "ngs_done",
    }


def _seed_round_two_wells(
    round_id: str,
    mutation_a: str,
    mutation_b: str,
    activity_a: float,
    activity_b: float,
) -> None:
    """Seed a round with two mutant wells (B03=mutation_a, B04=mutation_b)
    plus one WT well (A01). Used to build closed 2-swap-cycle fixtures,
    which require >=2 wells/mutations (a single-well round can only ever
    produce an open, unclosed mismatch)."""
    _rounds[round_id] = {
        "n": 1,
        "plate_meta": {
            "plates": [
                {"plate_id": "P01", "wt_wells": ["A01"], "control_wells": []}
            ]
        },
        "design": {
            "plateMap": [
                {"plate_id": "P01", "well_id": "B03", "mutation": mutation_a},
                {"plate_id": "P01", "well_id": "B04", "mutation": mutation_b},
            ]
        },
        "genotype": {
            "verdict": [
                {"plate_id": "P01", "well_id": "B03", "called_mutation": mutation_a},
                {"plate_id": "P01", "well_id": "B04", "called_mutation": mutation_b},
            ]
        },
        "activity": {
            "raw_records": [
                {
                    "plate_id": "P01", "well_id": "A01",
                    "value": 1.0, "replicate_idx": 1,
                    "is_wt": True, "source_file": "act.csv",
                },
                {
                    "plate_id": "P01", "well_id": "B03",
                    "value": activity_a, "replicate_idx": 1,
                    "is_wt": False, "source_file": "act.csv",
                },
                {
                    "plate_id": "P01", "well_id": "B04",
                    "value": activity_b, "replicate_idx": 1,
                    "is_wt": False, "source_file": "act.csv",
                },
            ]
        },
        "merged_table": [],
        "status": "ngs_done",
    }


# ---------------------------------------------------------------------------
# Scenario 1: legacy-path
# ---------------------------------------------------------------------------

class TestLegacyPath:
    """No replicate data → replicate merge skipped, backwards compatible."""

    def test_replicate_stats_is_null(self):
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
        })
        assert res["replicate_stats"] is None

    def test_activity_merged_mean_is_null(self):
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
        })
        for row in res["merged"]:
            assert row["activity_merged_mean"] is None

    def test_existing_stats_fields_unchanged(self):
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
        })
        stats = res["stats"]
        assert stats["n_total_wells"] == 2
        assert stats["n_wt"] == 1
        assert res["export_blocked"] is False


# ---------------------------------------------------------------------------
# Scenario 2: authoritative-only
# ---------------------------------------------------------------------------

class TestAuthoritativeOnly:
    """authoritative has data, fallback is empty."""

    def test_replicate_stats_authoritative_count(self):
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"89W": [1.2, 1.3]},
            "fallback_measurements": {},
            "ref_seq": REF_SEQ,
        })
        rs = res["replicate_stats"]
        assert rs is not None
        assert rs["authoritative_count"] == 1
        assert rs["fallback_count"] == 0

    def test_activity_merged_mean_is_mean_of_replicates(self):
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"89W": [1.2, 1.3]},
            "fallback_measurements": {},
            "ref_seq": REF_SEQ,
        })
        # F89W row should have activity_merged_mean = mean([1.2, 1.3]) = 1.25
        f89w_rows = [r for r in res["merged"] if r["mutation"] == "F89W"]
        assert len(f89w_rows) == 1
        assert abs(f89w_rows[0]["activity_merged_mean"] - 1.25) < 1e-9

    def test_wt_keys_filtered_not_in_merged_dict(self):
        """WT key in authoritative must be silently dropped, not converted."""
        _seed_round()
        # Providing "WT" should not cause ValueError from from_evolvepro.
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"89W": [1.2, 1.3], "WT": [1.0, 1.0]},
            "fallback_measurements": {},
            "ref_seq": REF_SEQ,
        })
        # Only non-WT variant should be counted.
        rs = res["replicate_stats"]
        assert rs is not None
        assert rs["authoritative_count"] == 1  # "WT" filtered out


# ---------------------------------------------------------------------------
# Scenario 3: fallback-fill
# ---------------------------------------------------------------------------

class TestFallbackFill:
    """fallback has data, authoritative is empty."""

    def test_merged_count_reflects_fallback(self):
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {},
            "fallback_measurements": {"89W": [0.9, 1.1]},
            "ref_seq": REF_SEQ,
        })
        rs = res["replicate_stats"]
        assert rs is not None
        assert rs["merged_count"] == 1

    def test_activity_merged_mean_from_fallback(self):
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {},
            "fallback_measurements": {"89W": [0.9, 1.1]},
            "ref_seq": REF_SEQ,
        })
        f89w_rows = [r for r in res["merged"] if r["mutation"] == "F89W"]
        assert len(f89w_rows) == 1
        assert abs(f89w_rows[0]["activity_merged_mean"] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Scenario 4: mismatch-flag
# ---------------------------------------------------------------------------

class TestMismatchFlag:
    """Both sources present, mean difference exceeds threshold → mismatched list."""

    def test_mismatched_contains_variant(self):
        _seed_round()
        # auth_mean=1.55, fall_mean=1.05, diff=0.50 > threshold=0.1
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"89W": [1.5, 1.6]},
            "fallback_measurements": {"89W": [1.0, 1.1]},
            "mismatch_threshold": 0.1,
            "ref_seq": REF_SEQ,
        })
        rs = res["replicate_stats"]
        assert rs is not None
        assert "F89W" in rs["mismatched"]

    def test_authoritative_value_used_despite_mismatch(self):
        """Authoritative mean is used even when mismatch is flagged."""
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"89W": [1.5, 1.6]},
            "fallback_measurements": {"89W": [1.0, 1.1]},
            "mismatch_threshold": 0.1,
            "ref_seq": REF_SEQ,
        })
        f89w_rows = [r for r in res["merged"] if r["mutation"] == "F89W"]
        assert len(f89w_rows) == 1
        # auth_mean = (1.5 + 1.6) / 2 = 1.55
        assert abs(f89w_rows[0]["activity_merged_mean"] - 1.55) < 1e-9


# ---------------------------------------------------------------------------
# Scenario 5: empty-list-error
# ---------------------------------------------------------------------------

class TestEmptyListError:
    """Empty replicate list raises ValueError → dispatcher maps to -32602."""

    def test_empty_authoritative_list_raises_value_error(self):
        _seed_round()
        with pytest.raises(ValueError, match="empty list"):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": {},
                "authoritative_measurements": {"89W": []},
                "fallback_measurements": {},
                "ref_seq": REF_SEQ,
            })


# ---------------------------------------------------------------------------
# Scenario 6: bad-notation
# ---------------------------------------------------------------------------

class TestBadNotation:
    """Unparseable short variant key raises ValueError → -32602."""

    def test_invalid_key_raises_value_error(self):
        _seed_round()
        with pytest.raises(ValueError):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": {},
                "authoritative_measurements": {"invalidkey": [1.0]},
                "fallback_measurements": {},
                "ref_seq": REF_SEQ,
            })


# ---------------------------------------------------------------------------
# Scenario 7: missing ref_seq — fail-closed for non-WT replicate data
# ---------------------------------------------------------------------------


class TestMissingRefSeq:
    """Non-WT replicate data without ref_seq fails clearly (ValueError)."""

    def test_missing_ref_seq_raises_value_error(self):
        """No ref_seq with non-WT measurement → ValueError (-32602)."""
        _seed_round()
        with pytest.raises(ValueError, match="ref_seq is required"):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": {},
                "authoritative_measurements": {"89W": [1.2, 1.3]},
                # ref_seq intentionally omitted
            })

    def test_none_ref_seq_raises_value_error(self):
        """ref_seq=None with non-WT measurement → ValueError (-32602)."""
        _seed_round()
        with pytest.raises(ValueError, match="ref_seq is required"):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": {},
                "authoritative_measurements": {"89W": [1.0]},
                "ref_seq": None,
            })

    def test_empty_ref_seq_raises_value_error(self):
        """ref_seq="" (empty string) with non-WT measurement → ValueError (-32602)."""
        _seed_round()
        with pytest.raises(ValueError, match="ref_seq is required"):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": {},
                "authoritative_measurements": {"89W": [1.0]},
                "ref_seq": "",
            })

    def test_whitespace_only_ref_seq_raises_value_error(self):
        """ref_seq containing only whitespace is treated as missing."""
        _seed_round()
        with pytest.raises(ValueError, match="ref_seq is required"):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": {},
                "authoritative_measurements": {"89W": [1.0]},
                "ref_seq": "   ",
            })

    def test_explicit_ref_seq_succeeds(self):
        """Explicit non-empty ref_seq is trimmed and accepted."""
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"89W": [1.2, 1.3]},
            "ref_seq": f"  {REF_SEQ}  ",
        })
        assert res["replicate_stats"] is not None
        assert res["replicate_stats"]["authoritative_count"] == 1


# ---------------------------------------------------------------------------
# Scenario 7b: WT-only measurements do not require ref_seq
# ---------------------------------------------------------------------------


class TestWtOnlyMeasurements:
    """WT-only measurement keys are filtered; no non-WT data → ref_seq not required."""

    def test_wt_only_authoritative_no_ref_seq_required(self):
        """authoritative with only WT keys and no ref_seq → not an error."""
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"WT": [1.0, 1.1], "WT_1": [0.9]},
            # ref_seq intentionally omitted — must not raise
        })
        # All WT keys filtered → no replicate merge → replicate_stats is null.
        assert res["replicate_stats"] is None

    def test_wt_only_fallback_no_ref_seq_required(self):
        """fallback with only WT keys and no ref_seq → not an error."""
        _seed_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {},
            "fallback_measurements": {"WT": [1.0]},
            # ref_seq intentionally omitted — must not raise
        })
        assert res["replicate_stats"] is None

    def test_mixed_wt_and_non_wt_requires_ref_seq(self):
        """Mixed WT + non-WT keys: after WT filtering non-WT remains → ref_seq required."""
        _seed_round()
        with pytest.raises(ValueError, match="ref_seq is required"):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": {},
                "authoritative_measurements": {"WT": [1.0], "89W": [1.2]},
                # ref_seq intentionally omitted
            })


# ---------------------------------------------------------------------------
# Scenario 8: export-blocked (via label-swap with replicate data)
# ---------------------------------------------------------------------------

class TestExportBlockedWithReplicates:
    """Open label mismatch warns (not blocks) even with replicate data.

    A single unclosed mismatch (89W's measured value matches "OTHER" in
    prev EP, with no reverse OTHER->89W) does not confirm a real
    relabeling, so it is severity="warning" and does not raise
    ExportBlockedError (see sanity_check._group_swap_cycles: only closed
    cycles are severity="error").
    """

    def test_open_swap_mismatch_warns_without_export_blocked_error(self):
        _seed_round(activity_value=2.0)
        # prev EP: "OTHER" had activity=2.0, "89W" had 99.9.
        # Measured B03 activity=2.0 matches "OTHER" not "89W" → open mismatch.
        prev_ep = {"OTHER": 2.0, "89W": 99.9}
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": prev_ep,
            "authoritative_measurements": {"89W": [1.2, 1.3]},
            "fallback_measurements": {},
            "ref_seq": REF_SEQ,
        })
        assert res["export_blocked"] is False
        swap_warnings = res["stats"]["warnings"]
        assert any(
            w["severity"] == "warning" and w["code"] == "label_swap_cycle"
            for w in swap_warnings
        )


# ---------------------------------------------------------------------------
# Scenario 8b: export-blocked (closed 2-swap cycle -> severity=error)
# ---------------------------------------------------------------------------

class TestExportBlockedClosedCycle:
    """A closed 2-swap cycle raises ExportBlockedError.

    Two mutant wells are required to close a swap cycle: B03=F89W measured
    activity_a, B04=A50G measured activity_b. prev_round_evolvepro is
    constructed so each measured value matches the *other* variant's prior
    value (89W's measured value == prev "50G" value, and 50G's measured
    value == prev "89W" value). detect_label_swap then reports mismatch
    pairs (89W->50G) and (50G->89W), which _group_swap_cycles closes into
    a cycle (severity="error"), and handle_merge_for_evolvepro raises
    ExportBlockedError.

    Note on -32004: handle_merge_for_evolvepro itself only raises the plain
    ExportBlockedError (see activity.py — the numeric code is not an
    attribute of the exception). The -32004 mapping happens one layer up,
    in sidecar_mame/dispatcher.py's `except ExportBlockedError` branch
    (dispatcher.py:143-147, `_error(req_id, -32004, str(exc))`), which is
    only reachable via the JSON-RPC dispatch loop, not by calling the
    handler directly as these tests do. We assert the exception type here
    and cross-check the -32004 literal is still wired to ExportBlockedError
    in dispatcher.py source, without invoking the JSON-RPC loop.
    """

    def test_closed_swap_cycle_raises_export_blocked_error(self):
        _seed_round_two_wells(
            "round_1",
            mutation_a="F89W",
            mutation_b="A50G",
            activity_a=2.0,
            activity_b=3.0,
        )
        # prev EP: "89W" had 3.0 (== measured activity_b), "50G" had 2.0
        # (== measured activity_a) -> each well's value matches the
        # *other* variant's prior value -> closed 2-swap cycle.
        prev_ep = {"89W": 3.0, "50G": 2.0}
        with pytest.raises(ExportBlockedError):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": prev_ep,
                "authoritative_measurements": {},
                "fallback_measurements": {},
                "ref_seq": REF_SEQ,
            })

    def test_dispatcher_maps_export_blocked_error_to_minus_32004(self):
        """Source-level check that dispatcher.py still wires
        ExportBlockedError -> -32004 (see dispatcher.py:143-147)."""
        import inspect
        import sidecar_mame.dispatcher as dispatcher_module

        src = inspect.getsource(dispatcher_module._dispatch_handler)
        assert "except ExportBlockedError as exc:" in src
        assert "-32004" in src
