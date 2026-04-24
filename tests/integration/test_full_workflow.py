"""End-to-end Python integration: Kuro export → Mame meta read → match.

Simulates Task 10 Step 10.1 flow via the sidecar dispatchers directly:
1. Kuro `handle_export_excel` writes xlsx with project_id and kuma_version.
2. Mame `handle_read_kuma_meta` reads the same file and returns a dict.
3. project_id, kuma_version, kuro_module_version round-trip through the xlsx.

Runs without Tauri or an actual sidecar process; operates on in-process
handlers with state fixtures so that `project_id` binding between Kuro
output and Mame ingestion is verified at the data layer.
"""
from __future__ import annotations

import openpyxl
import pytest

from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.export import handle_export_excel
from sidecar_mame.handlers.kuma_meta import handle_read_kuma_meta
from kuma_core.mame.io.kuma_meta import read_kuma_meta
from kuma_core.shared.version import KUMA_VERSION, KURO_MODULE_VERSION


@pytest.fixture
def clean_state():
    """Reset sidecar_kuro state around each test."""
    with _state_lock:
        saved_results = list(_state.results)
        saved_mappings = list(_state.plate_mappings)
        saved_dedup = dict(_state.dedup_info) if _state.dedup_info else {}
        _state.results = []
        _state.plate_mappings = []
        _state.dedup_info = {}
    yield
    with _state_lock:
        _state.results = saved_results
        _state.plate_mappings = saved_mappings
        _state.dedup_info = saved_dedup


def _mock_mapping():
    return {
        "well": "A1",
        "primer_name": "M1_F",
        "sequence": "ACGTACGTACGT",
        "primer_type": "forward",
        "mutation": "M1",
    }


def test_kuro_export_to_mame_read_roundtrip(tmp_path, clean_state):
    """Kuro export → xlsx on disk → Mame read_kuma_meta matches project_id."""
    out = tmp_path / "expected_mutations.xlsx"
    project_id = "integration-test-uuid-001"

    handle_export_excel(
        {
            "filepath": str(out),
            "mappings": [_mock_mapping()],
            "dedup_info": {},
            "project_id": project_id,
            "kuma_version": "0.03.00",
        }
    )
    assert out.exists(), "xlsx should be written to disk"

    # Mame handler path
    meta_dict = handle_read_kuma_meta({"path": str(out)})
    assert meta_dict is not None
    assert meta_dict["project_id"] == project_id
    assert meta_dict["kuma_version"] == "0.03.00"
    assert meta_dict["kuro_module_version"] == KURO_MODULE_VERSION
    assert meta_dict["exported_at"]  # non-empty iso timestamp

    # Direct parser path
    meta = read_kuma_meta(out)
    assert meta is not None
    assert meta.project_id == project_id
    assert meta.kuma_version == "0.03.00"


def test_mame_returns_none_for_scratch_kuro_export(tmp_path, clean_state):
    """Export without project_id (scratch mode) → Mame returns None."""
    out = tmp_path / "scratch.xlsx"
    handle_export_excel(
        {
            "filepath": str(out),
            "mappings": [_mock_mapping()],
            "dedup_info": {},
        }
    )
    assert handle_read_kuma_meta({"path": str(out)}) is None


def test_mame_mismatch_project_id_surfaces_correct_value(tmp_path, clean_state):
    """Two separate exports produce distinguishable meta. Supports match dialog path."""
    out_a = tmp_path / "a.xlsx"
    out_b = tmp_path / "b.xlsx"

    handle_export_excel(
        {
            "filepath": str(out_a),
            "mappings": [_mock_mapping()],
            "dedup_info": {},
            "project_id": "proj-A",
        }
    )
    handle_export_excel(
        {
            "filepath": str(out_b),
            "mappings": [_mock_mapping()],
            "dedup_info": {},
            "project_id": "proj-B",
        }
    )

    meta_a = handle_read_kuma_meta({"path": str(out_a)})
    meta_b = handle_read_kuma_meta({"path": str(out_b)})
    assert meta_a["project_id"] == "proj-A"
    assert meta_b["project_id"] == "proj-B"


def test_kuma_version_defaults_when_omitted(tmp_path, clean_state):
    """project_id without kuma_version → handler falls back to KUMA_VERSION."""
    out = tmp_path / "defaulted.xlsx"
    handle_export_excel(
        {
            "filepath": str(out),
            "mappings": [_mock_mapping()],
            "dedup_info": {},
            "project_id": "proj-X",
        }
    )
    wb = openpyxl.load_workbook(out)
    sheet = wb["__kuma_meta__"]
    kv = {row[0].value: row[1].value for row in sheet.iter_rows(max_col=2)}
    assert kv["kuma_version"] == KUMA_VERSION
