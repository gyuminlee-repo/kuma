"""Generic variant-list input for MAME (io/variant_list.py)."""

from __future__ import annotations

import pytest
from openpyxl import Workbook

from kuma_core.mame.io.variant_list import (
    inspect_variant_source,
    read_variant_source,
)
from kuma_core.mame.layout import build_draft_layout


def _write_sheet(path, rows, sheet_title="Sheet1"):
    wb = Workbook()
    ws = wb.worksheets[0]
    ws.title = sheet_title
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _write_kuro_export(path, mutants):
    """A KURO results xlsx: 10 fixed columns on an `expected_mutations` sheet."""
    wb = Workbook()
    wb.worksheets[0].title = "primers"
    ws = wb.create_sheet("expected_mutations")
    ws.append([
        "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon",
        "mt_codon", "group_id", "primer_set_ref", "notation_type", "status",
    ])
    for mutant_id, position, wt, mt, status in mutants:
        ws.append([mutant_id, position, wt, mt, "GTG", "TTT", "", "", "single", status])
    wb.save(path)
    return path


class TestPlainList:
    def test_rows_are_read_in_file_order(self, tmp_path):
        path = _write_sheet(
            tmp_path / "variants.xlsx",
            [["variant"], ["V5F"], ["K53N"], ["T10A"]],
        )

        result = read_variant_source(path)

        # 파일에 적힌 순서가 곧 plate 순서다. 정렬하지 않는다.
        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N", "T10A"]

    def test_label_is_split_into_the_fields_verdict_comparison_uses(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["variant"], ["V5F"]])

        (mutation,) = read_variant_source(path).expected

        assert (mutation.wt_aa, mutation.position, mutation.mt_aa) == ("V", 5, "F")
        # MAME 가 읽지 않는 필드는 지어내지 않는다.
        assert mutation.wt_codon == ""
        assert mutation.group_id == ""

    def test_order_survives_into_the_draft_layout(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], ["K53N"], ["T10A"]],
        )

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, include_wt=not result.has_explicit_wt)

        assert list(draft.layout.values())[:3] == ["V5F", "K53N", "T10A"]
        assert draft.is_complete

    @pytest.mark.parametrize("header", ["variant", "Mutation", "MUTANT_ID", "variants"])
    def test_common_header_names_are_recognised(self, tmp_path, header):
        path = _write_sheet(tmp_path / "v.xlsx", [[header], ["V5F"]])

        assert read_variant_source(path).variant_column == header

    def test_single_unnamed_column_is_used_without_asking(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["anything"], ["V5F"], ["K53N"]])

        assert len(read_variant_source(path).expected) == 2

    def test_ambiguous_columns_ask_instead_of_guessing(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["alpha", "beta"], ["V5F", "x"]],
        )

        with pytest.raises(ValueError, match="cannot tell which column"):
            read_variant_source(path)

    def test_named_column_wins(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["note", "target"], ["ignore", "V5F"], ["ignore", "K53N"]],
        )

        result = read_variant_source(path, variant_column="target")

        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]

    def test_named_sheet_wins(self, tmp_path):
        wb = Workbook()
        first = wb.worksheets[0]
        first.title = "notes"
        first.append(["variant"])
        first.append(["A1G"])
        ws = wb.create_sheet("round2")
        ws.append(["variant"])
        ws.append(["V5F"])
        path = tmp_path / "v.xlsx"
        wb.save(path)

        result = read_variant_source(path, sheet="round2")

        assert [m.mutant_id for m in result.expected] == ["V5F"]
        assert result.sheet == "round2"

    def test_blank_rows_are_skipped_not_placed(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], [None], [""], ["K53N"]],
        )

        assert [m.mutant_id for m in read_variant_source(path).expected] == ["V5F", "K53N"]

    def test_csv_is_accepted(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("variant\nV5F\nK53N\n", encoding="utf-8")

        result = read_variant_source(path)

        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]
        assert result.sheet is None


class TestWildTypeRow:
    def test_explicit_wt_row_is_reported_not_parsed(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], ["WT"], ["K53N"]],
        )

        result = read_variant_source(path)

        assert result.has_explicit_wt is True
        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]

    def test_plate_gets_one_wt_well_not_two(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["variant"], ["V5F"], ["WT"]])

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, include_wt=not result.has_explicit_wt)

        assert list(draft.layout.values()).count("WT") == 0
        assert list(draft.layout.values()) == ["V5F"]

    def test_wt_is_still_appended_when_the_list_omits_it(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["variant"], ["V5F"]])

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, include_wt=not result.has_explicit_wt)

        assert result.has_explicit_wt is False
        assert list(draft.layout.values()) == ["V5F", "WT"]


class TestRefusals:
    def test_unreadable_notation_names_the_row(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], ["not-a-mutation"]],
        )

        with pytest.raises(ValueError, match="row 3"):
            read_variant_source(path)

    def test_duplicate_variant_is_refused_with_both_rows(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], ["K53N"], ["V5F"]],
        )

        with pytest.raises(ValueError, match="duplicate variant 'V5F'.*rows 2 and 4"):
            read_variant_source(path)

    def test_a_list_with_no_variants_is_refused(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["variant"]])

        with pytest.raises(ValueError, match="no variants found"):
            read_variant_source(path)

    def test_missing_named_column_lists_what_is_available(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["alpha", "beta"], ["V5F", "x"]])

        with pytest.raises(ValueError, match="alpha, beta"):
            read_variant_source(path, variant_column="gamma")

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_variant_source(tmp_path / "absent.xlsx")


class TestKuroExportStillWorks:
    def test_kuro_export_is_routed_to_the_strict_reader(self, tmp_path):
        path = _write_kuro_export(
            tmp_path / "kuro.xlsx",
            [("V5F", 5, "V", "F", "DESIGNED"), ("K53N", 53, "K", "N", "DESIGNED")],
        )

        result = read_variant_source(path)

        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]
        assert result.sheet == "expected_mutations"
        # 강한 판독 경로를 그대로 타므로 codon 이 살아 있다.
        assert result.expected[0].wt_codon == "GTG"

    def test_kuro_status_filter_is_unchanged(self, tmp_path):
        path = _write_kuro_export(
            tmp_path / "kuro.xlsx",
            [
                ("V5F", 5, "V", "F", "DESIGNED"),
                ("Z9Z", 9, "Z", "Z", "FAILED"),
                ("K53N", 53, "K", "N", "DESIGNED"),
            ],
        )

        result = read_variant_source(path)

        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]

    def test_kuro_export_never_reports_an_explicit_wt(self, tmp_path):
        path = _write_kuro_export(tmp_path / "kuro.xlsx", [("V5F", 5, "V", "F", "DESIGNED")])

        assert read_variant_source(path).has_explicit_wt is False


class TestInspect:
    def test_reports_sheets_and_headers_for_a_plain_workbook(self, tmp_path):
        wb = Workbook()
        first = wb.worksheets[0]
        first.title = "first"
        first.append(["variant", "note"])
        wb.create_sheet("second").append(["x"])
        path = tmp_path / "v.xlsx"
        wb.save(path)

        info = inspect_variant_source(path)

        assert info.is_kuro_export is False
        assert info.sheets == ["first", "second"]
        assert info.headers["first"] == ["variant", "note"]
        assert info.suggested_column == "variant"

    def test_flags_a_kuro_export_so_no_mapping_is_asked_for(self, tmp_path):
        path = _write_kuro_export(tmp_path / "kuro.xlsx", [("V5F", 5, "V", "F", "DESIGNED")])

        info = inspect_variant_source(path)

        assert info.is_kuro_export is True
        assert info.suggested_column is None

    def test_reports_no_suggestion_when_columns_are_ambiguous(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["alpha", "beta"], ["V5F", "x"]])

        assert inspect_variant_source(path).suggested_column is None


class TestExplicitSheetBeatsRecognition:
    """One workbook can hold the strict sheet next to the sheet built on the bench."""

    def _mixed_workbook(self, path):
        """`expected_mutations` and a plate sheet carrying the same set, reordered."""
        wb = Workbook()
        plate = wb.worksheets[0]
        plate.title = "Fwd List"
        plate.append(["Well", "Primer Name", "Mutation"])
        for well, mutant in (("A1", "S11I"), ("B1", "S22T"), ("C1", "K53I")):
            plate.append([well, f"{mutant}_F", mutant])
        strict = wb.create_sheet("expected_mutations")
        strict.append([
            "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon",
            "mt_codon", "group_id", "primer_set_ref", "notation_type", "status",
        ])
        # Same three mutants, design order rather than plate order.
        for mutant_id, position, wt, mt in (
            ("K53I", 53, "K", "I"), ("S11I", 11, "S", "I"), ("S22T", 22, "S", "T"),
        ):
            strict.append(
                [mutant_id, position, wt, mt, "GTG", "TTT", "", "", "single", "DESIGNED"]
            )
        wb.save(path)
        return path

    def test_naming_another_sheet_reads_that_sheet(self, tmp_path):
        path = self._mixed_workbook(tmp_path / "platemap.xlsx")

        result = read_variant_source(path, sheet="Fwd List", variant_column="Mutation")

        # 플레이트 시트를 고르면 그 순서가 곧 well 순서다.
        assert [m.mutant_id for m in result.expected] == ["S11I", "S22T", "K53I"]
        # column-major: seq 1..3 -> A1,B1,C1 이고 WT 는 그 다음 칸이다.
        layout = build_draft_layout(result.expected).layout
        assert [layout[w] for w in ("A1", "B1", "C1")] == ["S11I", "S22T", "K53I"]
        assert layout["D1"] == "WT"

    def test_naming_no_sheet_keeps_the_strict_reader(self, tmp_path):
        path = self._mixed_workbook(tmp_path / "platemap.xlsx")

        result = read_variant_source(path)

        assert result.sheet == "expected_mutations"
        assert [m.mutant_id for m in result.expected] == ["K53I", "S11I", "S22T"]

    def test_naming_the_strict_sheet_keeps_the_strict_reader(self, tmp_path):
        path = self._mixed_workbook(tmp_path / "platemap.xlsx")

        result = read_variant_source(path, sheet="expected_mutations")

        assert result.variant_column == "mutant_id"
        assert [m.mutant_id for m in result.expected] == ["K53I", "S11I", "S22T"]

    def test_headers_are_offered_for_every_sheet_of_a_kuro_export(self, tmp_path):
        path = self._mixed_workbook(tmp_path / "platemap.xlsx")

        info = inspect_variant_source(path)

        # 강판독이 기본이라는 사실은 유지하되, 다른 시트를 고를 재료는 준다.
        assert info.is_kuro_export is True
        assert "Fwd List" in info.sheets
        assert info.headers["Fwd List"] == ["Well", "Primer Name", "Mutation"]
