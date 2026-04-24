"""Tests for reading __kuma_meta__ from xlsx."""
from __future__ import annotations

from pathlib import Path

import openpyxl

from kuma_core.mame.io.kuma_meta import KumaMeta, read_kuma_meta


def _make_xlsx_with_meta(path: Path, project_id: str = "abc-123") -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["col"])
    meta = wb.create_sheet("__kuma_meta__")
    meta.sheet_state = "hidden"
    meta.append(["project_id", project_id])
    meta.append(["kuma_version", "0.02.02"])
    meta.append(["kuro_module_version", "0.02.02"])
    meta.append(["exported_at", "2026-04-24T00:00:00+00:00"])
    wb.save(path)
    return path


def _make_plain_xlsx(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["only", "data"])
    wb.save(path)
    return path


def test_reads_meta_sheet_if_present(tmp_path):
    xlsx = _make_xlsx_with_meta(tmp_path / "meta.xlsx", project_id="abc-123")
    meta = read_kuma_meta(xlsx)
    assert isinstance(meta, KumaMeta)
    assert meta.project_id == "abc-123"
    assert meta.kuma_version == "0.02.02"


def test_returns_none_if_meta_absent(tmp_path):
    xlsx = _make_plain_xlsx(tmp_path / "plain.xlsx")
    assert read_kuma_meta(xlsx) is None
