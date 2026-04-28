"""Janus mapping export for final cell-stock pick (mame K4 spec).

Header design follows the 260428 meeting §2.5 decision:
  name | source_plate | source_well | dest_well | priority_score

- ``source_plate``: P1 / P2 / P3  (NB01→P1, NB02→P2, NB03→P3)
- ``source_well``:  well label in the NB plate (e.g. "A1")
- ``dest_well``:    destination well in the final 96-well plate.
                    Auto-filled from the custom_barcode position.
                    Users can overwrite in the saved CSV/XLSX.
- ``priority_score``: ``file_size_kb`` in Phase 1.
                      G6/A6 round will replace with actual read_count.

Sorted by ``priority_score`` DESC (highest-volume clones first), per §2.5
recommended placement order.

Phase 1 read_count policy
--------------------------
``BarcodeRecord.read_count`` is None in Phase 1.  ``file_size_kb`` is used
as a volume proxy.  Column is named ``priority_score`` to remain meaningful
regardless of the underlying metric.
"""

from __future__ import annotations

import csv
from pathlib import Path

from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.models import ReplicateResult

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


def _build_janus_rows(
    replicates: list[ReplicateResult],
) -> list[dict[str, object]]:
    """Build sorted Janus mapping rows from replicate results.

    Only includes mutants that have a confirmed selected plate (not failed).
    Rows are sorted by ``priority_score`` DESC.
    """
    rows: list[dict[str, object]] = []

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
        else:
            well_label = seq_to_well(seq)

        source_plate = _PLATE_LABEL.get(rr.selected_plate, rr.selected_plate)
        # Phase 1: file_size_kb as priority proxy.
        priority_score = round(bc.file_size_kb, 3)

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
    return rows


def export_mame_janus_csv(
    replicates: list[ReplicateResult],
    output_path: Path,
) -> Path:
    """Export final cell-stock Janus mapping as CSV.

    Header: name | source_plate | source_well | dest_well | priority_score

    Sorted by priority_score DESC (high file_size_kb first).
    Only confirmed (non-failed) replicates are included.

    Phase 1: priority_score = file_size_kb proxy.
    G6/A6 round: replace with BarcodeRecord.read_count when available.
    """
    rows = _build_janus_rows(replicates)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_JANUS_HEADER)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def export_mame_janus_xlsx(
    replicates: list[ReplicateResult],
    output_path: Path,
) -> Path:
    """Export final cell-stock Janus mapping as XLSX.

    Same data as the CSV variant.  Provides header bold-styling and
    column freeze for readability.

    Phase 1: priority_score = file_size_kb proxy.
    """
    import openpyxl
    from openpyxl.styles import Font

    rows = _build_janus_rows(replicates)

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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


__all__ = ["export_mame_janus_csv", "export_mame_janus_xlsx"]
