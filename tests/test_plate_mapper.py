"""Tests for plate mapping, Excel export, and order CSV export."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kuro.plate_mapper import (
    PlateMapping,
    deduplicate_reverse,
    export_idt_csv,
    export_plate_excel,
    export_twist_csv,
    generate_plate_map,
)
from kuro.sdm_engine import SdmPrimerResult, design_sdm_primers
from tests.conftest import FIXTURES_DIR, TARGET_START


@pytest.fixture(scope="module")
def sdm_results(fasta_path, mutations_csv) -> list[SdmPrimerResult]:
    results, _, _f = design_sdm_primers(
        fasta_path=fasta_path,
        target_start=TARGET_START,
        mutations_csv=mutations_csv,
        polymerase="Q5",
        overlap_len=20,
    )
    return results


class TestDeduplicateReverse:
    def test_no_duplicates(self, sdm_results):
        rev_map = deduplicate_reverse(sdm_results)
        total_mutations = sum(len(v) for v in rev_map.values())
        assert total_mutations == len(sdm_results)


class TestGeneratePlateMap:
    def test_plate_map_count(self, sdm_results):
        fwd_map, rev_map = generate_plate_map(sdm_results, deduplicate_rev=True)
        assert len(fwd_map) == len(sdm_results)
        assert len(rev_map) <= len(sdm_results)

    def test_well_names_valid(self, sdm_results):
        fwd_map, rev_map = generate_plate_map(sdm_results)
        for m in fwd_map + rev_map:
            assert m.well[0] in "ABCDEFGH"
            col = int(m.well[1:])
            assert 1 <= col <= 12

    def test_column_order(self, sdm_results):
        fwd_map, _ = generate_plate_map(sdm_results, well_order="column")
        if len(fwd_map) >= 8:
            first_8 = [m.well for m in fwd_map[:8]]
            expected = ["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"]
            assert first_8 == expected

    def test_no_dedup(self, sdm_results):
        fwd_map, rev_map = generate_plate_map(sdm_results, deduplicate_rev=False)
        assert len(fwd_map) == len(sdm_results)
        assert len(rev_map) == len(sdm_results)


class TestExportExcel:
    def test_export_creates_file(self, sdm_results, tmp_path):
        fwd_map, rev_map = generate_plate_map(sdm_results)
        xlsx_path = tmp_path / "test_plate.xlsx"
        export_plate_excel(fwd_map + rev_map, xlsx_path)
        assert xlsx_path.exists()
        assert xlsx_path.stat().st_size > 0

    def test_export_four_sheets(self, sdm_results, tmp_path):
        from openpyxl import load_workbook
        fwd_map, rev_map = generate_plate_map(sdm_results)
        xlsx_path = tmp_path / "test_plate.xlsx"
        export_plate_excel(fwd_map + rev_map, xlsx_path)

        wb = load_workbook(xlsx_path)
        assert "Fwd List" in wb.sheetnames
        assert "Fwd Plate" in wb.sheetnames
        assert "Rev List" in wb.sheetnames
        assert "Rev Plate" in wb.sheetnames


class TestExportIdtCsv:
    def test_idt_csv_creates_file(self, sdm_results, tmp_path):
        csv_path = tmp_path / "idt_order.csv"
        export_idt_csv(sdm_results, csv_path)
        assert csv_path.exists()
        assert csv_path.stat().st_size > 0

    def test_idt_csv_header(self, sdm_results, tmp_path):
        csv_path = tmp_path / "idt_order.csv"
        export_idt_csv(sdm_results, csv_path)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == ["Name", "Sequence", "Scale", "Purification"]

    def test_idt_csv_row_count(self, sdm_results, tmp_path):
        csv_path = tmp_path / "idt_order.csv"
        export_idt_csv(sdm_results, csv_path)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        # header + 2 rows per result (fwd + rev)
        assert len(rows) == 1 + len(sdm_results) * 2

    def test_idt_csv_naming_convention(self, sdm_results, tmp_path):
        csv_path = tmp_path / "idt_order.csv"
        export_idt_csv(sdm_results, csv_path)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            for i, row in enumerate(reader):
                name = row[0]
                if i % 2 == 0:
                    assert name.endswith("_F")
                else:
                    assert name.endswith("_R")

    def test_idt_csv_default_scale_and_purification(self, sdm_results, tmp_path):
        csv_path = tmp_path / "idt_order.csv"
        export_idt_csv(sdm_results, csv_path)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                assert row[2] == "25nm"
                assert row[3] == "STD"

    def test_idt_csv_custom_scale(self, sdm_results, tmp_path):
        csv_path = tmp_path / "idt_order.csv"
        export_idt_csv(sdm_results, csv_path, scale="100nm", purification="PAGE")
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                assert row[2] == "100nm"
                assert row[3] == "PAGE"


class TestExportTwistCsv:
    def test_twist_csv_creates_file(self, sdm_results, tmp_path):
        csv_path = tmp_path / "twist_order.csv"
        export_twist_csv(sdm_results, csv_path)
        assert csv_path.exists()
        assert csv_path.stat().st_size > 0

    def test_twist_csv_header(self, sdm_results, tmp_path):
        csv_path = tmp_path / "twist_order.csv"
        export_twist_csv(sdm_results, csv_path)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert header == ["Name", "Sequence", "Notes"]

    def test_twist_csv_row_count(self, sdm_results, tmp_path):
        csv_path = tmp_path / "twist_order.csv"
        export_twist_csv(sdm_results, csv_path)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 1 + len(sdm_results) * 2

    def test_twist_csv_notes_contain_mutation(self, sdm_results, tmp_path):
        csv_path = tmp_path / "twist_order.csv"
        export_twist_csv(sdm_results, csv_path)
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                # Notes column should contain the mutation name
                assert len(row[2]) > 0
