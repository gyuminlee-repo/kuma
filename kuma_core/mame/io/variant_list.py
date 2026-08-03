"""Generic variant-list adapter for the MAME expected-variant input.

MAME needs one thing from this input: which variant is meant to be in each well,
in plate order. Until now the only accepted shape was a KURO results xlsx with an
``expected_mutations`` sheet whose first ten columns matched exactly, which left
anyone running MAME without KURO unable to supply a list they already had.

This module makes the file shape a detail instead of a requirement, the same way
the KURO input step stopped distinguishing an "EVOLVEpro CSV" from an "Others"
file and simply reads whichever sheet and column the user points at. A KURO
export keeps working untouched: it is recognised and routed to the strict reader,
so its ``status`` filter and rescue-stage handling are unchanged.

Recognition is a default, not a verdict. Naming a sheet overrides it, because one
workbook can carry the strict sheet next to the sheet that describes the plate on
the bench, and the two can disagree on both membership and order. Preferring the
strict sheet in that case places every well from a list nobody chose, and the
result reads like a finished plate rather than a mis-set one.

Row order is plate order. ``build_draft_layout`` already assigns well *i* from
element *i*, so a plain list needs no extra ordering rule. This is in fact more
faithful than the KURO path, where non-designed rows are filtered out first and
sheet row numbers therefore drift from well numbers.

The five fields MAME never reads (``wt_codon``, ``mt_codon``, ``group_id``,
``primer_set_ref``, ``notation_type``) are left empty rather than invented.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from kuma_core.kuro.mutation import parse_mutation_notation
from kuma_core.mame.io.kuro_reader import read_expected_mutations
from kuma_core.mame.models import ExpectedMutation

#: Sheet that marks a file as a KURO export. Routed to the strict reader.
KURO_SHEET = "expected_mutations"

#: Header names accepted as the variant column when the caller does not name one.
#: Matched case-insensitively after stripping.
_VARIANT_HEADER_CANDIDATES = (
    "variant",
    "variants",
    "mutant",
    "mutants",
    "mutation",
    "mutations",
    "mutant_id",
    "variant_id",
)

#: Labels that denote the wild-type control rather than a mutant.
_WT_LABELS = {"wt", "wildtype", "wild-type", "wild type", "control"}


@dataclass(frozen=True)
class VariantListReadResult:
    """Parsed variant list plus what the caller needs to know about it."""

    #: Plate-ordered mutants. Excludes any explicit WT row.
    expected: list[ExpectedMutation]
    #: True when the source listed a wild-type row itself. The draft layout must
    #: not then append its own WT well, or the plate ends up with two.
    has_explicit_wt: bool
    #: Sheet the values were read from. ``None`` for CSV.
    sheet: str | None
    #: Header of the column the values were read from, for reporting back.
    variant_column: str


@dataclass(frozen=True)
class VariantSourceInfo:
    """What a file offers, so a caller can present sheet and column choices."""

    #: True when this is a KURO export and needs no column mapping.
    is_kuro_export: bool
    #: Sheet names in workbook order. Empty for CSV.
    sheets: list[str]
    #: ``{sheet: [header, ...]}``. CSV uses the single key ``""``.
    headers: dict[str, list[str]]
    #: Column this module would pick on its own, when it can pick one.
    suggested_column: str | None


def _is_csv(path: Path) -> bool:
    return path.suffix.lower() in {".csv", ".tsv", ".txt"}


def _csv_rows(path: Path) -> list[list[str]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return [list(row) for row in csv.reader(handle, delimiter=delimiter)]


def _suggest_column(headers: list[str]) -> str | None:
    """Pick the variant column from headers, or None when it is ambiguous."""
    normalised = [(h or "").strip() for h in headers]
    for candidate in _VARIANT_HEADER_CANDIDATES:
        for header in normalised:
            if header.lower() == candidate:
                return header
    non_empty = [h for h in normalised if h]
    if len(non_empty) == 1:
        return non_empty[0]
    return None


def inspect_variant_source(path: Path) -> VariantSourceInfo:
    """Report the sheets and headers a file offers, without reading its rows.

    Lets a caller show the same sheet/column pickers the KURO input step uses
    instead of failing on a file whose layout is merely unfamiliar.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"variant list not found: {path}")

    if _is_csv(path):
        rows = _csv_rows(path)
        csv_headers = [str(c).strip() for c in rows[0]] if rows else []
        return VariantSourceInfo(
            is_kuro_export=False,
            sheets=[],
            headers={"": csv_headers},
            suggested_column=_suggest_column(csv_headers),
        )

    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = list(workbook.sheetnames)
        is_kuro = KURO_SHEET in sheets
        sheet_headers: dict[str, list[str]] = {}
        for name in sheets:
            first = next(workbook[name].iter_rows(values_only=True), None)
            sheet_headers[name] = [
                "" if cell is None else str(cell).strip() for cell in (first or ())
            ]
        # Headers are reported for every sheet even on a KURO export. A workbook can
        # carry the strict sheet next to the sheet that actually describes the plate
        # in front of the operator, and without headers there is nothing to pick from.
        first_sheet = KURO_SHEET if is_kuro else (sheets[0] if sheets else "")
        return VariantSourceInfo(
            is_kuro_export=is_kuro,
            sheets=sheets,
            headers=sheet_headers,
            suggested_column=(
                None if is_kuro else _suggest_column(sheet_headers.get(first_sheet, []))
            ),
        )
    finally:
        workbook.close()


def _rows_from_xlsx(path: Path, sheet: str | None) -> tuple[str, list[list[object]]]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet is not None and sheet not in workbook.sheetnames:
            raise ValueError(
                f"sheet '{sheet}' not in {path.name}. "
                f"Available: {', '.join(workbook.sheetnames)}"
            )
        name = sheet if sheet is not None else workbook.sheetnames[0]
        rows: list[list[object]] = [
            [cell for cell in row]
            for row in workbook[name].iter_rows(values_only=True)
        ]
        return name, rows
    finally:
        workbook.close()


def _resolve_column_index(headers: list[str], variant_column: str | None) -> int:
    normalised = [(h or "").strip() for h in headers]
    if variant_column is not None:
        wanted = variant_column.strip().lower()
        for index, header in enumerate(normalised):
            if header.lower() == wanted:
                return index
        raise ValueError(
            f"column '{variant_column}' not found. "
            f"Available: {', '.join(h for h in normalised if h) or '(none)'}"
        )
    suggested = _suggest_column(normalised)
    if suggested is None:
        raise ValueError(
            "cannot tell which column holds the variants; name one explicitly. "
            f"Available: {', '.join(h for h in normalised if h) or '(none)'}"
        )
    return normalised.index(suggested)


def read_variant_source(
    path: Path,
    sheet: str | None = None,
    variant_column: str | None = None,
) -> VariantListReadResult:
    """Read a variant list from *path*, whatever shape it comes in.

    A KURO export (a workbook carrying an ``expected_mutations`` sheet) is routed
    to :func:`read_expected_mutations` unchanged, so its status filtering and
    codon fields behave exactly as before.

    Anything else is read as a plain list: one variant per row, in plate order,
    from the named sheet and column. A wild-type row is recognised and reported
    rather than parsed as a mutation.

    Raises:
        ValueError: on an unreadable notation, a duplicate variant, an empty
            list, or a column that cannot be identified. Each is a mis-scored
            plate if it were let through, so none of them is a warning.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"variant list not found: {path}")

    if not _is_csv(path):
        import openpyxl

        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            is_kuro = KURO_SHEET in workbook.sheetnames
        finally:
            workbook.close()
        # An explicit sheet wins. A workbook can hold the strict sheet alongside the
        # sheet that describes the plate on the bench, and those two can disagree on
        # both membership and order; silently preferring the strict one then places
        # every well from a list the operator did not choose. Naming no sheet, or
        # naming the strict one, keeps the previous behaviour exactly.
        if is_kuro and sheet in (None, KURO_SHEET):
            return VariantListReadResult(
                expected=read_expected_mutations(path),
                has_explicit_wt=False,
                sheet=KURO_SHEET,
                variant_column="mutant_id",
            )

    if _is_csv(path):
        rows = _csv_rows(path)
        sheet_name = None
    else:
        sheet_name, rows = _rows_from_xlsx(path, sheet)

    if not rows:
        raise ValueError(f"{path.name} is empty")

    headers = ["" if c is None else str(c).strip() for c in rows[0]]
    index = _resolve_column_index(headers, variant_column)

    expected: list[ExpectedMutation] = []
    has_explicit_wt = False
    seen: dict[str, int] = {}
    for offset, row in enumerate(rows[1:], start=2):
        if index >= len(row):
            continue
        cell = row[index]
        label = "" if cell is None else str(cell).strip()
        if not label:
            continue
        if label.lower() in _WT_LABELS:
            has_explicit_wt = True
            continue
        if label in seen:
            raise ValueError(
                f"duplicate variant '{label}' in {path.name} "
                f"(rows {seen[label]} and {offset}). "
                "Each well needs a distinct variant to be scored."
            )
        seen[label] = offset
        try:
            wt_aa, position, mt_aa = parse_mutation_notation(label)
        except ValueError as exc:
            raise ValueError(f"{path.name} row {offset}: {exc}") from exc
        expected.append(
            ExpectedMutation(
                mutant_id=label,
                position=position,
                wt_aa=wt_aa,
                mt_aa=mt_aa,
                wt_codon="",
                mt_codon="",
                group_id="",
                primer_set_ref="",
                notation_type="",
                status="DESIGNED",
            )
        )

    if not expected:
        raise ValueError(
            f"no variants found in {path.name} "
            f"(column '{headers[index] or index}'). "
            "The file needs one variant per row below the header."
        )

    return VariantListReadResult(
        expected=expected,
        has_explicit_wt=has_explicit_wt,
        sheet=sheet_name,
        variant_column=headers[index] or str(index),
    )


__all__ = [
    "KURO_SHEET",
    "VariantListReadResult",
    "VariantSourceInfo",
    "inspect_variant_source",
    "read_variant_source",
]
