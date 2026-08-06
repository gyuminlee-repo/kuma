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
# Net indel of the consensus itself; the FRAMESHIFT gate reads this one.
CONSENSUS_NET_INDEL = "consensus_net_indel"
# Median per-read net indel; a read-quality metric, never a verdict input.
READ_NET_INDEL = "read_net_indel"
# Legacy key. Files written between #201 and the fix carry ``net_indel=K`` whose
# value is the per-read median, not the consensus net indel, even though the key
# reads like the latter. Renaming rather than reinterpreting is deliberate: an
# old file must not be re-read under the new meaning and re-fail as a frameshift,
# so the parser maps this key onto the read-quality metric only.
NET_INDEL = "net_indel"
# Identifies which denominator produced ``consensus_n_fraction``. Files written
# before this key existed carry the legacy whole-reference denominator, so the
# stored number is NOT comparable to a covered-scoped threshold. The parser uses
# the presence of this key to tell the two meanings apart instead of guessing.
CONSENSUS_N_FRACTION_BASIS = "consensus_n_fraction_basis"
# Denominator = positions whose pileup depth reached ``min_depth``.
BASIS_COVERED = "covered"
# Weakest read support among the substitutions the consensus calls, and the
# number of those positions. Written only when a substitution exists, so absence
# means "unknown or no substitution", never "zero support".
MIN_VARIANT_SUPPORT = "min_variant_support"
VARIANT_POSITIONS = "variant_positions"
# Depth the support fraction was measured on, so a reader can weigh it.
MIN_VARIANT_SUPPORT_DEPTH = "min_variant_support_depth"
# Noise floor the well ran at, so the mixed-position gate can be audited.
MEDIAN_MINOR_ALLELE_FRACTION = "median_minor_allele_fraction"


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
    consensus_net_indel: int = 0
    read_net_indel: int = 0
    # Denominator that produced ``consensus_n_fraction``. Always written so any
    # file produced from here on is self-describing.
    consensus_n_fraction_basis: str = BASIS_COVERED
    # Weakest read support among the substitutions the consensus calls.  Absent
    # from files written before this key existed, and absent for a well whose
    # consensus matches the reference everywhere, so the key is only emitted when
    # a value exists.  A reader must treat "missing" as unknown, never as 0.0.
    min_variant_support: float | None = None
    variant_positions: int = 0
    min_variant_support_depth: int = 0
    median_minor_allele_fraction: float = 0.0

    def header_items(self) -> Iterable[tuple[str, str]]:
        """Yield metadata pairs in the stable FASTA-header order."""

        yield DEPTH, str(self.depth)
        yield INPUT_READS, str(self.input_reads)
        yield ALIGNED_READS, str(self.aligned_reads)
        yield MAPQ_FAILED, str(self.mapq_failed)
        yield SPAN_FAILED, str(self.span_failed)
        yield MIXED_POSITIONS, str(self.mixed_positions)
        yield MAX_MINOR_ALLELE_FRACTION, f"{self.max_minor_allele_fraction:.3f}"
        yield MEDIAN_MINOR_ALLELE_FRACTION, f"{self.median_minor_allele_fraction:.4f}"
        yield LOW_DEPTH_POSITIONS, str(self.low_depth_positions)
        yield CONSENSUS_N_FRACTION, f"{self.consensus_n_fraction:.3f}"
        yield LOW_QUALITY_BASES, str(self.low_quality_bases)
        yield INDEL_EVENT_POSITIONS, str(self.n_indel_event_positions)
        yield MAX_INDEL_EVENT_FRACTION, f"{self.max_indel_event_fraction:.3f}"
        yield MAX_DEL_RUN_LENGTH, str(self.max_del_run_length)
        yield CONSENSUS_NET_INDEL, str(self.consensus_net_indel)
        yield READ_NET_INDEL, str(self.read_net_indel)
        yield CONSENSUS_N_FRACTION_BASIS, self.consensus_n_fraction_basis
        if self.min_variant_support is not None:
            yield MIN_VARIANT_SUPPORT, f"{self.min_variant_support:.3f}"
            yield VARIANT_POSITIONS, str(self.variant_positions)
            yield MIN_VARIANT_SUPPORT_DEPTH, str(self.min_variant_support_depth)

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
    "BASIS_COVERED",
    "CONSENSUS_N_FRACTION",
    "CONSENSUS_N_FRACTION_BASIS",
    "DEPTH",
    "INPUT_READS",
    "LOW_DEPTH_POSITIONS",
    "LOW_QUALITY_BASES",
    "MAPQ_FAILED",
    "MAX_MINOR_ALLELE_FRACTION",
    "MEDIAN_MINOR_ALLELE_FRACTION",
    "MIN_VARIANT_SUPPORT",
    "MIN_VARIANT_SUPPORT_DEPTH",
    "MIXED_POSITIONS",
    "SPAN_FAILED",
    "VARIANT_POSITIONS",
    "ConsensusMetadata",
    "format_consensus_fasta_record",
    "INDEL_EVENT_POSITIONS",
    "MAX_INDEL_EVENT_FRACTION",
    "MAX_DEL_RUN_LENGTH",
    "CONSENSUS_NET_INDEL",
    "READ_NET_INDEL",
    "NET_INDEL",
]
