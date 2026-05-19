"""Unit tests for handle_merge_for_evolvepro — Phase B replicate merge integration.

8 scenarios from design spec §5:
  1. legacy-path        — no replicate data → replicate_stats=null
  2. authoritative-only — authoritative only → stats.authoritative_count=1
  3. fallback-fill      — fallback only → merged value filled
  4. mismatch-flag      — both present with large diff → mismatched list populated
  5. empty-list-error   — empty list in authoritative → ValueError (-32602)
  6. bad-notation       — unparseable short variant → ValueError (-32602)
  7. no-ref_seq         — replicate data without ref_seq → ValueError (-32602)
  8. export-blocked     — swap_warnings severity=error → ExportBlockedError (-32004)

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
# Scenario 7: no-ref_seq  (OQ-④: auto-load IspS fallback)
# ---------------------------------------------------------------------------

# Real EGFP AA at position 89 (index 88) as returned by get_egfp_wt_aa_seq().
# Derived from fixtures/ispS.fa; used to seed the round with a realistic mutation.
_ISPS_AA89 = None  # resolved lazily in _seed_round_isps()


def _get_isps_aa89() -> str:
    """Return the actual IspS WT AA at 1-based position 89 (index 88)."""
    from kuma_core.mame.activity.ref_seq import get_egfp_wt_aa_seq
    return get_egfp_wt_aa_seq()[88]


def _seed_round_isps(round_id: str = "round_isps") -> str:
    """Seed a round using the real IspS position-89 AA. Returns mutation string."""
    wt_aa = _get_isps_aa89()
    mutation = f"{wt_aa}89W"
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
                    "value": 2.0, "replicate_idx": 1,
                    "is_wt": False, "source_file": "act.csv",
                },
            ]
        },
        "merged_table": [],
        "status": "ngs_done",
    }
    return mutation


class TestNoRefSeq:
    """OQ-④: ref_seq omission triggers IspS auto-load; explicit failure tested via monkeypatch."""

    def test_missing_ref_seq_auto_loads_isps(self):
        """No ref_seq → get_egfp_wt_aa_seq() called automatically → success."""
        from kuma_core.mame.activity.ref_seq import get_egfp_wt_aa_seq
        get_egfp_wt_aa_seq.cache_clear()
        mutation = _seed_round_isps()
        res = handle_merge_for_evolvepro({
            "round_id": "round_isps",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"89W": [1.2, 1.3]},
            # ref_seq intentionally omitted → auto-load
        })
        assert res["replicate_stats"] is not None
        assert res["replicate_stats"]["authoritative_count"] == 1
        get_egfp_wt_aa_seq.cache_clear()

    def test_explicit_none_ref_seq_auto_loads_isps(self):
        """ref_seq=None → same auto-load path as omission."""
        from kuma_core.mame.activity.ref_seq import get_egfp_wt_aa_seq
        get_egfp_wt_aa_seq.cache_clear()
        _seed_round_isps()
        res = handle_merge_for_evolvepro({
            "round_id": "round_isps",
            "prev_round_evolvepro": {},
            "authoritative_measurements": {"89W": [1.0]},
            "ref_seq": None,
        })
        assert res["replicate_stats"] is not None
        get_egfp_wt_aa_seq.cache_clear()

    def test_auto_load_failure_raises_value_error_with_message(self, monkeypatch):
        """When get_egfp_wt_aa_seq raises, ValueError includes 'EGFP auto-load failed'.

        The handler uses a lazy "from ... import get_egfp_wt_aa_seq" inside the
        function body.  Patching sys.modules ensures the function call inside the
        handler sees the mock regardless of import timing.
        """
        import sys
        import kuma_core.mame.activity.ref_seq as ref_seq_module

        def _raise(*a, **kw):
            raise FileNotFoundError("mocked missing file")

        # Patch the module attribute so the lazy import inside the handler gets
        # the mock (handler calls get_egfp_wt_aa_seq() after importing it from
        # the module at call time).
        monkeypatch.setattr(ref_seq_module, "get_egfp_wt_aa_seq", _raise)
        # Also ensure the module cached in sys.modules is the patched one.
        sys.modules["kuma_core.mame.activity.ref_seq"] = ref_seq_module
        _seed_round()
        with pytest.raises(ValueError, match="EGFP auto-load failed"):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": {},
                "authoritative_measurements": {"89W": [1.0]},
                # ref_seq intentionally omitted
            })


# ---------------------------------------------------------------------------
# Scenario 8: export-blocked (via label-swap with replicate data)
# ---------------------------------------------------------------------------

class TestExportBlockedWithReplicates:
    """Export blocked when swap warning severity=error detected, even with replicate data."""

    def test_swap_warning_raises_export_blocked_error(self):
        _seed_round(activity_value=2.0)
        # prev EP: "OTHER" had activity=2.0, "89W" had 99.9.
        # Measured B03 activity=2.0 matches "OTHER" not "89W" → swap detected.
        prev_ep = {"OTHER": 2.0, "89W": 99.9}
        with pytest.raises(ExportBlockedError):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": prev_ep,
                "authoritative_measurements": {"89W": [1.2, 1.3]},
                "fallback_measurements": {},
                "ref_seq": REF_SEQ,
            })
