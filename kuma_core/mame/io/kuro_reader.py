"""KURO xlsx `expected_mutations` sheet adapter (Blocker B resolved)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from kuma_core.mame.models import ExpectedMutation

_EXPECTED_SHEET = "expected_mutations"
_EXPECTED_HEADER = [
    "mutant_id",
    "position",
    "wt_aa",
    "mt_aa",
    "wt_codon",
    "mt_codon",
    "group_id",
    "primer_set_ref",
    "notation_type",
    "status",
]
_DESIGNED_STATUSES = {
    "DESIGNED",
    "SAME_POSITION",
    "DIFF_POSITION",
    "AUTO_SUGGESTION",
    "AUTO_SUGGESTION_L1",
    "AUTO_SUGGESTION_L2",
    "AUTO_SUGGESTION_L3",
    "AUTO_SUGGESTION_L4",
    "POOL_CASCADE",
    "AUTO_RELAX",
}


@dataclass(frozen=True)
class KuroReadResult:
    """The designed rows of a KURO export, plus the rows the filter removed.

    Row numbers travel with both lists because a dropped row is not a neutral
    omission: MAME reads row order as plate order, so every row removed between
    two kept rows moves each later mutant one well up. Nothing downstream can
    see that shift once the rows are gone, which is why the caller is handed the
    row numbers rather than a count.
    """

    #: Designed rows, in sheet order.
    expected: list[ExpectedMutation]
    #: 1-based sheet row number of each element of :attr:`expected`, same order.
    row_numbers: list[int] = field(default_factory=list)
    #: ``(row number, status)`` for rows the status filter removed.
    dropped_rows: list[tuple[int, str]] = field(default_factory=list)


def read_expected_mutations(path: Path) -> list[ExpectedMutation]:
    """Read the designed rows of the `expected_mutations` sheet.

    Only designed rows are returned; FAILED rows are Phase 2. Interim KURO
    exports that stored rescue stage names in status are accepted as designed.
    Raises ValueError if the expected sheet is missing (old KURO version).

    Thin wrapper over :func:`read_expected_mutations_with_rows` for callers that
    only need the mutations. A caller that places wells wants the other reader:
    the rows this one drops shift every later well.
    """
    return read_expected_mutations_with_rows(path).expected


def read_expected_mutations_with_rows(path: Path) -> KuroReadResult:
    """Read the `expected_mutations` sheet, reporting what the filter removed.

    The filter itself is unchanged: a row whose status is outside
    ``_DESIGNED_STATUSES`` is not returned. What is new is that it is no longer
    silent. ``plate_order_check._expected_order`` reads the same sheet without
    looking at status, so the two readers see different row sets and disagree
    about which well each mutant sits in; naming the dropped rows is what lets a
    caller refuse that file instead of scoring the shifted plate.
    """

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if _EXPECTED_SHEET not in wb.sheetnames:
            raise ValueError(
                f"'{path}' cannot be read as an expected-variant list. MAME accepts "
                "either a KURO export (a workbook carrying an "
                f"'{_EXPECTED_SHEET}' sheet) or a plain variant list: one variant "
                "per row under a single variant column, in plate order. This file "
                "is neither."
            )
        ws = wb[_EXPECTED_SHEET]
        rows_iter = ws.iter_rows(values_only=True)
        header = next(rows_iter, None)
        if header is None:
            raise ValueError(f"'{_EXPECTED_SHEET}' sheet in '{path}' is empty.")
        header_list = [str(c) if c is not None else "" for c in header]
        expected = [h.lower() for h in _EXPECTED_HEADER]
        got = [h.strip().lower() for h in header_list]
        if got[: len(expected)] != expected:
            raise ValueError(
                f"'{_EXPECTED_SHEET}' header mismatch. Expected {expected}, got {got}."
            )

        results: list[ExpectedMutation] = []
        row_numbers: list[int] = []
        dropped_rows: list[tuple[int, str]] = []
        # Row 1 is the header, so data rows are numbered from 2 and the number
        # matches what the operator sees in Excel.
        for row_number, raw in enumerate(rows_iter, start=2):
            if raw is None or all(c is None or (isinstance(c, str) and not c.strip()) for c in raw):
                continue
            cells = list(raw) + [None] * (len(_EXPECTED_HEADER) - len(raw))
            status = _s(cells[9])
            if status.upper() not in _DESIGNED_STATUSES:
                dropped_rows.append((row_number, status))
                continue
            row_numbers.append(row_number)
            results.append(
                ExpectedMutation(
                    mutant_id=_s(cells[0]),
                    position=_int(cells[1]),
                    wt_aa=_s(cells[2]),
                    mt_aa=_s(cells[3]),
                    wt_codon=_s(cells[4]),
                    mt_codon=_s(cells[5]),
                    group_id=_s(cells[6]),
                    primer_set_ref=_s(cells[7]),
                    notation_type=_s(cells[8]),
                    status=status,
                )
            )
        return KuroReadResult(
            expected=results,
            row_numbers=row_numbers,
            dropped_rows=dropped_rows,
        )
    finally:
        wb.close()


def expected_to_labels(expected: list[ExpectedMutation]) -> list[str]:
    """Produce the human-readable mutation label list consumed by compare.verdict."""

    return [f"{m.wt_aa}{m.position}{m.mt_aa}" for m in expected]


def _s(cell: object) -> str:
    if cell is None:
        return ""
    return str(cell).strip()


def _int(cell: object) -> int:
    if cell is None:
        return 0
    try:
        return int(str(cell).strip())
    except (TypeError, ValueError):
        return 0
