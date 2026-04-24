"""KURO xlsx reader tests (Blocker B acceptance)."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.io.kuro_reader import expected_to_labels, read_expected_mutations


def test_read_expected_mutations_returns_two_rows(kuro_xlsx_path: Path) -> None:
    result = read_expected_mutations(kuro_xlsx_path)
    assert len(result) == 2
    labels = expected_to_labels(result)
    assert labels == ["V5F", "K53N"]


def test_missing_expected_sheet_raises(tmp_path: Path) -> None:
    bad = tmp_path / "KURO_legacy.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Fwd List"
    ws.append(["Well", "Primer Name"])
    wb.save(bad)

    with pytest.raises(ValueError):
        read_expected_mutations(bad)
