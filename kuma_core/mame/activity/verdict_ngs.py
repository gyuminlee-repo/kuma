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

from dataclasses import dataclass, field
from pathlib import Path

import python_calamine

from kuma_core.mame.activity.plate_layout_xlsx import _normalise_well

_PASS = "PASS"


@dataclass(frozen=True)
class VerdictRow:
    """One well's verdict-sheet record: verdict class, observed AA, mutant id."""

    verdict: str
    observed_aa: tuple[str, ...] = field(default_factory=tuple)
    mutant_id: str = ""


def parse_verdict_rows(path: str | Path) -> dict[str, VerdictRow]:
    """Parse {well_id(A01..): VerdictRow} from an Analyze verdict xlsx.

    Scans every sheet; picks the sheet whose header row (case-insensitive,
    stripped) contains BOTH a well column ('well_id' or 'well') AND 'verdict'.
    Prefers a sheet that also has 'mutant_id' or 'selected_plate' (the Final
    per-well sheet). One row per well; on duplicate wells, PASS wins (a well is
    PASS if any of its rows is PASS), else the last non-empty verdict. Wells are
    normalised to zero-padded form ('A1'->'A01'). Rows with an empty well or
    empty verdict are skipped.

    ``observed_aa`` is read from an ``observed_aa`` column when present
    (comma-separated cell value split into a tuple); absent when the sheet
    predates that column. ``mutant_id`` is read from a 'mutant_id' column when
    present.

    Args:
        path: Path to an Analyze verdict xlsx.

    Returns:
        Mapping {well_id: VerdictRow}.

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

    header = [str(cell).strip().lower() for cell in best_rows[0]]
    observed_aa_col = header.index("observed_aa") if "observed_aa" in header else -1
    mutant_id_col = header.index("mutant_id") if "mutant_id" in header else -1

    max_col = max(best_well_col, best_verdict_col, observed_aa_col, mutant_id_col)

    result: dict[str, VerdictRow] = {}
    for row in best_rows[1:]:
        extended = list(row)
        while len(extended) <= max_col:
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

        if observed_aa_col >= 0:
            raw_observed = str(extended[observed_aa_col]).strip()
            observed_aa = tuple(
                part.strip() for part in raw_observed.split(",") if part.strip()
            )
        else:
            observed_aa = ()

        mutant_id = (
            str(extended[mutant_id_col]).strip() if mutant_id_col >= 0 else ""
        )

        # PASS-priority dedupe: a well counts PASS if any of its rows is PASS;
        # otherwise the last non-empty verdict for that well wins.
        existing = result.get(well)
        if existing is not None and existing.verdict == _PASS:
            continue
        verdict = _PASS if raw_verdict == _PASS else raw_verdict
        result[well] = VerdictRow(
            verdict=verdict, observed_aa=observed_aa, mutant_id=mutant_id
        )

    return result


def parse_verdict_wells(path: str | Path) -> dict[str, str]:
    """Parse {well_id(A01..): verdict_class_upper} from an Analyze verdict xlsx.

    Thin wrapper over :func:`parse_verdict_rows` retained for backward
    compatibility with existing callers/tests. See that function's docstring
    for the sheet-selection and dedupe rules.

    Args:
        path: Path to an Analyze verdict xlsx.

    Returns:
        Mapping {well_id: verdict_class} with verdict classes upper-cased.

    Raises:
        ValueError: no sheet contains both a well column and a verdict column.
    """
    return {well: row.verdict for well, row in parse_verdict_rows(path).items()}
