"""Literal text cells for metadata sheets that never contain formulas."""
from __future__ import annotations

from collections.abc import Iterable
from openpyxl.worksheet.worksheet import Worksheet


def append_literal_row(sheet: Worksheet, values: Iterable[object]) -> None:
    """Keep external text (including leading '=') as XLSX strings, verbatim."""
    row = list(values)
    sheet.append(row)
    for index, value in enumerate(row, start=1):
        if isinstance(value, str):
            sheet.cell(row=sheet.max_row, column=index).data_type = "s"
