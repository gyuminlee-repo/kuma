"""Excel export: per-native-barcode sheets + Final 96-well matrix."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook import Workbook

from kuma_core.mame.export.well_mapper import WellMapper, seq_to_well
from kuma_core.mame.models import ReplicateResult, VerdictClass, VerdictRecord

# Confirmed color map (040 AC-09).
VERDICT_FILL: dict[VerdictClass, str] = {
    VerdictClass.PASS: "00B050",
    VerdictClass.AMBIGUOUS: "FFFF00",
    VerdictClass.FRAMESHIFT: "FF0000",
    VerdictClass.MANY: "FF0000",
    VerdictClass.WRONG_AA: "FF0000",
    VerdictClass.LOWDEPTH: "808080",
}

FAILED_FILL = "FF0000"
WELL_HIGHLIGHT_PURPLE = "A02B93"  # Final sheet coord column highlight
SELECTED_PLATE_YELLOW = "FFFF00"  # Final sheet chosen plate highlight

_SHEET1_HEADER = [
    "well_id",
    "file_size_kb",
    "custom_barcode",
    "observed_mutations",
    "observed_aa",
    "verdict",
    "verdict_notes",
]

_FINAL_HEADER = [
    "well_id",
    "selected_plate",
    "custom_barcode",
    "mutant_id",
    "verdict",
]


def _fill(color_hex: str) -> PatternFill:
    return PatternFill(start_color=color_hex, end_color=color_hex, fill_type="solid")


def _custom_barcode_to_seq(custom: str) -> int | None:
    """`{R}_{F}` -> 1-based column-major sequence index.

    Uses F as the well column (1..12) and R as the row contribution within the
    column. Returns None if the label cannot be parsed.
    """

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


def _write_sheet1(wb: Workbook, native_barcode: str, records: Iterable[VerdictRecord]) -> None:
    ws = wb.create_sheet(native_barcode)
    ws.append(_SHEET1_HEADER)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for vr in sorted(
        records,
        key=lambda r: _custom_barcode_to_seq(r.translated.barcode.custom_barcode) or 0,
    ):
        br = vr.translated.barcode
        seq = _custom_barcode_to_seq(br.custom_barcode)
        well_id = seq_to_well(seq) if seq else ""
        row = [
            well_id,
            round(br.file_size_kb, 3),
            br.custom_barcode,
            ", ".join(vr.translated.observed_nt_changes),
            ", ".join(vr.translated.observed_aa_changes),
            vr.verdict.value,
            vr.verdict_notes,
        ]
        ws.append(row)
        fill = _fill(VERDICT_FILL[vr.verdict])
        for cell in ws[ws.max_row]:
            cell.fill = fill


def _write_final(
    wb: Workbook,
    replicate_results: Iterable[ReplicateResult],
    mapper: WellMapper,
) -> None:
    ws = wb.create_sheet("Final")
    ws.append(_FINAL_HEADER)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Index replicate results by the chosen custom_barcode's well when selectable.
    replicate_by_seq: dict[int, ReplicateResult] = {}
    failed_wells: list[str] = []
    unassigned: list[ReplicateResult] = []

    for rr in replicate_results:
        seq: int | None = None
        if rr.selected_plate is not None:
            vr = rr.plate_verdicts.get(rr.selected_plate)
            if vr is not None:
                seq = _custom_barcode_to_seq(vr.translated.barcode.custom_barcode)
        else:
            # Failed — try to borrow a well from any available verdict to place
            # a FAILED marker.
            for vr in rr.plate_verdicts.values():
                s = _custom_barcode_to_seq(vr.translated.barcode.custom_barcode)
                if s is not None:
                    seq = s
                    break
        if seq is not None and seq not in replicate_by_seq:
            replicate_by_seq[seq] = rr
        else:
            unassigned.append(rr)

    confirmed = 0
    failed_count = 0
    redo_targets: list[str] = []

    for seq in range(1, 97):
        well = mapper.seq_to_well(seq)
        rr = replicate_by_seq.get(seq)
        if rr is None:
            ws.append([well, "", "", "", ""])
            _highlight_well_cell(ws, ws.max_row)
            continue

        if rr.failed or rr.selected_plate is None:
            failed_wells.append(well)
            failed_count += 1
            redo_targets.append(rr.mutant_id)
            ws.append([well, "FAILED", "-", rr.mutant_id, "-"])
            for cell in ws[ws.max_row]:
                cell.fill = _fill(FAILED_FILL)
        else:
            vr = rr.plate_verdicts[rr.selected_plate]
            ws.append(
                [
                    well,
                    rr.selected_plate,
                    vr.translated.barcode.custom_barcode,
                    rr.mutant_id,
                    vr.verdict.value,
                ]
            )
            row_idx = ws.max_row
            # Selected-plate yellow highlight per 050 spec.
            ws.cell(row=row_idx, column=2).fill = _fill(SELECTED_PLATE_YELLOW)
            # Verdict-class fill on the verdict column for visual continuity.
            ws.cell(row=row_idx, column=5).fill = _fill(VERDICT_FILL[vr.verdict])
            confirmed += 1
        _highlight_well_cell(ws, ws.max_row)

    # Summary footer.
    ws.append([])
    summary = (
        f"confirmed: {confirmed}/96 | FAILED: {failed_count} | "
        f"REDO targets: {', '.join(redo_targets) if redo_targets else '(none)'}"
    )
    ws.append([summary])
    ws.cell(row=ws.max_row, column=1).alignment = Alignment(horizontal="left")

    # Any replicate results that could not be assigned (extra wells) go in a
    # secondary block so they are not silently dropped.
    if unassigned:
        ws.append([])
        ws.append(["unassigned replicate results:"])
        for rr in unassigned:
            ws.append(
                [
                    "",
                    rr.selected_plate or "FAILED",
                    "",
                    rr.mutant_id,
                    rr.selection_reason,
                ]
            )


def _highlight_well_cell(ws, row_idx: int) -> None:
    ws.cell(row=row_idx, column=1).fill = _fill(WELL_HIGHLIGHT_PURPLE)
    ws.cell(row=row_idx, column=1).font = Font(color="FFFFFF", bold=True)


def write_excel(
    verdict_records: list[VerdictRecord],
    replicate_results: list[ReplicateResult],
    output_path: Path,
    mapper: WellMapper | None = None,
    mode: Literal["amplicon", "plasmid"] = "amplicon",  # reserved for Phase 2
) -> Path:
    """Write the combined Excel report to ``output_path``. Returns the path."""

    del mode  # Phase 1: mode does not alter Excel layout.
    mapper = mapper or WellMapper()

    wb = openpyxl.Workbook()
    default = wb.active
    if default is not None:
        wb.remove(default)

    by_nb: dict[str, list[VerdictRecord]] = {}
    for vr in verdict_records:
        by_nb.setdefault(vr.translated.barcode.native_barcode, []).append(vr)

    for nb in sorted(by_nb):
        _write_sheet1(wb, nb, by_nb[nb])

    _write_final(wb, replicate_results, mapper)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path
