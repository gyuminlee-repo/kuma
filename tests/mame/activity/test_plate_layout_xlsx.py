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
# Replicate suffix and blank rows (experimenter notation)
# ---------------------------------------------------------------------------

def test_replicate_suffix_wt_detected(tmp_path: Path):
    """'WT_r<n>' is still a WT row once the replicate suffix is stripped."""
    path = _make_xlsx(
        [
            ["sample_name", "well"],
            ["WT_r1", "A1"],
            ["WT_r2", "A2"],
            ["WT_r3", "A3"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert len(entries) == 3
    assert all(e.mutant == "WT" for e in entries)
    assert all(e.is_wt for e in entries)
    assert [e.well_id for e in entries] == ["A01", "A02", "A03"]


def test_replicate_suffix_collapses_to_one_mutant(tmp_path: Path):
    """Three replicate rows share one mutant name but keep distinct wells."""
    path = _make_xlsx(
        [
            ["sample_name", "well"],
            ["Q232A_r1", "A4"],
            ["Q232A_r2", "A5"],
            ["Q232A_r3", "A6"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert {e.mutant for e in entries} == {"Q232A"}
    assert [e.well_id for e in entries] == ["A04", "A05", "A06"]
    assert all(e.is_wt is False for e in entries)


def test_replicate_suffix_preserves_inner_underscore(tmp_path: Path):
    """Only the trailing '_r<n>' is removed from a multi-substitution label."""
    path = _make_xlsx(
        [
            ["sample_name", "well"],
            ["A40P_E61Y_r1", "D1"],
            ["A40P_E61Y_r2", "D2"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert [e.mutant for e in entries] == ["A40P_E61Y", "A40P_E61Y"]


def test_replicate_suffix_case_insensitive(tmp_path: Path):
    path = _make_xlsx(
        [
            ["sample_name", "well"],
            ["Q232A_R2", "A5"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert entries[0].mutant == "Q232A"


def test_no_replicate_suffix_unchanged(tmp_path: Path):
    """Labels without the suffix keep their original form."""
    path = _make_xlsx(
        [
            ["sample_name", "well"],
            ["Q232A", "A4"],
            ["A40P_E61Y", "D1"],
            ["WT", "A1"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert [e.mutant for e in entries] == ["Q232A", "A40P_E61Y", "WT"]
    assert [e.is_wt for e in entries] == [False, False, True]


def test_blank_rows_excluded(tmp_path: Path):
    """'blank' wells carry no mutant and drop out of the result."""
    path = _make_xlsx(
        [
            ["sample_name", "well"],
            ["Q232A_r1", "A4"],
            ["blank", "H12"],
            ["BLANK", "H11"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert len(entries) == 1
    assert entries[0].mutant == "Q232A"


def test_template_plate_layout_replicate_notation():
    """templates/06_mame_plate_layout.xlsx parses into the experimenter layout.

    This used to be asserted of `05_mame_sample_map.xlsx`, with a second test
    checking that the two templates agreed. The 05 template went with the sample
    map, and 06 carries the same plate, so the assertions move here rather than
    being dropped: `_r<n>` replicates and `blank` rows are activity-layout
    behaviour and have nothing to do with the removed analyze input.
    """
    path = (
        Path(__file__).resolve().parents[3] / "templates" / "06_mame_plate_layout.xlsx"
    )
    entries = parse_plate_layout_xlsx(path)

    assert len(entries) == 21
    assert not any(e.mutant.lower() == "blank" for e in entries)

    wt_entries = [e for e in entries if e.is_wt]
    assert len(wt_entries) == 3
    assert {e.well_id for e in wt_entries} == {"A01", "A02", "A03"}

    mutant_names = {e.mutant for e in entries if not e.is_wt}
    assert mutant_names == {
        "Q232A",
        "Y233A",
        "A40P",
        "E61Y",
        "L150V",
        "A40P_E61Y",
    }
    for name in mutant_names:
        wells = [e.well_id for e in entries if e.mutant == name]
        assert len(wells) == 3
        assert len(set(wells)) == 3


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_parse_sample_map_format(tmp_path: Path):
    """The sample map sheet generated for step 1/2 parses without edits."""
    path = _make_xlsx(
        [
            ["sample_name", "well"],
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


def test_sample_map_extra_columns_ignored(tmp_path: Path):
    """Barcode and other sample map columns do not disturb parsing."""
    path = _make_xlsx(
        [
            ["sample_name", "well", "barcode"],
            ["F89W", "B2", "isps_f_1"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert len(entries) == 1
    assert entries[0].mutant == "F89W"
    assert entries[0].well_id == "B02"


def test_sample_map_header_case_insensitive(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Sample_Name", "Well"],
            ["G10A", "C3"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert entries[0].well_id == "C03"


def test_sample_map_wt_case_insensitive(tmp_path: Path):
    path = _make_xlsx(
        [
            ["sample_name", "well"],
            ["wt", "H12"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert entries[0].is_wt is True


def test_both_pairs_prefers_plate_layout(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Mutant", "Well Pos.", "sample_name", "well"],
            ["F89W", "A1", "G10A", "B2"],
        ],
        tmp_path,
    )
    entries = parse_plate_layout_xlsx(path)
    assert len(entries) == 1
    assert entries[0].mutant == "F89W"
    assert entries[0].well_id == "A01"


def test_template_plate_layout_parses():
    """templates/06_mame_plate_layout.xlsx keeps working unchanged."""
    path = (
        Path(__file__).resolve().parents[3] / "templates" / "06_mame_plate_layout.xlsx"
    )
    entries = parse_plate_layout_xlsx(path)
    assert len(entries) > 0
    assert any(e.is_wt for e in entries)


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


def test_no_supported_pair_lists_both_formats(tmp_path: Path):
    path = _make_xlsx(
        [
            ["Variant", "Position"],
            ["F89W", "A1"],
        ],
        tmp_path,
    )
    with pytest.raises(ValueError) as exc:
        parse_plate_layout_xlsx(path)
    message = str(exc.value)
    assert "Mutant" in message
    assert "Well Pos." in message
    assert "sample_name" in message
    assert "well" in message


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
