"""The plate a barcode file has to describe, and what happens when it does not.

Both failures these cover are silent in the product they were found in: a set
numbered past the plate loses the well coordinate (empty cell in the workbook,
indistinguishable from a well that failed to sequence), and a gap renumbers
everything after it (reads filed under the wrong column with nothing to show).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python-core"))

from kuma_core.mame.plate_geometry import (  # noqa: E402
    PLATE_CAPACITY,
    PLATE_COLS,
    PLATE_ROWS,
    check_barcode_layout,
)

FULL_R = list(range(1, PLATE_ROWS + 1))
FULL_F = list(range(1, PLATE_COLS + 1))


def test_plate_constants_describe_a_96_well_plate() -> None:
    assert (PLATE_ROWS, PLATE_COLS) == (8, 12)
    assert PLATE_CAPACITY == 96


def test_the_standard_set_fits_and_names_every_well() -> None:
    report = check_barcode_layout(FULL_R, FULL_F)
    assert report.fits
    assert report.out_of_range == ()
    assert report.gaps == ()
    assert report.describable_wells == PLATE_CAPACITY


def test_swapping_the_axes_is_reported_rather_than_silently_halved() -> None:
    # 12 reverse and 8 forward: still 96 combinations, but R is the row, so the
    # ninth through twelfth have no row to land on.
    report = check_barcode_layout(list(range(1, 13)), list(range(1, 9)))
    assert not report.fits
    assert report.out_of_range == (("R", 9), ("R", 10), ("R", 11), ("R", 12))
    # 8 usable rows x 8 columns: a third of the plate would come out unnamed.
    assert report.describable_wells == 64


def test_a_set_that_is_not_8_by_12_is_reported_even_when_it_multiplies_to_96() -> None:
    report = check_barcode_layout(list(range(1, 5)), list(range(1, 25)))
    assert not report.fits
    assert ("F", 13) in report.out_of_range
    assert report.describable_wells == 4 * PLATE_COLS


def test_a_gap_is_reported_because_it_shifts_every_later_barcode() -> None:
    # load_barcode_prefixes sorts by index and keeps position, so 1, 2, 5 makes
    # the matcher call the third barcode F3 and file _f_5 reads under column 3.
    report = check_barcode_layout(FULL_R, [1, 2, 5])
    assert report.gaps == (("F", 3), ("F", 4))
    # Nothing is out of range here, so `fits` alone would call this file good.
    assert report.fits


def test_duplicate_indices_collapse() -> None:
    report = check_barcode_layout([1, 1, 2], [1, 2])
    assert report.r_indices == (1, 2)
    assert report.f_indices == (1, 2)


def test_an_empty_set_reports_nothing_out_of_range() -> None:
    report = check_barcode_layout([], [])
    assert report.fits
    assert report.gaps == ()
    assert report.describable_wells == 0


def _write_barcode_xlsx(path: Path, r_idx: list[int], f_idx: list[int]) -> Path:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    for i in f_idx:
        ws.append([f"isps_f_{i}", "ACGTACGTACcacaggaggttaaacc"])
    for i in r_idx:
        ws.append([f"isps_r_{i}", "TGCATGCATGtgcgttgcgctctag"])
    wb.save(path)
    return path


def test_validation_accepts_a_standard_barcode_file(tmp_path: Path) -> None:
    from sidecar_mame.handlers.analyze import _barcode_layout_error

    path = _write_barcode_xlsx(tmp_path / "bc.xlsx", FULL_R, FULL_F)
    assert _barcode_layout_error(path) is None


def test_validation_names_the_indices_that_fall_off_the_plate(tmp_path: Path) -> None:
    from sidecar_mame.handlers.analyze import _barcode_layout_error

    path = _write_barcode_xlsx(tmp_path / "bc.xlsx", list(range(1, 13)), list(range(1, 9)))
    message = _barcode_layout_error(path)
    assert message is not None
    assert "R9" in message
    # The operator has to be able to act on it, so the message states the rule.
    assert "1..8" in message and "1..12" in message


def test_validation_names_a_gap(tmp_path: Path) -> None:
    from sidecar_mame.handlers.analyze import _barcode_layout_error

    path = _write_barcode_xlsx(tmp_path / "bc.xlsx", FULL_R, [1, 2, 5])
    message = _barcode_layout_error(path)
    assert message is not None
    assert "F3" in message and "F4" in message


def test_validation_reports_a_file_with_no_barcode_rows(tmp_path: Path) -> None:
    from sidecar_mame.handlers.analyze import _barcode_layout_error

    path = _write_barcode_xlsx(tmp_path / "bc.xlsx", [], [])
    message = _barcode_layout_error(path)
    assert message is not None
    assert "isps_f_1" in message
