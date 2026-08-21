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

# Regex for valid well position on a 96-well plate: row A-H, column 1-12.
#
# Written out rather than as [0-9]{1,2}, which also accepted A0, A00 and
# everything up to A99. Those are not wells, and _normalise_well turned A0 into
# A00, so a typo became a plate address that no plate has and that nothing
# downstream could match back to a sample.
_WELL_RE = re.compile(r"^[A-H](?:0?[1-9]|1[0-2])$")

_WT_LITERAL = "WT"

# Experimenter replicate suffix: '<sample name>_r<n>' (case-insensitive 'r').
# The greedy name group keeps inner underscores intact, so only the trailing
# suffix is removed ('A40P_E61Y_r1' -> 'A40P_E61Y').
_REPLICATE_SUFFIX_RE = re.compile(r"^(?P<name>.+)_[rR](?P<rep>\d+)$")

# Sample name reserved for empty wells; excluded from the parsed entries.
_BLANK_LITERAL = "blank"


def _strip_replicate_suffix(label: str) -> str:
    """Remove a trailing '_r<n>' replicate suffix from *label*.

    Labels without the suffix are returned unchanged.
    """
    match = _REPLICATE_SUFFIX_RE.match(label)
    if match is None:
        return label
    return match.group("name")


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
    """Parse a plate layout xlsx into a list of PlateLayoutEntry.

    Header detection:
        Two column pairs are accepted, and each pair is atomic:
          - 'Mutant' + 'Well Pos.'      (plate layout format, legacy)
          - 'sample_name' + 'well'      (sample map format, the sheet the
            MAME barcode package already generates for step 1/2)
        Matching is case-insensitive. When a sheet carries both pairs the
        plate layout pair wins and a warning is logged. Raises when neither
        pair is complete.

    Replicate suffix:
        A trailing '_r<n>' on the label (the experimenter notation, 'r'
        case-insensitive) marks a replicate of the same sample and is stripped
        before every other rule applies: 'Q232A_r1' and 'Q232A_r2' both become
        mutant 'Q232A' on their own wells. Only the trailing suffix is removed,
        so multi-substitution labels keep their inner underscores
        ('A40P_E61Y_r1' -> 'A40P_E61Y'). Labels without the suffix pass through
        unchanged.

    Blank rows:
        Rows whose sample name (after suffix stripping) is 'blank'
        (case-insensitive) mark empty wells and are omitted from the result.

    WT row detection:
        Rows whose label cell is 'WT' (case-insensitive, after suffix
        stripping) produce PlateLayoutEntry with is_wt=True. Identical for
        both formats.

    Well position validation:
        Each well value must match [A-H][0-9]{1,2}. Non-matching
        values raise ValueError with the offending row information.

    Args:
        path:        Path to the xlsx file.
        sheet_index: Zero-based sheet index (default 0).

    Returns:
        List of PlateLayoutEntry, one per data row.

    Raises:
        ValueError: Neither accepted column pair found in the header row.
        ValueError: A well cell does not match the expected pattern.
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
    well_pos_col: int | None = None
    sample_name_col: int | None = None
    well_col: int | None = None
    for idx, name in enumerate(header_lower):
        if name == "mutant":
            mutant_col = idx
        elif name in ("well pos.", "well pos", "well_pos", "wellpos"):
            well_pos_col = idx
        elif name in ("sample_name", "sample name", "samplename"):
            sample_name_col = idx
        elif name == "well":
            well_col = idx

    # Column pairs are atomic: a 'Mutant' + 'well' mix does not form a layout.
    if mutant_col is not None and well_pos_col is not None:
        if sample_name_col is not None and well_col is not None:
            logger.warning(
                "parse_plate_layout_xlsx: header carries both the plate "
                "layout pair ('Mutant', 'Well Pos.') and the sample map pair "
                "('sample_name', 'well') in %s. Using the plate layout pair.",
                resolved,
            )
        label_col, position_col = mutant_col, well_pos_col
    elif sample_name_col is not None and well_col is not None:
        label_col, position_col = sample_name_col, well_col
    else:
        raise ValueError(
            "parse_plate_layout_xlsx: no supported column pair found in "
            "header. Expected either 'Mutant' + 'Well Pos.' (plate layout) "
            "or 'sample_name' + 'well' (sample map). "
            f"Found columns: {header!r} in {resolved}"
        )

    # --- Data rows ---
    entries: list[PlateLayoutEntry] = []
    for row_idx, row in enumerate(rows[1:], start=2):  # 1-based for error msg
        # Extend row if shorter than expected (calamine may omit trailing empty).
        while len(row) <= max(label_col, position_col):
            row = list(row) + [""]

        raw_mutant = str(row[label_col]).strip()
        raw_well = str(row[position_col]).strip()

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
        sample_name = _strip_replicate_suffix(raw_mutant)

        if sample_name.lower() == _BLANK_LITERAL:
            # Empty well marker; carries no mutant.
            continue

        is_wt = sample_name.upper() == _WT_LITERAL

        entries.append(
            PlateLayoutEntry(
                mutant=sample_name,
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
