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

from kuma_core.mame.ingest.align import Alignment, align_reads_with_stats
from kuma_core.mame.ingest.consensus import call_consensus_with_metrics, per_position_depth
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
    alignments: list[Alignment] = field(default_factory=list, repr=False)


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
                alignments=[],
            )
            continue

        # Compute per-position depth for mean_depth statistic.
        depths = per_position_depth(alignments, ref_len)
        mean_d = statistics.mean(depths) if depths else 0.0

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
            alignments=alignments,
        )

    return results


def _read_reference_seq(reference_fasta: Path) -> str:
    """Read and return the first sequence from a FASTA file."""
    seq_parts: list[str] = []
    in_seq = False
    with reference_fasta.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if line.startswith(">"):
                if in_seq:
                    break  # stop after first record
                in_seq = True
            elif in_seq:
                seq_parts.append(line.strip())
    seq = "".join(seq_parts).upper()
    if not seq:
        raise ValueError(f"Reference FASTA contains no sequence data: {reference_fasta}")
    return seq


__all__ = ["ConsensusResult", "compute_well_consensuses"]
