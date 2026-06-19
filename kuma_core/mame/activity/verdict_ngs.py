"""Parse an Analyze verdict xlsx into a {well_id: verdict_class} map.

The file-based EVOLVEpro reports build can optionally gate variants on an NGS
verdict: a well whose verdict is an explicit non-PASS class (an NGS-failed
design) is excluded from the assembled input. The verdict source is the
Analyze Excel report's Final sheet, whose header includes ``well_id``,
``mutant_id`` and ``verdict``. Header positions are resolved by name (not
index) so layout drift between report versions does not silently mis-read a
column.

Reading uses python-calamine (the repo convention; openpyxl is write-only).
"""

from __future__ import annotations

from pathlib import Path

import python_calamine

from kuma_core.mame.activity.plate_layout_xlsx import _normalise_well

_PASS = "PASS"


def parse_verdict_wells(path: str | Path) -> dict[str, str]:
    """Parse {well_id(A01..): verdict_class_upper} from an Analyze verdict xlsx.

    Scans every sheet; picks the sheet whose header row (case-insensitive,
    stripped) contains BOTH a well column ('well_id' or 'well') AND 'verdict'.
    Prefers a sheet that also has 'mutant_id' or 'selected_plate' (the Final
    per-well sheet). One row per well; on duplicate wells, PASS wins (a well is
    PASS if any of its rows is PASS), else the last non-empty verdict. Wells are
    normalised to zero-padded form ('A1'->'A01'). Rows with an empty well or
    empty verdict are skipped.

    Args:
        path: Path to an Analyze verdict xlsx.

    Returns:
        Mapping {well_id: verdict_class} with verdict classes upper-cased.

    Raises:
        ValueError: no sheet contains both a well column and a verdict column.
    """
    resolved = Path(path)
    wb = python_calamine.CalamineWorkbook.from_path(str(resolved))

    best_rows: list[list] | None = None
    best_well_col = -1
    best_verdict_col = -1
    best_score = -1

    for idx in range(len(wb.sheet_names)):
        rows: list[list] = list(wb.get_sheet_by_index(idx).to_python())
        if not rows:
            continue
        header = [str(cell).strip().lower() for cell in rows[0]]

        if "well_id" in header:
            well_col = header.index("well_id")
        elif "well" in header:
            well_col = header.index("well")
        else:
            continue
        if "verdict" not in header:
            continue
        verdict_col = header.index("verdict")

        score = 1 if ("mutant_id" in header or "selected_plate" in header) else 0
        if score > best_score:
            best_score = score
            best_rows = rows
            best_well_col = well_col
            best_verdict_col = verdict_col

    if best_rows is None:
        raise ValueError(
            f"no sheet with well + verdict columns found in {resolved}"
        )

    result: dict[str, str] = {}
    for row in best_rows[1:]:
        extended = list(row)
        while len(extended) <= max(best_well_col, best_verdict_col):
            extended.append("")
        raw_well = str(extended[best_well_col]).strip().upper()
        raw_verdict = str(extended[best_verdict_col]).strip().upper()
        if not raw_well or not raw_verdict:
            continue
        try:
            well = _normalise_well(raw_well)
        except (ValueError, IndexError):
            # Non-well value in the well column (defensive); skip the row.
            continue
        # PASS-priority dedupe: a well counts PASS if any of its rows is PASS;
        # otherwise the last non-empty verdict for that well wins.
        if result.get(well) == _PASS:
            continue
        if raw_verdict == _PASS:
            result[well] = _PASS
        else:
            result[well] = raw_verdict

    return result
