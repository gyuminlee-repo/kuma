"""96-well plate mapping and Excel export for SDM primers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .sdm_engine import SdmPrimerResult


@dataclass
class PlateMapping:
    """Single well assignment in a 96-well plate."""

    well: str               # e.g. "A1", "B1"
    primer_name: str        # e.g. "Q232A_F" or "Q232A_R"
    sequence: str           # Primer sequence
    primer_type: str        # "forward" or "reverse"
    mutation: str           # Original mutation notation
    tm: float | None = None          # Whole-primer Tm (Fwd or Rev)
    tm_overlap: float | None = None  # Overlap Tm
    wt_codon: str | None = None      # Wild-type codon
    mt_codon: str | None = None      # Mutant codon


def _well_name(index: int, order: str = "column") -> str:
    """Convert a 0-based index to a well name.

    Args:
        index: 0-based well index.
        order: 'column' (A1->H1->A2) or 'row' (A1->A12->B1).

    Returns:
        Well name like "A1".
    """
    rows = "ABCDEFGH"
    if order == "column":
        col = index // 8 + 1
        row = index % 8
    else:  # row
        row = index // 12
        col = index % 12 + 1
    if row >= 8 or col > 12:
        raise ValueError(f"Well index {index} exceeds 96-well plate capacity")
    return f"{rows[row]}{col}"


def _assign_well(index: int, well_order: str = "column") -> str:
    """Generate well name with overflow to additional plates."""
    plate_num = index // 96
    local_idx = index % 96
    well = _well_name(local_idx, well_order)
    if plate_num == 0:
        return well
    return f"P{plate_num + 1}-{well}"


def deduplicate_reverse(
    results: list[SdmPrimerResult],
) -> dict[str, list[str]]:
    """Find mutations sharing identical reverse primers.

    Returns:
        Dict mapping reverse primer sequence to list of mutation names.
    """
    rev_map: dict[str, list[str]] = {}
    for r in results:
        rev_seq = r.reverse_seq
        if rev_seq not in rev_map:
            rev_map[rev_seq] = []
        rev_map[rev_seq].append(r.mutation.raw)
    return rev_map


def generate_plate_map(
    results: list[SdmPrimerResult],
    well_order: str = "column",
    deduplicate_rev: bool = True,
) -> tuple[list[PlateMapping], list[PlateMapping]]:
    """Generate separate Fwd and Rev plate mappings.

    Forward plate: one primer per mutation, sequential well assignment.
    Reverse plate: deduplicated reverse primers, sequential well assignment.

    Returns:
        Tuple of (fwd_mappings, rev_mappings).
    """
    # Forward plate
    fwd_mappings: list[PlateMapping] = []
    for idx, r in enumerate(results):
        well = _assign_well(idx, well_order)
        fwd_mappings.append(PlateMapping(
            well=well,
            primer_name=f"{r.mutation.raw}_F",
            sequence=r.forward_seq,
            primer_type="forward",
            mutation=r.mutation.raw,
        ))

    # Reverse plate (deduplicated)
    rev_mappings: list[PlateMapping] = []
    if deduplicate_rev:
        rev_groups = deduplicate_reverse(results)
        for idx, (rev_seq, mut_names) in enumerate(rev_groups.items()):
            label = mut_names[0]
            well = _assign_well(idx, well_order)
            rev_mappings.append(PlateMapping(
                well=well,
                primer_name=f"{label}_R",
                sequence=rev_seq,
                primer_type="reverse",
                mutation=label,
            ))
    else:
        for idx, r in enumerate(results):
            well = _assign_well(idx, well_order)
            rev_mappings.append(PlateMapping(
                well=well,
                primer_name=f"{r.mutation.raw}_R",
                sequence=r.reverse_seq,
                primer_type="reverse",
                mutation=r.mutation.raw,
            ))

    return fwd_mappings, rev_mappings


def _is_shared_rev(m: PlateMapping, rev_groups: dict[str, list[str]] | None) -> bool:
    """Check if a reverse primer is shared by multiple mutations."""
    if m.primer_type != "reverse" or rev_groups is None:
        return False
    return len(rev_groups.get(m.sequence, [])) > 1


# Colors matching the UI: Fwd=green, Rev=orange, Shared=blue
_COLOR_FWD = "C6EFCE"       # light green
_COLOR_REV = "FCE4D6"       # light orange
_COLOR_SHARED = "BDD7EE"    # light blue


def _write_list_sheet(
    ws,
    mappings: list[PlateMapping],
    fill_color: str,
    rev_groups: dict[str, list[str]] | None = None,
) -> None:
    """Write a primer list sheet with row coloring."""
    from openpyxl.styles import Font, PatternFill

    headers = ["Well", "Primer Name", "Sequence", "Length",
               "Tm", "Tm_Overlap", "WT_Codon", "MT_Codon", "Mutation"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="D9E1F2", fill_type="solid")

    num_cols = len(headers)
    for i, m in enumerate(mappings, 2):
        ws.cell(row=i, column=1, value=m.well)
        ws.cell(row=i, column=2, value=m.primer_name)
        ws.cell(row=i, column=3, value=m.sequence)
        ws.cell(row=i, column=4, value=len(m.sequence))
        ws.cell(row=i, column=5, value=m.tm)
        ws.cell(row=i, column=6, value=m.tm_overlap)
        ws.cell(row=i, column=7, value=m.wt_codon)
        ws.cell(row=i, column=8, value=m.mt_codon)
        ws.cell(row=i, column=9, value=m.mutation)

        # Row color: shared=blue, otherwise fill_color
        row_color = _COLOR_SHARED if _is_shared_rev(m, rev_groups) else fill_color
        row_fill = PatternFill(start_color=row_color, fill_type="solid")
        for col_idx in range(1, num_cols + 1):
            ws.cell(row=i, column=col_idx).fill = row_fill

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)


def _write_plate_sheet(
    ws,
    mappings: list[PlateMapping],
    fill_color: str,
    rev_groups: dict[str, list[str]] | None = None,
) -> None:
    """Write a 96-well plate layout sheet with shared primers in blue."""
    from openpyxl.styles import Alignment, Font, PatternFill

    rows_label = "ABCDEFGH"

    for c in range(1, 13):
        cell = ws.cell(row=1, column=c + 1, value=c)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    for r_idx, r_label in enumerate(rows_label):
        ws.cell(row=r_idx + 2, column=1, value=r_label).font = Font(bold=True)

    default_fill = PatternFill(start_color=fill_color, fill_type="solid")
    shared_fill = PatternFill(start_color=_COLOR_SHARED, fill_type="solid")

    for m in mappings:
        if not m.well[0].isalpha():
            continue
        row_letter = m.well[0]
        col_num = int(m.well[1:])
        if row_letter not in rows_label or col_num > 12:
            continue
        r_idx = rows_label.index(row_letter) + 2
        c_idx = col_num + 1

        cell = ws.cell(row=r_idx, column=c_idx, value=m.primer_name)
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.fill = shared_fill if _is_shared_rev(m, rev_groups) else default_fill

    ws.column_dimensions["A"].width = 4
    for c in range(2, 14):
        ws.column_dimensions[chr(64 + c)].width = 14


def _chunk_by_plate(mappings: list[PlateMapping]) -> list[list[PlateMapping]]:
    """Split mappings into 96-well plate chunks."""
    plates: list[list[PlateMapping]] = []
    current: list[PlateMapping] = []
    for m in mappings:
        # Normalize well: strip overflow prefix like "P2-"
        well = m.well
        if "-" in well:
            well = well.split("-", 1)[1]
            m = PlateMapping(
                well=well,
                primer_name=m.primer_name,
                sequence=m.sequence,
                primer_type=m.primer_type,
                mutation=m.mutation,
                tm=m.tm,
                tm_overlap=m.tm_overlap,
                wt_codon=m.wt_codon,
                mt_codon=m.mt_codon,
            )
        current.append(m)
        if len(current) >= 96:
            plates.append(current)
            current = []
    if current:
        plates.append(current)
    return plates if plates else [[]]


def _pair_rev_per_plate(
    fwd_plates: list[list[PlateMapping]],
    rev_all: list[PlateMapping],
    rev_groups: dict[str, list[str]] | None,
) -> list[list[PlateMapping]]:
    """Pair reverse primers with each fwd plate by mutation membership.

    For each fwd plate chunk, collect the deduplicated reverse primers
    that belong to that chunk's mutations, reassigning well names.
    """
    # Build mutation → rev sequence lookup
    mut_to_rev_seq: dict[str, str] = {}
    if rev_groups:
        for seq, muts in rev_groups.items():
            for mut in muts:
                mut_to_rev_seq[mut] = seq

    rev_by_seq = {r.sequence: r for r in rev_all}

    paired: list[list[PlateMapping]] = []
    for fwd_chunk in fwd_plates:
        seen_seq: set[str] = set()
        rev_chunk: list[PlateMapping] = []
        well_idx = 0
        for fwd_m in fwd_chunk:
            rev_seq = mut_to_rev_seq.get(fwd_m.mutation)
            if rev_seq and rev_seq not in seen_seq:
                seen_seq.add(rev_seq)
                rev_m = rev_by_seq.get(rev_seq)
                if rev_m:
                    rev_chunk.append(PlateMapping(
                        well=_well_name(well_idx),
                        primer_name=rev_m.primer_name,
                        sequence=rev_m.sequence,
                        primer_type="reverse",
                        mutation=rev_m.mutation,
                        tm=rev_m.tm,
                        tm_overlap=rev_m.tm_overlap,
                        wt_codon=rev_m.wt_codon,
                        mt_codon=rev_m.mt_codon,
                    ))
                    well_idx += 1
        paired.append(rev_chunk)
    return paired


def export_plate_excel(
    mappings: list[PlateMapping],
    output_path: Path,
    rev_groups: dict[str, list[str]] | None = None,
) -> None:
    """Export plate mappings to Excel with per-plate sheets.

    Forward and reverse primers are paired per plate: Rev Plate N contains
    only the reverse primers for Fwd Plate N's mutations.

    For N plates, creates sheets:
    - 'Fwd List 1', 'Fwd Plate 1', 'Rev List 1', 'Rev Plate 1'
    - 'Fwd List 2', 'Fwd Plate 2', ... (if multi-plate)

    Single plate omits the number suffix.

    Args:
        rev_groups: Original reverse deduplication map (seq -> mutation names).
            Used to pair rev with fwd plates and detect shared primers.
    """
    from openpyxl import Workbook

    fwd_all = [m for m in mappings if m.primer_type == "forward"]
    rev_all = [m for m in mappings if m.primer_type == "reverse"]

    fwd_plates = _chunk_by_plate(fwd_all)
    rev_plates = _pair_rev_per_plate(fwd_plates, rev_all, rev_groups)
    plate_count = len(fwd_plates)
    suffix = plate_count > 1

    wb = Workbook()
    first_sheet = True
    chunk_rev_groups = rev_groups or {}

    for i in range(plate_count):
        tag = f" {i + 1}" if suffix else ""
        fwd_chunk = fwd_plates[i]
        rev_chunk = rev_plates[i] if i < len(rev_plates) else []

        if first_sheet:
            ws = wb.active
            ws.title = f"Fwd List{tag}"
            first_sheet = False
        else:
            ws = wb.create_sheet(f"Fwd List{tag}")
        _write_list_sheet(ws, fwd_chunk, _COLOR_FWD)

        ws = wb.create_sheet(f"Fwd Plate{tag}")
        _write_plate_sheet(ws, fwd_chunk, _COLOR_FWD)

        ws = wb.create_sheet(f"Rev List{tag}")
        _write_list_sheet(ws, rev_chunk, _COLOR_REV, rev_groups=chunk_rev_groups)

        ws = wb.create_sheet(f"Rev Plate{tag}")
        _write_plate_sheet(ws, rev_chunk, _COLOR_REV, rev_groups=chunk_rev_groups)

    wb.save(output_path)


def export_idt_csv(
    results: list[SdmPrimerResult],
    output_path: Path,
    scale: str = "25nm",
    purification: str = "STD",
) -> None:
    """Export primer order CSV in IDT OligoEntry format.

    CSV columns: Name, Sequence, Scale, Purification.
    Each mutation produces two rows (forward and reverse).

    Args:
        results: List of SdmPrimerResult from primer design.
        output_path: Path to output CSV file.
        scale: Synthesis scale (default: "25nm").
        purification: Purification type (default: "STD").
    """
    import csv

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Sequence", "Scale", "Purification"])
        for r in results:
            writer.writerow([f"{r.mutation.raw}_F", r.forward_seq, scale, purification])
            writer.writerow([f"{r.mutation.raw}_R", r.reverse_seq, scale, purification])


def export_twist_csv(
    results: list[SdmPrimerResult],
    output_path: Path,
) -> None:
    """Export primer order CSV in Twist Bioscience bulk order format.

    CSV columns: Name, Sequence, Notes.
    Each mutation produces two rows (forward and reverse).

    Args:
        results: List of SdmPrimerResult from primer design.
        output_path: Path to output CSV file.
    """
    import csv

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Sequence", "Notes"])
        for r in results:
            writer.writerow([f"{r.mutation.raw}_F", r.forward_seq, r.mutation.raw])
            writer.writerow([f"{r.mutation.raw}_R", r.reverse_seq, r.mutation.raw])
