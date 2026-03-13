"""Overlap window generation for SDM primer design."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OverlapWindow:
    """A candidate overlap region around a mutation site."""

    sequence: str           # Overlap nucleotide sequence
    start: int              # 0-based start position in the (mutated) sequence
    end: int                # 0-based end position (exclusive)
    codon_offset: int       # Offset of mutant codon within the overlap
    contains_mutation: bool  # Always True for valid windows


def generate_overlap_windows(
    seq: str,
    codon_start: int,
    overlap_len: int = 20,
    step: int = 1,
) -> list[OverlapWindow]:
    """Generate sliding overlap windows centered around a mutation site.

    The overlap window must fully contain the mutant codon (3 bp).
    Windows slide from (codon_start - overlap_len + 3) to codon_start,
    ensuring the 3-bp codon is always within the window.

    Args:
        seq: Full DNA sequence (mutated).
        codon_start: 0-based start position of the mutant codon.
        overlap_len: Length of the overlap window in bp.
        step: Sliding step size.

    Returns:
        List of OverlapWindow candidates.
    """
    seq = seq.upper()
    seq_len = len(seq)
    windows: list[OverlapWindow] = []

    # The window must contain all 3 bases of the codon
    # Window start ranges from (codon_start - overlap_len + 3) to codon_start
    earliest_start = codon_start - overlap_len + 3
    latest_start = codon_start

    for start in range(earliest_start, latest_start + 1, step):
        # Handle circular wrapping
        if start < 0:
            start_adj = start + seq_len
        else:
            start_adj = start

        end = start_adj + overlap_len

        # Extract sequence (handle circular wrap)
        if end <= seq_len:
            overlap_seq = seq[start_adj:end]
        else:
            overlap_seq = seq[start_adj:] + seq[:end - seq_len]

        codon_offset = codon_start - start  # can be negative if wrapped
        if start < 0:
            codon_offset = codon_start - start

        windows.append(OverlapWindow(
            sequence=overlap_seq,
            start=start_adj,
            end=end % seq_len if end > seq_len else end,
            codon_offset=codon_offset if codon_offset >= 0 else codon_offset + overlap_len,
            contains_mutation=True,
        ))

    return windows


def linearize_circular(
    seq: str,
    overlap_window: OverlapWindow,
) -> tuple[str, int]:
    """Linearize a circular sequence at the overlap window boundary.

    Cuts the circular sequence at the START of the overlap window,
    so the overlap is at position 0 of the returned linear sequence.

    Args:
        seq: Circular DNA sequence.
        overlap_window: The overlap window to cut at.

    Returns:
        Tuple of (linearized sequence, new codon position in linear seq).
    """
    seq = seq.upper()
    cut_point = overlap_window.start
    linear = seq[cut_point:] + seq[:cut_point]
    new_codon_start = overlap_window.codon_offset
    return linear, new_codon_start


def reverse_complement(seq: str) -> str:
    """Return the reverse complement of a DNA sequence."""
    complement = str.maketrans("ACGTacgt", "TGCAtgca")
    return seq.translate(complement)[::-1]
