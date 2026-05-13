"""Tests for Macrogen Plate Oligo .xls exporter."""

import pytest
import xlrd

from kuro.plate_mapper import PlateMapping, export_macrogen_xls


def _mk(seq: str, name: str, ptype: str = "forward") -> PlateMapping:
    return PlateMapping(
        well="A1",
        primer_name=name,
        sequence=seq,
        primer_type=ptype,
        mutation="",
    )


def test_macrogen_export_1plate_1well(tmp_path):
    out = tmp_path / "out.xls"
    export_macrogen_xls(
        fwd_primers=[_mk("ATCG", "p1")],
        rev_primers=[],
        fwd_plate_name="P1",
        rev_plate_name="",
        amount="0.05",
        purification="MOPC",
        output_path=str(out),
    )
    wb = xlrd.open_workbook(str(out))
    s = wb.sheets()[0]
    assert s.cell_value(0, 0) == "No."
    assert s.cell_value(1, 1) == "P1"
    assert s.cell_value(1, 2) == "A1"
    assert s.cell_value(1, 3) == "p1"
    assert s.cell_value(1, 4) == "ATCG"
    assert s.cell_value(1, 5) == "0.05"
    assert s.cell_value(1, 6) == "MOPC"


def test_column_major_well_order(tmp_path):
    primers = [_mk("A" * 4, f"p{i}") for i in range(9)]
    out = tmp_path / "out.xls"
    export_macrogen_xls(
        fwd_primers=primers,
        rev_primers=[],
        fwd_plate_name="P1",
        rev_plate_name="",
        amount="0.05",
        purification="MOPC",
        output_path=str(out),
    )
    wb = xlrd.open_workbook(str(out))
    s = wb.sheets()[0]
    wells = [s.cell_value(i, 2) for i in range(1, 10)]
    assert wells == ["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1", "A2"]


def test_2plates_concatenated(tmp_path):
    out = tmp_path / "out.xls"
    export_macrogen_xls(
        fwd_primers=[_mk("AAA", "f1", "forward")],
        rev_primers=[_mk("TTT", "r1", "reverse")],
        fwd_plate_name="Pfwd",
        rev_plate_name="Prev",
        amount="0.05",
        purification="MOPC",
        output_path=str(out),
    )
    wb = xlrd.open_workbook(str(out))
    s = wb.sheets()[0]
    assert s.nrows == 1 + 96 + 96
    assert s.cell_value(1, 1) == "Pfwd"
    assert s.cell_value(97, 1) == "Prev"
    assert s.cell_value(97, 0) == 97


def test_overflow_raises(tmp_path):
    out = tmp_path / "out.xls"
    with pytest.raises(ValueError, match="exceeds 96"):
        export_macrogen_xls(
            fwd_primers=[_mk("A", f"p{i}") for i in range(97)],
            rev_primers=[],
            fwd_plate_name="P1",
            rev_plate_name="",
            amount="0.05",
            purification="MOPC",
            output_path=str(out),
        )


def test_plate_name_rejects_korean(tmp_path):
    with pytest.raises(ValueError, match="plate name"):
        export_macrogen_xls(
            fwd_primers=[_mk("A", "p")],
            rev_primers=[],
            fwd_plate_name="한글",
            rev_plate_name="",
            amount="0.05",
            purification="MOPC",
            output_path=str(tmp_path / "x.xls"),
        )


def test_oligo_name_rejects_space(tmp_path):
    with pytest.raises(ValueError, match="oligo name"):
        export_macrogen_xls(
            fwd_primers=[_mk("A", "p 1")],
            rev_primers=[],
            fwd_plate_name="P",
            rev_plate_name="",
            amount="0.05",
            purification="MOPC",
            output_path=str(tmp_path / "x.xls"),
        )
