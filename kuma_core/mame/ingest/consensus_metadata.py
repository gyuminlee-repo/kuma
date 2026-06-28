"""Consensus FASTA metadata contract helpers.

The MAME demux→consensus pipeline writes a single-record FASTA per well.
Downstream analysis parses the header metadata to preserve read depth and QC
evidence.  Keep field names, order, and numeric formatting centralized here so
writers and parsers do not drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


DEPTH = "depth"
INPUT_READS = "input_reads"
ALIGNED_READS = "aligned_reads"
MAPQ_FAILED = "mapq_failed"
SPAN_FAILED = "span_failed"
MIXED_POSITIONS = "mixed_positions"
MAX_MINOR_ALLELE_FRACTION = "max_minor_allele_fraction"
LOW_DEPTH_POSITIONS = "low_depth_positions"
CONSENSUS_N_FRACTION = "consensus_n_fraction"
LOW_QUALITY_BASES = "low_quality_bases"
INDEL_EVENT_POSITIONS = "indel_event_positions"
MAX_INDEL_EVENT_FRACTION = "max_indel_event_fraction"
MAX_DEL_RUN_LENGTH = "max_del_run_length"


@dataclass(frozen=True)
class ConsensusMetadata:
    """QC metadata carried in MAME-generated consensus FASTA headers."""

    depth: int
    input_reads: int
    aligned_reads: int
    mapq_failed: int
    span_failed: int
    mixed_positions: int
    max_minor_allele_fraction: float
    low_depth_positions: int
    consensus_n_fraction: float
    low_quality_bases: int
    n_indel_event_positions: int = 0
    max_indel_event_fraction: float = 0.0
    max_del_run_length: int = 0

    def header_items(self) -> Iterable[tuple[str, str]]:
        """Yield metadata pairs in the stable FASTA-header order."""

        yield DEPTH, str(self.depth)
        yield INPUT_READS, str(self.input_reads)
        yield ALIGNED_READS, str(self.aligned_reads)
        yield MAPQ_FAILED, str(self.mapq_failed)
        yield SPAN_FAILED, str(self.span_failed)
        yield MIXED_POSITIONS, str(self.mixed_positions)
        yield MAX_MINOR_ALLELE_FRACTION, f"{self.max_minor_allele_fraction:.3f}"
        yield LOW_DEPTH_POSITIONS, str(self.low_depth_positions)
        yield CONSENSUS_N_FRACTION, f"{self.consensus_n_fraction:.3f}"
        yield LOW_QUALITY_BASES, str(self.low_quality_bases)
        yield INDEL_EVENT_POSITIONS, str(self.n_indel_event_positions)
        yield MAX_INDEL_EVENT_FRACTION, f"{self.max_indel_event_fraction:.3f}"
        yield MAX_DEL_RUN_LENGTH, str(self.max_del_run_length)

    def header_suffix(self) -> str:
        """Return ``key=value`` metadata joined for a FASTA header."""

        return " ".join(f"{key}={value}" for key, value in self.header_items())


def format_consensus_fasta_record(
    well_name: str,
    consensus_seq: str,
    metadata: ConsensusMetadata,
) -> str:
    """Return one MAME consensus FASTA record with the stable QC header."""

    return f">{well_name} {metadata.header_suffix()}\n{consensus_seq}\n"


__all__ = [
    "ALIGNED_READS",
    "CONSENSUS_N_FRACTION",
    "DEPTH",
    "INPUT_READS",
    "LOW_DEPTH_POSITIONS",
    "LOW_QUALITY_BASES",
    "MAPQ_FAILED",
    "MAX_MINOR_ALLELE_FRACTION",
    "MIXED_POSITIONS",
    "SPAN_FAILED",
    "ConsensusMetadata",
    "format_consensus_fasta_record",
    "INDEL_EVENT_POSITIONS",
    "MAX_INDEL_EVENT_FRACTION",
    "MAX_DEL_RUN_LENGTH",
]
