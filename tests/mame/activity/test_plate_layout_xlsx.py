"""Tests for kuma_core.mame.activity.plate_layout_xlsx.

Uses openpyxl to generate in-memory xlsx fixtures (write-only use;
calamine handles reading in production code).
"""

from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.activity.plate_layout_xlsx import (
    parse_plate_layout_xlsx,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_xlsx(rows: list[list], tmp_path: Path, filename: str = "layout.xlsx") -> Path:
    """Write rows to a temporary xlsx and return the path."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    dest = tmp_path / filename
    wb.save(str(dest))
    return dest


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

def test_parse_basic(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Well Pos."],
            ["F89W", "A1"],
            ["WT", "H12"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert len(entries) == 2
    assert entries[0].mutant == "F89W"
    assert entries[0].well_id == "A01"
    assert entries[0].is_wt is False
    assert entries[1].mutant == "WT"
    assert entries[1].well_id == "H12"
    assert entries[1].is_wt is True


def test_header_case_insensitive(tmp_path: Path):
    path = _make_xlsx(
        [
            ["MUTANT", "WELL POS."],
            ["G10A", "B2"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert len(entries) == 1
    assert entries[0].well_id == "B02"


def test_wt_case_insensitive(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Well Pos."],
            ["wt", "H12"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert entries[0].is_wt is True


def test_well_normalisation(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Well Pos."],
            ["F89W", "A9"],
            ["G10A", "H12"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert entries[0].well_id == "A09"
    assert entries[1].well_id == "H12"


def test_blank_rows_skipped(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Well Pos."],
            ["F89W", "A1"],
            ["", ""],
            ["G10A", "A2"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert len(entries) == 2


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_missing_mutant_column_raises(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Variant", "Well Pos."],
            ["F89W", "A1"],
        ],
        tmp_path,
    )
    with pytest.raises(ValueError, match="Mutant"):
        parse_plate_layout_xlsx(path)


def test_missing_well_column_raises(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Position"],
            ["F89W", "A1"],
        ],
        tmp_path,
    )
    with pytest.raises(ValueError, match="Well Pos"):
        parse_plate_layout_xlsx(path)


def test_invalid_well_pos_raises(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Well Pos."],
            ["F89W", "Z99"],
        ],
        tmp_path,
    )
    with pytest.raises(ValueError, match="Z99"):
        parse_plate_layout_xlsx(path)


def test_well_pos_letters_only_raises(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Well Pos."],
            ["F89W", "AB"],
        ],
        tmp_path,
    )
    with pytest.raises(ValueError):
        parse_plate_layout_xlsx(path)


def test_invalid_sheet_index_raises(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Well Pos."],
            ["F89W", "A1"],
        ],
        tmp_path,
    )
    with pytest.raises(ValueError, match="sheet_index"):
        parse_plate_layout_xlsx(path, sheet_index=5)
