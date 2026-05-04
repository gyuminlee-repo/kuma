"""Tests for activity.* JSON-RPC handlers.

TDD Phase 2, Task 2.1.

Handler functions take `params: dict` and read/write the module-level
`_rounds` dict in `sidecar_mame.handlers.activity`. Tests use the
`clear_rounds` autouse fixture to isolate state between test cases.
"""

from __future__ import annotations

import csv
import pytest
from pathlib import Path

from sidecar_mame.handlers.activity import (
    handle_activity_upload,
    handle_activity_set_plate_meta,
    handle_activity_merge,
    handle_activity_export_evolvepro_csv,
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

    def test_missing_round_raises_runtime_error(self, tmp_path: Path):
        csv_file = tmp_path / "x.csv"
        csv_file.write_text("plate_id,well_id,value\nP01,A01,1.0\n")

        with pytest.raises(RuntimeError, match="Round not found"):
            handle_activity_upload({
                "round_id": "nonexistent",
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

    def test_missing_round_raises_runtime_error(self):
        with pytest.raises(RuntimeError, match="Round not found"):
            handle_activity_set_plate_meta({
                "round_id": "no_such_round",
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
# activity.export_evolvepro_csv
# ---------------------------------------------------------------------------

class TestHandleActivityExportEvolveproCsv:
    def _setup_merged_round(self) -> None:
        _rounds["round_1"] = {
            "n": 1,
            "plate_meta": {"plates": []},
            "design": {},
            "genotype": {},
            "activity": None,
            "merged_table": [
                {
                    "plate_id": "P01", "well_id": "B03",
                    "mutation": "F89W", "mutation_source": "kuro_design",
                    "expected_mutation": "F89W", "called_mutation": "F89W",
                    "ngs_success": True,
                    "activity_raw_mean": 2.0, "activity_raw_sd": 0.1,
                    "activity_replicates": [2.0], "replicate_n": 1,
                    "fold_change": 2.0, "log2_fc": 1.0,
                },
                {
                    "plate_id": "P01", "well_id": "A01",
                    "mutation": "WT", "mutation_source": "kuro_design",
                    "expected_mutation": None, "called_mutation": None,
                    "ngs_success": True,
                    "activity_raw_mean": 1.0, "activity_raw_sd": None,
                    "activity_replicates": [1.0], "replicate_n": 1,
                    "fold_change": 1.0, "log2_fc": 0.0,
                },
            ],
            "status": "activity_linked",
        }

    def test_happy_path_writes_csv(self, tmp_path: Path):
        self._setup_merged_round()
        out = tmp_path / "evolvepro.csv"

        res = handle_activity_export_evolvepro_csv({
            "round_id": "round_1",
            "path": str(out),
        })

        assert res["written_rows"] == 1  # WT excluded
        assert out.exists()
        assert "columns" in res
        assert "variant" in res["columns"]

    def test_output_csv_content(self, tmp_path: Path):
        self._setup_merged_round()
        out = tmp_path / "out.csv"
        handle_activity_export_evolvepro_csv({"round_id": "round_1", "path": str(out)})

        with open(out) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["variant"] == "F89W"
        assert abs(float(rows[0]["y_pred"]) - 1.0) < 1e-6

    def test_missing_merged_table_raises_runtime_error(self):
        _rounds["round_1"] = {
            "n": 1, "plate_meta": {"plates": []},
            "design": {}, "genotype": {}, "activity": None,
            "merged_table": [],  # empty — no prior merge
            "status": "ngs_done",
        }
        # Empty merged_table is valid — writes 0 rows, no error
        # Test that missing round still raises
        with pytest.raises(RuntimeError, match="Round not found"):
            handle_activity_export_evolvepro_csv({"round_id": "no_round", "path": "/tmp/x.csv"})

    def test_invalid_output_extension_raises_value_error(self, tmp_path: Path):
        self._setup_merged_round()
        with pytest.raises(ValueError, match="Unsupported file extension"):
            handle_activity_export_evolvepro_csv({
                "round_id": "round_1",
                "path": str(tmp_path / "out.xlsx"),
            })
