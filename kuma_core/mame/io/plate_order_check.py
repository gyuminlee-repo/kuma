"""Does an exported workbook describe one plate, or two?

A KURO export carries the primer plate on ``Fwd List``/``Fwd Plate`` and the expected
variants on ``expected_mutations``. MAME reads row *i* of the expected sheet as well
*i*, so the two are the same statement written twice and they have to agree.

Exports written before v0.14.3 did not agree. The plate sheets came from the plate
mapping while the expected sheet followed the design ranking, so the same mutants sat
in different wells depending on which sheet was read. Nothing failed: every well got a
variant, the counts looked right, and the verdicts were scored against a plate nobody
had built. On the 260722 R2-1 export `K53I` sits at A2 by the primer list and `I92D`
sits there by the expected sheet.

A silent wrong answer is worth more noise than a loud one, so this reports the
disagreement rather than repairing it. Repair needs the operator to say which sheet
describes the tubes they actually pipetted, and that is not a guess to make for them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

#: The sheet MAME reads as the plate order.
EXPECTED_SHEET = "expected_mutations"
#: Sheets that carry the primer plate, in preference order. The first one present wins.
PLATE_SHEETS = ("Fwd List", "Fwd Plate")

_MUTATION = re.compile(r"^([A-Z])(\d+)([A-Z])$")


@dataclass(frozen=True)
class PlateOrderReport:
    """What the two sheets disagree about, if anything."""

    #: True when the file could be compared at all (both kinds of sheet present).
    comparable: bool
    #: True when a comparison ran and the orders differ.
    mismatched: bool = False
    #: ``(well, from_plate_sheet, from_expected_sheet)`` for the first few wells that
    #: disagree. Wells are labelled column-major, the order MAME assigns.
    examples: list[tuple[str, str, str]] = field(default_factory=list)
    #: Mutants on the plate with no row in the expected sheet. Each one shifts every
    #: later well by one, so this is a mismatch even when the shared rows line up.
    missing_from_expected: list[str] = field(default_factory=list)
    #: Rows in the expected sheet naming a mutant the plate does not carry.
    absent_from_plate: list[str] = field(default_factory=list)
    #: Which sheet supplied the plate order.
    plate_sheet: str | None = None

    @property
    def ok(self) -> bool:
        """True when nothing was found to report."""
        return not self.mismatched and not self.missing_from_expected


def _cell_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _mutation_from_primer(name: str) -> str:
    """Strip the ``_F``/``_R`` suffix a primer name carries."""
    stem = name[:-2] if name.upper().endswith(("_F", "_R")) else name
    return stem if _MUTATION.match(stem) else ""


def _plate_order_from_list_sheet(worksheet) -> list[str]:
    """Read a ``Fwd List`` sheet: a Well column plus a mutation or primer name."""
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [_cell_text(c).lower() for c in rows[0]]

    def column(*names: str) -> int | None:
        for name in names:
            if name in headers:
                return headers.index(name)
        return None

    well_at = column("well")
    label_at = column("mutation", "mutant_id", "primer name", "primer_name")
    if well_at is None or label_at is None:
        return []
    ordered: list[tuple[str, str]] = []
    for row in rows[1:]:
        if max(well_at, label_at) >= len(row):
            continue
        well = _cell_text(row[well_at]).upper()
        label = _cell_text(row[label_at])
        mutation = label if _MUTATION.match(label) else _mutation_from_primer(label)
        if well and mutation:
            ordered.append((well, mutation))
    # The Well column is the authority, not the row order, so sort by it column-major.
    def key(pair: tuple[str, str]) -> tuple[int, int]:
        well = pair[0]
        row_index = ord(well[0]) - ord("A")
        column_number = int(well[1:]) if well[1:].isdigit() else 0
        return (column_number, row_index)

    return [mutation for _, mutation in sorted(ordered, key=key)]


def _plate_order_from_grid_sheet(worksheet) -> list[str]:
    """Read a ``Fwd Plate`` grid: row labels down the side, column numbers on top."""
    rows = list(worksheet.iter_rows(values_only=True))
    if len(rows) < 2:
        return []
    header = [_cell_text(c) for c in rows[0]]
    cells: dict[tuple[int, int], str] = {}
    for row in rows[1:]:
        if not row:
            continue
        row_label = _cell_text(row[0]).upper()
        if len(row_label) != 1 or not ("A" <= row_label <= "P"):
            continue
        for index, value in enumerate(row[1:], start=1):
            if index >= len(header) or not header[index].isdigit():
                continue
            label = _cell_text(value)
            mutation = label if _MUTATION.match(label) else _mutation_from_primer(label)
            if mutation:
                cells[(int(header[index]), ord(row_label) - ord("A"))] = mutation
    return [cells[key] for key in sorted(cells)]


def _expected_order(worksheet) -> list[str]:
    rows = list(worksheet.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [_cell_text(c).lower() for c in rows[0]]
    at = headers.index("mutant_id") if "mutant_id" in headers else 0
    return [
        _cell_text(row[at])
        for row in rows[1:]
        if at < len(row) and _cell_text(row[at])
    ]


def _well_label(sequence: int) -> str:
    """Column-major well label for a 1-based index, matching ``seq_to_well``."""
    return f"{chr(ord('A') + (sequence - 1) % 8)}{(sequence - 1) // 8 + 1}"


def check_plate_order(path: Path, max_examples: int = 5) -> PlateOrderReport:
    """Compare the plate sheets against ``expected_mutations`` in *path*.

    A file missing either kind of sheet is reported as not comparable rather than as
    consistent, so a caller cannot read silence as agreement.
    """
    path = Path(path)
    if path.suffix.lower() not in {".xlsx", ".xlsm"} or not path.exists():
        return PlateOrderReport(comparable=False)

    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if EXPECTED_SHEET not in workbook.sheetnames:
            return PlateOrderReport(comparable=False)
        plate_order: list[str] = []
        plate_sheet: str | None = None
        for name in PLATE_SHEETS:
            if name not in workbook.sheetnames:
                continue
            reader = (
                _plate_order_from_list_sheet
                if name.endswith("List")
                else _plate_order_from_grid_sheet
            )
            plate_order = reader(workbook[name])
            if plate_order:
                plate_sheet = name
                break
        if not plate_order:
            return PlateOrderReport(comparable=False)
        expected_order = _expected_order(workbook[EXPECTED_SHEET])
    finally:
        workbook.close()

    if not expected_order:
        return PlateOrderReport(comparable=False, plate_sheet=plate_sheet)

    expected_set = set(expected_order)
    plate_set = set(plate_order)
    examples: list[tuple[str, str, str]] = []
    for index, plate_mutation in enumerate(plate_order, start=1):
        if index > len(expected_order):
            break
        found = expected_order[index - 1]
        if found != plate_mutation and len(examples) < max_examples:
            examples.append((_well_label(index), plate_mutation, found))

    return PlateOrderReport(
        comparable=True,
        mismatched=bool(examples) or len(plate_order) != len(expected_order),
        examples=examples,
        missing_from_expected=[m for m in plate_order if m not in expected_set],
        absent_from_plate=[m for m in expected_order if m not in plate_set],
        plate_sheet=plate_sheet,
    )


__all__ = ["EXPECTED_SHEET", "PLATE_SHEETS", "PlateOrderReport", "check_plate_order"]
