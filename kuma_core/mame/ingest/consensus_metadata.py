"""Consensus FASTA metadata contract helpers.

The MAME demux→consensus pipeline writes a single-record FASTA per well.
Downstream analysis parses the header metadata to preserve read depth and QC
evidence.  Keep field names, order, and numeric formatting centralized here so
writers and parsers do not drift.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

from kuma_core.mame.models import NoisyPosition

_logger = logging.getLogger(__name__)


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
# Strand evidence behind the minor allele at the position that produced
# ``max_minor_allele_fraction``: the weak-strand share and the two counts it was
# computed from. Written only when a mix-eligible position exists, so absence
# means "unknown", never "one strand only" (which is a share of 0.0 and a real
# measurement). Same emit-only-when-known rule as ``min_variant_support``.
MAX_MINOR_ALLELE_STRAND_SHARE = "max_minor_allele_strand_share"
MAX_MINOR_ALLELE_PLUS = "max_minor_allele_plus"
MAX_MINOR_ALLELE_MINUS = "max_minor_allele_minus"
# How many positions ``noisy_positions`` was sampled from. Always written, and 0
# is honest: a well with no eligible position reports an empty list drawn from
# nothing. Absent only in files written before the key existed, which also carry
# no list, so the pair stays consistent either way.
ELIGIBLE_POSITIONS = "eligible_positions"
# The per-position sample itself; see ``format_noisy_positions`` for the encoding.
NOISY_POSITIONS = "noisy_positions"
# Coverage-uniformity and consensus-identity evidence. Definitions live once, in
# ``well_consensus.depth_stats`` and ``well_consensus.consensus_identity``; these
# are only the header names. Each is emitted ONLY when measured, so absence means
# unknown and never 0.0, and each gates INDEPENDENTLY: a well with no reads has a
# real breadth of 0.0 while the other three are unmeasurable, so they are not a
# travel-together block the way the strand trio above is. Reported only; no
# verdict, gate or severity rule reads any of them.
DEPTH_CV = "depth_cv"
DEPTH_P10 = "depth_p10"
DEPTH_MIN_COVERED = "depth_min_covered"
BREADTH_AT_MIX_MIN_DEPTH = "breadth_at_mix_min_depth"
CONSENSUS_IDENTITY = "consensus_identity"

#: Field separator inside one ``noisy_positions`` record.
_NOISY_FIELD_SEP = ":"
#: Record separator. Neither may be whitespace: ``_METADATA_RE`` in fasta_parser
#: reads a header value as a run of non-space characters, so a space anywhere in
#: the value would truncate it at the first record.
_NOISY_RECORD_SEP = ","
#: Values per record: position, minor fraction, depth, plus count, minus count.
_NOISY_FIELDS = 5


def format_noisy_positions(positions: Sequence[NoisyPosition]) -> str:
    """Encode *positions* as ``pos:frac:depth:plus:minus`` records, comma-joined.

    One key rather than five parallel lists, because the five numbers of one
    position only mean anything together and parallel lists can go out of step.

    ``minor_fraction`` is written at the same ``.3f`` the other fraction keys use
    and the rounding costs nothing: the exact value is ``(plus + minus) / depth``
    by construction (the strand counts split the minor allele, so they sum to its
    count, and the fraction is that count over the depth). The written fraction is
    therefore a convenience for a human reading the header, and a consumer that
    needs full precision recomputes it. The parser does NOT recompute or verify
    it, so a hand-edited file reads back exactly what it says.
    """

    return _NOISY_RECORD_SEP.join(
        _NOISY_FIELD_SEP.join(
            (
                str(p.position),
                f"{p.minor_fraction:.3f}",
                str(p.depth),
                str(p.plus_count),
                str(p.minus_count),
            )
        )
        for p in positions
    )


def parse_noisy_positions(raw: str | None) -> tuple[NoisyPosition, ...]:
    """Decode a ``noisy_positions`` header value; ``None`` or ``""`` gives ``()``.

    A malformed record (wrong field count, or a field that will not parse as a
    number) is SKIPPED and the rest of the list is kept, with one warning naming
    the record. Dropping the whole list would lose the good positions next to the
    bad one, and raising would take down the parse of an otherwise readable
    consensus file over evidence that no gate reads. The surviving records keep
    their written order, which is the writer's ranking; nothing is re-sorted.
    """

    if not raw:
        return ()
    out: list[NoisyPosition] = []
    for record in raw.split(_NOISY_RECORD_SEP):
        if not record:
            continue
        fields = record.split(_NOISY_FIELD_SEP)
        if len(fields) != _NOISY_FIELDS:
            _logger.warning(
                "Skipping malformed %s record %r (expected %d %r-separated "
                "fields, got %d).",
                NOISY_POSITIONS,
                record,
                _NOISY_FIELDS,
                _NOISY_FIELD_SEP,
                len(fields),
            )
            continue
        try:
            out.append(
                NoisyPosition(
                    position=int(fields[0]),
                    minor_fraction=float(fields[1]),
                    depth=int(fields[2]),
                    plus_count=int(fields[3]),
                    minus_count=int(fields[4]),
                )
            )
        except ValueError:
            _logger.warning(
                "Skipping unparseable %s record %r.", NOISY_POSITIONS, record
            )
    return tuple(out)


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
    # Weak-strand share of the minor allele at the position behind
    # ``max_minor_allele_fraction``, and the two counts it divides.  ``None`` is
    # unknown (no mix-eligible position) and 0.0 is "one strand only", so the
    # trio is emitted only when the share exists.  A reader must treat the
    # missing keys as unknown, never as a one-strand measurement.
    max_minor_allele_strand_share: float | None = None
    max_minor_allele_plus: int = 0
    max_minor_allele_minus: int = 0
    # Size of the pool ``noisy_positions`` samples, so its truncation is visible.
    # Always written; 0 is a real answer.
    n_eligible_positions: int = 0
    noisy_positions: tuple[NoisyPosition, ...] = ()
    # Coverage uniformity and consensus identity, all report-only. ``None`` means
    # NOT MEASURED and the key is then omitted; 0.0 is a real reading (a flat
    # well, or a consensus matching the reference nowhere) and is written.
    depth_cv: float | None = None
    depth_p10: float | None = None
    depth_min_covered: int | None = None
    breadth_at_mix_min_depth: float | None = None
    consensus_identity: float | None = None

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
        if self.max_minor_allele_strand_share is not None:
            yield (
                MAX_MINOR_ALLELE_STRAND_SHARE,
                f"{self.max_minor_allele_strand_share:.3f}",
            )
            yield MAX_MINOR_ALLELE_PLUS, str(self.max_minor_allele_plus)
            yield MAX_MINOR_ALLELE_MINUS, str(self.max_minor_allele_minus)
        yield ELIGIBLE_POSITIONS, str(self.n_eligible_positions)
        # Five INDEPENDENT emissions, deliberately not one block. A well with no
        # reads covers nothing, so its breadth is a measured 0.0 while the other
        # four are unmeasurable; guarding them together would drop that 0.0.
        # Fractions carry six decimals because three would round a single
        # mismatch in a 3 kb amplicon to a perfect 1.000.
        if self.depth_cv is not None:
            yield DEPTH_CV, f"{self.depth_cv:.6f}"
        if self.depth_p10 is not None:
            yield DEPTH_P10, f"{self.depth_p10:.1f}"
        if self.depth_min_covered is not None:
            yield DEPTH_MIN_COVERED, str(self.depth_min_covered)
        if self.breadth_at_mix_min_depth is not None:
            yield BREADTH_AT_MIX_MIN_DEPTH, f"{self.breadth_at_mix_min_depth:.6f}"
        if self.consensus_identity is not None:
            yield CONSENSUS_IDENTITY, f"{self.consensus_identity:.6f}"
        if self.noisy_positions:
            yield NOISY_POSITIONS, format_noisy_positions(self.noisy_positions)

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
    "BREADTH_AT_MIX_MIN_DEPTH",
    "CONSENSUS_IDENTITY",
    "DEPTH_CV",
    "DEPTH_MIN_COVERED",
    "DEPTH_P10",
    "CONSENSUS_N_FRACTION",
    "CONSENSUS_N_FRACTION_BASIS",
    "DEPTH",
    "ELIGIBLE_POSITIONS",
    "INPUT_READS",
    "LOW_DEPTH_POSITIONS",
    "LOW_QUALITY_BASES",
    "MAPQ_FAILED",
    "MAX_MINOR_ALLELE_FRACTION",
    "MAX_MINOR_ALLELE_MINUS",
    "MAX_MINOR_ALLELE_PLUS",
    "MAX_MINOR_ALLELE_STRAND_SHARE",
    "MEDIAN_MINOR_ALLELE_FRACTION",
    "MIN_VARIANT_SUPPORT",
    "MIN_VARIANT_SUPPORT_DEPTH",
    "MIXED_POSITIONS",
    "NOISY_POSITIONS",
    "SPAN_FAILED",
    "VARIANT_POSITIONS",
    "ConsensusMetadata",
    "NoisyPosition",
    "format_consensus_fasta_record",
    "format_noisy_positions",
    "parse_noisy_positions",
    "INDEL_EVENT_POSITIONS",
    "MAX_INDEL_EVENT_FRACTION",
    "MAX_DEL_RUN_LENGTH",
    "CONSENSUS_NET_INDEL",
    "READ_NET_INDEL",
    "NET_INDEL",
]
