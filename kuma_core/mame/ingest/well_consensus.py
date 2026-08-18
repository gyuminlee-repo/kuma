"""A6 — Per-well consensus orchestration.

Coordinates the align → filter → consensus pipeline for all wells produced
by the demux step.  The output is a dictionary mapping well name to a
:class:`ConsensusResult`, which carries the consensus sequence and alignment
statistics.

Typical call sequence
---------------------
1. ``demux_native_barcode`` produces per-well raw-read (id, seq) lists.
2. ``compute_well_consensuses`` is called with those lists + a reference FASTA.
3. The caller writes single-record FASTA files using the consensus sequences.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

from kuma_core.mame.ingest.align import Alignment, align_reads_with_stats
from kuma_core.mame.reference_fasta import multi_record_reason
from kuma_core.mame.ingest.consensus import (
    DEFAULT_MIX_MIN_DEPTH,
    call_consensus_with_metrics,
    per_position_depth,
)
from kuma_core.mame.models import NoisyPosition


@dataclass
class ConsensusResult:
    """Per-well consensus calling statistics and output sequence.

    Attributes
    ----------
    consensus_seq:
        Consensus nucleotide string (length == reference length).
        'N' at positions with insufficient depth or no clear majority.
    n_input_reads:
        Total reads for this well entering the alignment step.
    n_aligned:
        Reads that had at least one alignment hit (before MAPQ / span filter).
    n_passed_filter:
        Reads that passed MAPQ ≥ 25 and full-span filter.
    mean_depth:
        Mean per-position read depth across the reference, computed from
        passing alignments.  0.0 when n_passed_filter == 0.
    n_mixed_positions:
        Number of positions with a second A/C/G/T base above the configured
        minor-allele fraction threshold.
    max_minor_allele_fraction:
        Largest second-base fraction observed across positions.
    n_low_depth_positions:
        Number of reference positions whose pileup depth is below ``min_depth``.
    consensus_n_fraction:
        Fraction of consensus positions emitted as ``N``.
    n_low_quality_bases:
        Number of FASTQ bases excluded from pileup voting by the base-quality
        gate. Zero for legacy FASTA-only inputs.
    consensus_net_indel_bp:
        Net indel of the consensus itself relative to the reference (inserted bp
        accepted by majority, minus deletion-majority reference positions).
        Non-zero modulo 3 marks a frameshift. 0 for wells with no passing reads.
    median_read_net_indel_bp:
        Median per-read net indel length (insertions minus deletions) over the
        whole aligned span. Read-quality evidence only; on ONT data it tracks the
        per-read homopolymer error rate and is not a frameshift signal.
    max_minor_allele_strand_share:
        Weak-strand share of the minor allele at the position behind
        ``max_minor_allele_fraction``. ``None`` is unknown (no mix-eligible
        position, including every well that had no passing read); 0.0 is a real
        one-strand measurement. See ConsensusCall for why the two never merge.
    max_minor_allele_plus_count, max_minor_allele_minus_count:
        The counts that share divides. 0 when the share is unknown.
    n_eligible_positions:
        Mix-eligible positions this well had, i.e. the pool ``noisy_positions``
        samples. Its own truncation signal.
    noisy_positions:
        Top-K of that pool by minor fraction. Empty for wells with no eligible
        position.
    depth_cv, depth_p10, depth_min_covered, breadth_at_mix_min_depth:
        Coverage-uniformity evidence. ``mean_depth`` alone cannot separate a
        well covered evenly at 100x from one averaging 100x with a 200 bp hole,
        and the two are not the same evidence for the same consensus. See
        ``depth_stats`` for each definition and for why ``None`` is not 0.0.
    consensus_identity:
        Fraction of called consensus bases matching the reference. See
        ``consensus_identity``.

    The five coverage and identity fields are REPORTED ONLY. No verdict, gate
    or severity rule reads them; they exist so an operator can see WHY a well
    scored the way it did, and adding a threshold on them would be a new
    classification rule rather than a new report.
    """

    consensus_seq: str
    n_input_reads: int
    n_aligned: int
    n_passed_filter: int
    mean_depth: float
    n_unaligned: int = 0
    n_mapq_failed: int = 0
    n_span_failed: int = 0
    n_mixed_positions: int = 0
    max_minor_allele_fraction: float = 0.0
    n_low_depth_positions: int = 0
    consensus_n_fraction: float = 0.0
    n_low_quality_bases: int = 0
    n_indel_event_positions: int = 0
    max_indel_event_fraction: float = 0.0
    max_del_run_length: int = 0
    consensus_net_indel_bp: int = 0
    median_read_net_indel_bp: int = 0
    max_minor_allele_strand_share: float | None = None
    max_minor_allele_plus_count: int = 0
    max_minor_allele_minus_count: int = 0
    n_eligible_positions: int = 0
    noisy_positions: tuple[NoisyPosition, ...] = ()
    # Coverage uniformity and consensus identity. All five are report-only and
    # all five default to ``None`` meaning NOT MEASURED, never 0.0. A CV of 0.0
    # is a perfectly flat well and an identity of 0.0 is a consensus that
    # matches the reference nowhere; both are strong statements that an unmeasured
    # well has no right to make. Same rule as ``min_variant_support`` above.
    depth_cv: float | None = None
    depth_p10: float | None = None
    depth_min_covered: int | None = None
    breadth_at_mix_min_depth: float | None = None
    consensus_identity: float | None = None
    alignments: list[Alignment] = field(default_factory=list, repr=False)


def depth_stats(
    depths: Sequence[int],
    mix_min_depth: int = DEFAULT_MIX_MIN_DEPTH,
) -> tuple[float | None, float | None, int | None, float | None]:
    """Coverage-uniformity evidence from a per-position depth vector.

    Returns ``(depth_cv, depth_p10, depth_min_covered, breadth_at_mix_min_depth)``.

    ``depths`` is the vector ``per_position_depth`` returns, one entry per
    reference position, counting reads whose CIGAR puts an aligned base there
    (M/=/X only).  A read that spans a position through a D operation does NOT
    count here, which is deliberate and is the difference from the pileup
    ``covered`` mask inside ``call_consensus_with_metrics``: that mask counts
    deletion votes as coverage because a deletion is evidence about the base,
    while this asks how many reads actually read the position.  Using the same
    vector as ``mean_depth`` is what makes these numbers comparable to it;
    mixing the two definitions inside one result object would not be.

    A position is COVERED when its depth is > 0.

    depth_cv:
        Population standard deviation over mean of the covered depths, i.e. the
        spread of coverage relative to its own level, so a shallow-but-even well
        and a deep-but-even well both score near 0.  This is the number
        ``mean_depth`` cannot express: 100x flat and 100x with a 200 bp hole are
        the same mean and not the same evidence.  ``None`` when nothing is
        covered.  A single covered position yields 0.0, which is a true
        statement about a one-position sample rather than a missing value, so
        the population deviation is used instead of the sample one (the latter
        is undefined at n=1).  The mean of a non-empty covered set is at least
        1, so a zero denominator cannot arise.
    depth_p10:
        10th percentile of the covered depths (linear interpolation, numpy
        default).  Answers what the thin tenth of the amplicon looks like,
        which a mean hides and a minimum reduces to a single position.  ``None``
        when nothing is covered.
    depth_min_covered:
        Shallowest covered position.  Never 0 by construction; ``None`` when
        nothing is covered.  Reference positions with no reads at all are
        counted by ``breadth`` below, not here, because a minimum of 0 would
        collapse "thin somewhere" and "absent somewhere" into one number.
    breadth_at_mix_min_depth:
        Fraction of the WHOLE reference (denominator ``len(depths)``, not the
        covered subset) at depth >= ``mix_min_depth``, the depth at which this
        pipeline is willing to read a minor allele.  This is the field that
        exposes the hole: the well with a 200 bp gap scores below 1.0 while the
        even well scores 1.0, at identical ``mean_depth``.  ``None`` only when
        the reference is empty; a well with zero reads measures a real 0.0.

    None of the four is a gate.  No verdict, severity or threshold reads them,
    and turning any into one would be a new classification rule.
    """
    ref_len = len(depths)
    if ref_len == 0:
        return None, None, None, None

    arr = np.asarray(depths, dtype=np.int64)
    breadth = float((arr >= mix_min_depth).sum() / ref_len)

    covered = arr[arr > 0]
    if covered.size == 0:
        return None, None, None, breadth

    mean = float(covered.mean())
    cv = float(np.std(covered) / mean)
    p10 = float(np.percentile(covered, 10))
    min_covered = int(covered.min())
    return cv, p10, min_covered, breadth


def consensus_identity(consensus_seq: str, reference_seq: str) -> float | None:
    """Fraction of CALLED consensus bases that match the reference.

    Denominator is the positions the consensus actually calls, i.e. those whose
    character is not ``N``.  Every uncovered or ambiguous position is already an
    ``N`` by construction (see ``call_consensus``), so "called" and "covered and
    unambiguous" are the same set and no separate depth mask is needed.

    ``None`` means the denominator was empty: the well called nothing, so its
    identity is UNKNOWN.  0.0 is the opposite and much stronger statement, that
    bases were called and none of them matched, which is what a wrong reference
    or a swapped well looks like.  The two must never be conflated; same rule as
    ``min_variant_support``.

    Comparison stops at the shorter of the two sequences.  They are equal length
    on every path here (the consensus is emitted at reference length), and the
    guard exists so a caller that pairs a consensus with the wrong reference gets
    a low identity rather than an IndexError.

    REPORTED ONLY.  A designed variant well is SUPPOSED to differ from the
    reference, so a low identity is not by itself a defect and no gate reads
    this field.  What it is for is the opposite direction: an identity far below
    what the intended mutation count explains says the well is not the clone it
    claims to be.
    """
    n = min(len(consensus_seq), len(reference_seq))
    if n == 0:
        return None

    cons = np.frombuffer(consensus_seq[:n].upper().encode("ascii"), dtype=np.uint8)
    ref = np.frombuffer(reference_seq[:n].upper().encode("ascii"), dtype=np.uint8)
    called = cons != ord("N")
    n_called = int(called.sum())
    if n_called == 0:
        return None
    return float((cons[called] == ref[called]).sum() / n_called)


def compute_well_consensuses(
    per_well_reads: dict[str, list[tuple[str, ...]]],
    reference_fasta: Path,
    min_mapq: int = 25,
    require_full_span: bool = True,
    min_depth: int = 1,
) -> dict[str, ConsensusResult]:
    """Compute consensus sequences for all wells.

    Parameters
    ----------
    per_well_reads:
        Mapping from well name to a list of ``(read_id, sequence)`` pairs.
        Produced by the demux step (pure Python or cutadapt backend).
    reference_fasta:
        Path to the reference FASTA used for alignment.  Must contain exactly
        one sequence record.
    min_mapq:
        MAPQ threshold for the alignment filter (default 25).
    require_full_span:
        When True, only reads whose alignment spans the full reference are
        counted.  Equivalent to bedtools intersect -f 1.0.
    min_depth:
        Minimum per-position depth for a base call (default 1).

    Returns
    -------
    Dictionary mapping well name to :class:`ConsensusResult`.  Wells with
    zero passing reads receive a consensus of all 'N' characters.
    """
    if not reference_fasta.exists():
        raise FileNotFoundError(f"Reference FASTA not found: {reference_fasta}")

    # Read reference sequence once for depth/consensus calls.
    ref_seq = _read_reference_seq(reference_fasta)
    ref_len = len(ref_seq)

    results: dict[str, ConsensusResult] = {}

    for well, reads in per_well_reads.items():
        n_input = len(reads)

        if n_input == 0:
            results[well] = ConsensusResult(
                consensus_seq="N" * ref_len,
                n_input_reads=0,
                n_aligned=0,
                n_passed_filter=0,
                mean_depth=0.0,
                n_low_depth_positions=ref_len,
                consensus_n_fraction=1.0 if ref_len > 0 else 0.0,
                # A well with no reads covers nothing, so breadth is a real
                # measurement of 0.0. The other three stay ``None``: there is no
                # covered position to spread, and no called base to compare.
                breadth_at_mix_min_depth=0.0 if ref_len > 0 else None,
            )
            continue

        alignments, aln_stats = align_reads_with_stats(
            reads=reads,
            reference_fasta=reference_fasta,
            preset="map-ont",
            min_mapq=min_mapq,
            require_full_span=require_full_span,
        )

        n_passed = len(alignments)

        if n_passed == 0:
            results[well] = ConsensusResult(
                consensus_seq="N" * ref_len,
                n_input_reads=n_input,
                n_aligned=aln_stats.n_primary_alignments,
                n_passed_filter=0,
                mean_depth=0.0,
                n_unaligned=aln_stats.n_unaligned,
                n_mapq_failed=aln_stats.n_failed_mapq,
                n_span_failed=aln_stats.n_failed_span,
                n_low_depth_positions=ref_len,
                consensus_n_fraction=1.0 if ref_len > 0 else 0.0,
                # No read survived the filter, so nothing is covered: same
                # reasoning as the zero-read branch above.
                breadth_at_mix_min_depth=0.0 if ref_len > 0 else None,
                alignments=[],
            )
            continue

        # Compute per-position depth for mean_depth statistic.
        depths = per_position_depth(alignments, ref_len)
        mean_d = statistics.mean(depths) if depths else 0.0
        # Uniformity read off the SAME depth vector as mean_depth, so the two
        # are comparable. See depth_stats.
        depth_cv, depth_p10, depth_min_covered, breadth = depth_stats(depths)

        consensus_call = call_consensus_with_metrics(
            alignments,
            ref_seq,
            min_depth=min_depth,
        )

        results[well] = ConsensusResult(
            consensus_seq=consensus_call.consensus_seq,
            n_input_reads=n_input,
            n_aligned=aln_stats.n_primary_alignments,
            n_passed_filter=n_passed,
            mean_depth=mean_d,
            n_unaligned=aln_stats.n_unaligned,
            n_mapq_failed=aln_stats.n_failed_mapq,
            n_span_failed=aln_stats.n_failed_span,
            n_mixed_positions=consensus_call.n_mixed_positions,
            max_minor_allele_fraction=consensus_call.max_minor_allele_fraction,
            n_low_depth_positions=consensus_call.n_low_depth_positions,
            consensus_n_fraction=consensus_call.consensus_n_fraction,
            n_low_quality_bases=consensus_call.n_low_quality_bases,
            n_indel_event_positions=consensus_call.n_indel_event_positions,
            max_indel_event_fraction=consensus_call.max_indel_event_fraction,
            max_del_run_length=consensus_call.max_del_run_length,
            consensus_net_indel_bp=consensus_call.consensus_net_indel_bp,
            median_read_net_indel_bp=consensus_call.median_read_net_indel_bp,
            max_minor_allele_strand_share=(
                consensus_call.max_minor_allele_strand_share
            ),
            max_minor_allele_plus_count=consensus_call.max_minor_allele_plus_count,
            max_minor_allele_minus_count=(
                consensus_call.max_minor_allele_minus_count
            ),
            n_eligible_positions=consensus_call.n_eligible_positions,
            # Handed straight over. ``NoisyPosition`` is declared once, in
            # ``models``, so the engine already produced the transfer-object
            # type; this used to re-box the five numbers into a same-named
            # mirror class. The records are frozen, so sharing them is safe.
            noisy_positions=consensus_call.noisy_positions,
            depth_cv=depth_cv,
            depth_p10=depth_p10,
            depth_min_covered=depth_min_covered,
            breadth_at_mix_min_depth=breadth,
            consensus_identity=consensus_identity(
                consensus_call.consensus_seq, ref_seq
            ),
            alignments=alignments,
        )

    return results


def _read_reference_seq(reference_fasta: Path) -> str:
    """Read and return the single sequence in a FASTA file.

    This is the reader ``compute_well_consensuses`` calls for every well in a
    run, and ``combinatorial_demux`` calls it too, so it is the reader on the
    raw-MinKNOW-run-folder path -- the primary user-facing input. It used to
    stop after the first record silently, which meant a plasmid-backbone-plus-
    target reference lost the second sequence with no sign anything had been
    dropped rather than every well being graded against a chimera; that is a
    smaller wrong than the one ``reference_fasta.multi_record_reason`` guards
    against elsewhere, but it is still silent, so the same refusal applies
    here.
    """
    lines = reference_fasta.read_text(encoding="utf-8").splitlines()
    reason = multi_record_reason(lines)
    if reason is not None:
        raise ValueError(f"{reason}: {reference_fasta}")
    seq_parts: list[str] = []
    for line in lines:
        line = line.rstrip("\r\n")
        if line.startswith(">"):
            continue
        seq_parts.append(line.strip())
    seq = "".join(seq_parts).upper()
    if not seq:
        raise ValueError(f"Reference FASTA contains no sequence data: {reference_fasta}")
    return seq


# ``depth_stats`` and ``consensus_identity`` are exported because the raw
# MinKNOW run path (``combinatorial_demux``) computes the same five report-only
# numbers and must compute them from the same definitions. Two copies of these
# formulas would be two metrics wearing one name.
__all__ = [
    "ConsensusResult",
    "compute_well_consensuses",
    "consensus_identity",
    "depth_stats",
]
