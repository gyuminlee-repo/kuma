"""Does the clone plate the run fills sit where the primer plate says?

(``io/clone_plate_crosscheck.py``)

The fixtures here are the same shape ``test_plate_order_check.py`` uses, and
deliberately so: both modules read one KURO export, and a fixture that only one
of them accepts would make a difference between the two look like a difference
in the export.
"""

from __future__ import annotations

from openpyxl import Workbook

from kuma_core.mame.io.clone_plate_crosscheck import crosscheck_clone_plate
from kuma_core.mame.io.plate_order_check import check_plate_order

#: The ten columns a KURO export writes, in order. The strict reader checks them
#: exactly, so an abbreviated header is not an export and is refused before any
#: comparison runs.
_STRICT_HEADER = [
    "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon",
    "mt_codon", "group_id", "primer_set_ref", "notation_type", "status",
]


def _expected_row(mutant_id: str, group_id: str = "") -> list:
    """One ``expected_mutations`` row for a single substitution."""
    return [
        mutant_id, int(mutant_id[1:-1]), mutant_id[0], mutant_id[-1],
        "GTG", "TTT", group_id, "", "single", "DESIGNED",
    ]


def _workbook(path, plate_rows, expected_rows, plate_title="Fwd List"):
    """A KURO export: a primer plate sheet with stated wells, and an expected sheet."""
    wb = Workbook()
    plate = wb.worksheets[0]
    plate.title = plate_title
    plate.append(["Well", "Primer Name", "Mutation"])
    for well, mutation in plate_rows:
        plate.append([well, f"{mutation}_F", mutation])
    sheet = wb.create_sheet("expected_mutations")
    sheet.append(_STRICT_HEADER)
    for row in expected_rows:
        sheet.append(row if isinstance(row, list) else _expected_row(row))
    wb.save(path)
    return path


class TestTheComparisonRuns:
    def test_a_design_ordered_export_disagrees_with_the_clone_plate(self, tmp_path):
        """KURO wells follow the sheet; the run fills by residue position.

        The sheet here is written S22T, S11I, N28S, so the primer plate puts
        S22T in A1. The clone plate orders by position and puts S11I there. Two
        wells differ and the third, C1, holds N28S on both.
        """
        path = _workbook(
            tmp_path / "design_order.xlsx",
            [("A1", "S22T"), ("B1", "S11I"), ("C1", "N28S")],
            ["S22T", "S11I", "N28S"],
        )

        report = crosscheck_clone_plate(path)

        assert report.status == "mismatch"
        assert report.plate_sheet == "Fwd List"
        assert report.mismatch_count == 2
        assert report.wells_compared == 3
        assert report.examples == [
            ("A1", "S22T", "S11I"),
            ("B1", "S11I", "S22T"),
        ]

    def test_the_export_that_disagrees_here_agrees_with_itself(self, tmp_path):
        """The two checks answer different questions about the same file.

        Without this the new finding could be read as a restatement of the old
        one. The same workbook is internally consistent and still names a
        different clone in A1 than the plate the run fills.
        """
        path = _workbook(
            tmp_path / "design_order.xlsx",
            [("A1", "S22T"), ("B1", "S11I"), ("C1", "N28S")],
            ["S22T", "S11I", "N28S"],
        )

        assert check_plate_order(path).ok is True
        assert crosscheck_clone_plate(path).status == "mismatch"

    def test_a_position_ordered_export_agrees(self, tmp_path):
        path = _workbook(
            tmp_path / "position_order.xlsx",
            [("A1", "S11I"), ("B1", "S22T"), ("C1", "N28S")],
            ["S11I", "S22T", "N28S"],
        )

        report = crosscheck_clone_plate(path)

        assert report.status == "match"
        assert report.mismatch_count == 0
        assert report.examples == []
        assert report.reportable is False

    def test_the_control_well_is_not_a_disagreement(self, tmp_path):
        """H12 holds the control and no primer, which is not two answers."""
        path = _workbook(
            tmp_path / "position_order.xlsx",
            [("A1", "S11I"), ("B1", "S22T")],
            ["S11I", "S22T"],
        )

        report = crosscheck_clone_plate(path)

        assert report.status == "match"
        assert report.wells_compared == 2

    def test_examples_are_capped_and_the_count_is_not(self, tmp_path):
        """An operator sees a few wells; the number is the whole plate."""
        sheet_order = [f"S{position}I" for position in range(20, 10, -1)]
        wells = [f"{row}1" for row in "ABCDEFGH"] + ["A2", "B2"]
        path = _workbook(
            tmp_path / "reversed.xlsx",
            list(zip(wells, sheet_order)),
            sheet_order,
        )

        report = crosscheck_clone_plate(path, max_examples=3)

        assert report.status == "mismatch"
        assert report.mismatch_count == 10
        assert len(report.examples) == 3


class TestTheComparisonCannotRun:
    def test_a_combination_genotype_is_not_comparable(self, tmp_path):
        """One clone, two primer pairs, so a well is not one address on both sides."""
        path = _workbook(
            tmp_path / "combo.xlsx",
            [("A1", "S11I"), ("B1", "S22T")],
            [
                _expected_row("S11I", group_id="G1"),
                _expected_row("S11I", group_id="G1"),
                _expected_row("S22T"),
            ],
        )

        report = crosscheck_clone_plate(path)

        assert report.status == "combination"
        assert report.reportable is False

    def test_a_stated_well_column_is_not_compared_again(self, tmp_path):
        """Both sides then read the same addresses out of the file.

        ``build_clone_plate_layout`` passes a stated placement through without
        reordering it, so the comparison would reproduce ``check_plate_order``,
        which already runs and already blocks on a disagreement. Reporting a
        result here would claim a second, independent comparison.
        """
        path = _workbook(
            tmp_path / "stated.xlsx",
            [("A1", "S22T"), ("B1", "S11I")],
            ["S22T", "S11I"],
        )
        from openpyxl import load_workbook

        wb = load_workbook(path)
        stated = wb.create_sheet("Plate Order")
        stated.append(["Well", "Variant"])
        stated.append(["A1", "S22T"])
        stated.append(["B1", "S11I"])
        wb.save(path)

        report = crosscheck_clone_plate(path, sheet="Plate Order")

        assert report.status == "stated_wells"
        assert report.reportable is False

    def test_a_workbook_without_a_plate_sheet_says_so(self, tmp_path):
        path = _workbook(
            tmp_path / "no_plate.xlsx",
            [],
            ["S11I", "S22T"],
            plate_title="Notes",
        )

        assert crosscheck_clone_plate(path).status == "no_plate_sheet"

    def test_a_workbook_without_an_expected_sheet_says_so(self, tmp_path):
        wb = Workbook()
        plate = wb.worksheets[0]
        plate.title = "Fwd List"
        plate.append(["Well", "Mutation"])
        plate.append(["A1", "S11I"])
        wb.save(tmp_path / "primers_only.xlsx")

        report = crosscheck_clone_plate(tmp_path / "primers_only.xlsx")

        assert report.status == "no_expected_sheet"

    def test_a_missing_file_is_a_value_not_an_exception(self, tmp_path):
        assert crosscheck_clone_plate(tmp_path / "absent.xlsx").status == "not_a_workbook"

    def test_a_csv_is_not_a_workbook(self, tmp_path):
        path = tmp_path / "list.csv"
        path.write_text("variant\nS11I\n", encoding="utf-8")

        assert crosscheck_clone_plate(path).status == "not_a_workbook"

    def test_an_unreadable_variant_list_is_lowered_to_a_status(self, tmp_path):
        """The loading path reports this refusal; a diagnostic must not repeat it."""
        path = _workbook(
            tmp_path / "duplicate.xlsx",
            [("A1", "S11I"), ("B1", "S22T")],
            [
                _expected_row("S11I", group_id="G1"),
                _expected_row("S11I", group_id="G2"),
            ],
        )

        report = crosscheck_clone_plate(path)

        assert report.status == "unreadable"
        assert report.reportable is False
