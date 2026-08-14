"""Generic variant-list input for MAME (io/variant_list.py)."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from kuma_core.mame.io.variant_list import (
    inspect_variant_source,
    read_variant_source,
)
from kuma_core.mame.layout import build_draft_layout

#: Repository root, from this file rather than from the working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]


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
        draft = build_draft_layout(result.expected, wt_ordinal=result.wt_ordinal)

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

    def test_internal_blank_rows_are_refused_rather_than_skipped(self, tmp_path):
        """예전에는 조용히 흡수했다. 그게 K53N 을 한 칸 앞으로 당겼다."""
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], [None], [""], ["K53N"]],
        )

        with pytest.raises(ValueError, match="row 3.*row 4"):
            read_variant_source(path)

    def test_csv_is_accepted(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("variant\nV5F\nK53N\n", encoding="utf-8")

        result = read_variant_source(path)

        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]
        assert result.sheet is None


class TestWildTypeRow:
    def test_explicit_wt_row_keeps_its_place_in_the_order(self, tmp_path):
        """WT 행은 버려지지 않고 배치 서수를 갖는다.

        예전에는 이 행을 ``continue`` 로 버려서, WT 뒤의 변이가 전부 한 칸씩
        앞으로 당겨졌다. 결과는 꽉 찬 정상 플레이트처럼 보였고 어디에도
        밀렸다는 표시가 없었다.
        """
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], ["WT"], ["K53N"]],
        )

        result = read_variant_source(path)

        assert result.wt_ordinal == 2
        assert result.has_explicit_wt is True
        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]

    def test_the_wells_after_an_explicit_wt_do_not_move_up(self, tmp_path):
        """The regression, stated as wells rather than as an ordinal."""
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], ["WT"], ["K53N"]],
        )

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, wt_ordinal=result.wt_ordinal)

        assert list(draft.layout.items()) == [
            ("A1", "V5F"),
            ("B1", "WT"),
            ("C1", "K53N"),
        ]

    def test_plate_gets_one_wt_well_not_two(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["variant"], ["V5F"], ["WT"]])

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, wt_ordinal=result.wt_ordinal)

        assert list(draft.layout.values()).count("WT") == 1
        assert list(draft.layout.values()) == ["V5F", "WT"]

    def test_wt_is_appended_when_the_list_omits_it(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["variant"], ["V5F"]])

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, wt_ordinal=result.wt_ordinal)

        assert result.wt_ordinal is None
        assert result.has_explicit_wt is False
        assert list(draft.layout.values()) == ["V5F", "WT"]

    def test_two_wt_rows_name_both_of_them(self, tmp_path):
        """One plate carries one WT well, so the file has to say which row it is."""
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], ["WT"], ["K53N"], ["wt"]],
        )

        with pytest.raises(ValueError, match="rows 3 and 5"):
            read_variant_source(path)


class TestRowsThatCannotBePlaced:
    """행 순서가 곧 플레이트 순서이므로, 읽고 배치하지 못한 행은 거절된다."""

    def test_internal_blank_row_is_named_and_refused(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], [None], ["K53N"]],
        )

        with pytest.raises(ValueError, match="row 3"):
            read_variant_source(path)

    def test_trailing_blank_rows_are_openpyxl_phantoms_and_ignored(self, tmp_path):
        """마지막 값 뒤의 빈 행은 아무것도 밀지 않으므로 보고하지 않는다."""
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["variant"], ["V5F"], ["K53N"], [None], [None]],
        )

        result = read_variant_source(path)

        assert [m.mutant_id for m in result.expected] == ["V5F", "K53N"]

    def test_kuro_status_filter_drops_are_named_and_refused(self, tmp_path):
        """두 판독기가 서로 다른 행 집합을 보던 자리.

        플레이트 순서 검사가 status 를 보지 않고 같은 시트를 따로 읽던 시절,
        조용히 걸러진 행 하나가 두 판독기의 웰 번호를 통째로 어긋나게 했다.
        그 검사는 이제 이 리더가 정한 배치를 그대로 쓴다.
        """
        path = _write_kuro_export(
            tmp_path / "kuro.xlsx",
            [
                ("V5F", 5, "V", "F", "DESIGNED"),
                ("Z9Z", 9, "Z", "Z", "FAILED"),
                ("K53N", 53, "K", "N", "DESIGNED"),
            ],
        )

        with pytest.raises(ValueError, match="row 3.*FAILED"):
            read_variant_source(path)


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

    def test_kuro_status_filter_itself_is_unchanged(self, tmp_path):
        """필터 규칙은 그대로다. 달라진 것은 조용하지 않다는 것뿐이다."""
        from kuma_core.mame.io.kuro_reader import read_expected_mutations_with_rows

        path = _write_kuro_export(
            tmp_path / "kuro.xlsx",
            [
                ("V5F", 5, "V", "F", "DESIGNED"),
                ("Z9Z", 9, "Z", "Z", "FAILED"),
                ("K53N", 53, "K", "N", "DESIGNED"),
            ],
        )

        read = read_expected_mutations_with_rows(path)

        assert [m.mutant_id for m in read.expected] == ["V5F", "K53N"]
        assert read.row_numbers == [2, 4]
        assert read.dropped_rows == [(3, "FAILED")]

    def test_kuro_export_wt_row_follows_the_same_rule_as_a_plain_list(self, tmp_path):
        """두 분기의 WT 규칙이 통일됐다.

        KURO 분기는 ``has_explicit_wt=False`` 를 하드코딩하고 있었다. 그래서
        자기 WT 행을 가진 KURO 시트에 대조군 웰이 하나 더 붙었고, 그 행 뒤의
        웰은 전부 한 칸 밀렸다.
        """
        path = _write_kuro_export(
            tmp_path / "kuro.xlsx",
            [
                ("V5F", 5, "V", "F", "DESIGNED"),
                ("WT", 0, "A", "A", "DESIGNED"),
                ("K53N", 53, "K", "N", "DESIGNED"),
            ],
        )

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, wt_ordinal=result.wt_ordinal)

        assert result.wt_ordinal == 2
        assert list(draft.layout.items()) == [
            ("A1", "V5F"),
            ("B1", "WT"),
            ("C1", "K53N"),
        ]

    def test_kuro_export_without_a_wt_row_reports_none(self, tmp_path):
        path = _write_kuro_export(tmp_path / "kuro.xlsx", [("V5F", 5, "V", "F", "DESIGNED")])

        assert read_variant_source(path).wt_ordinal is None


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


class TestControlStatusWildType:
    """KURO writes its WT row as `status=control`, which is not a design.

    The status filter removed it, the reader reported that removal as a row it
    could not place, and the whole workbook was refused. Every KURO export
    carrying its own control row was unreadable, the two shipped ones included.
    """

    def test_a_control_status_wt_row_does_not_refuse_the_file(self, tmp_path):
        path = _write_kuro_export(
            tmp_path / "kuro.xlsx",
            [
                ("M001", 5, "V", "F", "designed"),
                ("WT", 0, "-", "-", "control"),
                ("M002", 53, "K", "N", "designed"),
            ],
        )

        result = read_variant_source(path)

        assert [m.mutant_id for m in result.expected] == ["M001", "M002"]

    def test_the_control_row_occupies_the_well_its_row_number_names(self, tmp_path):
        """대조군 행은 자기 순서의 웰을 차지한다. 버리면 뒤가 한 칸씩 당겨진다."""
        path = _write_kuro_export(
            tmp_path / "kuro.xlsx",
            [
                ("M001", 5, "V", "F", "designed"),
                ("WT", 0, "-", "-", "control"),
                ("M002", 53, "K", "N", "designed"),
            ],
        )

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, wt_ordinal=result.wt_ordinal)

        assert result.wt_ordinal == 2
        assert list(draft.layout.items()) == [
            ("A1", "M001"),
            ("B1", "WT"),
            ("C1", "M002"),
        ]

    def test_a_mutant_row_is_still_judged_by_status_alone(self, tmp_path):
        """판정 기준은 라벨이지 status 가 아니다. 진짜 mutant 는 그대로 걸린다."""
        path = _write_kuro_export(
            tmp_path / "kuro.xlsx",
            [
                ("M001", 5, "V", "F", "designed"),
                ("M002", 9, "Z", "Z", "control"),
                ("M003", 53, "K", "N", "designed"),
            ],
        )

        with pytest.raises(ValueError, match="row 3.*control"):
            read_variant_source(path)

    @pytest.mark.parametrize(
        ("relative", "occupants"),
        [
            ("templates/03_mame_expected_mutations.xlsx", 8),
            ("src-tauri/samples/mame/03_mame_expected_mutations.xlsx", 10),
        ],
    )
    def test_the_shipped_workbooks_are_readable(self, relative, occupants):
        """Help -> Load Sample Data 가 읽는 바로 그 파일들이다."""
        path = _REPO_ROOT / relative
        assert path.exists(), path

        result = read_variant_source(path)

        # WT 는 두 파일 모두 마지막 행이므로 서수는 점유자 수와 같다.
        assert result.wt_ordinal == occupants
        assert len(result.expected) == occupants - 1
        assert "WT" not in [m.mutant_id for m in result.expected]


class TestHeaderlessList:
    """헤더 없이 변이만 적은 파일에서 첫 변이가 컬럼명으로 먹히던 자리.

    예외도 경고도 없이 첫 변이가 사라졌고, 남은 변이가 전부 한 칸씩 앞으로
    당겨졌다. 이 모듈이 막으려는 바로 그 밀림이 이 경로만 무증상이었다.
    """

    def test_the_first_variant_is_not_eaten_as_a_column_name(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("S65T\nY66H\n", encoding="utf-8")

        result = read_variant_source(path)
        draft = build_draft_layout(result.expected, wt_ordinal=result.wt_ordinal)

        assert [m.mutant_id for m in result.expected] == ["S65T", "Y66H"]
        assert draft.layout["A1"] == "S65T"
        assert draft.layout["B1"] == "Y66H"

    def test_the_absence_of_a_header_is_reported_rather_than_a_variant(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("S65T\nY66H\n", encoding="utf-8")

        assert read_variant_source(path).variant_column == "(no header)"

    def test_row_numbers_start_at_one_because_no_row_is_a_header(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("S65T\nnot-a-mutation\n", encoding="utf-8")

        with pytest.raises(ValueError, match="row 2"):
            read_variant_source(path)

    def test_a_named_column_does_not_reopen_the_hole(self, tmp_path):
        """UI 는 inspect 의 제안을 그대로 넘긴다. 인자가 있어도 헤더리스다."""
        path = tmp_path / "v.csv"
        path.write_text("S65T\nY66H\n", encoding="utf-8")

        result = read_variant_source(path, variant_column="S65T")

        assert [m.mutant_id for m in result.expected] == ["S65T", "Y66H"]
        assert result.variant_column == "(no header)"

    def test_a_wt_first_row_is_recognised_too(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("WT\nS65T\n", encoding="utf-8")

        result = read_variant_source(path)

        assert result.wt_ordinal == 1
        assert [m.mutant_id for m in result.expected] == ["S65T"]

    def test_an_xlsx_without_a_header_reads_the_same_way(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["S65T"], ["Y66H"]])

        result = read_variant_source(path)

        assert [m.mutant_id for m in result.expected] == ["S65T", "Y66H"]

    def test_a_lower_case_first_variant_is_not_eaten_either(self, tmp_path):
        """소문자 표기도 데이터다. 컬럼명으로 먹히면 조용히 사라진다.

        ``parse_mutation_notation`` 은 대문자만 받으므로, 이 행은 헤더리스로
        인식된 뒤 파서에 넘어가 행 번호와 함께 큰 소리로 거절된다. 그것이
        아무 말 없이 한 칸 밀린 플레이트보다 낫다.
        """
        path = tmp_path / "v.csv"
        path.write_text("s65t\nY66H\n", encoding="utf-8")

        with pytest.raises(ValueError, match="row 1"):
            read_variant_source(path)

    def test_a_lower_case_first_variant_is_not_offered_as_a_column(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("s65t\nY66H\n", encoding="utf-8")

        assert inspect_variant_source(path).suggested_column is None

    def test_a_named_header_still_behaves_exactly_as_before(self, tmp_path):
        """회귀 방지. 헤더가 있으면 헤더고, 데이터 행은 2 부터다."""
        path = tmp_path / "v.csv"
        path.write_text("variant\nS65T\nnot-a-mutation\n", encoding="utf-8")

        with pytest.raises(ValueError, match="row 3"):
            read_variant_source(path)

    def test_a_header_that_is_a_variant_is_not_offered_as_a_column(self, tmp_path):
        """제안했다면 UI 가 그 값을 되넘겨 첫 변이를 잃게 했을 것이다."""
        path = tmp_path / "v.csv"
        path.write_text("S65T\nY66H\n", encoding="utf-8")

        assert inspect_variant_source(path).suggested_column is None

    def test_a_lone_ordinary_header_is_still_suggested(self, tmp_path):
        path = _write_sheet(tmp_path / "v.xlsx", [["anything"], ["V5F"]])

        assert inspect_variant_source(path).suggested_column == "anything"


class TestMultiColumnFirstRowIsRefused:
    """다열 파일에서는 첫 행이 헤더인지 데이터인지 파일이 말해주지 않는다.

    단열은 비어있지 않은 셀이 하나뿐이라 추론이 결정적이지만, 다열에서는
    나머지 열이 헤더일 수도 값일 수도 있다. 헤더로 읽으면 첫 변이를 잃고
    데이터로 읽으면 나머지 열의 이름을 지어내는 셈이라 어느 쪽도 고를 수
    없다. 그래서 추측하지 않고 거절한다.
    """

    def test_a_named_column_whose_header_is_a_variant_is_refused(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("S65T,plate1\nY66H,plate1\n", encoding="utf-8")

        with pytest.raises(ValueError, match="'S65T' in v.csv is itself a variant"):
            read_variant_source(path, variant_column="S65T")

    def test_the_refusal_says_what_to_do_about_it(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("S65T,plate1\nY66H,plate1\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Add a header row"):
            read_variant_source(path, variant_column="S65T")

    def test_a_wt_label_header_is_refused_the_same_way(self, tmp_path):
        path = tmp_path / "v.csv"
        path.write_text("WT,plate1\nY66H,plate1\n", encoding="utf-8")

        with pytest.raises(ValueError, match="'WT' in v.csv is itself a variant"):
            read_variant_source(path, variant_column="WT")

    def test_the_variant_is_not_quietly_dropped_instead(self, tmp_path):
        """거절 전에는 이 입력이 `['Y66H']` 로 조용히 통과했다."""
        path = tmp_path / "v.csv"
        path.write_text("S65T,plate1\nY66H,plate1\n", encoding="utf-8")

        with pytest.raises(ValueError):
            read_variant_source(path, variant_column="S65T")

    def test_an_xlsx_is_refused_the_same_way(self, tmp_path):
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [["S65T", "plate1"], ["Y66H", "plate1"]],
        )

        with pytest.raises(ValueError, match="itself a variant"):
            read_variant_source(path, variant_column="S65T")

    def test_a_single_column_headerless_file_still_reads(self, tmp_path):
        """경계. 단열은 추론이 결정적이므로 거절 대상이 아니다."""
        path = tmp_path / "v.csv"
        path.write_text("S65T\nY66H\n", encoding="utf-8")

        result = read_variant_source(path, variant_column="S65T")

        assert [m.mutant_id for m in result.expected] == ["S65T", "Y66H"]

    @pytest.mark.parametrize("header", ["variant", "mutation", "mutant_id"])
    def test_ordinary_header_names_are_untouched(self, tmp_path, header):
        """정상 헤더명은 변이로 파싱되지 않으므로 이 규칙에 걸리지 않는다."""
        path = _write_sheet(
            tmp_path / "v.xlsx",
            [[header, "note"], ["S65T", "x"], ["Y66H", "x"]],
        )

        result = read_variant_source(path, variant_column=header)

        assert [m.mutant_id for m in result.expected] == ["S65T", "Y66H"]

    def test_naming_no_column_keeps_the_old_message(self, tmp_path):
        """컬럼을 안 넘긴 다열 파일의 거절 문구는 그대로다."""
        path = tmp_path / "v.csv"
        path.write_text("S65T,plate1\nY66H,plate1\n", encoding="utf-8")

        with pytest.raises(ValueError, match="cannot tell which column"):
            read_variant_source(path)
