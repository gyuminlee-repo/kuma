"""Agilent GC-FID xlsx parsers + EVOLVEpro xlsx read/write.

v0.3 Phase A-2.
Spec: notes/architecture/2026-05-06-v0.3-phase-ab-interfaces.md §2-2

Supported formats:
  AGILENT_STANDARD  — 251001_report.xlsx  (FID1B 5-row block layout)
  AGILENT_REP_BATCH — 260327_Ep_R1_positive.xlsx  (numeric ID + _rep pattern)
  RELATIVE_ONLY     — GC data.xlsx  ([Sample Name, Area] already normalised)
  EVOLVEPRO         — IspS_round1_Ep.xlsx  ([Variant, activity])

WT_PATTERN is imported from activity.constants as the single source of truth.
Uses python-calamine for reading. openpyxl is used for writing only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import python_calamine

from .constants import WT_PATTERN
from .variant_notation import to_evolvepro  # noqa: F401 (re-exported for callers)

logger = logging.getLogger(__name__)

# Replicate pattern for AGILENT_REP_BATCH: numeric id optionally followed by
# underscore + rep label (e.g. '12', '12_rep1', '12_A').
_REP_BATCH_SAMPLE_RE = re.compile(r"^(\d+)(?:[_\-].*)?$")


class XlsxFormat(str, Enum):
    AGILENT_STANDARD = "agilent_standard"
    AGILENT_REP_BATCH = "agilent_rep_batch"
    RELATIVE_ONLY = "relative_only"
    EVOLVEPRO = "evolvepro"


@dataclass(frozen=True)
class AgilentRecord:
    """Single measurement from a GC-FID Agilent report.

    replicate_n: For WT wells, the replicate number extracted from the
        sample name (e.g., WT_1 → 1).  For mutant wells with a single
        measurement, 0 (undefined). 1-based when explicitly enumerated.
    is_relative: Always False for raw FID area values.
    """

    sample_name: str
    area: float
    is_wt: bool
    replicate_n: int
    is_relative: bool = field(default=False)


@dataclass(frozen=True)
class RelativeActivityRecord:
    """Single measurement from a pre-normalised GC data sheet.

    area: Already relative activity (not raw FID area).
    is_relative: Always True.
    """

    sample_name: str
    area: float
    is_relative: bool = field(default=True)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_rows(path: Path, sheet_index: int) -> list[list]:
    """Return all rows from a calamine sheet as a list of lists."""
    wb = python_calamine.CalamineWorkbook.from_path(str(path))
    sheets = wb.sheet_names
    if sheet_index >= len(sheets):
        raise ValueError(
            f"sheet_index={sheet_index} out of range "
            f"(file has {len(sheets)} sheet(s)): {path}"
        )
    return list(wb.get_sheet_by_index(sheet_index).to_python())


def _str(cell: object) -> str:
    return str(cell).strip()


def _float_or_raise(cell: object, context: str) -> float:
    """Convert cell to float; raise ValueError with context on failure."""
    raw = _str(cell)
    if raw == "":
        raise ValueError(
            f"Expected numeric area value but got empty cell — {context}"
        )
    try:
        return float(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Cannot convert area value {raw!r} to float — {context}"
        ) from exc


def _is_numeric_id(sample_name: str) -> bool:
    """Return True if sample_name starts with a pure integer."""
    return _REP_BATCH_SAMPLE_RE.match(sample_name) is not None


def _replicate_n_from_wt(sample_name: str) -> int:
    """Extract replicate number from WT sample name.

    'WT_1' → 1, 'WT1' → 1, 'WT' → 0 (unspecified).
    """
    m = re.match(r"^WT_?(\d+)$", sample_name, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


def _sample_name_is_calibration(name: str) -> bool:
    """Return True if sample_name is purely numeric (calibration row).

    This is intentional non-error use of float() as a type probe:
    float('0') succeeds → calibration; float('WT_1') fails → not calibration.
    """
    try:
        float(name)
        return True
    except ValueError:
        # Non-numeric: not a calibration row — this is the success path.
        return False


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def detect_format(
    path: str | Path,
    *,
    sheet_index: int = 0,
    rep_batch_numeric_ratio: float = 0.5,
) -> XlsxFormat:
    """Auto-detect xlsx format from sheet content.

    Priority (spec §2-2):
        1. 'Signal:' + 'FID1B' text in any cell → AGILENT_STANDARD
        2. Columns ['Variant', 'activity'] → EVOLVEPRO
        3. ['Sample Name', 'Area'] + ≥rep_batch_numeric_ratio of data
           rows have a numeric-id sample name → AGILENT_REP_BATCH
        4. ['Sample Name', 'Area'] → RELATIVE_ONLY

    Args:
        path:                   Path to xlsx file.
        sheet_index:            Zero-based sheet index.
        rep_batch_numeric_ratio: Fraction of data rows that must look like
            numeric IDs to classify as AGILENT_REP_BATCH (default 0.5).

    Raises:
        ValueError: Format cannot be determined.
    """
    resolved = Path(path)
    rows = _extract_rows(resolved, sheet_index)

    # Priority 1: FID1B block marker anywhere in first 20 rows.
    has_signal = False
    has_fid1b = False
    for row in rows[:20]:
        for cell in row:
            text = _str(cell).lower()
            if "signal:" in text:
                has_signal = True
            if "fid1b" in text:
                has_fid1b = True
    if has_signal and has_fid1b:
        return XlsxFormat.AGILENT_STANDARD

    if not rows:
        raise ValueError(f"detect_format: empty file {resolved}")

    # Normalise header row.
    header_lower = [_str(c).lower() for c in rows[0]]

    # Priority 2: EVOLVEpro columns.
    if "variant" in header_lower and "activity" in header_lower:
        return XlsxFormat.EVOLVEPRO

    # Priority 3 & 4: [Sample Name, Area]
    if "sample name" in header_lower and "area" in header_lower:
        sn_col = header_lower.index("sample name")
        data_rows = [row for row in rows[1:] if row and _str(row[0]) != ""]
        if not data_rows:
            return XlsxFormat.RELATIVE_ONLY

        numeric_count = sum(
            1
            for row in data_rows
            if len(row) > sn_col and _is_numeric_id(_str(row[sn_col]))
        )
        ratio = numeric_count / len(data_rows)
        if ratio >= rep_batch_numeric_ratio:
            return XlsxFormat.AGILENT_REP_BATCH
        return XlsxFormat.RELATIVE_ONLY

    raise ValueError(
        f"detect_format: cannot determine format of {resolved}. "
        f"Header row: {[_str(c) for c in rows[0]]!r}"
    )


# ---------------------------------------------------------------------------
# Parser 1: AGILENT_STANDARD (FID1B 5-row block)
# ---------------------------------------------------------------------------

@dataclass
class _AgilentParseStats:
    n_calibration_skipped: int = 0
    n_records_parsed: int = 0


def parse_agilent_standard(
    path: str | Path,
    *,
    sheet_index: int = 0,
) -> list[AgilentRecord]:
    """Parse FID1B block-format Agilent report xlsx.

    Block structure (each GC injection is one block):
      Row type:  | Content
      -----------|-----------------------
      Signal row | Cell contains 'Signal:' and 'FID1B'
      Header row | Columns include 'Sample Name' and 'Area'
      Data rows  | One row per sample
      Sum row    | First cell is 'Sum'

    Skip conditions (warn-and-skip, NOT raise):
        Sample Name is purely numeric → calibration; skip + log WARNING.

    Raise conditions:
        Area value is non-numeric (excluding empty/whitespace) → ValueError.
        Block header not found after Signal row → ValueError.

    Args:
        path:        Path to xlsx file.
        sheet_index: Zero-based sheet index.

    Returns:
        List of AgilentRecord, one per non-calibration sample.
    """
    resolved = Path(path)
    rows = _extract_rows(resolved, sheet_index)
    stats = _AgilentParseStats()
    records: list[AgilentRecord] = []

    i = 0
    while i < len(rows):
        row = rows[i]
        row_texts = [_str(c).lower() for c in row]

        # Detect Signal row.
        if any("signal:" in t for t in row_texts) and any("fid1b" in t for t in row_texts):
            # Next row should be the column header.
            i += 1
            if i >= len(rows):
                raise ValueError(
                    f"parse_agilent_standard: Signal block at row {i} has no "
                    f"subsequent header row in {resolved}"
                )
            header_row = [_str(c).lower() for c in rows[i]]
            sn_col: int | None = None
            area_col: int | None = None
            for col_idx, hdr in enumerate(header_row):
                if hdr == "sample name":
                    sn_col = col_idx
                elif hdr == "area":
                    area_col = col_idx

            if sn_col is None or area_col is None:
                raise ValueError(
                    f"parse_agilent_standard: expected 'Sample Name' and 'Area' "
                    f"in header row {i + 1} but found {[_str(c) for c in rows[i]]!r} "
                    f"in {resolved}"
                )

            # Parse data rows until 'Sum' row or end.
            i += 1
            while i < len(rows):
                data_row = rows[i]
                if not data_row:
                    i += 1
                    continue

                first_cell = _str(data_row[0]).lower()
                if first_cell == "sum":
                    i += 1
                    break

                # Extend row if needed.
                while len(data_row) <= max(sn_col, area_col):
                    data_row = list(data_row) + [""]

                sample_name = _str(data_row[sn_col])
                if not sample_name:
                    i += 1
                    continue

                # Calibration skip: purely numeric sample name.
                if _sample_name_is_calibration(sample_name):
                    logger.warning(
                        "parse_agilent_standard: skipping calibration row "
                        "(numeric Sample Name=%r) at row %d in %s",
                        sample_name,
                        i + 1,
                        resolved.name,
                    )
                    stats.n_calibration_skipped += 1
                    i += 1
                    continue

                area_raw = _str(data_row[area_col])
                if area_raw == "":
                    i += 1
                    continue

                area = _float_or_raise(
                    area_raw,
                    f"Sample Name={sample_name!r} row {i + 1} in {resolved}",
                )

                is_wt = bool(WT_PATTERN.match(sample_name))
                rep_n = _replicate_n_from_wt(sample_name) if is_wt else 0

                records.append(
                    AgilentRecord(
                        sample_name=sample_name,
                        area=area,
                        is_wt=is_wt,
                        replicate_n=rep_n,
                    )
                )
                stats.n_records_parsed += 1
                i += 1
        else:
            i += 1

    logger.debug(
        "parse_agilent_standard: %d records, %d calibration skipped from %s",
        stats.n_records_parsed,
        stats.n_calibration_skipped,
        resolved.name,
    )
    return records


# ---------------------------------------------------------------------------
# Parser 2: AGILENT_REP_BATCH (numeric ID + rep)
# ---------------------------------------------------------------------------

def parse_agilent_rep_batch(
    path: str | Path,
    *,
    sheet_index: int = 0,
    mutant_count: int | None = None,
) -> list[AgilentRecord]:
    """Parse rep-batch Agilent xlsx with numeric sample IDs.

    Sample names use a numeric ID (1, 2, 3, ...) optionally suffixed with
    a replicate label ('_rep1', '_A', etc.).

    When mutant_count is None, it is estimated as the maximum integer found
    among sample names that match the numeric-ID pattern.

    Args:
        path:         Path to xlsx file.
        sheet_index:  Zero-based sheet index.
        mutant_count: Known number of mutants. None triggers auto-estimation.

    Returns:
        List of AgilentRecord. sample_name preserves original value.
        Well-ID mapping is performed by the caller (join layer).
    """
    resolved = Path(path)
    rows = _extract_rows(resolved, sheet_index)

    if not rows:
        raise ValueError(f"parse_agilent_rep_batch: empty file {resolved}")

    header_lower = [_str(c).lower() for c in rows[0]]
    sn_col: int | None = None
    area_col: int | None = None
    for idx, h in enumerate(header_lower):
        if h == "sample name":
            sn_col = idx
        elif h == "area":
            area_col = idx

    if sn_col is None or area_col is None:
        raise ValueError(
            f"parse_agilent_rep_batch: 'Sample Name' / 'Area' columns not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {resolved}"
        )

    records: list[AgilentRecord] = []
    max_numeric_id = 0

    for row_idx, row in enumerate(rows[1:], start=2):
        while len(row) <= max(sn_col, area_col):
            row = list(row) + [""]

        sample_name = _str(row[sn_col])
        area_raw = _str(row[area_col])
        if not sample_name and not area_raw:
            continue

        area = _float_or_raise(
            area_raw,
            f"Sample Name={sample_name!r} row {row_idx} in {resolved}",
        )

        is_wt = bool(WT_PATTERN.match(sample_name))
        rep_n = _replicate_n_from_wt(sample_name) if is_wt else 0

        if not is_wt:
            m = _REP_BATCH_SAMPLE_RE.match(sample_name)
            if m:
                numeric_id = int(m.group(1))
                if numeric_id > max_numeric_id:
                    max_numeric_id = numeric_id

        records.append(
            AgilentRecord(
                sample_name=sample_name,
                area=area,
                is_wt=is_wt,
                replicate_n=rep_n,
            )
        )

    if mutant_count is None:
        mutant_count = max_numeric_id
        logger.debug(
            "parse_agilent_rep_batch: auto-estimated mutant_count=%d from %s",
            mutant_count,
            resolved.name,
        )
    else:
        logger.debug(
            "parse_agilent_rep_batch: mutant_count=%d (caller-provided) from %s",
            mutant_count,
            resolved.name,
        )

    return records


# ---------------------------------------------------------------------------
# Parser 3: RELATIVE_ONLY
# ---------------------------------------------------------------------------

def parse_relative_only(
    path: str | Path,
    *,
    sheet_index: int = 0,
) -> list[RelativeActivityRecord]:
    """Parse pre-normalised GC data xlsx with [Sample Name, Area] columns.

    Area values are treated as already-relative activity (not raw FID area).

    Args:
        path:        Path to xlsx file.
        sheet_index: Zero-based sheet index.

    Returns:
        List of RelativeActivityRecord, is_relative=True for all entries.

    Raises:
        ValueError: 'Sample Name' or 'Area' column not found.
        ValueError: Area cell is non-numeric.
    """
    resolved = Path(path)
    rows = _extract_rows(resolved, sheet_index)

    if not rows:
        raise ValueError(f"parse_relative_only: empty file {resolved}")

    header_lower = [_str(c).lower() for c in rows[0]]
    sn_col: int | None = None
    area_col: int | None = None
    for idx, h in enumerate(header_lower):
        if h == "sample name":
            sn_col = idx
        elif h == "area":
            area_col = idx

    if sn_col is None:
        raise ValueError(
            f"parse_relative_only: 'Sample Name' column not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {resolved}"
        )
    if area_col is None:
        raise ValueError(
            f"parse_relative_only: 'Area' column not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {resolved}"
        )

    records: list[RelativeActivityRecord] = []
    for row_idx, row in enumerate(rows[1:], start=2):
        while len(row) <= max(sn_col, area_col):
            row = list(row) + [""]

        sample_name = _str(row[sn_col])
        area_raw = _str(row[area_col])
        if not sample_name and not area_raw:
            continue

        area = _float_or_raise(
            area_raw,
            f"Sample Name={sample_name!r} row {row_idx} in {resolved}",
        )

        records.append(RelativeActivityRecord(sample_name=sample_name, area=area))

    return records


# ---------------------------------------------------------------------------
# EVOLVEpro reader / writer
# ---------------------------------------------------------------------------

def read_evolvepro_xlsx(path: str | Path) -> dict[str, float]:
    """Read EVOLVEpro input xlsx → {short_variant: activity}.

    Expects a sheet with columns 'Variant' and 'activity'.

    Returns:
        Mapping from short variant notation (e.g. '89W') to activity float.

    Raises:
        ValueError: 'Variant' or 'activity' column not found.
        ValueError: activity cell is non-numeric.
    """
    resolved = Path(path)
    rows = _extract_rows(resolved, 0)

    if not rows:
        raise ValueError(f"read_evolvepro_xlsx: empty file {resolved}")

    header_lower = [_str(c).lower() for c in rows[0]]
    variant_col: int | None = None
    activity_col: int | None = None
    for idx, h in enumerate(header_lower):
        if h == "variant":
            variant_col = idx
        elif h == "activity":
            activity_col = idx

    if variant_col is None:
        raise ValueError(
            f"read_evolvepro_xlsx: 'Variant' column not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {resolved}"
        )
    if activity_col is None:
        raise ValueError(
            f"read_evolvepro_xlsx: 'activity' column not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {resolved}"
        )

    result: dict[str, float] = {}
    for row_idx, row in enumerate(rows[1:], start=2):
        while len(row) <= max(variant_col, activity_col):
            row = list(row) + [""]

        variant = _str(row[variant_col])
        activity_raw = _str(row[activity_col])
        if not variant and not activity_raw:
            continue

        activity = _float_or_raise(
            activity_raw,
            f"Variant={variant!r} row {row_idx} in {resolved}",
        )
        result[variant] = activity

    return result


def write_evolvepro_xlsx(
    rows: list[tuple[str, float]],
    output_path: str | Path,
) -> int:
    """Write EVOLVEpro input xlsx from (short_variant, relative_activity) pairs.

    Fixed headers: 'Variant', 'activity'.
    Uses openpyxl for writing (calamine is read-only).

    Args:
        rows:        List of (short_variant, relative_activity) tuples.
        output_path: Destination path. Parent directory must exist.

    Returns:
        Number of data rows written (header excluded).

    Raises:
        FileNotFoundError: Parent directory of *output_path* does not exist.
    """
    import openpyxl  # write-only use; calamine cannot write.

    resolved = Path(output_path)
    if not resolved.parent.exists():
        raise FileNotFoundError(
            f"write_evolvepro_xlsx: output directory does not exist: "
            f"{resolved.parent}"
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    ws.title = "EVOLVEpro"
    ws.append(["Variant", "activity"])

    for short_variant, relative_activity in rows:
        ws.append([short_variant, relative_activity])

    wb.save(str(resolved))
    logger.debug(
        "write_evolvepro_xlsx: wrote %d rows to %s", len(rows), resolved.name
    )
    return len(rows)
