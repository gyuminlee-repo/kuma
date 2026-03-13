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


def deduplicate_reverse(
    results: list[SdmPrimerResult],
) -> dict[str, list[str]]:
    """Find mutations sharing identical reverse primers.

    Mutations at the same codon position with different substitutions
    may share the same reverse primer (since the reverse primer binds
    upstream of the mutation site).

    Args:
        results: List of SdmPrimerResult.

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
) -> list[PlateMapping]:
    """Generate 96-well plate mappings for SDM primers.

    Forward primers are placed first, followed by (deduplicated) reverse primers.

    Args:
        results: SDM primer design results.
        well_order: 'column' (A1->H1->A2) or 'row' (A1->A12->B1).
        deduplicate_rev: If True, merge identical reverse primers.

    Returns:
        List of PlateMapping assignments.
    """
    mappings: list[PlateMapping] = []
    well_idx = 0

    # Forward primers: one per mutation
    for r in results:
        if well_idx >= 96:
            raise ValueError("Exceeded 96-well plate capacity")
        mappings.append(PlateMapping(
            well=_well_name(well_idx, well_order),
            primer_name=f"{r.mutation.raw}_F",
            sequence=r.forward_seq,
            primer_type="forward",
            mutation=r.mutation.raw,
        ))
        well_idx += 1

    # Reverse primers: deduplicated or individual
    if deduplicate_rev:
        rev_groups = deduplicate_reverse(results)
        for rev_seq, mut_names in rev_groups.items():
            if well_idx >= 96:
                raise ValueError("Exceeded 96-well plate capacity")
            label = "+".join(mut_names) if len(mut_names) > 1 else mut_names[0]
            mappings.append(PlateMapping(
                well=_well_name(well_idx, well_order),
                primer_name=f"{label}_R",
                sequence=rev_seq,
                primer_type="reverse",
                mutation=label,
            ))
            well_idx += 1
    else:
        for r in results:
            if well_idx >= 96:
                raise ValueError("Exceeded 96-well plate capacity")
            mappings.append(PlateMapping(
                well=_well_name(well_idx, well_order),
                primer_name=f"{r.mutation.raw}_R",
                sequence=r.reverse_seq,
                primer_type="reverse",
                mutation=r.mutation.raw,
            ))
            well_idx += 1

    return mappings


def export_plate_excel(
    mappings: list[PlateMapping],
    output_path: Path,
) -> None:
    """Export plate mappings to an Excel file.

    Creates two sheets:
    1. 'Primer List' — linear list of all primers with well assignments
    2. 'Plate Layout' — visual 96-well plate grid

    Args:
        mappings: List of PlateMapping.
        output_path: Path for the output .xlsx file.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()

    # Sheet 1: Primer List
    ws1 = wb.active
    ws1.title = "Primer List"
    headers = ["Well", "Primer Name", "Sequence", "Length", "Type", "Mutation"]
    for col, h in enumerate(headers, 1):
        cell = ws1.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="D9E1F2", fill_type="solid")

    for i, m in enumerate(mappings, 2):
        ws1.cell(row=i, column=1, value=m.well)
        ws1.cell(row=i, column=2, value=m.primer_name)
        ws1.cell(row=i, column=3, value=m.sequence)
        ws1.cell(row=i, column=4, value=len(m.sequence))
        ws1.cell(row=i, column=5, value=m.primer_type)
        ws1.cell(row=i, column=6, value=m.mutation)

    # Auto-adjust column widths
    for col in ws1.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws1.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)

    # Sheet 2: Plate Layout
    ws2 = wb.create_sheet("Plate Layout")
    rows_label = "ABCDEFGH"

    # Column headers (1-12)
    for c in range(1, 13):
        cell = ws2.cell(row=1, column=c + 1, value=c)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    # Row headers (A-H)
    for r_idx, r_label in enumerate(rows_label):
        ws2.cell(row=r_idx + 2, column=1, value=r_label).font = Font(bold=True)

    # Fill in primer names
    fwd_fill = PatternFill(start_color="C6EFCE", fill_type="solid")
    rev_fill = PatternFill(start_color="FCE4D6", fill_type="solid")

    for m in mappings:
        row_letter = m.well[0]
        col_num = int(m.well[1:])
        r_idx = rows_label.index(row_letter) + 2
        c_idx = col_num + 1

        cell = ws2.cell(row=r_idx, column=c_idx, value=m.primer_name)
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        cell.fill = fwd_fill if m.primer_type == "forward" else rev_fill

    # Adjust widths
    ws2.column_dimensions["A"].width = 4
    for c in range(2, 14):
        ws2.column_dimensions[chr(64 + c)].width = 14

    wb.save(output_path)
