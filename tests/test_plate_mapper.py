"""Tests for plate mapping, Excel export, and order CSV export."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kuro.plate_mapper import (
    PlateMapping,
    deduplicate_reverse,
    export_echo_mapping_csv,
    export_idt_csv,
    export_janus_mapping_csv,
    export_plate_excel,
    export_twist_csv,
    generate_plate_map,
    _to_384_well_fwd,
    _to_384_well_rev,
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


class Test384WellConversion:
    def test_fwd_row_mapping(self):
        assert _to_384_well_fwd("A1") == "A1"
        assert _to_384_well_fwd("B1") == "C1"
        assert _to_384_well_fwd("C1") == "E1"
        assert _to_384_well_fwd("H1") == "O1"
        assert _to_384_well_fwd("A12") == "A12"

    def test_rev_row_mapping(self):
        assert _to_384_well_rev("A1") == "B1"
        assert _to_384_well_rev("B1") == "D1"
        assert _to_384_well_rev("C1") == "F1"
        assert _to_384_well_rev("H1") == "P1"

    def test_fwd_rev_no_overlap(self):
        wells_96 = [f"{r}{c}" for c in range(1, 13) for r in "ABCDEFGH"]
        fwd_384 = {_to_384_well_fwd(w) for w in wells_96}
        rev_384 = {_to_384_well_rev(w) for w in wells_96}
        assert fwd_384.isdisjoint(rev_384)


class TestEchoMappingExport:
    def test_row_count(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        rev_groups = deduplicate_reverse(sdm_results)
        csv_path = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, csv_path, rev_groups=rev_groups)

        with open(csv_path, encoding="utf-8") as f:
            rows = list(csv.reader(f))

        # Header + one row per fwd + one row per (rev→dest) pair
        # With dedup, rev rows = len(fwd) (one dest per mutation)
        assert len(rows) == 1 + len(fwd) + len(fwd)

    def test_header(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        csv_path = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, csv_path)

        with open(csv_path, encoding="utf-8") as f:
            header = next(csv.reader(f))

        assert header == [
            "Source Plate Name", "Source Well Name", "Source Well",
            "Dest Plate Name", "Dest Well Name", "Dest Well", "Transfer Vol",
        ]

    def test_source_plate_constant(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        csv_path = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, csv_path)

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                assert row[0] == "Source [1]"
                assert row[3] == "Destination [1]"

    def test_transfer_vol_default(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        csv_path = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, csv_path)

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                assert row[6] == "100"

    def test_fwd_source_well_odd_rows(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        csv_path = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, csv_path)

        odd_384_rows = set("ACEGIKMO")
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            fwd_rows = [row for row in reader if row[1].endswith("_F")]
        for row in fwd_rows:
            assert row[2][0] in odd_384_rows, f"Fwd source well {row[2]} not in odd rows"

    def test_rev_source_well_even_rows(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        csv_path = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, csv_path)

        even_384_rows = set("BDFHJLNP")
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            rev_rows = [row for row in reader if row[1].endswith("_R")]
        for row in rev_rows:
            assert row[2][0] in even_384_rows, f"Rev source well {row[2]} not in even rows"


class TestJanusMappingExport:
    def test_row_count(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        rev_groups = deduplicate_reverse(sdm_results)
        csv_path = tmp_path / "janus.csv"
        export_janus_mapping_csv(fwd, rev, csv_path, rev_groups=rev_groups)

        with open(csv_path, encoding="utf-8") as f:
            rows = list(csv.reader(f))

        assert len(rows) == 1 + len(fwd) + len(fwd)

    def test_header(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        csv_path = tmp_path / "janus.csv"
        export_janus_mapping_csv(fwd, rev, csv_path)

        with open(csv_path, encoding="utf-8") as f:
            header = next(csv.reader(f))

        assert header == [
            "name", "type", "Dsp. Rack", "no",
            "Asp. Rack", "Asp. Posi", "Dsp. Rack", "Dsp. Posi", "volume",
        ]

    def test_asp_rack_separation(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        csv_path = tmp_path / "janus.csv"
        export_janus_mapping_csv(fwd, rev, csv_path)

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            rows = list(reader)

        fw_rows = [r for r in rows if r[0].endswith("-fw")]
        rv_rows = [r for r in rows if r[0].endswith("-rv")]
        assert all(r[4] == "1" for r in fw_rows), "fw rows must use Asp. Rack 1"
        assert all(r[4] == "2" for r in rv_rows), "rv rows must use Asp. Rack 2"

    def test_transfer_vol_default(self, sdm_results, tmp_path):
        fwd, rev = generate_plate_map(sdm_results, deduplicate_rev=True)
        csv_path = tmp_path / "janus.csv"
        export_janus_mapping_csv(fwd, rev, csv_path)

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                assert float(row[8]) == 2.0
