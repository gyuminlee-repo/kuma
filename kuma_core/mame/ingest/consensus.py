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
When alignments carry FASTQ quality strings, bases below
``min_base_quality`` are excluded from the pileup before majority voting.
Legacy FASTA-only alignments have no quality string and keep the previous
unweighted majority vote behavior.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ConsensusCall:
    """Consensus sequence plus MAME-native quality metrics."""

    consensus_seq: str
    n_mixed_positions: int = 0
    max_minor_allele_fraction: float = 0.0
    n_low_depth_positions: int = 0
    consensus_n_fraction: float = 0.0
    n_low_quality_bases: int = 0
    # Per-well insertion-event evidence. Insertions are discarded from the
    # reference-length consensus (same as samtools consensus default), so
    # variant clones with only an in-frame insertion reach a WT-identical
    # consensus and pass verdict unchallenged. These two counters surface
    # the buried signal without altering the consensus sequence itself.
    #
    # Calibration (bench_v2 depth_50, 177 bp CDS, ~190 reads/well):
    #   WT / SNV wells (G1-G3): max_indel_event_fraction <= 0.21
    #   True deletion wells (G4 2bp del, G5 1bp HomoDel): >= 0.83
    #   Synthetic proof cases (100% INS/DEL reads): 1.00
    # A threshold of 0.50 provides a wide margin between noise (<=0.21)
    # and true indel signal (>=0.83).
    n_indel_event_positions: int = 0
    max_indel_event_fraction: float = 0.0
    # Longest contiguous run of ref positions whose deletion fraction exceeds
    # majority (del_frac > 0.5). 0 = indel gate is insertion-driven (no del-
    # majority run); 1 = isolated single-position deletion (review for an
    # alignment artifact); >=2 = an N-bp contiguous deletion (more likely real).
    # Informational only; does not change the consensus or the verdict gate.
    max_del_run_length: int = 0


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
    return call_consensus_with_metrics(
        alignments=alignments,
        reference_seq=reference_seq,
        min_depth=min_depth,
    ).consensus_seq


def call_consensus_with_metrics(
    alignments: Sequence[Alignment],
    reference_seq: str,
    min_depth: int = 1,
    mix_min_depth: int = 10,
    mix_minor_fraction_threshold: float = 0.20,
    min_base_quality: int = 10,
) -> ConsensusCall:
    """Call consensus and report native per-well quality evidence.

    ``n_mixed_positions`` counts positions where the second-most common A/C/G/T
    base reaches ``mix_minor_fraction_threshold`` at depth >= ``mix_min_depth``.
    This exposes 51/49-style mixed wells without changing the majority-vote
    consensus sequence or introducing a new frontend verdict enum.

    ``n_low_depth_positions`` counts positions whose total pileup depth is below
    ``min_depth``. ``consensus_n_fraction`` captures all consensus ``N`` calls,
    including low depth, deletion majority, ambiguous ties, and raw N votes.
    ``n_low_quality_bases`` counts FASTQ bases excluded by ``min_base_quality``.
    """
    ref_len = len(reference_seq)

    # per_position[ref_pos] = {base: count}
    per_position: list[dict[str, int]] = [defaultdict(int) for _ in range(ref_len)]
    # insertion_events[ref_pos] = number of reads with insertion starting here
    insertion_events: list[int] = [0] * ref_len

    n_low_quality_bases = 0
    for aln in alignments:
        n_low_quality_bases += _accumulate(
            aln,
            per_position,
            insertion_events,
            min_base_quality=min_base_quality,
        )

    # Build consensus string.
    out: list[str] = []
    n_mixed_positions = 0
    max_minor_allele_fraction = 0.0
    n_low_depth_positions = 0
    for pos in range(ref_len):
        counts = per_position[pos]
        total = sum(counts.values())
        if total < min_depth:
            n_low_depth_positions += 1
            out.append("N")
            continue

        base_counts = {
            base: count for base, count in counts.items() if base.upper() in "ACGT"
        }
        base_total = sum(base_counts.values())
        if base_total >= mix_min_depth and len(base_counts) >= 2:
            ranked = sorted(base_counts.values(), reverse=True)
            minor_fraction = ranked[1] / base_total
            max_minor_allele_fraction = max(max_minor_allele_fraction, minor_fraction)
            if minor_fraction >= mix_minor_fraction_threshold:
                n_mixed_positions += 1

        # Find majority base.
        best_base, best_count = max(counts.items(), key=lambda kv: kv[1])
        if best_base == "-" or best_count / total < 0.5:
            # Deletion majority or no clear winner → N (gap-free output).
            out.append("N")
        else:
            out.append(best_base.upper() if best_base.upper() in "ACGT" else "N")

    consensus_seq = "".join(out)
    consensus_n_fraction = (
        consensus_seq.count("N") / ref_len if ref_len > 0 else 0.0
    )

    # Aggregate indel event signal.
    # Deletion fraction: deletion votes / (base votes + deletion votes) per pos.
    # Insertion fraction: insertion events / base depth at anchor pos.
    # max_indel_event_fraction = max across all positions of either fraction.
    max_indel_event_fraction = 0.0
    n_indel_event_positions = 0
    # Track the longest contiguous run of deletion-majority positions
    # (del_frac > 0.5). pos iterates in ascending order, so a simple counter
    # captures contiguity. Same 0.5 majority definition used for base calls.
    max_del_run = 0
    cur_del_run = 0
    for pos in range(ref_len):
        counts = per_position[pos]
        depth_pos = sum(counts.values())
        del_votes = counts.get("-", 0)
        base_depth = depth_pos - del_votes  # reads that voted a base
        ins_ev = insertion_events[pos]
        # Spanning depth: reads that covered this position (base votes + del
        # votes). Inserting reads always vote a base at the anchor M op before
        # the I op, so they are already counted in base_depth. Using depth_pos
        # as the denominator guarantees ins_frac <= 1.0 whenever ins_ev <=
        # depth_pos (true by construction: every inserting read contributed a
        # base vote at the anchor). del_frac uses the same denominator for
        # consistency; del_votes is a subset of depth_pos so del_frac <= 1.0.
        ins_frac = ins_ev / depth_pos if depth_pos > 0 else 0.0
        del_frac = del_votes / depth_pos if depth_pos > 0 else 0.0
        pos_max = max(ins_frac, del_frac)
        if pos_max > max_indel_event_fraction:
            max_indel_event_fraction = pos_max
        if pos_max >= 0.05:
            n_indel_event_positions += 1
        if del_frac > 0.5:
            cur_del_run += 1
            max_del_run = max(max_del_run, cur_del_run)
        else:
            cur_del_run = 0

    return ConsensusCall(
        consensus_seq=consensus_seq,
        n_mixed_positions=n_mixed_positions,
        max_minor_allele_fraction=max_minor_allele_fraction,
        n_low_depth_positions=n_low_depth_positions,
        consensus_n_fraction=consensus_n_fraction,
        n_low_quality_bases=n_low_quality_bases,
        n_indel_event_positions=n_indel_event_positions,
        max_indel_event_fraction=max_indel_event_fraction,
        max_del_run_length=max_del_run,
    )


def _phred33(qual: str, idx: int) -> int | None:
    if idx < 0 or idx >= len(qual):
        return None
    return max(0, ord(qual[idx]) - 33)


def _accumulate(
    aln: Alignment,
    per_position: list[dict[str, int]],
    insertion_events: list[int],
    min_base_quality: int,
) -> int:
    """Walk a single alignment's CIGAR and add base votes to per_position.

    CIGAR walking uses two cursors:
    - ``ref_pos``: current position on the reference (0-based).
    - ``q_pos``: current position on the query (read) sequence (0-based).

    The query sequence is reverse-complemented when ``aln.strand == -1``.

    ``insertion_events[ref_pos]`` is incremented for each read that carries an
    insertion starting at ``ref_pos`` (anchored at the base just before the
    inserted sequence).  This lets callers track insertion evidence per
    reference position without altering the consensus length.
    """
    # Prepare query sequence oriented to the forward strand.
    if aln.strand == -1:
        q_seq = _reverse_complement(aln.read_seq)
        q_qual = aln.read_qual[::-1] if aln.read_qual is not None else None
    else:
        q_seq = aln.read_seq
        q_qual = aln.read_qual

    ref_pos = aln.r_st
    q_pos = aln.q_st
    ref_len = len(per_position)
    n_low_quality_bases = 0

    for length, op in aln.cigar:
        if op in (_CIGAR_M, _CIGAR_EQ, _CIGAR_X):
            # Aligned bases (match or mismatch): vote at each ref position.
            for i in range(length):
                rp = ref_pos + i
                qp = q_pos + i
                if 0 <= rp < ref_len and qp < len(q_seq):
                    if q_qual is not None:
                        q_score = _phred33(q_qual, qp)
                        if q_score is not None and q_score < min_base_quality:
                            n_low_quality_bases += 1
                            continue
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
            # Track the event count at the ref_pos just before the insertion
            # so callers can detect insertion-bearing wells.
            rp = ref_pos - 1
            if 0 <= rp < ref_len:
                insertion_events[rp] += 1
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

    return n_low_quality_bases


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


__all__ = ["ConsensusCall", "call_consensus", "call_consensus_with_metrics", "per_position_depth"]
