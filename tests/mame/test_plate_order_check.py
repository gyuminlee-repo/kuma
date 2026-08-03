"""Does an exported workbook describe one plate, or two? (io/plate_order_check.py)"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from kuma_core.mame.io.plate_order_check import check_plate_order

REAL_EXPORT = Path(
    "/mnt/d/_workspace/020.admin/projects/070.KUMA_elements/260730 MAME test"
    "/260722_Ep_R2-1_platemap.xlsx"
)


def _workbook(path, plate_rows, expected_ids, plate_title="Fwd List"):
    wb = Workbook()
    plate = wb.worksheets[0]
    plate.title = plate_title
    plate.append(["Well", "Primer Name", "Mutation"])
    for well, mutation in plate_rows:
        plate.append([well, f"{mutation}_F", mutation])
    strict = wb.create_sheet("expected_mutations")
    strict.append(["mutant_id", "position", "wt_aa", "mt_aa", "status"])
    for mutation in expected_ids:
        strict.append([mutation, int(mutation[1:-1]), mutation[0], mutation[-1], "DESIGNED"])
    wb.save(path)
    return path


class TestAgreement:
    def test_matching_order_is_reported_clean(self, tmp_path):
        path = _workbook(
            tmp_path / "ok.xlsx",
            [("A1", "S11I"), ("B1", "S22T"), ("C1", "N28S")],
            ["S11I", "S22T", "N28S"],
        )

        report = check_plate_order(path)

        assert report.comparable is True
        assert report.ok is True

    def test_the_well_column_decides_not_the_row_order(self, tmp_path):
        """플레이트 시트의 행이 섞여 있어도 Well 열이 좌표다."""
        path = _workbook(
            tmp_path / "shuffled.xlsx",
            [("C1", "N28S"), ("A1", "S11I"), ("B1", "S22T")],
            ["S11I", "S22T", "N28S"],
        )

        assert check_plate_order(path).ok is True


class TestDisagreement:
    def test_a_reordered_expected_sheet_is_reported_with_the_well(self, tmp_path):
        path = _workbook(
            tmp_path / "reordered.xlsx",
            [("A1", "S11I"), ("B1", "S22T"), ("C1", "N28S")],
            ["N28S", "S11I", "S22T"],
        )

        report = check_plate_order(path)

        assert report.mismatched is True
        assert report.examples[0] == ("A1", "S11I", "N28S")

    def test_a_well_missing_from_the_expected_sheet_is_named(self, tmp_path):
        """V263I 사례. 뒤쪽 well 이 전부 한 칸 밀린다."""
        path = _workbook(
            tmp_path / "missing.xlsx",
            [("A1", "R262N"), ("B1", "V263I"), ("C1", "I277V")],
            ["R262N", "I277V"],
        )

        report = check_plate_order(path)

        assert report.missing_from_expected == ["V263I"]
        assert report.ok is False
        assert ("B1", "V263I", "I277V") in report.examples


class TestNotComparable:
    def test_a_file_without_the_expected_sheet_is_not_called_consistent(self, tmp_path):
        wb = Workbook()
        wb.worksheets[0].title = "Fwd List"
        wb.worksheets[0].append(["Well", "Mutation"])
        wb.worksheets[0].append(["A1", "S11I"])
        path = tmp_path / "plate-only.xlsx"
        wb.save(path)

        report = check_plate_order(path)

        # 비교 불가와 일치는 다르다. 침묵을 합격으로 읽지 못하게 한다.
        assert report.comparable is False

    def test_a_missing_file_is_not_comparable(self, tmp_path):
        assert check_plate_order(tmp_path / "nope.xlsx").comparable is False


class TestGridSheet:
    def test_a_plate_grid_can_supply_the_order(self, tmp_path):
        wb = Workbook()
        grid = wb.worksheets[0]
        grid.title = "Fwd Plate"
        grid.append(["", "1", "2"])
        grid.append(["A", "S11I_F", "K53I_F"])
        grid.append(["B", "S22T_F", ""])
        strict = wb.create_sheet("expected_mutations")
        strict.append(["mutant_id", "status"])
        for mutation in ("S11I", "S22T", "K53I"):
            strict.append([mutation, "DESIGNED"])
        path = tmp_path / "grid.xlsx"
        wb.save(path)

        report = check_plate_order(path)

        assert report.plate_sheet == "Fwd Plate"
        assert report.ok is True


@pytest.mark.skipif(not REAL_EXPORT.exists(), reason="260730 test data not on this machine")
def test_the_260722_export_is_reported_as_mismatched():
    report = check_plate_order(REAL_EXPORT)

    assert report.comparable is True
    assert report.mismatched is True
    assert report.missing_from_expected == ["V263I"]
    # 첫 well 부터 어긋난다. 프라이머 목록은 S11I 로 시작하고 expected 시트는 V233I 다.
    assert report.examples[0] == ("A1", "S11I", "V233I")
    assert report.plate_sheet == "Fwd List"
