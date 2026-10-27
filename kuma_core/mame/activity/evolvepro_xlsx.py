"""Agilent GC-FID xlsx parsers + EVOLVEpro xlsx read/write.

v0.3 Phase A-2.
Spec: notes/architecture/2026-05-06-v0.3-phase-ab-interfaces.md §2-2

Supported inputs:
  report.xlsx: FID1B block layout, well-labelled or numeric-ID sample names
  relative_activity.xlsx: flat [Sample Name, Area], already normalised
  round_activity.xlsx: EVOLVEpro [Variant, activity]

Which reader applies is decided by the step 4.1 field the file was chosen
for (see detect_measurement_source); nothing here dispatches on content.

WT_PATTERN is imported from activity.constants as the single source of truth.
Uses python-calamine for reading. openpyxl is used for writing only.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import python_calamine

from .constants import WT_PATTERN
from .variant_notation import to_evolvepro  # noqa: F401 (re-exported for callers)

logger = logging.getLogger(__name__)

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
    # Where the row sits in the workbook: the 1-based FID1B block number and
    # the 1-based sheet row. Zero when a caller builds a record by hand.
    block_index: int = 0
    row_index: int = 0


@dataclass(frozen=True)
class RelativeActivityRecord:
    """Single measurement from a pre-normalised GC data sheet.

    area: Already relative activity (not raw FID area).
    is_relative: Always True.
    """

    sample_name: str
    area: float
    is_relative: bool = field(default=True)
    # 1-based sheet row; zero when a caller builds a record by hand.
    row_index: int = 0


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
            f"Expected numeric area value but got empty cell - {context}"
        )
    try:
        value = float(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"Cannot convert area value {raw!r} to float, {context}"
        ) from exc
    # float() accepts "nan", "inf" and "-inf", so the conversion above is not
    # the check it looks like. This is the third reader of an activity value
    # and the only one that had no finiteness rule at all; the other two are
    # build_evolvepro_input.py (raises) and ingest_long_csv.py (drops the row).
    # An infinite area is the largest value on the plate and takes the top of
    # every ranking the round is judged on.
    if not math.isfinite(value):
        raise ValueError(
            f"Area value {raw!r} is not finite, {context}"
        )
    return value


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
    float('0') succeeds (calibration); float('WT_1') fails (not calibration).
    """
    try:
        float(name)
        return True
    except ValueError:
        # Non-numeric: not a calibration row. This is the success path.
        return False


# Replicate-suffix pattern for FID1B block sample names in rep-batch files.
# Matches a numeric base ID optionally followed by a '-<rep>' suffix:
#   '12' (base=12, rep=None), '12-2' (base=12, rep=2), '12-3' (base=12, rep=3).
_BLOCK_REP_ID_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


@dataclass(frozen=True)
class GcRow:
    """One data row of a GC report exactly as read, with its position.

    This is the reading layer: it states what the sheet holds and where, and
    judges nothing. Whether a name is wild-type, a well, a numeric ID, a
    calibration standard or somebody else's sample is decided by
    ``gc_sample`` (what the name is) and by the build (whether it belongs to
    this run). A row whose name or area is empty is still a row here, so a
    caller can report it rather than lose it.

    row_index: 1-based sheet row, the number a spreadsheet shows.
    block_index: 1-based FID1B block number, ``None`` for a flat sheet.
    """

    sample_name: str
    area_raw: str
    row_index: int
    block_index: int | None = None

    @property
    def location(self) -> str:
        if self.block_index is None:
            return f"row {self.row_index}"
        return f"block {self.block_index}, row {self.row_index}"

    def area(self, context: str) -> float | None:
        """The area as a number, ``None`` when the cell is empty.

        A cell that holds something other than a finite number is a malformed
        file rather than a row to set aside, so it raises.
        """
        if self.area_raw == "":
            return None
        return _float_or_raise(self.area_raw, context)


def _has_block_signature(row: list) -> bool:
    texts = [_str(c).lower() for c in row]
    return any("signal:" in t for t in texts) and any("fid1b" in t for t in texts)


def iter_block_rows(rows: list[list]):
    """Yield a :class:`GcRow` for every data row of every FID1B block.

    A FID1B block is::

        Signal: ... FID1B          (signal marker row)
        ... Area ... Sample Name   (header row, column order varies)
        <one or more data rows>
        Sum ...                    (terminator row, first cell == 'Sum')

    Column positions are resolved by header *name* (not index) so that the
    two observed layouts (``[Area, Sample Name]`` and
    ``['', Area, '', Sample Name]``) both parse.

    This is the only block walk. A row with an empty name or an empty area is
    yielded; only a row with neither is skipped, because it holds nothing to
    report.

    Raises:
        ValueError: A signal row is not followed by a header row containing
            both 'Sample Name' and 'Area'.
    """
    i = 0
    n = len(rows)
    block_index = 0
    while i < n:
        if not _has_block_signature(rows[i]):
            i += 1
            continue

        block_index += 1
        i += 1
        if i >= n:
            raise ValueError(
                "FID1B signal row has no subsequent header row "
                f"(signal at row {i})"
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
                "FID1B block header missing 'Sample Name' / 'Area' in header "
                f"row {i + 1}: {[_str(c) for c in rows[i]]!r}"
            )

        i += 1
        while i < n:
            data_row = rows[i]
            if not data_row:
                i += 1
                continue
            if _str(data_row[0]).lower() == "sum":
                i += 1
                break
            extended = list(data_row)
            while len(extended) <= max(sn_col, area_col):
                extended.append("")
            sample_name = _str(extended[sn_col])
            area_raw = _str(extended[area_col])
            if sample_name or area_raw:
                yield GcRow(
                    sample_name=sample_name,
                    area_raw=area_raw,
                    row_index=i + 1,
                    block_index=block_index,
                )
            i += 1


def iter_flat_rows(rows: list[list], reader: str, source: object):
    """Yield a :class:`GcRow` per data row of a flat ``Sample Name``/``Area`` sheet.

    The header is the first row. Rows with neither a name nor an area are
    skipped; every other row is yielded, empty name or empty area included.

    Raises:
        ValueError: The sheet is empty or either column is missing.
    """
    if not rows:
        raise ValueError(f"{reader}: empty file {source}")
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
            f"{reader}: 'Sample Name' column not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {source}"
        )
    if area_col is None:
        raise ValueError(
            f"{reader}: 'Area' column not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {source}"
        )
    for row_idx, row in enumerate(rows[1:], start=2):
        extended = list(row)
        while len(extended) <= max(sn_col, area_col):
            extended.append("")
        sample_name = _str(extended[sn_col])
        area_raw = _str(extended[area_col])
        if sample_name or area_raw:
            yield GcRow(sample_name=sample_name, area_raw=area_raw, row_index=row_idx)


def read_block_report(path: str | Path, *, sheet_index: int = 0) -> list[GcRow]:
    """Every data row of a FID1B block report, positioned and unjudged."""
    return list(iter_block_rows(_extract_rows(Path(path), sheet_index)))


def read_flat_sheet(path: str | Path, *, sheet_index: int = 0, reader: str = "read_flat_sheet") -> list[GcRow]:
    """Every data row of a flat ``Sample Name``/``Area`` sheet, positioned and unjudged."""
    resolved = Path(path)
    return list(iter_flat_rows(_extract_rows(resolved, sheet_index), reader, resolved))


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
    stats = _AgilentParseStats()
    records: list[AgilentRecord] = []

    for row in read_block_report(resolved, sheet_index=sheet_index):
        sample_name = row.sample_name
        if not sample_name:
            continue

        # Calibration skip: purely numeric sample name.
        if _sample_name_is_calibration(sample_name):
            logger.warning(
                "parse_agilent_standard: skipping calibration row "
                "(numeric Sample Name=%r) at row %d in %s",
                sample_name,
                row.row_index,
                resolved.name,
            )
            stats.n_calibration_skipped += 1
            continue

        area = row.area(f"Sample Name={sample_name!r} row {row.row_index} in {resolved}")
        if area is None:
            continue

        is_wt = bool(WT_PATTERN.match(sample_name))
        rep_n = _replicate_n_from_wt(sample_name) if is_wt else 0

        records.append(
            AgilentRecord(
                sample_name=sample_name,
                area=area,
                is_wt=is_wt,
                replicate_n=rep_n,
                block_index=row.block_index or 0,
                row_index=row.row_index,
            )
        )
        stats.n_records_parsed += 1

    logger.debug(
        "parse_agilent_standard: %d records, %d calibration skipped from %s",
        stats.n_records_parsed,
        stats.n_calibration_skipped,
        resolved.name,
    )
    return records


# ---------------------------------------------------------------------------
# Parser 2b: FID1B block layout with numeric base/rep IDs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BlockRepBatchResult:
    """Grouped result from parse_agilent_block_rep_batch.

    reps: base integer ID -> list of replicate areas, ordered by the
        replicate number embedded in the sample name (no suffix is treated
        as replicate 1, '-2' as replicate 2, '-3' as replicate 3, and so
        on for any numeric suffix). The list holds every area found for a
        base ID, so no replicate is silently dropped.
    wt_areas: All WT block areas (one per WT block such as 'WT1', 'WT2').
    n_blocks: Number of FID1B data rows consumed (diagnostics only).
    """

    reps: dict[int, list[float]]
    wt_areas: list[float]
    n_blocks: int


def _block_rep_index(rep_token: str | None) -> int:
    """Map an optional replicate suffix token to a 1-based replicate number.

    None (no suffix) -> 1, '2' -> 2, '3' -> 3, and so on. Caller passes the
    second capture group of _BLOCK_REP_ID_RE.
    """
    if rep_token is None:
        return 1
    return int(rep_token)


def parse_agilent_block_rep_batch(
    path: str | Path,
    *,
    sheet_index: int = 0,
) -> BlockRepBatchResult:
    """Parse a FID1B block-layout Agilent report with numeric base/rep IDs.

    This handles a block shape parse_agilent_standard cannot: it skips
    pure-numeric names as calibration, losing every replicate-1 row. This
    parser walks the blocks and groups numeric base IDs across their
    replicate suffixes.

    Sample-name grammar inside each FID1B block:
        '<base>'          replicate 1 (e.g. '12')
        '<base>-<rep>'    replicate <rep> (e.g. '12-2', '12-3')
        'WT<n>' / 'WT_<n>' wild-type block area

    Non-numeric, non-WT names are ignored with a debug log.

    Args:
        path:        Path to the xlsx file.
        sheet_index: Zero-based sheet index.

    Returns:
        BlockRepBatchResult with grouped replicate areas and WT areas.

    Raises:
        ValueError: A block area cell is non-numeric, or a signal row lacks
            a following header row (raised by iter_block_rows).
    """
    resolved = Path(path)

    reps: dict[int, list[float]] = {}
    rep_index_seen: dict[int, set[int]] = {}
    wt_areas: list[float] = []
    n_blocks = 0

    for row in read_block_report(resolved, sheet_index=sheet_index):
        sample_name = row.sample_name
        if not sample_name:
            continue
        n_blocks += 1
        area = _float_or_raise(
            row.area_raw,
            f"Sample Name={sample_name!r} in {resolved}",
        )

        if WT_PATTERN.match(sample_name) or sample_name.upper() == "WT":
            wt_areas.append(area)
            continue

        m = _BLOCK_REP_ID_RE.match(sample_name)
        if not m:
            logger.debug(
                "parse_agilent_block_rep_batch: ignoring non-numeric, "
                "non-WT sample name %r in %s",
                sample_name,
                resolved.name,
            )
            continue

        base_id = int(m.group(1))
        rep_idx = _block_rep_index(m.group(2))
        seen = rep_index_seen.setdefault(base_id, set())
        if rep_idx in seen:
            logger.warning(
                "parse_agilent_block_rep_batch: duplicate replicate %d for "
                "base ID %d in %s; keeping all areas",
                rep_idx,
                base_id,
                resolved.name,
            )
        seen.add(rep_idx)
        reps.setdefault(base_id, []).append(area)

    logger.debug(
        "parse_agilent_block_rep_batch: %d base IDs, %d WT areas, "
        "%d blocks from %s",
        len(reps),
        len(wt_areas),
        n_blocks,
        resolved.name,
    )
    return BlockRepBatchResult(reps=reps, wt_areas=wt_areas, n_blocks=n_blocks)


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
    records: list[RelativeActivityRecord] = []
    for row in read_flat_sheet(resolved, sheet_index=sheet_index, reader="parse_relative_only"):
        area = _float_or_raise(
            row.area_raw,
            f"Sample Name={row.sample_name!r} row {row.row_index} in {resolved}",
        )
        records.append(
            RelativeActivityRecord(sample_name=row.sample_name, area=area, row_index=row.row_index)
        )

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


def read_evolvepro_rows(path: str | Path) -> list[tuple[str, float]]:
    """Read an EVOLVEpro xlsx as an *ordered* list of (variant, activity).

    Unlike read_evolvepro_xlsx (which returns a dict and therefore collapses
    duplicate Variant keys and loses physical row order), this preserves the
    exact row sequence. The rank-based ID->variant mapping depends on row
    order, so duplicate-key collapse would silently shift every rank below
    the first duplicate. Callers that need rank must use this reader.

    Args:
        path: Path to an EVOLVEpro xlsx with 'Variant' and 'activity' columns.

    Returns:
        List of (variant, activity) tuples in file row order, including any
        WT row and any duplicate variants (callers filter as needed).

    Raises:
        ValueError: 'Variant' or 'activity' column not found, empty file, or
            a non-numeric activity cell.
    """
    resolved = Path(path)
    rows = _extract_rows(resolved, 0)

    if not rows:
        raise ValueError(f"read_evolvepro_rows: empty file {resolved}")

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
            f"read_evolvepro_rows: 'Variant' column not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {resolved}"
        )
    if activity_col is None:
        raise ValueError(
            f"read_evolvepro_rows: 'activity' column not found. "
            f"Header: {[_str(c) for c in rows[0]]!r} in {resolved}"
        )

    ordered: list[tuple[str, float]] = []
    for row_idx, row in enumerate(rows[1:], start=2):
        extended = list(row)
        while len(extended) <= max(variant_col, activity_col):
            extended.append("")
        variant = _str(extended[variant_col])
        activity_raw = _str(extended[activity_col])
        if not variant and not activity_raw:
            continue
        activity = _float_or_raise(
            activity_raw,
            f"Variant={variant!r} row {row_idx} in {resolved}",
        )
        ordered.append((variant, activity))

    return ordered


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


# Fixed header of a pre-normalised relative-activity sheet (the 'GC data.xlsx'
# shape). Single source of truth for both the writer below and its callers.
RELATIVE_ACTIVITY_COLUMNS: tuple[str, str] = ("Sample Name", "Area")

_RELATIVE_ACTIVITY_SHEET = "GC data"


def write_relative_activity_xlsx(
    rows: list[tuple[str, float]],
    output_path: str | Path,
    sheet_name: str = _RELATIVE_ACTIVITY_SHEET,
) -> int:
    """Write a relative-activity xlsx in the pre-normalised 'GC data' shape.

    Fixed headers come from RELATIVE_ACTIVITY_COLUMNS ('Sample Name', 'Area'),
    so the file round-trips through parse_relative_only. Uses openpyxl for
    writing (calamine is read-only).

    Args:
        rows:        List of (sample_name, relative_activity) tuples, written
                     in the given order.
        output_path: Destination path. Parent directory must exist.
        sheet_name:  Worksheet title.

    Returns:
        Number of data rows written (header excluded).

    Raises:
        FileNotFoundError: Parent directory of *output_path* does not exist.
    """
    import openpyxl  # write-only use; calamine cannot write.

    resolved = Path(output_path)
    if not resolved.parent.exists():
        raise FileNotFoundError(
            f"write_relative_activity_xlsx: output directory does not exist: "
            f"{resolved.parent}"
        )

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet()
    ws.title = sheet_name
    ws.append(list(RELATIVE_ACTIVITY_COLUMNS))

    for sample_name, relative_activity in rows:
        ws.append([sample_name, relative_activity])

    wb.save(str(resolved))
    logger.debug(
        "write_relative_activity_xlsx: wrote %d rows to %s",
        len(rows),
        resolved.name,
    )
    return len(rows)
