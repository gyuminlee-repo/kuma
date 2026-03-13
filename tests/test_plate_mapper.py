"""Tests for plate mapping and Excel export."""

from __future__ import annotations

from pathlib import Path

import pytest

from evolveprimer.plate_mapper import (
    PlateMapping,
    deduplicate_reverse,
    export_plate_excel,
    generate_plate_map,
)
from evolveprimer.sdm_engine import SdmPrimerResult, design_sdm_primers
from tests.conftest import FIXTURES_DIR, TARGET_START


@pytest.fixture(scope="module")
def sdm_results(fasta_path, mutations_csv) -> list[SdmPrimerResult]:
    return design_sdm_primers(
        fasta_path=fasta_path,
        target_start=TARGET_START,
        mutations_csv=mutations_csv,
        polymerase="Q5",
        overlap_len=20,
    )


class TestDeduplicateReverse:
    def test_no_duplicates(self, sdm_results):
        rev_map = deduplicate_reverse(sdm_results)
        # All 12 mutations at different positions should have unique reverse primers
        total_mutations = sum(len(v) for v in rev_map.values())
        assert total_mutations == 12


class TestGeneratePlateMap:
    def test_plate_map_count(self, sdm_results):
        mappings = generate_plate_map(sdm_results, deduplicate_rev=True)
        # 12 forward + N reverse (deduplicated)
        fwd_count = sum(1 for m in mappings if m.primer_type == "forward")
        rev_count = sum(1 for m in mappings if m.primer_type == "reverse")
        assert fwd_count == 12
        assert rev_count <= 12  # Could be fewer if deduplicated
        assert len(mappings) <= 96

    def test_well_names_valid(self, sdm_results):
        mappings = generate_plate_map(sdm_results)
        for m in mappings:
            assert m.well[0] in "ABCDEFGH"
            col = int(m.well[1:])
            assert 1 <= col <= 12

    def test_column_order(self, sdm_results):
        mappings = generate_plate_map(sdm_results, well_order="column")
        # First 8 wells should be A1-H1
        if len(mappings) >= 8:
            first_8 = [m.well for m in mappings[:8]]
            expected = ["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"]
            assert first_8 == expected

    def test_no_dedup(self, sdm_results):
        mappings = generate_plate_map(sdm_results, deduplicate_rev=False)
        fwd_count = sum(1 for m in mappings if m.primer_type == "forward")
        rev_count = sum(1 for m in mappings if m.primer_type == "reverse")
        assert fwd_count == 12
        assert rev_count == 12  # No deduplication


class TestExportExcel:
    def test_export_creates_file(self, sdm_results, tmp_path):
        mappings = generate_plate_map(sdm_results)
        xlsx_path = tmp_path / "test_plate.xlsx"
        export_plate_excel(mappings, xlsx_path)
        assert xlsx_path.exists()
        assert xlsx_path.stat().st_size > 0

    def test_export_two_sheets(self, sdm_results, tmp_path):
        from openpyxl import load_workbook
        mappings = generate_plate_map(sdm_results)
        xlsx_path = tmp_path / "test_plate.xlsx"
        export_plate_excel(mappings, xlsx_path)

        wb = load_workbook(xlsx_path)
        assert "Primer List" in wb.sheetnames
        assert "Plate Layout" in wb.sheetnames
