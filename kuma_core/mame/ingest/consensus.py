"""A5 — CIGAR-based pileup consensus caller.

Implements a majority-vote consensus algorithm equivalent to
``samtools consensus`` default mode:

- Per-position base counts from aligned reads via CIGAR walking.
- Majority base (≥ 0.5 fraction of total depth) is adopted.
- Positions with depth < ``min_depth`` yield 'N'.
- Insertions: counted but not incorporated into the linear consensus
  (same as samtools consensus default, which omits insertions from
  the output sequence).
- Deletions: contribute a deletion token ('-') to the position vote;
  if deletions are the majority base the output is 'N' (gap-free output).
- Reverse-complement reads: bases are reverse-complemented before voting.

Reference
---------
https://www.htslib.org/doc/samtools-consensus.html — "Default (simple) mode":
  Each position calls the most common base across all reads.  Positions with
  only deletions/no coverage output 'N'.

Note on quality weighting
--------------------------
The current demux pipeline (``demux.py``) produces per-well FASTA files with
no quality strings.  Therefore quality-weighted voting (as used by
samtools consensus in quality mode) is not possible from FASTA input.
This implementation uses unweighted majority vote, which is equivalent to
samtools consensus -m simple (the default pileup mode).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from kuma_core.mame.ingest.align import (
    Alignment,
    _CIGAR_D,
    _CIGAR_EQ,
    _CIGAR_H,
    _CIGAR_I,
    _CIGAR_M,
    _CIGAR_N,
    _CIGAR_P,
    _CIGAR_S,
    _CIGAR_X,
)

# Complement table (single-char, uppercase).
_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")

def _reverse_complement(seq: str) -> str:
    """Return the reverse complement of a DNA sequence."""
    return seq.translate(_COMP)[::-1]


def call_consensus(
    alignments: Sequence[Alignment],
    reference_seq: str,
    min_depth: int = 1,
) -> str:
    """Call per-position majority-vote consensus from a list of alignments.

    Parameters
    ----------
    alignments:
        List of :class:`~kuma_core.mame.ingest.align.Alignment` objects for a
        single well.  Mixed strands are handled automatically (reverse-strand
        reads are reverse-complemented before voting).
    reference_seq:
        Reference nucleotide sequence (same as used during alignment).
        Used to determine output length and as fallback for uncovered positions.
    min_depth:
        Minimum number of reads that must cover a position for a base call
        to be made.  Positions below this threshold yield 'N'.

    Returns
    -------
    Consensus sequence string of length ``len(reference_seq)``.  Each character
    is one of A/C/G/T/N.  Indels (deletions) that achieve majority vote are
    collapsed to 'N' (gap-free output, matching samtools consensus default).
    """
    ref_len = len(reference_seq)

    # per_position[ref_pos] = {base: count}
    per_position: list[dict[str, int]] = [defaultdict(int) for _ in range(ref_len)]

    for aln in alignments:
        _accumulate(aln, per_position)

    # Build consensus string.
    out: list[str] = []
    for pos in range(ref_len):
        counts = per_position[pos]
        total = sum(counts.values())
        if total < min_depth:
            out.append("N")
            continue
        # Find majority base.
        best_base, best_count = max(counts.items(), key=lambda kv: kv[1])
        if best_base == "-" or best_count / total < 0.5:
            # Deletion majority or no clear winner → N (gap-free output).
            out.append("N")
        else:
            out.append(best_base.upper() if best_base.upper() in "ACGT" else "N")

    return "".join(out)


def _accumulate(aln: Alignment, per_position: list[dict[str, int]]) -> None:
    """Walk a single alignment's CIGAR and add base votes to per_position.

    CIGAR walking uses two cursors:
    - ``ref_pos``: current position on the reference (0-based).
    - ``q_pos``: current position on the query (read) sequence (0-based).

    The query sequence is reverse-complemented when ``aln.strand == -1``.
    """
    # Prepare query sequence oriented to the forward strand.
    if aln.strand == -1:
        q_seq = _reverse_complement(aln.read_seq)
    else:
        q_seq = aln.read_seq

    ref_pos = aln.r_st
    q_pos = aln.q_st
    ref_len = len(per_position)

    for length, op in aln.cigar:
        if op in (_CIGAR_M, _CIGAR_EQ, _CIGAR_X):
            # Aligned bases (match or mismatch): vote at each ref position.
            for i in range(length):
                rp = ref_pos + i
                qp = q_pos + i
                if 0 <= rp < ref_len and qp < len(q_seq):
                    base = q_seq[qp].upper()
                    if base in "ACGTN":
                        per_position[rp][base] += 1
            ref_pos += length
            q_pos += length

        elif op == _CIGAR_D or op == _CIGAR_N:
            # Deletion / skip: advance ref_pos, vote deletion at each position.
            for i in range(length):
                rp = ref_pos + i
                if 0 <= rp < ref_len:
                    per_position[rp]["-"] += 1
            ref_pos += length
            # q_pos unchanged (deletion consumes reference only)

        elif op == _CIGAR_I:
            # Insertion: advance query only; insertions are not represented in
            # the reference-length output (same as samtools consensus default).
            q_pos += length

        elif op == _CIGAR_S:
            # Soft clip: query bases are present but not aligned; skip.
            q_pos += length

        elif op in (_CIGAR_H, _CIGAR_P):
            # Hard clip / padding: no bases consumed in either sequence.
            pass

        else:
            # Unknown op — skip without advancing (defensive).
            pass


def per_position_depth(
    alignments: Sequence[Alignment],
    ref_len: int,
) -> list[int]:
    """Return per-position read depth (for ConsensusResult.mean_depth).

    Counts aligned (non-gap) reads at each reference position.
    """
    depths = [0] * ref_len
    for aln in alignments:
        ref_pos = aln.r_st
        q_pos = aln.q_st

        for length, op in aln.cigar:
            if op in (_CIGAR_M, _CIGAR_EQ, _CIGAR_X):
                for i in range(length):
                    rp = ref_pos + i
                    if 0 <= rp < ref_len:
                        depths[rp] += 1
                ref_pos += length
                q_pos += length
            elif op == _CIGAR_D or op == _CIGAR_N:
                ref_pos += length
            elif op == _CIGAR_I:
                q_pos += length
            elif op == _CIGAR_S:
                q_pos += length
            # Hard clip / padding: no advance

    return depths


__all__ = ["call_consensus", "per_position_depth"]
