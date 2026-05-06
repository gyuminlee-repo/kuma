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


def test_read_expected_mutations_accepts_rescue_status_from_interim_exports(tmp_path: Path) -> None:
    path = tmp_path / "KURO_rescue_status.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "expected_mutations"
    ws.append([
        "mutant_id", "position", "wt_aa", "mt_aa",
        "wt_codon", "mt_codon", "group_id", "primer_set_ref",
        "notation_type", "status", "rescue_type", "rescue_stage", "rescued_from",
    ])
    ws.append(["K53N", 53, "K", "N", "AAG", "AAC", "", "K53N", "substitution", "auto_suggestion_l2", "", "", ""])
    ws.append(["E61Y", 61, "E", "Y", "GAA", "TAT", "", "E61Y", "substitution", "FAILED", "", "", ""])
    wb.save(path)

    result = read_expected_mutations(path)

    assert expected_to_labels(result) == ["K53N"]
