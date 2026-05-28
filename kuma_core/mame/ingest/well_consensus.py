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

from kuma_core.mame.ingest.align import Alignment, align_reads
from kuma_core.mame.ingest.consensus import call_consensus, per_position_depth


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
    """

    consensus_seq: str
    n_input_reads: int
    n_aligned: int
    n_passed_filter: int
    mean_depth: float
    alignments: list[Alignment] = field(default_factory=list, repr=False)


def compute_well_consensuses(
    per_well_reads: dict[str, list[tuple[str, str]]],
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
            )
            continue

        # align_reads returns only passing alignments (MAPQ + span filtered).
        # To compute n_aligned separately we would need a two-pass approach.
        # As a pragmatic approximation: n_aligned is not tracked here because
        # mappy only returns hits that pass its internal filter; the distinction
        # between "no hit" and "low-MAPQ hit" is opaque from the mappy API.
        # n_aligned is set equal to n_passed_filter (conservative lower bound).
        alignments = align_reads(
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
                n_aligned=0,
                n_passed_filter=0,
                mean_depth=0.0,
                alignments=[],
            )
            continue

        # Compute per-position depth for mean_depth statistic.
        depths = per_position_depth(alignments, ref_len)
        mean_d = statistics.mean(depths) if depths else 0.0

        consensus_seq = call_consensus(alignments, ref_seq, min_depth=min_depth)

        results[well] = ConsensusResult(
            consensus_seq=consensus_seq,
            n_input_reads=n_input,
            n_aligned=n_passed,       # conservative: mappy doesn't expose pre-filter counts
            n_passed_filter=n_passed,
            mean_depth=mean_d,
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
