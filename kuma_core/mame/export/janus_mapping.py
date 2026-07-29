"""Janus mapping export for final cell-stock pick (mame K4 spec).

Header design follows the 260428 meeting §2.5 decision:
  name | source_plate | source_well | dest_well | priority_score

- ``source_plate``: P1 / P2 / P3  (NB01→P1, NB02→P2, NB03→P3)
- ``source_well``:  well label in the NB plate (e.g. "A1")
- ``dest_well``:    destination well in the final 96-well plate.
                    Auto-filled from the custom_barcode position.
                    Users can overwrite in the saved CSV/XLSX.
- ``priority_score``: ``read_count`` when available (G6/A6+); otherwise
                      ``file_size_kb`` as a volume proxy (Phase 1 fallback).

Sorted by ``priority_score`` DESC (highest-volume clones first), per §2.5
recommended placement order.

read_count policy (G6/A6)
--------------------------
``BarcodeRecord.read_count`` is populated by the consensus parser from
``depth=N`` header metadata when available, falling back to single-record
counts for legacy consensus files. ``priority_score`` uses read_count when
non-None; falls back to file_size_kb. Column name ``priority_score`` is kept
for downstream consumers regardless of which underlying metric is used.

G3 run-meta embedding
---------------------
``export_mame_janus_csv`` and ``export_mame_janus_xlsx`` accept an optional
``ngs_run_meta`` argument (``NgsRunMeta | None``).

- CSV: when *ngs_run_meta* is not ``None``, a single comment line is prepended
  before the header row::

      # kuma_run_meta: flow_cell=PAX12345, kit=SQK-LSK109, started=2024-01-01T00:00:00Z

  When ``None`` no comment line is written, preserving backward compatibility
  with existing tests that use ``csv.DictReader`` directly.

- XLSX: a ``__kuma_meta__`` sheet is appended with key/value rows.  The sheet
  is always present; content is optional (placeholder when meta is ``None``).
"""

from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.models import ReplicateResult

if TYPE_CHECKING:
    from kuma_core.mame.ingest.run_meta import NgsRunMeta

# NB plate name → Janus deck plate name mapping (meeting §2.5).
_PLATE_LABEL: dict[str, str] = {
    "NB01": "P1",
    "NB02": "P2",
    "NB03": "P3",
}

_JANUS_HEADER = [
    "name",
    "source_plate",
    "source_well",
    "dest_well",
    "priority_score",
]


def _custom_barcode_to_seq(custom: str) -> int | None:
    """`{R}_{F}` -> 1-based column-major sequence index."""
    parts = custom.split("_")
    if len(parts) != 2:
        return None
    try:
        r = int(parts[0])
        f = int(parts[1])
    except ValueError:
        return None
    if not (1 <= r <= 8 and 1 <= f <= 12):
        return None
    return (f - 1) * 8 + r


def _find_unresolved_wells(
    bad_barcodes: list[tuple[str, str]],
) -> dict[str, object] | None:
    """Report rows whose ``custom_barcode`` could not be mapped to a well.

    A blank well silently shipped to JANUS is an unusable instruction, so the
    export refuses it (no silent fallback) and the preview surfaces it.
    """
    if not bad_barcodes:
        return None
    detail = ", ".join(f"{mid} (custom_barcode={cb!r})" for mid, cb in bad_barcodes)
    return {
        "code": "unresolved_well",
        "message": (
            "Janus mapping: unparseable custom_barcode, well position unknown for "
            f"{len(bad_barcodes)} mutant(s): {detail}. "
            "Expected '<row>_<col>' with row 1-8 and col 1-12."
        ),
        "mutant_ids": [mid for mid, _ in bad_barcodes],
    }


def _find_plate_overflow(rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Report selections larger than one 96-well destination plate.

    Evaluated before compact reassignment so the message names the real problem
    rather than surfacing ``seq_to_well``'s internal range error.
    """
    if len(rows) <= 96:
        return None
    return {
        "code": "plate_capacity",
        "message": (
            f"Janus mapping: {len(rows)} picks exceed the 96-well destination "
            "plate capacity. Reduce the selection to at most 96 clones."
        ),
        "mutant_ids": [str(row["name"]) for row in rows[96:]],
    }


def _find_duplicate_dests(rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Report duplicate ``dest_well`` (JANUS would double-dispense one well).

    Duplicates arise in source layout when two plates carry a pick at the same
    position, which is normal in multi-plate runs, so the message names the
    compact layout as the way out.

    Blank destinations are skipped: they mean the well never resolved, which
    ``_find_unresolved_wells`` already reports. In the export path that check
    raises first, so skipping blanks here leaves export behaviour unchanged.
    """
    seen: dict[str, list[str]] = {}
    for row in rows:
        well = str(row["dest_well"])
        if not well:
            continue
        seen.setdefault(well, []).append(str(row["name"]))
    dups = {well: names for well, names in seen.items() if len(names) > 1}
    if not dups:
        return None
    detail = "; ".join(
        f"{well} <- {', '.join(names)}" for well, names in sorted(dups.items())
    )
    mutant_ids: list[str] = []
    for _, names in sorted(dups.items()):
        mutant_ids.extend(names)
    return {
        "code": "duplicate_dest_well",
        "message": (
            "Janus mapping: duplicate dest_well would dispense multiple clones "
            f"into the same well: {detail}. "
            "Use dest_layout='compact' to assign destinations sequentially."
        ),
        "mutant_ids": mutant_ids,
    }


def _raise_if(finding: dict[str, object] | None) -> None:
    """Fail-fast wrapper: turn a structured finding into the export ``ValueError``."""
    if finding is not None:
        raise ValueError(str(finding["message"]))


def _assemble_janus_rows(
    replicates: list[ReplicateResult],
    dest_layout: str,
) -> tuple[list[dict[str, object]], list[tuple[str, str]]]:
    """Build and sort rows without validating them.

    Returns ``(rows, bad_barcodes)``. Destinations still mirror the source
    position; compact reassignment is applied by the caller so that both the
    export and the preview can decide what to do about capacity first.
    """
    if dest_layout not in ("source", "compact"):
        raise ValueError(
            f"Invalid dest_layout {dest_layout!r}. Expected 'source' or 'compact'."
        )

    rows: list[dict[str, object]] = []
    bad_barcodes: list[tuple[str, str]] = []

    for rr in replicates:
        if rr.failed or rr.selected_plate is None:
            continue

        vr = rr.plate_verdicts.get(rr.selected_plate)
        if vr is None:
            continue

        bc = vr.translated.barcode
        custom_barcode = bc.custom_barcode
        seq = _custom_barcode_to_seq(custom_barcode)
        if seq is None or not (1 <= seq <= 96):
            well_label = ""
            bad_barcodes.append((rr.mutant_id, custom_barcode))
        else:
            well_label = seq_to_well(seq)

        source_plate = _PLATE_LABEL.get(rr.selected_plate, rr.selected_plate)
        # G6/A6: read_count preferred; fall back to file_size_kb proxy.
        rc = bc.read_count
        priority_score: float = float(rc) if rc is not None else round(bc.file_size_kb, 3)

        rows.append(
            {
                "name": rr.mutant_id,
                "source_plate": source_plate,
                "source_well": well_label,
                "dest_well": well_label,  # default = same position; user may override
                "priority_score": priority_score,
            }
        )

    # Sort by priority DESC (high-volume first per §2.5 recommendation).
    rows.sort(key=lambda r: float(r["priority_score"]), reverse=True)  # type: ignore[arg-type]
    return rows, bad_barcodes


def _apply_compact_layout(rows: list[dict[str, object]]) -> None:
    """Reassign ``dest_well`` sequentially from A1, in place.

    Only the first 96 rows get a destination; ``seq_to_well`` rejects anything
    past 96. Overflow rows keep a blank destination and are reported by
    ``_find_plate_overflow``.
    """
    for idx, row in enumerate(rows):
        row["dest_well"] = seq_to_well(idx + 1) if idx < 96 else ""


def _build_janus_rows(
    replicates: list[ReplicateResult],
    dest_layout: str = "source",
) -> list[dict[str, object]]:
    """Build sorted Janus mapping rows from replicate results.

    Only includes mutants that have a confirmed selected plate (not failed).
    Rows are sorted by ``priority_score`` DESC.

    *dest_layout* controls ``dest_well`` assignment:

    - ``"source"`` (default): ``dest_well`` mirrors ``source_well``.
    - ``"compact"``: destinations are assigned sequentially from A1 in sorted
      (priority DESC) order, following the column-major ``seq_to_well``
      convention (A1, B1, ... H1, A2, ...).

    Raises ``ValueError`` on empty wells, >96 rows, or duplicate destinations.
    """
    rows, bad_barcodes = _assemble_janus_rows(replicates, dest_layout)

    # Empty-well and capacity checks run before compact reassignment so the
    # capacity error names the picks instead of tripping seq_to_well's range.
    _raise_if(_find_unresolved_wells(bad_barcodes))
    _raise_if(_find_plate_overflow(rows))

    if dest_layout == "compact":
        _apply_compact_layout(rows)

    # Duplicate check runs in both modes (defensive; unreachable in compact).
    _raise_if(_find_duplicate_dests(rows))
    return rows


def build_janus_preview_rows(
    replicates: list[ReplicateResult],
    dest_layout: str = "source",
) -> dict[str, object]:
    """Build Janus mapping rows in-memory, collecting problems instead of raising.

    Mirrors ``_build_janus_rows`` row-for-row so the preview shows exactly what
    the export would write, but the three guards (unresolved well, >96 picks,
    duplicate destination) are returned as structured entries. Showing every
    problem at once is the point: the export path keeps its fail-fast behaviour.

    Returns ``{"rows": [...], "errors": [...], "row_count": N}`` where each
    error entry is ``{"code": str, "message": str, "mutant_ids": [str, ...]}``.

    Rows with an unresolved well are kept with blank ``source_well`` and
    ``dest_well`` so the broken clone stays visible in the preview.
    """
    rows, bad_barcodes = _assemble_janus_rows(replicates, dest_layout)

    errors: list[dict[str, object]] = []
    for finding in (
        _find_unresolved_wells(bad_barcodes),
        _find_plate_overflow(rows),
    ):
        if finding is not None:
            errors.append(finding)

    if dest_layout == "compact":
        _apply_compact_layout(rows)

    # Evaluated after compaction: compact layout is the documented way out of a
    # duplicate, so reporting a pre-compaction duplicate would be misleading.
    dup = _find_duplicate_dests(rows)
    if dup is not None:
        errors.append(dup)

    return {"rows": rows, "errors": errors, "row_count": len(rows)}


def _meta_comment_line(meta: "NgsRunMeta") -> str:
    """Build a single-line CSV comment from *meta* (G3 spec).

    Format: ``# kuma_run_meta: flow_cell=X, kit=Y, started=Z``
    Fields that are ``None`` are omitted from the comment.
    """
    parts: list[str] = []
    if meta.flow_cell_id:
        parts.append(f"flow_cell={meta.flow_cell_id}")
    if meta.kit:
        parts.append(f"kit={meta.kit}")
    if meta.started:
        parts.append(f"started={meta.started}")
    if meta.instrument:
        parts.append(f"instrument={meta.instrument}")
    if meta.position:
        parts.append(f"position={meta.position}")
    return "# kuma_run_meta: " + ", ".join(parts)


def _write_janus_kuma_meta_sheet(
    wb: "object",
    meta: "NgsRunMeta | None",
    kuma_version: str,
) -> None:
    """Append ``__kuma_meta__`` sheet to an openpyxl Workbook.

    Mirrors the logic in excel_writer._write_kuma_meta_sheet but is a
    standalone helper to avoid a circular import between the two modules.
    """
    import openpyxl  # local import keeps cold-start fast
    from openpyxl.styles import Font as _Font

    ws = wb.create_sheet("__kuma_meta__")  # type: ignore[union-attr]
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 40

    ws.append(["key", "value"])
    for cell in ws[1]:
        cell.font = _Font(bold=True)

    ws.append(["kuma_version", kuma_version])
    ws.append([
        "generated_at",
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ])

    if meta is None:
        ws.append(["ngs_run_meta", "(not found — no MinKNOW run folder detected)"])
        return

    fields: list[tuple[str, object]] = [
        ("instrument", meta.instrument),
        ("position", meta.position),
        ("flow_cell_id", meta.flow_cell_id),
        ("sample_id", meta.sample_id),
        ("kit", meta.kit),
        ("started", meta.started),
        ("basecalling_enabled", (
            None if meta.basecalling_enabled is None
            else ("true" if meta.basecalling_enabled else "false")
        )),
        ("raw_run_dir", meta.raw_run_dir),
    ]
    for key, value in fields:
        ws.append([key, "" if value is None else value])


def export_mame_janus_csv(
    replicates: list[ReplicateResult],
    output_path: Path,
    ngs_run_meta: "NgsRunMeta | None" = None,
    dest_layout: str = "source",
) -> Path:
    """Export final cell-stock Janus mapping as CSV.

    Header: name | source_plate | source_well | dest_well | priority_score

    Sorted by priority_score DESC (high file_size_kb first).
    Only confirmed (non-failed) replicates are included.

    G3: when *ngs_run_meta* is not ``None``, a ``# kuma_run_meta: ...`` comment
    line is prepended before the header row.  When *ngs_run_meta* is ``None``
    no comment is written (backward-compatible with existing consumers).

    Phase 1: priority_score = file_size_kb proxy.
    G6/A6 round: replace with BarcodeRecord.read_count when available.

    *dest_layout* is ``"source"`` (dest mirrors source position, default) or
    ``"compact"`` (destinations assigned sequentially from A1 in sorted order).
    Raises ``ValueError`` on unresolved wells, >96 picks, or duplicate dests.
    """
    rows = _build_janus_rows(replicates, dest_layout=dest_layout)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        if ngs_run_meta is not None:
            fh.write(_meta_comment_line(ngs_run_meta) + "\n")
        writer = csv.DictWriter(fh, fieldnames=_JANUS_HEADER)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def export_mame_janus_xlsx(
    replicates: list[ReplicateResult],
    output_path: Path,
    ngs_run_meta: "NgsRunMeta | None" = None,
    kuma_version: str = "",
    dest_layout: str = "source",
) -> Path:
    """Export final cell-stock Janus mapping as XLSX.

    Same data as the CSV variant.  Provides header bold-styling and
    column freeze for readability.

    G3: when *ngs_run_meta* is provided, a ``__kuma_meta__`` sheet is appended.
    The sheet is always written (placeholder when meta is ``None``).

    Phase 1: priority_score = file_size_kb proxy.

    *dest_layout* behaves exactly as in ``export_mame_janus_csv``.
    """
    import openpyxl
    from openpyxl.styles import Font

    rows = _build_janus_rows(replicates, dest_layout=dest_layout)

    wb = openpyxl.Workbook()
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet("Janus Mapping")
    else:
        ws.title = "Janus Mapping"

    ws.append(_JANUS_HEADER)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"

    for row in rows:
        ws.append(
            [
                row["name"],
                row["source_plate"],
                row["source_well"],
                row["dest_well"],
                row["priority_score"],
            ]
        )

    # G3: always append __kuma_meta__ sheet.
    _write_janus_kuma_meta_sheet(wb, ngs_run_meta, kuma_version)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


__all__ = ["export_mame_janus_csv", "export_mame_janus_xlsx"]
