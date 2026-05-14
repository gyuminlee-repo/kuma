"""Tests for handle_export_macrogen and handle_export_all sidecar handlers."""

from pathlib import Path

import pytest

import sidecar_kuro.core as _core
from kuma_core.kuro.plate_mapper import PlateMapping
from sidecar_kuro.handlers.export import handle_export_all, handle_export_macrogen


def _mk(seq: str, name: str, ptype: str, well: str = "A1") -> PlateMapping:
    return PlateMapping(
        well=well,
        primer_name=name,
        sequence=seq,
        primer_type=ptype,
        mutation="X1Y",
    )


@pytest.fixture(autouse=True)
def _reset_state():
    with _core._state_lock:
        _core._state.results = []
        _core._state.plate_mappings = []
        _core._state.dedup_info = {}
    yield
    with _core._state_lock:
        _core._state.results = []
        _core._state.plate_mappings = []
        _core._state.dedup_info = {}


def test_handle_export_macrogen_writes_file(tmp_path):
    with _core._state_lock:
        _core._state.plate_mappings = [_mk("ATCG", "p1", "forward")]
    res = handle_export_macrogen({
        "output_path": str(tmp_path / "x.xls"),
        "fwd_plate_name": "P1",
    })
    assert res["ok"] is True
    assert (tmp_path / "x.xls").exists()


def test_handle_export_all_writes_multiple_files(tmp_path):
    with _core._state_lock:
        _core._state.plate_mappings = [
            _mk("ATCG", "p1", "forward", "A1"),
            _mk("CGAT", "p1r", "reverse", "A1"),
        ]
    res = handle_export_all({
        "output_dir": str(tmp_path),
        "fwd_plate_name": "Pfwd",
        "rev_plate_name": "Prev",
    })
    assert "success" in res
    assert "failed" in res
    assert res["output_dir"] == str(tmp_path)
    # Macrogen + fasta should always succeed when plate_mappings exist
    assert any(name.endswith(".macrogen.xls") for name in res["success"])
    assert any(name.endswith(".primers.fasta") for name in res["success"])


def test_handle_export_macrogen_validates_name(tmp_path):
    with _core._state_lock:
        _core._state.plate_mappings = [_mk("ATCG", "p1", "forward")]
    with pytest.raises(ValueError):
        handle_export_macrogen({
            "output_path": str(tmp_path / "x.xls"),
            "fwd_plate_name": "한글",
        })
