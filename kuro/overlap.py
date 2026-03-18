"""Overlap window generation for SDM primer design."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OverlapWindow:
    """A candidate overlap region around a mutation site."""

    sequence: str           # Overlap nucleotide sequence
    start: int              # 0-based start position in the (mutated) sequence
    end: int                # 0-based end position (exclusive)
    codon_offset: int       # Offset of mutant codon (= overlap_len when upstream-only)


def generate_overlap_windows(
    seq: str,
    codon_start: int,
    overlap_len: int = 20,
    step: int = 1,
) -> list[OverlapWindow]:
    """Generate overlap windows UPSTREAM of the mutation codon.

    The overlap region ends at the mutation codon start (exclusive).
    This follows the EVOLVEpro partially-overlapping primer design:
      Forward = [overlap upstream] + [mutant codon] + [downstream extension]
      Reverse = [upstream extension] + [rc(overlap)]

    Args:
        seq: Full DNA sequence (mutated).
        codon_start: 0-based start position of the mutant codon.
        overlap_len: Length of the overlap window in bp.
        step: Sliding step size (unused, kept for API compat).

    Returns:
        List of OverlapWindow candidates (one per overlap_len).
    """
    seq = seq.upper()
    seq_len = len(seq)

    # Overlap ends at codon_start (upstream only, mutation NOT inside)
    start = codon_start - overlap_len
    if start < 0:
        # Circular wrap
        start_adj = start + seq_len
        overlap_seq = seq[start_adj:] + seq[:codon_start]
    else:
        start_adj = start
        overlap_seq = seq[start_adj:codon_start]

    if len(overlap_seq) != overlap_len:
        return []

    return [OverlapWindow(
        sequence=overlap_seq,
        start=start_adj,
        end=codon_start,
        codon_offset=overlap_len,  # codon is right after the window
    )]


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
