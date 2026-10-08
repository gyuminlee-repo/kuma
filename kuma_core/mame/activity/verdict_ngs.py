"""Parse an Analyze verdict xlsx into strict per-well NGS evidence.

Duplicate canonical wells must agree exactly. Conflicting rows are retained as
``CONFLICT`` evidence, which Step 3 treats as non-evaluable rather than letting
an arbitrary PASS row override a failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import python_calamine

from kuma_core.mame.activity.plate_layout_xlsx import _normalise_well

_PASS = "PASS"
_CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class VerdictRow:
    """One well's verdict-sheet record: verdict class, observed AA, mutant id."""

    verdict: str
    observed_aa: tuple[str, ...] = field(default_factory=tuple)
    mutant_id: str = ""
    is_fallback: bool = False
    failed: bool = False


def parse_verdict_rows(path: str | Path) -> dict[str, VerdictRow]:
    """Parse strict {well_id(A01..): VerdictRow} evidence from an Analyze xlsx.

    The selected sheet must contain a well and verdict column. Rows with empty
    or invalid wells/verdicts are skipped. Repeated canonical wells are accepted
    only when verdict, observed amino-acid evidence, and mutant identity agree;
    any disagreement becomes a ``CONFLICT`` row and is therefore non-evaluable.
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
    fallback_col = header.index("is_fallback") if "is_fallback" in header else -1
    failed_col = header.index("failed") if "failed" in header else -1

    max_col = max(
        best_well_col,
        best_verdict_col,
        observed_aa_col,
        mutant_id_col,
        fallback_col,
        failed_col,
    )

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
        is_fallback = (
            str(extended[fallback_col]).strip().upper() in {"Y", "YES", "TRUE", "1"}
            if fallback_col >= 0
            else False
        )
        failed = (
            str(extended[failed_col]).strip().upper() in {"Y", "YES", "TRUE", "1"}
            if failed_col >= 0
            else False
        )

        candidate = VerdictRow(
            verdict=raw_verdict,
            observed_aa=observed_aa,
            mutant_id=mutant_id,
            is_fallback=is_fallback,
            failed=failed,
        )
        existing = result.get(well)
        if existing is None:
            result[well] = candidate
        elif existing != candidate:
            # Keep an agreed identity so downstream gating reports the real
            # cause as a conflict instead of degrading it to missing evidence.
            shared_id = existing.mutant_id if existing.mutant_id == candidate.mutant_id else ""
            result[well] = VerdictRow(verdict=_CONFLICT, mutant_id=shared_id)

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
