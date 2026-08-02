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

import os
import statistics
from dataclasses import dataclass
from typing import Sequence

import numpy as np

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

# ---------------------------------------------------------------------------
# Vectorized pileup internals
# ---------------------------------------------------------------------------
# The pileup keeps one column per possible vote token.  Column order is only a
# storage layout and never a tie-break rule: the scalar implementation resolved
# majority ties via ``max(counts.items())``, which returns the *first* key in
# ``dict`` insertion order, i.e. the token first incremented at that reference
# position.  The vectorized path reproduces that by recording, per (position,
# token), the index of the earliest alignment that voted it and breaking ties on
# the smallest such index.  Alignment index is the right granularity because a
# single alignment votes at most once per reference position (reference-consuming
# CIGAR ops never overlap), so no two tokens at one position can share an index.
_TOKENS = "ACGTN-"
_N_TOKENS = len(_TOKENS)
_TOK_N = 4
_TOK_DEL = 5

# ASCII -> token column, 255 for anything the scalar path dropped.  The scalar
# path upper-cased the base before the ``base in "ACGTN"`` membership test, so
# both cases map to the same column.
_BASE_LUT = np.full(256, 255, dtype=np.uint8)
for _i, _c in enumerate("ACGTN"):
    _BASE_LUT[ord(_c)] = _i
    _BASE_LUT[ord(_c.lower())] = _i

_CONSENSUS_CHARS = np.frombuffer(b"ACGTNN", dtype=np.uint8)

# Op-code lookup tables (sized past the highest BAM op so an out-of-range op
# code cannot index out of bounds; unknown ops consume nothing, matching the
# scalar path's defensive fall-through).
_MAX_OP = 16
_REF_CONSUMES = np.zeros(_MAX_OP, dtype=np.int64)
_QRY_CONSUMES = np.zeros(_MAX_OP, dtype=np.int64)
_IS_MATCH = np.zeros(_MAX_OP, dtype=bool)
_IS_DEL = np.zeros(_MAX_OP, dtype=bool)
for _op in (_CIGAR_M, _CIGAR_D, _CIGAR_N, _CIGAR_EQ, _CIGAR_X):
    _REF_CONSUMES[_op] = 1
for _op in (_CIGAR_M, _CIGAR_I, _CIGAR_S, _CIGAR_EQ, _CIGAR_X):
    _QRY_CONSUMES[_op] = 1
for _op in (_CIGAR_M, _CIGAR_EQ, _CIGAR_X):
    _IS_MATCH[_op] = True
for _op in (_CIGAR_D, _CIGAR_N):
    _IS_DEL[_op] = True

_BIG = np.int64(np.iinfo(np.int64).max)

# Query bases per vectorized batch.
#
# The pileup is linear in aligned bases in operation count, but flattening a
# whole well at once is not linear in *time*: every intermediate
# (``_expand_ranges`` output, the query/quality gather indices, the flat vote
# codes) is one int64 per aligned base, so a deep well builds hundreds of MB of
# transients that no longer fit any cache. Measured on a 1683 bp reference, the
# single-batch cost per aligned base rose from 47 ns at depth 50 to 90 ns at
# depth 3200 purely from that effect. Well count saturates at the plate size
# while run size keeps growing, so depth is exactly the axis that scales.
#
# Batching caps the working set instead. Batches are consecutive slices in read
# order, so the ``first_touch`` tie-break is preserved by a running minimum
# (see ``_accumulate_batch``) and every other accumulator is a plain sum.
#
# The value is set from whole-pipeline interleaved A/B, not from a microbenchmark.
# Consensus runs on a ThreadPool of ``cpu_count - 1`` inside each of three demux
# processes, and that oversubscription changes the answer: an isolated
# single-threaded replay of real wells prefers a budget near 32 Ki and reports a
# 3x win, while the same wells inside the pipeline regress at that budget. Tune
# this against ``scripts/perf_step2_harness.py``, never against a standalone loop.
#
# Measured, per-worker-summed ``well_consensus_wall``, interleaved so machine load
# hits both arms, with ``align_minimap2`` quoted as an untouched control:
#
#   scale                 unbatched   262144   ratio   control (align)
#   s2  488 MB, 306 rd/well  7.33 s   9.61 s   0.76x   63.2 -> 72.3 s
#   s3 2201 MB, 1724 rd/well 53.87 s  28.83 s  1.87x   270.8 -> 261.2 s
#   s3 second pair           56.34 s  29.50 s  1.91x   272.7 -> 280.6 s
#
# So this trades roughly 20 percent of the consensus phase at s2 (about 2 percent
# of a worker wall, inside pipeline run-to-run noise) for 1.9x at s3, and the gap
# widens with depth because well count saturates at the plate size while run size
# keeps growing. Peak RSS is the other half of the reason: at s3 the unbatched
# path peaked at 5901 MB across the process tree and 4325 MB in a single worker,
# against 2636 MB and 1511 MB batched. The real run is 5902 MB of FASTQ, larger
# than s3, so the unbatched transients are an out-of-memory hazard there.
#
# Raising the budget does not recover the s2 cost (524288 measured within 2
# percent of 262144 across three pairs), so the s2 side is inherent to splitting
# at all rather than a budget that is merely too small.
#
# PORTABILITY (measured 2026-08-02, same box). Asked whether this should be
# derived from CPU cache size the way the memory bounds in combinatorial_demux
# are now derived from RAM. It should NOT, and the reason is arithmetic rather
# than taste.
#
# At this budget each int64 intermediate is 262144 * 8 B = 2 MiB, and there are
# roughly five of them live at once (_expand_ranges output, the query and
# quality gather indices, the flat vote codes, the compress scratch), so one
# thread's working set is ~10 MiB. This box has 3 MiB of L2 per core and 20 MiB
# of L3 shared by ten of them, and consensus runs on a ThreadPool inside each of
# three worker processes. The chosen budget is therefore already far outside
# cache, by more than an order of magnitude, and moving it by a factor of two
# does not change which side of the cache boundary it sits on.
#
# The budget that WOULD be cache-resident is ~32768 query bases (1.25 MiB of
# intermediates, a comfortable fit in 3 MiB of L2). That value was measured, and
# it is the loser: 2.73x single-threaded but 0.89x at four threads (section 3 of
# notes/perf/consensus-depth.md), i.e. a cache-derived rule would reliably pick
# the configuration that is slower in the arrangement the pipeline actually
# runs. What moves the optimum is thread oversubscription, not cache size.
#
# Measured plateau on the reference fixture, five interleaved rounds per arm,
# phase seconds summed over the three workers (min of 5, then median of 5):
#
#   budget    compute_sum        well_consensus_wall
#    32768    4.176 / 4.262      3.239 / 3.371
#    65536    3.721 / 3.949      2.997 / 3.239
#   131072    3.410 / 3.844      2.931 / 3.249
#   262144    3.195 / 3.426      2.980 / 3.038
#   524288    3.300 / 3.623      2.926 / 3.135
#  1048576    2.916 / 3.355      2.700 / 3.005
#
# 32768 is off the plateau and losing, by 31 percent of `compute_sum` against
# 262144, exactly as the cache arithmetic above predicts. From 65536 upward the
# consensus wall spans 2.70 to 3.00 s min, under 10 percent across a 16x range
# of budgets, and non-monotone within it; that phase is about a fifth of a
# worker wall, so the whole span is ~2 percent of the run, which is pipeline
# run-to-run noise (`align_minimap2`, untouched by this constant, moved 8.35 to
# 9.22 s across the same arms).
#
# A plateau that wide is not worth a derivation: any box landing anywhere in it
# is within noise of the optimum, whereas a cache-derived rule would leave the
# plateau entirely and land on 32768. So this stays a fixed constant. The env
# override below is the escape hatch for the one input that could actually move
# the optimum, a machine whose consensus thread count is far from this one.
_BATCH_BASE_BUDGET = int(
    os.environ.get("KUMA_MAME_CONSENSUS_BASE_BUDGET", "").strip() or 262144
)


def _expand_ranges(starts: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Concatenate ``range(s, s + c)`` for every (start, count) pair."""
    total = int(counts.sum())
    if total == 0:
        return np.empty(0, dtype=np.int64)
    ends = np.cumsum(counts)
    offsets = ends - counts
    flat = np.arange(total, dtype=np.int64) - np.repeat(offsets, counts)
    return np.repeat(starts, counts) + flat


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
    # Net indel of the CONSENSUS relative to the reference, in bp:
    #   (bp of majority-supported insertion) - (deletion-majority ref positions)
    # Both terms are read off the same majority rule that produces the base
    # calls, so this is what the called molecule looks like, not what any single
    # read looks like. This is the value the FRAMESHIFT gate consumes.
    consensus_net_indel_bp: int = 0
    # Median over reads of (inserted bp - deleted bp) in that read CIGAR.
    # QUALITY METRIC ONLY, never a verdict input. ONT reads carry a high
    # per-read indel error rate in homopolymers, so on a real run the median can
    # sit at -1 while the consensus built from those same reads is indel-free.
    median_read_net_indel_bp: int = 0


def _reverse_complement(seq: str) -> str:
    """Return the reverse complement of a DNA sequence."""
    return seq.translate(_COMP)[::-1]


def _oriented_q_st(aln: Alignment) -> int:
    """Query start of *aln* in the orientation the CIGAR walks.

    ``Alignment.q_st``/``q_en`` are stored in the original (as-input) read
    orientation, matching mappy.  The consensus pileup walks the CIGAR over the
    reverse complement of ``read_seq`` when ``strand == -1``, and in that
    coordinate system the alignment starts at ``len(read_seq) - q_en``.

    The two agree only when the leading and trailing clips happen to be equal.
    They are usually equal here because reads reach consensus as
    ``read_seq[q_st - trim : q_en + trim]`` slices with a symmetric flank, but
    the slice is clamped at the read boundaries, so a read whose alignment ends
    within ``trim_flank_bp`` of its end yields an asymmetric clip and, under the
    old convention, shifted the whole read by the difference.
    """
    if aln.strand == -1:
        return len(aln.read_seq) - aln.q_en
    return aln.q_st


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
    ``min_depth``. ``consensus_n_fraction`` is the no-call rate **within the
    covered amplicon**: numerator and denominator both range over positions whose
    pileup depth reaches ``min_depth``, so it captures deletion majority,
    ambiguous ties, and raw N votes while ignoring reference positions the reads
    never interrogate. ``n_low_quality_bases`` counts FASTQ bases excluded by
    ``min_base_quality``.
    """
    ref_len = len(reference_seq)

    (
        counts,
        first_touch,
        insertion_events,
        insertion_bp,
        n_low_quality_bases,
        per_read_net_indel,
    ) = _accumulate_all(alignments, ref_len, min_base_quality)

    # --- per-position majority vote (vectorized) ---------------------------
    total = counts.sum(axis=1)
    covered = total >= min_depth
    n_low_depth_positions = int(ref_len - int(covered.sum()))
    n_covered_positions = int(covered.sum())

    # Mixed-position evidence: second-most-common A/C/G/T base.  ``base_counts``
    # in the scalar path only held tokens with a nonzero count, so requiring
    # >= 2 distinct nonzero bases makes "second largest including zeros" and
    # "second largest among present" the same value.
    acgt = counts[:, :4]
    base_total = acgt.sum(axis=1)
    n_distinct_bases = (acgt > 0).sum(axis=1)
    mix_eligible = covered & (base_total >= mix_min_depth) & (n_distinct_bases >= 2)
    n_mixed_positions = 0
    max_minor_allele_fraction = 0.0
    if bool(mix_eligible.any()):
        second = np.sort(acgt[mix_eligible], axis=1)[:, -2]
        minor_fraction = second / base_total[mix_eligible]
        max_minor_allele_fraction = float(minor_fraction.max())
        n_mixed_positions = int(
            (minor_fraction >= mix_minor_fraction_threshold).sum()
        )

    # Majority token.  Ties resolve to the token first seen at that position,
    # matching ``max(dict.items(), key=count)`` over an insertion-ordered dict.
    best_count = counts.max(axis=1) if ref_len else np.zeros(0, dtype=np.int64)
    tie_key = np.where(counts == best_count[:, None], first_touch, _BIG)
    best_idx = tie_key.argmin(axis=1)

    with np.errstate(invalid="ignore", divide="ignore"):
        majority_frac = np.where(total > 0, best_count / np.maximum(total, 1), 0.0)
    # A covered position with zero depth is only reachable for min_depth <= 0,
    # where the scalar path raised on an empty dict; call it 'N'.
    no_call = (
        (best_idx == _TOK_DEL) | (majority_frac < 0.5) | (best_idx == _TOK_N)
    ) | (total == 0)
    n_covered_no_call = int((covered & no_call).sum())

    out_chars = np.where(
        covered & ~no_call, _CONSENSUS_CHARS[best_idx], np.uint8(ord("N"))
    ).astype(np.uint8)
    consensus_seq = out_chars.tobytes().decode("ascii")
    # Amplicon-scoped no-call rate. The denominator is the set of positions the
    # reads actually interrogate at usable depth, NOT the full reference length.
    # A reference longer than the amplicon (a plasmid map carrying backbone/UTR,
    # which translate/aa_translator.py explicitly supports) is all-N outside the
    # amplicon by construction; dividing by ref_len made that structural gap look
    # like a quality failure and drove every well to NO_CALL. Ragged read ends are
    # excluded on the same grounds: they are a coverage shortfall, already reported
    # via n_low_depth_positions, not a consensus-ambiguity signal.
    # No position reached usable depth: nothing was callable, so the well is
    # fully no-call (1.0), not vacuously clean (0.0). Matches the zero-read
    # ConsensusResult in ingest/well_consensus.py.
    if n_covered_positions > 0:
        consensus_n_fraction = n_covered_no_call / n_covered_positions
    else:
        consensus_n_fraction = 1.0 if ref_len > 0 else 0.0
    median_read_net_indel_bp = (
        round(statistics.median(per_read_net_indel))
        if per_read_net_indel
        else 0
    )

    # Aggregate indel event signal.
    # Deletion fraction: deletion votes / (base votes + deletion votes) per pos.
    # Insertion fraction: insertion events / base depth at anchor pos.
    # max_indel_event_fraction = max across all positions of either fraction.
    #
    # Spanning depth: reads that covered this position (base votes + del votes).
    # Inserting reads always vote a base at the anchor M op before the I op, so
    # they are already counted. Using total depth as the denominator guarantees
    # ins_frac <= 1.0 whenever ins_ev <= depth (true by construction). del_frac
    # uses the same denominator; del_votes is a subset of depth so it is <= 1.0.
    del_votes = counts[:, _TOK_DEL]
    safe_depth = np.maximum(total, 1)
    ins_frac = np.where(total > 0, insertion_events / safe_depth, 0.0)
    del_frac = np.where(total > 0, del_votes / safe_depth, 0.0)
    pos_max = np.maximum(ins_frac, del_frac)
    max_indel_event_fraction = float(pos_max.max()) if ref_len else 0.0
    n_indel_event_positions = int((pos_max >= 0.05).sum())

    # Longest contiguous run of deletion-majority positions (del_frac > 0.5).
    # Same 0.5 majority definition used for base calls.
    del_major = del_frac > 0.5
    max_del_run = 0
    if bool(del_major.any()):
        edges = np.flatnonzero(
            np.concatenate(([True], del_major[1:] != del_major[:-1], [True]))
        )
        run_lengths = np.diff(edges)
        max_del_run = int(run_lengths[del_major[edges[:-1]]].max())

    # Net indel of the CONSENSUS, from the same majority rule that calls bases.
    #
    # Deleted bp: every reference position whose deletion fraction wins the
    # majority is absent from the called molecule; the gap-free consensus writes
    # 'N' there, so the length stays at ref_len and the bp count has to be read
    # off ``del_major`` rather than off ``len(consensus_seq)``.
    #
    # Inserted bp: an insertion anchored at a position carried by a majority of
    # the spanning reads is part of the called molecule even though the
    # reference-length consensus drops it. ``insertion_bp / insertion_events``
    # is the mean inserted length among the reads that inserted there, which is
    # exactly the inserted length when they agree (the ordinary case) and a
    # rounded consensus of the lengths when they do not.
    #
    # NOT the per-read median. On ONT data the median per-read net indel tracks
    # the homopolymer error rate of individual reads, and averaging those errors
    # away is the whole purpose of building a consensus: a well whose reads are
    # mostly -1 bp but whose consensus aligns to the reference gap-free has a
    # consensus net indel of 0 and is not a frameshift.
    n_del_majority = int(del_major.sum())
    ins_major = ins_frac > 0.5
    inserted_bp = 0
    if bool(ins_major.any()):
        ev = insertion_events[ins_major]
        bp = insertion_bp[ins_major]
        inserted_bp = int(np.rint(bp / np.maximum(ev, 1)).sum())
    consensus_net_indel_bp = inserted_bp - n_del_majority

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
        consensus_net_indel_bp=consensus_net_indel_bp,
        median_read_net_indel_bp=median_read_net_indel_bp,
    )


def _accumulate_all(
    alignments: Sequence[Alignment],
    ref_len: int,
    min_base_quality: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int, list[int]]:
    """Build the whole-well pileup from every alignment.

    Returns ``(counts, first_touch, insertion_events, insertion_bp,
    n_low_quality_bases, per_read_net_indel)``.  ``insertion_bp[ref_pos]`` is the
    total inserted length summed over the reads counted in
    ``insertion_events[ref_pos]``, so their ratio is the mean inserted length at
    that anchor.  ``counts`` and ``first_touch`` are ``(ref_len, 6)``
    int64 arrays over the ``_TOKENS`` columns; ``first_touch`` holds the index
    of the earliest alignment that voted each (position, token) pair and exists
    solely to reproduce the scalar dict-insertion-order tie-break.

    Alignments are flattened into vectorized batches (one concatenated CIGAR
    table, one concatenated query buffer per batch) so the cost is a fixed
    handful of array operations per batch instead of per read.  Batches are
    capped at ``_BATCH_BASE_BUDGET`` query bases; see that constant for why the
    whole well is not flattened at once.
    """
    n_reads = len(alignments)
    counts = np.zeros((ref_len, _N_TOKENS), dtype=np.int64)
    first_touch = np.full((ref_len, _N_TOKENS), _BIG, dtype=np.int64)
    insertion_events = np.zeros(ref_len, dtype=np.int64)
    insertion_bp = np.zeros(ref_len, dtype=np.int64)
    if n_reads == 0 or ref_len == 0:
        return (
            counts,
            first_touch,
            insertion_events,
            insertion_bp,
            0,
            [0] * n_reads,
        )

    n_low_quality_bases = 0
    per_read_net_indel: list[int] = []
    # Scratch reused across batches so the merge below allocates nothing.
    batch_first = np.empty((ref_len, _N_TOKENS), dtype=np.int64)
    for lo_read, hi_read in _batch_bounds(alignments):
        n_low_quality_bases += _accumulate_batch(
            alignments,
            lo_read,
            hi_read,
            ref_len,
            min_base_quality,
            counts,
            first_touch,
            batch_first,
            insertion_events,
            insertion_bp,
            per_read_net_indel,
        )

    return (
        counts,
        first_touch,
        insertion_events,
        insertion_bp,
        n_low_quality_bases,
        per_read_net_indel,
    )


def _batch_bounds(alignments: Sequence[Alignment]) -> list[tuple[int, int]]:
    """Split ``alignments`` into consecutive read ranges of bounded query size.

    Ranges are consecutive and in read order, which is what keeps the
    ``first_touch`` tie-break well defined: every read in batch *k* has a larger
    alignment index than every read in batch *k-1*, so merging batch results
    with a running minimum reproduces the single-batch answer exactly.
    """
    bounds: list[tuple[int, int]] = []
    lo = 0
    acc = 0
    for i, aln in enumerate(alignments):
        acc += len(aln.read_seq)
        if acc >= _BATCH_BASE_BUDGET:
            bounds.append((lo, i + 1))
            lo = i + 1
            acc = 0
    if lo < len(alignments):
        bounds.append((lo, len(alignments)))
    return bounds


def _accumulate_batch(
    alignments: Sequence[Alignment],
    lo_read: int,
    hi_read: int,
    ref_len: int,
    min_base_quality: int,
    counts: np.ndarray,
    first_touch: np.ndarray,
    batch_first: np.ndarray,
    insertion_events: np.ndarray,
    insertion_bp: np.ndarray,
    per_read_net_indel: list[int],
) -> int:
    """Fold ``alignments[lo_read:hi_read]`` into the running well accumulators.

    ``counts``, ``first_touch``, ``insertion_events``, ``insertion_bp`` and
    ``per_read_net_indel`` are updated in place; the low-quality base count for
    this batch is returned.
    ``batch_first`` is caller-owned scratch of the same shape as ``first_touch``.
    """
    batch = alignments[lo_read:hi_read]
    n_reads = len(batch)

    # --- flatten reads -----------------------------------------------------
    seq_parts: list[bytes] = []
    qual_parts: list[bytes] = []
    cigar_pairs: list[list[int]] = []
    n_ops = np.empty(n_reads, dtype=np.int64)
    seq_len = np.empty(n_reads, dtype=np.int64)
    qual_len = np.zeros(n_reads, dtype=np.int64)
    r_st = np.empty(n_reads, dtype=np.int64)
    q_st = np.empty(n_reads, dtype=np.int64)
    any_qual = False

    for i, aln in enumerate(batch):
        if aln.strand == -1:
            q_seq = _reverse_complement(aln.read_seq)
            q_qual = aln.read_qual[::-1] if aln.read_qual is not None else None
        else:
            q_seq = aln.read_seq
            q_qual = aln.read_qual
        # "replace" keeps the mapping one byte per character, so query offsets
        # stay aligned; the replacement byte is not in _BASE_LUT and is dropped
        # exactly like the scalar `base in "ACGTN"` test dropped it.
        enc = q_seq.encode("ascii", "replace")
        seq_parts.append(enc)
        seq_len[i] = len(enc)
        if q_qual is not None:
            any_qual = True
            qenc = q_qual.encode("ascii", "replace")
            qual_parts.append(qenc)
            qual_len[i] = len(qenc)
        else:
            qual_parts.append(b"")
        cigar_pairs.extend(aln.cigar)
        n_ops[i] = len(aln.cigar)
        r_st[i] = aln.r_st
        q_st[i] = _oriented_q_st(aln)

    seq_arr = np.frombuffer(b"".join(seq_parts), dtype=np.uint8)
    seq_off = np.concatenate(([0], np.cumsum(seq_len)[:-1]))
    qual_arr = np.frombuffer(b"".join(qual_parts), dtype=np.uint8)
    qual_off = np.concatenate(([0], np.cumsum(qual_len)[:-1]))

    n_total_ops = int(n_ops.sum())
    if n_total_ops == 0:
        per_read_net_indel.extend([0] * n_reads)
        return 0

    cigar = np.array(cigar_pairs, dtype=np.int64).reshape(-1, 2)
    lengths = cigar[:, 0]
    raw_ops = cigar[:, 1]
    # Fold anything outside the BAM op range onto a spare no-op slot, matching
    # the scalar path's "unknown op consumes nothing" fall-through.
    ops = np.where((raw_ops >= 0) & (raw_ops < _MAX_OP), raw_ops, _MAX_OP - 1)
    op_read = np.repeat(np.arange(n_reads, dtype=np.int64), n_ops)

    # --- per-read CIGAR cursors, computed as one segmented cumulative sum ---
    ref_step = _REF_CONSUMES[ops] * lengths
    qry_step = _QRY_CONSUMES[ops] * lengths
    ref_excl = np.cumsum(ref_step) - ref_step
    qry_excl = np.cumsum(qry_step) - qry_step
    # Index of each read's first op; reads with no ops never index through it.
    op_base = np.concatenate(([0], np.cumsum(n_ops)[:-1]))
    op_base = np.minimum(op_base, n_total_ops - 1)
    ref_starts = r_st[op_read] + (ref_excl - ref_excl[op_base][op_read])
    qry_starts = q_st[op_read] + (qry_excl - qry_excl[op_base][op_read])

    is_match = _IS_MATCH[ops]
    is_del = _IS_DEL[ops]
    is_ins = ops == _CIGAR_I

    signed_indel = np.where(is_ins, lengths, 0) - np.where(is_del, lengths, 0)
    net = np.bincount(
        op_read, weights=signed_indel.astype(np.float64), minlength=n_reads
    )
    per_read_net_indel.extend(int(v) for v in net)

    n_low_quality_bases = 0
    flat_match = np.empty(0, dtype=np.int64)
    read_match = np.empty(0, dtype=np.int64)
    flat_del = np.empty(0, dtype=np.int64)
    read_del = np.empty(0, dtype=np.int64)

    # --- aligned bases -----------------------------------------------------
    if is_match.any():
        rp0 = ref_starts[is_match]
        qp0 = qry_starts[is_match]
        rd = op_read[is_match]
        n = lengths[is_match]
        # The scalar guard was `0 <= rp < ref_len and qp < len(q_seq)`.  Both
        # bounds are monotone in the op offset, so the surviving offsets form
        # one contiguous slice per op.
        lo = np.maximum(0, -rp0)
        hi = np.minimum(n, np.minimum(ref_len - rp0, seq_len[rd] - qp0))
        cnt = np.maximum(0, hi - lo)
        rp = _expand_ranges(rp0 + lo, cnt)
        qp = _expand_ranges(qp0 + lo, cnt)
        ridx = np.repeat(rd, cnt)
        if rp.size:
            keep = np.ones(rp.size, dtype=bool)
            if any_qual:
                # _phred33 returns None past the end of the quality string, and
                # the scalar path kept those bases unfiltered.
                scored = qp < qual_len[ridx]
                if scored.any():
                    where_scored = np.flatnonzero(scored)
                    idx = qual_off[ridx[where_scored]] + qp[where_scored]
                    scores = (qual_arr[idx].astype(np.int32) - 33).clip(min=0)
                    low = scores < min_base_quality
                    n_low_quality_bases = int(low.sum())
                    keep[where_scored[low]] = False
            codes = _BASE_LUT[seq_arr[seq_off[ridx] + qp]]
            keep &= codes != 255
            flat_match = rp[keep] * _N_TOKENS + codes[keep]
            read_match = ridx[keep]

    # --- deletions / reference skips ---------------------------------------
    if is_del.any():
        rp0 = ref_starts[is_del]
        rd = op_read[is_del]
        n = lengths[is_del]
        lo = np.maximum(0, -rp0)
        hi = np.minimum(n, ref_len - rp0)
        cnt = np.maximum(0, hi - lo)
        rp = _expand_ranges(rp0 + lo, cnt)
        if rp.size:
            flat_del = rp * _N_TOKENS + _TOK_DEL
            read_del = np.repeat(rd, cnt)

    # --- insertion anchors --------------------------------------------------
    if is_ins.any():
        anchors = ref_starts[is_ins] - 1
        ins_len = lengths[is_ins]
        in_range = (anchors >= 0) & (anchors < ref_len)
        anchors = anchors[in_range]
        ins_len = ins_len[in_range]
        if anchors.size:
            insertion_events += np.bincount(anchors, minlength=ref_len).astype(
                np.int64
            )
            # Same anchors, weighted by inserted length, so the two arrays stay
            # element-wise comparable and their ratio is a mean over exactly the
            # reads counted in ``insertion_events``.
            insertion_bp += np.bincount(
                anchors, weights=ins_len.astype(np.float64), minlength=ref_len
            ).astype(np.int64)

    if flat_match.size or flat_del.size:
        allflat = np.concatenate((flat_match, flat_del))
        flat_counts = counts.reshape(-1)
        flat_counts += np.bincount(allflat, minlength=ref_len * _N_TOKENS).astype(
            np.int64
        )
        # Base votes and deletion votes land in disjoint columns, so the two
        # writes below never collide and each can be done independently.  Both
        # index arrays are ordered by alignment, and duplicate fancy-index
        # writes keep the last assignment, so writing in reverse leaves the
        # smallest alignment index (the first-touch) in place.
        #
        # Writes land in per-batch scratch and are folded into the running
        # ``first_touch`` with a minimum.  Batches are consecutive slices in read
        # order, so an earlier batch always holds the smaller alignment index and
        # the minimum picks the same winner a single flattened batch would.
        batch_first.fill(_BIG)
        flat_first = batch_first.reshape(-1)
        if flat_match.size:
            flat_first[flat_match[::-1]] = read_match[::-1] + lo_read
        if flat_del.size:
            flat_first[flat_del[::-1]] = read_del[::-1] + lo_read
        np.minimum(first_touch, batch_first, out=first_touch)

    return n_low_quality_bases


def _phred33(qual: str, idx: int) -> int | None:
    if idx < 0 or idx >= len(qual):
        return None
    return max(0, ord(qual[idx]) - 33)


def _accumulate(
    aln: Alignment,
    per_position: list[dict[str, int]],
    insertion_events: list[int],
    min_base_quality: int,
) -> tuple[int, int]:
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
    q_pos = _oriented_q_st(aln)
    ref_len = len(per_position)
    n_low_quality_bases = 0
    net_indel = 0

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
            net_indel -= length
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
            net_indel += length
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

    return n_low_quality_bases, net_indel


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
