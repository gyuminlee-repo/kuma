"""Excel export: per-native-barcode sheets + Final 96-well matrix.

G6/A6 read_count policy
------------------------
``BarcodeRecord.read_count`` is populated by the consensus parser from
``depth=N`` header metadata when available, falling back to single-record
counts for legacy consensus files.  The "NGS Results" sheet columns are named
``NB0X_reads`` and carry read_count when non-None, falling back to file_size_kb
as a volume proxy.
The per-plate ``NB0X`` sheets retain ``file_size_kb`` in their header (Sheet1
format) for backward compatibility; only the unified "NGS Results" sheet uses
the ``reads`` naming.

A11 / G3 __kuma_meta__ sheet
------------------------------
``write_excel`` appends a ``__kuma_meta__`` sheet with MinKNOW run metadata
when ``ngs_run_meta`` is supplied.  The sheet contains key/value rows for
instrument, flow_cell_id, sample_id, kit, started, position,
basecalling_enabled, and raw_run_dir.  A ``kuma_version`` row is always
written so consumers can identify the generating software version.
When ``ngs_run_meta`` is ``None`` a single placeholder row is written to
keep the sheet structure consistent.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook import Workbook

from kuma_core.mame.export.well_mapper import WellMapper, seq_to_well
from kuma_core.mame.models import ReplicateResult, VerdictClass, VerdictRecord
from kuma_core.mame.detected import compute_recovery, replicate_is_recovered

if TYPE_CHECKING:
    from kuma_core.mame.ingest.run_meta import NgsRunMeta

# Confirmed color map (040 AC-09).
VERDICT_FILL: dict[VerdictClass, str] = {
    VerdictClass.PASS: "00B050",
    VerdictClass.AMBIGUOUS: "FFFF00",
    VerdictClass.MIXED: "FFC000",
    VerdictClass.FRAMESHIFT: "FF0000",
    VerdictClass.MANY: "FF0000",
    VerdictClass.WRONG_AA: "FF0000",
    VerdictClass.LOWDEPTH: "808080",
    VerdictClass.NO_CALL: "595959",
}

FAILED_FILL = "FF0000"
WELL_HIGHLIGHT_PURPLE = "A02B93"  # Final sheet coord column highlight
SELECTED_PLATE_YELLOW = "FFFF00"  # Final sheet chosen plate highlight

_SHEET1_HEADER = [
    "well_id",
    "file_size_kb",
    "read_count",
    "input_reads",
    "aligned_reads",
    "mapq_failed",
    "span_failed",
    "low_depth_positions",
    "consensus_n_fraction",
    "low_quality_bases",
    "mixed_positions",
    "max_minor_allele_fraction",
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

# Reference-format "NGS Results" sheet (3 plates side-by-side, 96 mutant rows).
# Phase 1: reads columns carry file_size_kb as a proxy — header makes this explicit.
# G6/A6 round: replace file_size_kb values with actual read_count from BarcodeRecord.
_KNOWN_PLATES = ("NB01", "NB02", "NB03")

_NGS_RESULT_HEADER = [
    "index",
    "mutant",
    "well",
    "custom_barcode",
    "NB01_detected",
    "NB01_reads",
    "NB01_quality",
    "NB02_detected",
    "NB02_reads",
    "NB02_quality",
    "NB03_detected",
    "NB03_reads",
    "NB03_quality",
    "recovered",
]

_FINAL_MATRIX_HEADER = [
    "index",
    "mutant",
    "well",
    "NB01",
    "NB02",
    "NB03",
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
            br.read_count,
            br.n_input_reads,
            br.n_aligned_reads,
            br.n_mapq_failed,
            br.n_span_failed,
            br.n_low_depth_positions,
            round(br.consensus_n_fraction, 4),
            br.n_low_quality_bases,
            br.n_mixed_positions,
            round(br.max_minor_allele_fraction, 4),
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


# ---------------------------------------------------------------------------
# Reference-format sheets (G7 + G2 implementation).
# ---------------------------------------------------------------------------


def _build_unified_ngs_data(
    replicate_results: list[ReplicateResult],
) -> list[dict]:
    """Build per-mutant rows for the "NGS Results" sheet.

    Each row holds a mutant_id key and per-plate detected/file_size_kb values.
    Mutant ordering follows the ``replicate_results`` list (which preserves
    expected_mutations.xlsx row order from the pipeline).

    G6/A6 read_count policy: ``read_count`` is used when non-None; falls back
    to ``file_size_kb`` as a volume proxy for older or low-depth records.
    """
    rows: list[dict] = []
    for idx, rr in enumerate(replicate_results, start=1):
        # Determine the well from the selected plate if available, otherwise
        # from any available plate verdict.
        ref_vr: VerdictRecord | None = None
        if rr.selected_plate is not None:
            ref_vr = rr.plate_verdicts.get(rr.selected_plate)
        if ref_vr is None:
            for plate in _KNOWN_PLATES:
                ref_vr = rr.plate_verdicts.get(plate)
                if ref_vr is not None:
                    break

        seq: int | None = None
        cb: str = ""
        if ref_vr is not None:
            cb = ref_vr.translated.barcode.custom_barcode
            seq = _custom_barcode_to_seq(cb)

        well_id = seq_to_well(seq) if seq is not None and 1 <= seq <= 96 else ""

        row: dict = {
            "index": idx,
            "mutant": rr.mutant_id,
            "well": well_id,
            "custom_barcode": cb,
        }

        for plate in _KNOWN_PLATES:
            vr = rr.plate_verdicts.get(plate)
            if vr is not None:
                detected = ", ".join(vr.translated.observed_aa_changes) or vr.verdict.value
                bc = vr.translated.barcode
                # G6/A6: read_count preferred; fall back to file_size_kb proxy.
                reads_val: int | float | None = (
                    bc.read_count if bc.read_count is not None else bc.file_size_kb
                )
                quality = (
                    f"N={bc.consensus_n_fraction:.3f}; "
                    f"low_depth={bc.n_low_depth_positions}; "
                    f"low_q={bc.n_low_quality_bases}; "
                    f"mix={bc.n_mixed_positions}/"
                    f"{bc.max_minor_allele_fraction:.3f}; "
                    f"drop_mapq={bc.n_mapq_failed}; "
                    f"drop_span={bc.n_span_failed}"
                )
            else:
                detected = ""
                reads_val = None
                quality = ""
            row[f"{plate}_detected"] = detected
            row[f"{plate}_reads"] = reads_val
            row[f"{plate}_quality"] = quality

        # 재현(recovered): OR across this mutant's plate verdicts (PASS/AMBIGUOUS).
        row["recovered"] = "Y" if replicate_is_recovered(rr) else "N"
        rows.append(row)

    return rows


def _write_unified_ngs_sheet(
    wb: Workbook,
    replicate_results: list[ReplicateResult],
    designed_mutant_ids: frozenset[str] | None = None,
) -> None:
    """Write the reference-format "NGS Results" sheet (G7 spec)."""
    ws = wb.create_sheet("NGS Results")
    ws.append(_NGS_RESULT_HEADER)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    rows = _build_unified_ngs_data(replicate_results)
    for row in rows:
        ws.append(
            [
                row["index"],
                row["mutant"],
                row["well"],
                row["custom_barcode"],
                row["NB01_detected"],
                row["NB01_reads"],
                row["NB01_quality"],
                row["NB02_detected"],
                row["NB02_reads"],
                row["NB02_quality"],
                row["NB03_detected"],
                row["NB03_reads"],
                row["NB03_quality"],
                row["recovered"],
            ]
        )

    # Recovery (재현율) summary area below the per-mutant rows.
    recovery = compute_recovery(replicate_results, designed_mutant_ids)
    ws.append([])
    if recovery is None:
        ws.append(["Recovery (재현율)", "n/a"])
    else:
        ws.append([
            "Recovery (재현율)",
            f"{recovery.recovery_rate * 100:.1f}%",
        ])
        ws.append(["recovered_mutants", recovery.recovered_mutants])
        ws.append(["total_mutants", recovery.total_mutants])

    # Freeze top header row for readability.
    ws.freeze_panes = "A2"


def _write_final_matrix_sheet(
    wb: Workbook,
    replicate_results: list[ReplicateResult],
) -> None:
    """Write the reference-format binary selection matrix (G2 spec).

    Sheet name is "Final (matrix)" to avoid collision with the legacy "Final"
    sheet (which is preserved for backward compatibility).

    Column values: 1 if that plate was selected for the mutant, blank otherwise.
    """
    ws = wb.create_sheet("Final (matrix)")
    ws.append(_FINAL_MATRIX_HEADER)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for idx, rr in enumerate(replicate_results, start=1):
        # Determine well from selected plate or any available verdict.
        ref_vr: VerdictRecord | None = None
        if rr.selected_plate is not None:
            ref_vr = rr.plate_verdicts.get(rr.selected_plate)
        if ref_vr is None:
            for plate in _KNOWN_PLATES:
                ref_vr = rr.plate_verdicts.get(plate)
                if ref_vr is not None:
                    break

        seq: int | None = None
        if ref_vr is not None:
            seq = _custom_barcode_to_seq(ref_vr.translated.barcode.custom_barcode)

        well_id = seq_to_well(seq) if seq is not None and 1 <= seq <= 96 else ""

        plate_cols: list[int | str] = []
        for plate in _KNOWN_PLATES:
            if rr.selected_plate == plate and not rr.failed:
                plate_cols.append(1)
            else:
                plate_cols.append("")

        ws.append([idx, rr.mutant_id, well_id, *plate_cols])

        # Highlight the selected plate cell with yellow.
        if rr.selected_plate in _KNOWN_PLATES and not rr.failed:
            col_idx = list(_KNOWN_PLATES).index(rr.selected_plate)
            # +4: 1-based, 3 leading cols (index, mutant, well) + 1
            ws.cell(row=ws.max_row, column=4 + col_idx).fill = _fill(SELECTED_PLATE_YELLOW)

    ws.freeze_panes = "A2"


# ---------------------------------------------------------------------------
# __kuma_meta__ sheet (A11 / G3).
# ---------------------------------------------------------------------------


def _write_kuma_meta_sheet(
    wb: Workbook,
    meta: "NgsRunMeta | None",
    kuma_version: str,
) -> None:
    """Append a ``__kuma_meta__`` sheet to *wb*.

    Row format: col-A = key, col-B = value.
    When *meta* is ``None``, only the ``kuma_version`` and a ``ngs_run_meta``
    placeholder row are written so the sheet is always present.
    """
    ws = wb.create_sheet("__kuma_meta__")
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 40

    # Header row.
    ws.append(["key", "value"])
    for cell in ws[1]:
        cell.font = Font(bold=True)

    # Always include software version and generation timestamp.
    ws.append(["kuma_version", kuma_version])
    ws.append([
        "generated_at",
        datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ])

    if meta is None:
        ws.append(["ngs_run_meta", "(not found — no MinKNOW run folder detected)"])
        return

    # MinKNOW run fields.
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


def write_excel(
    verdict_records: list[VerdictRecord],
    replicate_results: list[ReplicateResult],
    output_path: Path,
    mapper: WellMapper | None = None,
    mode: Literal["amplicon", "plasmid"] = "amplicon",  # reserved for Phase 2
    ngs_run_meta: "NgsRunMeta | None" = None,
    kuma_version: str = "",
    designed_mutant_ids: frozenset[str] | None = None,
) -> Path:
    """Write the combined Excel report to ``output_path``. Returns the path.

    Parameters
    ----------
    ngs_run_meta:
        MinKNOW run metadata discovered by ``discover_run_meta``.  When
        ``None`` the ``__kuma_meta__`` sheet is still written with a
        placeholder row so the sheet always exists (A11).
    kuma_version:
        Software version string injected into the ``__kuma_meta__`` sheet.
    designed_mutant_ids:
        Distinct designed ``mutant_id`` set used to compute the recovery
        (재현율) summary in the "NGS Results" sheet.  ``None`` → recovery is
        rendered as ``n/a`` (designed set unavailable).
    """

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

    # Reference-format sheets (G7 + G2): appended after legacy sheets so that
    # existing consumers of NB01/NB02/NB03 and "Final" are not disturbed.
    _write_unified_ngs_sheet(wb, replicate_results, designed_mutant_ids)
    _write_final_matrix_sheet(wb, replicate_results)

    # A11 / G3: MinKNOW run metadata sheet — always present, content optional.
    _write_kuma_meta_sheet(wb, ngs_run_meta, kuma_version)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path
