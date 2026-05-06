"""Parser for mutants-well position.xlsx plate layout files.

v0.3 Phase A-1.
Spec: notes/architecture/2026-05-06-v0.3-phase-ab-interfaces.md §2-1

Uses python-calamine (openpyxl forbidden — Agilent fill-style incompatibility).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import python_calamine

logger = logging.getLogger(__name__)

# Regex for valid well position: letter A-H + 1 or 2 digits.
_WELL_RE = re.compile(r"^[A-H][0-9]{1,2}$")

_WT_LITERAL = "WT"


@dataclass(frozen=True)
class PlateLayoutEntry:
    """Single row parsed from a plate layout xlsx.

    mutant: Internal notation e.g. 'F89W', or 'WT' for WT wells.
    well_id: Well identifier A01–H12 (normalised to 2-digit column).
    is_wt: True when mutant == 'WT' (case-insensitive).
    """

    mutant: str
    well_id: str
    is_wt: bool


def _normalise_well(raw: str) -> str:
    """Normalise well position to letter + zero-padded 2-digit column.

    'H9' → 'H09', 'A12' stays 'A12'.
    Caller must validate raw before calling.
    """
    return f"{raw[0]}{int(raw[1:]):02d}"


def parse_plate_layout_xlsx(
    path: str | Path,
    *,
    sheet_index: int = 0,
) -> list[PlateLayoutEntry]:
    """Parse mutants-well position.xlsx into a list of PlateLayoutEntry.

    Header detection:
        Scans the first row for columns named 'Mutant' and 'Well Pos.'
        (case-insensitive). Raises if either is missing.

    WT row detection:
        Rows where the Mutant cell is 'WT' (case-insensitive) produce
        PlateLayoutEntry with is_wt=True.

    Well position validation:
        Each Well Pos. value must match [A-H][0-9]{1,2}. Non-matching
        values raise ValueError with the offending row information.

    Args:
        path:        Path to the xlsx file.
        sheet_index: Zero-based sheet index (default 0).

    Returns:
        List of PlateLayoutEntry, one per data row.

    Raises:
        ValueError: 'Mutant' or 'Well Pos.' column not found in header row.
        ValueError: A Well Pos. cell does not match the expected pattern.
        FileNotFoundError: *path* does not exist (raised by calamine).
    """
    resolved = Path(path)

    workbook = python_calamine.CalamineWorkbook.from_path(str(resolved))
    sheets = workbook.sheet_names
    if sheet_index >= len(sheets):
        raise ValueError(
            f"parse_plate_layout_xlsx: sheet_index={sheet_index} out of range "
            f"(file has {len(sheets)} sheet(s)): {resolved}"
        )
    sheet = workbook.get_sheet_by_index(sheet_index)
    rows: list[list] = list(sheet.to_python())

    if not rows:
        raise ValueError(
            f"parse_plate_layout_xlsx: sheet is empty in {resolved}"
        )

    # --- Header detection (first row, case-insensitive) ---
    header = [str(cell).strip() for cell in rows[0]]
    header_lower = [h.lower() for h in header]

    mutant_col: int | None = None
    well_col: int | None = None
    for idx, name in enumerate(header_lower):
        if name == "mutant":
            mutant_col = idx
        elif name in ("well pos.", "well pos", "well_pos", "wellpos"):
            well_col = idx

    if mutant_col is None:
        raise ValueError(
            f"parse_plate_layout_xlsx: 'Mutant' column not found in header. "
            f"Found columns: {header!r} in {resolved}"
        )
    if well_col is None:
        raise ValueError(
            f"parse_plate_layout_xlsx: 'Well Pos.' column not found in header. "
            f"Found columns: {header!r} in {resolved}"
        )

    # --- Data rows ---
    entries: list[PlateLayoutEntry] = []
    for row_idx, row in enumerate(rows[1:], start=2):  # 1-based for error msg
        # Extend row if shorter than expected (calamine may omit trailing empty).
        while len(row) <= max(mutant_col, well_col):
            row = list(row) + [""]

        raw_mutant = str(row[mutant_col]).strip()
        raw_well = str(row[well_col]).strip()

        if not raw_mutant and not raw_well:
            # Fully blank row — skip silently.
            continue

        # Well position validation — raise on mismatch (spec §2-1).
        if not _WELL_RE.match(raw_well):
            raise ValueError(
                f"parse_plate_layout_xlsx: invalid Well Pos. {raw_well!r} "
                f"at row {row_idx} in {resolved}. "
                "Expected pattern [A-H][0-9]{1,2} (e.g. 'H12')."
            )

        well_id = _normalise_well(raw_well)
        is_wt = raw_mutant.upper() == _WT_LITERAL

        entries.append(
            PlateLayoutEntry(
                mutant=raw_mutant,
                well_id=well_id,
                is_wt=is_wt,
            )
        )

    logger.debug(
        "parse_plate_layout_xlsx: parsed %d entries from %s",
        len(entries),
        resolved.name,
    )
    return entries
