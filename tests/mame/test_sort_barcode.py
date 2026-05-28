# ruff: noqa: S101
"""Tests for sort_barcode barcode xlsx parsers.

Coverage
--------
- _nb_to_sort_barcode_name: native barcode dir -> sort_barcode dir name
- parse_combinatorial_barcodes: xlsx -> 96-well (fwd, rev) map
- parse_sample_map: xlsx -> well_id -> sample_name dict
- _make_well_filename: build per-well FASTA filename stem

The combinatorial read-sorting algorithm (sort_barcode_run) was removed in
PR-B.  Canonical pipeline: kuma_core.mame.ingest.combinatorial_demux.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# openpyxl is required for xlsx fixture generation.
openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")

from kuma_core.mame.ingest.sort_barcode import (
    _make_well_filename,
    _nb_to_sort_barcode_name,
    parse_combinatorial_barcodes,
    parse_sample_map,
)


# ---------------------------------------------------------------------------
# xlsx fixture helpers
# ---------------------------------------------------------------------------

# Deterministic barcode sequences for testing.
_FWD_SEQS: dict[int, str] = {
    1:  "AATCCCACTACCACAGGAGGTTAAACC",   # egfp_f_1
    2:  "TGAACTGAGCGCACAGGAGGTTAAACC",   # egfp_f_2
    3:  "AAACGTCACAGGAGGTTAAACC",
    4:  "TTGCAATCACAGGAGGTTAAACC",
    5:  "CCAGTTTTCACAGGAGGTTAAACC",
    6:  "GGTAACAGCACAGGAGGTTAAACC",
    7:  "AAGCTATACAGGAGGTTAAACC",
    8:  "TTCAACGCACAGGAGGTTAAACC",
    9:  "CCGTGATACAGGAGGTTAAACC",
    10: "GGCATTTCACAGGAGGTTAAACC",
    11: "AACCGTTCACAGGAGGTTAAACC",
    12: "TTGGAAACAGGAGGTTAAACC",
}

_REV_SEQS: dict[int, str] = {
    1: "GCATGCATGCAT",
    2: "AGTCAGTCAGTC",
    3: "TTAGTTAGTTAG",
    4: "CCAACCAACCAA",
    5: "GGTGGGTGGGTG",
    6: "AACCTTAACCTT",
    7: "TTGGAATTGGAA",
    8: "CCGGTTCCGGTT",
}


def _make_barcode_xlsx(path: Path) -> None:
    """Write a minimal combinatorial barcode xlsx (12 fwd + 8 rev = 20 rows)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("openpyxl Workbook has no active sheet")
    ws.title = "Sheet1"
    for n, seq in _FWD_SEQS.items():
        ws.append([f"egfp_f_{n}", seq])
    for n, seq in _REV_SEQS.items():
        ws.append([f"egfp_r_{n}", seq])
    wb.save(str(path))


def _make_barcode_xlsx_missing_fwd(path: Path) -> None:
    """xlsx with only 11 fwd barcodes (egfp_f_12 missing)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("openpyxl Workbook has no active sheet")
    ws.title = "Sheet1"
    for n, seq in _FWD_SEQS.items():
        if n == 12:
            continue
        ws.append([f"egfp_f_{n}", seq])
    for n, seq in _REV_SEQS.items():
        ws.append([f"egfp_r_{n}", seq])
    wb.save(str(path))


def _make_barcode_xlsx_missing_rev(path: Path) -> None:
    """xlsx with only 7 rev barcodes (egfp_r_8 missing)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("openpyxl Workbook has no active sheet")
    ws.title = "Sheet1"
    for n, seq in _FWD_SEQS.items():
        ws.append([f"egfp_f_{n}", seq])
    for n, seq in _REV_SEQS.items():
        if n == 8:
            continue
        ws.append([f"egfp_r_{n}", seq])
    wb.save(str(path))


def _make_sample_map_xlsx(path: Path, entries: list[tuple[str, str]]) -> None:
    """Write a sample map xlsx. entries: [(sample_name, well_pos)]."""
    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        raise RuntimeError("openpyxl Workbook has no active sheet")
    ws.title = "Sheet1"
    for name, pos in entries:
        ws.append([name, pos])
    wb.save(str(path))


# ---------------------------------------------------------------------------
# Unit tests: _nb_to_sort_barcode_name
# ---------------------------------------------------------------------------


class TestNbToSortBarcodeName:
    def test_barcode06_style(self) -> None:
        assert _nb_to_sort_barcode_name("barcode06") == "sort_barcode06"

    def test_nb06_style(self) -> None:
        assert _nb_to_sort_barcode_name("NB06") == "sort_barcode06"

    def test_barcode100_three_digit(self) -> None:
        assert _nb_to_sort_barcode_name("barcode100") == "sort_barcode100"

    def test_nb100_three_digit(self) -> None:
        assert _nb_to_sort_barcode_name("NB100") == "sort_barcode100"

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError, match="sort_barcode name"):
            _nb_to_sort_barcode_name("unclassified")

    def test_invalid_name_no_digits_raises(self) -> None:
        with pytest.raises(ValueError, match="sort_barcode name"):
            _nb_to_sort_barcode_name("somefolder")

    def test_case_insensitive(self) -> None:
        assert _nb_to_sort_barcode_name("BARCODE01") == "sort_barcode01"


# ---------------------------------------------------------------------------
# Unit tests: parse_combinatorial_barcodes
# ---------------------------------------------------------------------------


class TestParseCombinatorial:
    def test_normal_96_wells(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "barcodes.xlsx"
        _make_barcode_xlsx(xlsx)
        result = parse_combinatorial_barcodes(xlsx)
        assert len(result) == 96
        # A01 = fwd_1, rev_1
        assert result["A01"] == (_FWD_SEQS[1], _REV_SEQS[1])
        # H12 = fwd_12, rev_8
        assert result["H12"] == (_FWD_SEQS[12], _REV_SEQS[8])

    def test_missing_fwd_raises(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "barcodes_miss_fwd.xlsx"
        _make_barcode_xlsx_missing_fwd(xlsx)
        with pytest.raises(ValueError, match="Missing forward barcodes"):
            parse_combinatorial_barcodes(xlsx)

    def test_missing_rev_raises(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "barcodes_miss_rev.xlsx"
        _make_barcode_xlsx_missing_rev(xlsx)
        with pytest.raises(ValueError, match="Missing reverse barcodes"):
            parse_combinatorial_barcodes(xlsx)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_combinatorial_barcodes(tmp_path / "nonexistent.xlsx")

    def test_invalid_prefix_skipped(self, tmp_path: Path) -> None:
        """Rows with unrecognised prefix are silently skipped."""
        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is None:
            raise RuntimeError("openpyxl Workbook has no active sheet")
        ws.title = "Sheet1"
        for n, seq in _FWD_SEQS.items():
            ws.append([f"egfp_f_{n}", seq])
        for n, seq in _REV_SEQS.items():
            ws.append([f"egfp_r_{n}", seq])
        ws.append(["random_barcode", "ACGTACGTAC"])
        xlsx = tmp_path / "barcodes_extra.xlsx"
        wb.save(str(xlsx))
        result = parse_combinatorial_barcodes(xlsx)
        assert len(result) == 96

    def test_well_id_mapping(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "barcodes.xlsx"
        _make_barcode_xlsx(xlsx)
        result = parse_combinatorial_barcodes(xlsx)
        # row=1 col=2 -> A02; row=2 col=1 -> B01
        assert result["A02"] == (_FWD_SEQS[2], _REV_SEQS[1])
        assert result["B01"] == (_FWD_SEQS[1], _REV_SEQS[2])


# ---------------------------------------------------------------------------
# Unit tests: parse_sample_map
# ---------------------------------------------------------------------------


class TestParseSampleMap:
    def test_basic_mapping(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(xlsx, [("V5F", "A1"), ("K53R", "B2"), ("WT", "H12")])
        result = parse_sample_map(xlsx)
        assert result["A01"] == "V5F"
        assert result["B02"] == "K53R"
        assert result["H12"] == "WT"

    def test_zero_padded_position(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(xlsx, [("MUT1", "A01"), ("MUT2", "A1")])
        result = parse_sample_map(xlsx)
        # Both "A01" and "A1" -> same key; first wins
        assert result["A01"] == "MUT1"

    def test_invalid_well_positions_skipped(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(xlsx, [
            ("V5F", "A1"),
            ("BAD", "Z9"),    # invalid row letter
            ("OK", "B3"),
        ])
        result = parse_sample_map(xlsx)
        assert "A01" in result
        assert "B03" in result
        assert len(result) == 2  # Z9 skipped

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="sample_map_path"):
            parse_sample_map(tmp_path / "missing.xlsx")


# ---------------------------------------------------------------------------
# Unit tests: _make_well_filename
# ---------------------------------------------------------------------------


class TestMakeWellFilename:
    def test_without_sample_map(self) -> None:
        assert _make_well_filename("A01", 1, 1, None) == "A01_F1_R1"

    def test_with_sample_map_match(self) -> None:
        assert _make_well_filename("A01", 1, 1, {"A01": "V5F"}) == "A01_V5F_F1_R1"

    def test_with_sample_map_no_match(self) -> None:
        assert _make_well_filename("C05", 5, 3, {"A01": "V5F"}) == "C05_F5_R3"

    def test_fwd_rev_indices_in_name(self) -> None:
        stem = _make_well_filename("H12", 12, 8, {"H12": "WT"})
        assert stem == "H12_WT_F12_R8"
