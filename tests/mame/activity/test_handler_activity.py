"""Tests for activity.* JSON-RPC handlers.

TDD Phase 2, Task 2.1.

Handler functions take `params: dict` and read/write the module-level
`_rounds` dict in `sidecar_mame.handlers.activity`. Tests use the
`clear_rounds` autouse fixture to isolate state between test cases.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from sidecar_mame.handlers.activity import (
    handle_activity_upload,
    handle_activity_set_plate_meta,
    handle_activity_merge,
    handle_merge_for_evolvepro,
    ExportBlockedError,
    _rounds,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_rounds():
    """Reset round state before every test."""
    _rounds.clear()
    yield
    _rounds.clear()


def _seed_round(round_id: str = "round_1", n: int = 1, extra: dict | None = None) -> None:
    """Seed a minimal round entry into _rounds for testing."""
    rd: dict = {
        "n": n,
        "plate_meta": {
            "plates": [
                {"plate_id": "P01", "wt_wells": ["A01"], "control_wells": []}
            ]
        },
        "design": {},
        "genotype": {},
        "activity": None,
        "merged_table": [],
        "status": "ngs_done",
    }
    if extra:
        rd.update(extra)
    _rounds[round_id] = rd


# ---------------------------------------------------------------------------
# activity.upload
# ---------------------------------------------------------------------------

class TestHandleActivityUpload:
    def test_happy_path_long_csv(self, tmp_path: Path):
        """Upload a valid long-format CSV; returns records list and empty warnings."""
        _seed_round()
        csv_file = tmp_path / "act.csv"
        csv_file.write_text("plate_id,well_id,value,replicate_idx\nP01,A01,1.0,1\nP01,B03,2.0,1\n")

        res = handle_activity_upload({
            "round_id": "round_1",
            "file_path": str(csv_file),
            "format": "long_csv",
        })

        assert "records" in res
        assert len(res["records"]) == 2
        assert res["warnings"] == []
        # activity persisted in state
        assert _rounds["round_1"]["activity"] is not None
        assert len(_rounds["round_1"]["activity"]["raw_records"]) == 2

    def test_wt_flag_set_correctly(self, tmp_path: Path):
        """is_wt field is True for wells listed in plate_meta wt_wells."""
        _seed_round()
        csv_file = tmp_path / "wt.csv"
        csv_file.write_text("plate_id,well_id,value\nP01,A01,1.0\nP01,B03,2.0\n")

        res = handle_activity_upload({
            "round_id": "round_1",
            "file_path": str(csv_file),
            "format": "long_csv",
        })

        by_well = {r["well_id"]: r for r in res["records"]}
        assert by_well["A01"]["is_wt"] is True
        assert by_well["B03"]["is_wt"] is False

    def test_missing_round_lazy_inits_round(self, tmp_path: Path):
        # Behaviour change: handle_activity_upload now lazily creates the round
        # so frontend addRound (which only mutates Zustand) does not require
        # a separate sidecar round.create RPC. Empty round_id still raises.
        csv_file = tmp_path / "x.csv"
        csv_file.write_text("plate_id,well_id,value\nP01,A01,1.0\n")

        res = handle_activity_upload({
            "round_id": "lazy_round",
            "file_path": str(csv_file),
            "format": "long_csv",
        })
        assert "records" in res
        assert _rounds["lazy_round"]["activity"]["raw_records"]

        with pytest.raises(ValueError, match="round_id"):
            handle_activity_upload({
                "round_id": "",
                "file_path": str(csv_file),
                "format": "long_csv",
            })

    def test_missing_file_raises_file_not_found(self):
        _seed_round()
        with pytest.raises(FileNotFoundError):
            handle_activity_upload({
                "round_id": "round_1",
                "file_path": "/nonexistent/path/act.csv",
                "format": "long_csv",
            })

    def test_invalid_extension_raises_value_error(self, tmp_path: Path):
        _seed_round()
        bad_file = tmp_path / "act.json"
        bad_file.write_text("{}")

        with pytest.raises(ValueError, match="Unsupported file extension"):
            handle_activity_upload({
                "round_id": "round_1",
                "file_path": str(bad_file),
                "format": "long_csv",
            })


# ---------------------------------------------------------------------------
# activity.set_plate_meta
# ---------------------------------------------------------------------------

class TestHandleActivitySetPlateMeta:
    def test_happy_path(self):
        _seed_round()
        new_meta = {
            "plates": [
                {"plate_id": "P02", "wt_wells": ["H12"], "control_wells": []}
            ]
        }

        res = handle_activity_set_plate_meta({
            "round_id": "round_1",
            "plate_meta": new_meta,
        })

        assert res == {"ok": True}
        assert _rounds["round_1"]["plate_meta"]["plates"][0]["plate_id"] == "P02"

    def test_missing_round_lazy_inits_round(self):
        # Behaviour change: handle_activity_set_plate_meta now lazily creates
        # the round to match the frontend addRound flow. Empty round_id still
        # raises ValueError (-32602).
        res = handle_activity_set_plate_meta({
            "round_id": "lazy_setmeta",
            "plate_meta": {"plates": []},
        })
        assert res == {"ok": True}
        assert _rounds["lazy_setmeta"]["plate_meta"] == {"plates": []}

        with pytest.raises(ValueError, match="round_id"):
            handle_activity_set_plate_meta({
                "round_id": "",
                "plate_meta": {"plates": []},
            })

    def test_missing_plate_meta_key_raises_key_error(self):
        _seed_round()
        with pytest.raises(KeyError):
            handle_activity_set_plate_meta({
                "round_id": "round_1",
                # plate_meta key omitted
            })


# ---------------------------------------------------------------------------
# activity.merge
# ---------------------------------------------------------------------------

class TestHandleActivityMerge:
    def _setup_round_with_activity(self, round_id: str = "round_1") -> None:
        """Seed round with design, genotype, and raw activity records."""
        _rounds[round_id] = {
            "n": 1,
            "plate_meta": {
                "plates": [
                    {"plate_id": "P01", "wt_wells": ["A01"], "control_wells": []}
                ]
            },
            "design": {
                "plateMap": [
                    {"plate_id": "P01", "well_id": "B03", "mutation": "F89W"},
                ]
            },
            "genotype": {
                "verdict": [
                    {"plate_id": "P01", "well_id": "B03", "called_mutation": "F89W"},
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

    def test_happy_path_returns_merged_rows_and_stats(self):
        self._setup_round_with_activity()

        res = handle_activity_merge({"round_id": "round_1"})

        assert "merged" in res
        assert "stats" in res
        assert len(res["merged"]) == 2  # WT + mutant
        stats = res["stats"]
        assert stats["n_total_wells"] == 2
        assert stats["n_ngs_success"] == 1  # B03 matches
        assert stats["n_wt"] == 1            # A01

    def test_status_updated_to_activity_linked(self):
        self._setup_round_with_activity()
        handle_activity_merge({"round_id": "round_1"})
        assert _rounds["round_1"]["status"] == "activity_linked"

    def test_merged_table_persisted_in_state(self):
        self._setup_round_with_activity()
        handle_activity_merge({"round_id": "round_1"})
        assert len(_rounds["round_1"]["merged_table"]) == 2

    def test_missing_round_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="Round not found"):
            handle_activity_merge({"round_id": "ghost_round"})

    def test_no_activity_data_returns_empty_merged(self):
        """When no activity records, merge still runs with empty activity."""
        _rounds["round_1"] = {
            "n": 1,
            "plate_meta": {"plates": [{"plate_id": "P01", "wt_wells": [], "control_wells": []}]},
            "design": {},
            "genotype": {},
            "activity": None,
            "merged_table": [],
            "status": "ngs_done",
        }

        res = handle_activity_merge({"round_id": "round_1"})
        assert res["merged"] == []
        assert res["stats"]["n_total_wells"] == 0


# ---------------------------------------------------------------------------
# B-5: mame.activity.merge_for_evolvepro
# ---------------------------------------------------------------------------

class TestHandleMergeForEvolvepro:
    """Tests for the new handle_merge_for_evolvepro handler (B-5)."""

    def _setup_round(self, round_id: str = "round_1") -> None:
        _rounds[round_id] = {
            "n": 1,
            "plate_meta": {
                "plates": [
                    {"plate_id": "P01", "wt_wells": ["A01"], "control_wells": []}
                ]
            },
            "design": {
                "plateMap": [
                    {"plate_id": "P01", "well_id": "B03", "mutation": "F89W"},
                ]
            },
            "genotype": {
                "verdict": [
                    {"plate_id": "P01", "well_id": "B03", "called_mutation": "F89W"},
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

    def _setup_round_two_wells(
        self,
        round_id: str = "round_1",
        mutation_a: str = "F89W",
        mutation_b: str = "A50G",
        activity_a: float = 2.0,
        activity_b: float = 3.0,
    ) -> None:
        """Two mutant wells, needed to close a 2-swap cycle (a single-well
        round can only ever produce an open, unclosed mismatch — see
        test_open_mismatch_warns_without_blocking_export above)."""
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

    def test_round1_no_prev_ep_returns_no_warnings(self):
        """round_n=1, prev_round_evolvepro={} → no swap warnings, export_blocked=False."""
        self._setup_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
        })
        assert "merged" in res
        assert "stats" in res
        assert res["export_blocked"] is False
        assert res["stats"]["warnings"] == []

    def test_response_contains_required_keys(self):
        self._setup_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
        })
        assert set(res.keys()) >= {"merged", "stats", "export_blocked"}

    def test_missing_round_id_param_raises_key_error(self):
        with pytest.raises(KeyError):
            handle_merge_for_evolvepro({
                "prev_round_evolvepro": {},
            })

    def test_nonexistent_round_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="Round not found"):
            handle_merge_for_evolvepro({
                "round_id": "no_such_round",
                "prev_round_evolvepro": {},
            })

    def test_open_mismatch_warns_without_blocking_export(self):
        """An open (unclosed) label mismatch is a warning, not an export block.

        F89W's measured value (2.0) coincidentally matches a different
        prev-round variant ("OTHER"), but there is no reverse mapping
        (OTHER -> 89W) to close the permutation, so this is ambiguous
        rather than a confirmed relabeling (see sanity_check._group_swap_cycles).
        """
        self._setup_round()
        prev_ep = {"OTHER": 2.0, "89W": 99.9}
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": prev_ep,
        })
        assert res["export_blocked"] is False
        swap_warnings = res["stats"]["warnings"]
        assert any(
            w["severity"] == "warning" and w["code"] == "label_swap_cycle"
            for w in swap_warnings
        )

    def test_closed_swap_cycle_raises_export_blocked_error(self):
        """A *closed* 2-swap cycle (both directions present) is severity=error
        and raises ExportBlockedError, unlike the open-mismatch case above.

        B03=F89W measured 2.0, B04=A50G measured 3.0. prev EP has "89W": 3.0
        (== measured activity_b) and "50G": 2.0 (== measured activity_a), so
        each well's value matches the *other* variant's prior value, closing
        the permutation (see sanity_check._group_swap_cycles).
        """
        self._setup_round_two_wells(
            mutation_a="F89W", mutation_b="A50G",
            activity_a=2.0, activity_b=3.0,
        )
        prev_ep = {"89W": 3.0, "50G": 2.0}
        with pytest.raises(ExportBlockedError):
            handle_merge_for_evolvepro({
                "round_id": "round_1",
                "prev_round_evolvepro": prev_ep,
            })

    def test_default_mismatch_threshold_applied(self):
        """Custom mismatch_threshold parameter is accepted without error."""
        self._setup_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
            "mismatch_threshold": 0.05,
        })
        assert res["export_blocked"] is False

    def test_stats_warnings_field_present(self):
        self._setup_round()
        res = handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
        })
        assert "warnings" in res["stats"]
        assert isinstance(res["stats"]["warnings"], list)

    def test_merged_table_persisted_in_state(self):
        self._setup_round()
        handle_merge_for_evolvepro({
            "round_id": "round_1",
            "prev_round_evolvepro": {},
        })
        assert len(_rounds["round_1"]["merged_table"]) == 2


class TestWtReplicateRowsEndToEnd:
    """upload -> merge wiring for dedicated WT replicate rows.

    The unit tests call merge_activity_with_genotype directly, so they cannot see
    whether the handler persists and restores wt_records. This covers that path.
    """

    def _upload(self, tmp_path: Path, round_id: str = "round_1") -> None:
        _seed_round(round_id)
        csv_path = tmp_path / "act.csv"
        # Plate WT well A01 = 1.0 while dedicated WT rows = 2.0, so the two
        # denominator definitions give different fold-change for B03.
        csv_path.write_text(
            "Sample Name,Area\n"
            "WT_1,2.0\nWT_2,2.0\nWT_3,2.0\n"
            "A01,1.0\nB03,2.0\n"
        )
        _rounds[round_id]["design"] = {
            "plateMap": [{"plate_id": "P01", "well_id": "B03", "mutation": "F89W"}]
        }
        _rounds[round_id]["genotype"] = {
            "verdict": [
                {"plate_id": "P01", "well_id": "B03", "called_mutation": "F89W"}
            ]
        }
        handle_activity_upload({"round_id": round_id, "file_path": str(csv_path)})

    def test_upload_persists_wt_records(self, tmp_path: Path):
        self._upload(tmp_path)
        stored = _rounds["round_1"]["activity"]["wt_records"]
        assert [r["sample_name"] for r in stored] == ["WT_1", "WT_2", "WT_3"]
        # WT labels stay out of the well-level records.
        assert all(
            r["well_id"] in ("A01", "B03")
            for r in _rounds["round_1"]["activity"]["raw_records"]
        )

    def test_merge_uses_dedicated_wt_denominator(self, tmp_path: Path):
        self._upload(tmp_path)
        res = handle_activity_merge({"round_id": "round_1"})
        b03 = next(r for r in res["merged"] if r["well_id"] == "B03")
        assert b03["fold_change"] == pytest.approx(1.0)  # 2.0 / mean(WT rows)
        assert res["stats"]["n_wt_replicate_rows"] == 3
        assert res["stats"]["n_plates_wt_from_replicates"] == 1

    def test_merge_for_evolvepro_uses_same_denominator(self, tmp_path: Path):
        self._upload(tmp_path)
        res = handle_merge_for_evolvepro(
            {"round_id": "round_1", "prev_round_evolvepro": {}}
        )
        b03 = next(r for r in res["merged"] if r["well_id"] == "B03")
        assert b03["fold_change"] == pytest.approx(1.0)
        # Provenance counters survive the stats rebuild that attaches warnings.
        assert res["stats"]["n_wt_replicate_rows"] == 3
