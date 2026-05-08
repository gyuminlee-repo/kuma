"""Tests for run manifest generation in kuro export handlers.

Verifies that handle_export_order and handle_export_excel produce
sibling ``{basename}.run.json`` files with correct ``method`` and
``schema_version`` fields after a successful export.

Also verifies SHA-256 checksum files (``{basename}.sha256``) are
produced alongside each export and that ``checksum_path`` is returned
in the response dict.
"""

from __future__ import annotations

import json
import re

import pytest

from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.export import handle_export_excel, handle_export_order
from kuma_core.shared.run_manifest import SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Shared fixture: minimal sidecar state
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_state():
    """Populate sidecar_kuro state with a single mapping so export can run."""
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


def _make_mapping_item():
    return {
        "well": "A1",
        "primer_name": "M1_F",
        "sequence": "ACGTACGTACGT",
        "primer_type": "forward",
        "mutation": "M1",
    }


def _make_order_item():
    return {
        "mutation": "M1T",
        "forward_seq": "ACGTACGTACGT",
        "reverse_seq": "TTTTACGTACGT",
    }


# ---------------------------------------------------------------------------
# handle_export_order manifest tests
# ---------------------------------------------------------------------------


def test_export_order_produces_manifest_file(tmp_path, minimal_state):
    out = tmp_path / "order.csv"
    result = handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    manifest_path = tmp_path / "order.run.json"
    assert manifest_path.exists(), "order.run.json manifest file not created"


def test_export_order_manifest_path_in_response(tmp_path, minimal_state):
    out = tmp_path / "primers.csv"
    result = handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    assert "manifest_path" in result
    assert result["manifest_path"].endswith("primers.run.json")


def test_export_order_manifest_method_field(tmp_path, minimal_state):
    out = tmp_path / "order_meta.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "twist",
        "results": [_make_order_item()],
    })
    manifest = json.loads((tmp_path / "order_meta.run.json").read_text())
    assert manifest["method"] == "export_order"


def test_export_order_manifest_schema_version(tmp_path, minimal_state):
    out = tmp_path / "order_schema.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    manifest = json.loads((tmp_path / "order_schema.run.json").read_text())
    assert manifest["schema_version"] == SCHEMA_VERSION


def test_export_order_manifest_inputs_empty(tmp_path, minimal_state):
    """Order export has no input files — inputs section must be empty dict."""
    out = tmp_path / "order_inputs.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    manifest = json.loads((tmp_path / "order_inputs.run.json").read_text())
    assert manifest["inputs"] == {}


def test_export_order_manifest_timestamps_present(tmp_path, minimal_state):
    out = tmp_path / "order_ts.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    manifest = json.loads((tmp_path / "order_ts.run.json").read_text())
    assert "started_at" in manifest
    assert "finished_at" in manifest
    assert "duration_seconds" in manifest


# ---------------------------------------------------------------------------
# handle_export_excel manifest tests
# ---------------------------------------------------------------------------


def test_export_excel_produces_manifest_file(tmp_path, minimal_state):
    out = tmp_path / "plate.xlsx"
    handle_export_excel({
        "filepath": str(out),
        "mappings": [_make_mapping_item()],
        "dedup_info": {},
    })
    manifest_path = tmp_path / "plate.run.json"
    assert manifest_path.exists(), "plate.run.json manifest file not created"


def test_export_excel_manifest_path_in_response(tmp_path, minimal_state):
    out = tmp_path / "plate2.xlsx"
    result = handle_export_excel({
        "filepath": str(out),
        "mappings": [_make_mapping_item()],
        "dedup_info": {},
    })
    assert "manifest_path" in result
    assert result["manifest_path"].endswith("plate2.run.json")


def test_export_excel_manifest_method_field(tmp_path, minimal_state):
    out = tmp_path / "plate3.xlsx"
    handle_export_excel({
        "filepath": str(out),
        "mappings": [_make_mapping_item()],
        "dedup_info": {},
    })
    manifest = json.loads((tmp_path / "plate3.run.json").read_text())
    assert manifest["method"] == "export_excel"


def test_export_excel_manifest_kuma_version_present(tmp_path, minimal_state):
    out = tmp_path / "plate4.xlsx"
    handle_export_excel({
        "filepath": str(out),
        "mappings": [_make_mapping_item()],
        "dedup_info": {},
    })
    manifest = json.loads((tmp_path / "plate4.run.json").read_text())
    assert "kuma_version" in manifest
    assert isinstance(manifest["kuma_version"], str)


# ---------------------------------------------------------------------------
# SHA-256 checksum file tests — export_order
# ---------------------------------------------------------------------------


def test_export_order_produces_sha256_file(tmp_path, minimal_state):
    out = tmp_path / "order_cs.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    checksum_file = tmp_path / "order_cs.csv.sha256"
    assert checksum_file.exists(), "order_cs.csv.sha256 not created"


def test_export_order_checksum_path_in_response(tmp_path, minimal_state):
    out = tmp_path / "order_csr.csv"
    result = handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    assert "checksum_path" in result
    assert result["checksum_path"].endswith("order_csr.csv.sha256")


def test_export_order_checksum_content_format(tmp_path, minimal_state):
    out = tmp_path / "order_fmt.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    checksum_file = tmp_path / "order_fmt.csv.sha256"
    text = checksum_file.read_text(encoding="utf-8")
    pattern = re.compile(r"^[0-9a-f]{64}  order_fmt\.csv\n$")
    assert pattern.match(text), f"Bad checksum format: {text!r}"


# ---------------------------------------------------------------------------
# SHA-256 checksum file tests — export_excel
# ---------------------------------------------------------------------------


def test_export_excel_produces_sha256_file(tmp_path, minimal_state):
    out = tmp_path / "plate_cs.xlsx"
    handle_export_excel({
        "filepath": str(out),
        "mappings": [_make_mapping_item()],
        "dedup_info": {},
    })
    checksum_file = tmp_path / "plate_cs.xlsx.sha256"
    assert checksum_file.exists(), "plate_cs.xlsx.sha256 not created"


def test_export_excel_checksum_path_in_response(tmp_path, minimal_state):
    out = tmp_path / "plate_csr.xlsx"
    result = handle_export_excel({
        "filepath": str(out),
        "mappings": [_make_mapping_item()],
        "dedup_info": {},
    })
    assert "checksum_path" in result
    assert result["checksum_path"].endswith("plate_csr.xlsx.sha256")


# ---------------------------------------------------------------------------
# UTF-8 BOM option tests — §17 Cross-platform
# ---------------------------------------------------------------------------

BOM = b"\xef\xbb\xbf"


def test_export_order_bom_true_produces_bom(tmp_path, minimal_state):
    """bom=True: first 3 bytes of output file must be UTF-8 BOM (EF BB BF)."""
    out = tmp_path / "order_bom.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
        "bom": True,
    })
    assert out.read_bytes()[:3] == BOM, "Expected UTF-8 BOM (EF BB BF) at start of file"


def test_export_order_bom_false_no_bom(tmp_path, minimal_state):
    """bom=False (default): output file must NOT start with BOM."""
    out = tmp_path / "order_nobom.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
        "bom": False,
    })
    assert out.read_bytes()[:3] != BOM, "Unexpected UTF-8 BOM when bom=False"


def test_export_order_default_no_bom(tmp_path, minimal_state):
    """Default (bom omitted): output must NOT start with BOM (backward compat)."""
    out = tmp_path / "order_default.csv"
    handle_export_order({
        "filepath": str(out),
        "format": "idt",
        "results": [_make_order_item()],
    })
    assert out.read_bytes()[:3] != BOM, "Unexpected UTF-8 BOM with default params"


def test_export_benchmark_csv_bom_true(tmp_path, minimal_state):
    """export_benchmark_csv with bom=True: first 3 bytes must be BOM."""
    from sidecar_kuro.handlers.export import handle_export_benchmark_csv
    out = tmp_path / "bench_bom.csv"
    handle_export_benchmark_csv({
        "filepath": str(out),
        "results": {
            "topn": {
                "n_selected": 10, "hit_rate": 0.5, "mean_fitness": 1.0,
                "unique_positions": 5, "position_coverage": 0.5,
                "domain_coverage": 0.8, "structural_spread": 0.3,
                "hits": 5, "threshold": 10.0, "n_trials": 100,
            }
        },
        "bom": True,
    })
    assert out.read_bytes()[:3] == BOM, "Expected BOM in benchmark CSV with bom=True"


def test_export_benchmark_csv_bom_false(tmp_path, minimal_state):
    """export_benchmark_csv with bom=False: no BOM."""
    from sidecar_kuro.handlers.export import handle_export_benchmark_csv
    out = tmp_path / "bench_nobom.csv"
    handle_export_benchmark_csv({
        "filepath": str(out),
        "results": {
            "topn": {
                "n_selected": 10, "hit_rate": 0.5, "mean_fitness": 1.0,
                "unique_positions": 5, "position_coverage": 0.5,
                "domain_coverage": 0.8, "structural_spread": 0.3,
                "hits": 5, "threshold": 10.0, "n_trials": 100,
            }
        },
        "bom": False,
    })
    assert out.read_bytes()[:3] != BOM, "Unexpected BOM with bom=False"
