"""Pure coordinate arithmetic for alignment-anchored barcode searches.

Coordinates are 0-based, half-open, on the ORIGINAL read. These bounds never
search the aligned insert. Strand normalization belongs to the caller; on the
minus strand it reverse-complements each returned slice independently.

This module has no alignment, file, process, or numerical-library dependency.
The formulas are extracted from combinatorial_demux without changing defaults,
clipping behavior, or the interpretation of existing saved parameters.
"""

from __future__ import annotations


def barcode_window_bounds(
    read_length: int,
    q_st: int,
    q_en: int,
    strand: int,
    window_bp: int,
    max_f_len: int,
    max_r_len: int,
) -> tuple[int, int, int, int]:
    """Return ``(f_start, f_end, r_start, r_end)`` on the original read.

    The aligner supplies valid read coordinates. Preserve the original min/max
    clipping exactly rather than adding a new acceptance policy here. A minus
    hit swaps the upstream/downstream roles, not the F/R barcode lengths.
    """
    if strand == -1:
        return (
            max(0, q_en),
            min(read_length, q_en + window_bp + max_f_len),
            max(0, q_st - window_bp - max_r_len),
            min(read_length, q_st),
        )
    return (
        max(0, q_st - window_bp - max_f_len),
        min(read_length, q_st),
        max(0, q_en),
        min(read_length, q_en + window_bp + max_r_len),
    )
