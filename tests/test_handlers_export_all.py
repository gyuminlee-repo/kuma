"""Tests for handle_export_macrogen and handle_export_all sidecar handlers."""

from datetime import datetime
from unittest.mock import patch

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
    if res["ok"] is not True:
        raise AssertionError(f"not ok: {res}")
    if not (tmp_path / "x.xls").exists():
        raise AssertionError("xls missing")


EXPECTED_FLAT_FILES = [
    "echo.csv",
    "echo.xlsx",
    "janus.csv",
    "janus.xlsx",
    "macrogen.xls",
    "primers.fasta",
    "platemap.xlsx",
    "run.json",
]


def _seed_state() -> None:
    with _core._state_lock:
        _core._state.plate_mappings = [
            _mk("ATCG", "p1", "forward", "A1"),
            _mk("CGAT", "p1r", "reverse", "A1"),
        ]


def test_handle_export_all_writes_multiple_files(tmp_path):
    _seed_state()
    res = handle_export_all({
        "output_dir": str(tmp_path),
        "project_name": "Proj",
        "fwd_plate_name": "Pfwd",
        "rev_plate_name": "Prev",
    })
    if "success" not in res or "failed" not in res:
        raise AssertionError("missing keys")
    if "macrogen.xls" not in res["success"]:
        raise AssertionError(f"macrogen missing; got: {res}")
    if "primers.fasta" not in res["success"]:
        raise AssertionError(f"fasta missing; got: {res}")


def test_export_all_creates_project_name_folder(tmp_path):
    _seed_state()
    with patch("sidecar_kuro.handlers.export._dt") as m_dt:
        m_dt.now.return_value = datetime(2026, 5, 19, 10, 25)
        res = handle_export_all({
            "output_dir": str(tmp_path),
            "project_name": "Q232A",
            "fwd_plate_name": "F1",
            "rev_plate_name": "R1",
        })
    subdir = tmp_path / "Q232A_20260519"
    if not subdir.is_dir():
        raise AssertionError(f"missing folder: {subdir}; res={res}")
    for name in EXPECTED_FLAT_FILES:
        if not (subdir / name).exists():
            raise AssertionError(f"missing file: {name}, failed list: {res.get('failed')}")
    if res["output_dir"] != str(subdir):
        raise AssertionError(f"output_dir mismatch: {res['output_dir']}")


def test_export_all_fallback_folder(tmp_path):
    _seed_state()
    with patch("sidecar_kuro.handlers.export._dt") as m_dt:
        m_dt.now.return_value = datetime(2026, 5, 19, 10, 25)
        handle_export_all({
            "output_dir": str(tmp_path),
            "fwd_plate_name": "F1",
            "rev_plate_name": "R1",
        })
    if not (tmp_path / "kuro_260519_1025").is_dir():
        raise AssertionError(f"fallback folder name not produced; tmp={list(tmp_path.iterdir())}")


def test_export_all_dedup_suffix(tmp_path):
    _seed_state()
    (tmp_path / "Q232A_20260519").mkdir()
    with patch("sidecar_kuro.handlers.export._dt") as m_dt:
        m_dt.now.return_value = datetime(2026, 5, 19, 10, 25)
        handle_export_all({
            "output_dir": str(tmp_path),
            "project_name": "Q232A",
            "fwd_plate_name": "F1",
            "rev_plate_name": "R1",
        })
    if not (tmp_path / "Q232A_20260519_2").is_dir():
        raise AssertionError(f"dedup suffix not applied; tmp={list(tmp_path.iterdir())}")


def test_handle_export_macrogen_validates_name(tmp_path):
    with _core._state_lock:
        _core._state.plate_mappings = [_mk("ATCG", "p1", "forward")]
    with pytest.raises(ValueError):
        handle_export_macrogen({
            "output_path": str(tmp_path / "x.xls"),
            "fwd_plate_name": "한글",
        })
