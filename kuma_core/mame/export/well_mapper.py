"""96-well coordinate mapping (column-major, confirmed Blocker C spec).

seq=1 -> A1, seq=2 -> B1, ..., seq=8 -> H1, seq=9 -> A2, ..., seq=96 -> H12.
"""

from __future__ import annotations


def seq_to_well(seq: int) -> str:
    """Convert a 1-based sequence index (1..96) to a column-major well label."""

    if not 1 <= seq <= 96:
        raise ValueError(f"seq must be in [1, 96]; got {seq}")
    row_idx = (seq - 1) % 8
    col_num = (seq - 1) // 8 + 1
    return f"{chr(ord('A') + row_idx)}{col_num}"


def well_to_seq(well: str) -> int:
    well = well.strip().upper()
    if len(well) < 2:
        raise ValueError(f"invalid well label: {well!r}")
    row_char = well[0]
    col_str = well[1:]
    if not ("A" <= row_char <= "H"):
        raise ValueError(f"invalid row in well: {well!r}")
    if not col_str.isdigit():
        raise ValueError(f"invalid column in well: {well!r}")
    col_num = int(col_str)
    if not 1 <= col_num <= 12:
        raise ValueError(f"column out of range in well: {well!r}")
    row_idx = ord(row_char) - ord("A")
    return (col_num - 1) * 8 + row_idx + 1


class WellMapper:
    """Column-major mapper; kept as a class for explicit API symmetry."""

    def seq_to_well(self, seq: int) -> str:
        return seq_to_well(seq)

    def well_to_seq(self, well: str) -> int:
        return well_to_seq(well)
