"""Which reference positions carry a minor allele in well after well.

A minor allele at one position in one well is a candidate mixture: a colony
that was not clonal, a neighbouring well that leaked. That reading only holds
while the observation is a property of the WELL. The same reference position
turning up across most of a plate cannot be a property of any one clone,
because the wells do not share a clone; they share an amplicon, a library
preparation and a basecaller.

``run_quality.summarise_position_recurrence`` already tallies WHICH positions
recur and what strand the minor allele was read off. What it does not carry is
the FRACTION those positions ran at, and the fraction is what separates the two
shapes on a real plate. Measured here over three technical replicates of one
DNA (96 wells each, 1683 bp ispS amplicon, ``sort_barcode06/13/20``):

    position 1232   reported by 90/93, 84/92, 88/95 wells
                    median minor fraction 0.0505, 0.0500, 0.0460
                    spread within a plate 0.024 - 0.087

    position   16   reported by  2/93,  0/92,  2/95 wells
                    well ``3_1`` reads 0.456 on one plate, 0.017 on another

Both are rows. Only the columns tell them apart: a tight fraction across nearly
every well, against one well an order of magnitude above two neighbours and not
reproducible in the same well on the next plate. A single scalar cannot state
that, which is why the minimum and the maximum are carried beside the median.

WHAT RECURRENCE MEANS, AND WHAT IT DOES NOT
-------------------------------------------
Recurrence across wells excludes ONE explanation: per-well biological mixing.
It does not choose among the rest. Three remain, and this module ranks none of
them:

  * basecaller error, which every well's reads passed through,
  * alignment artifact, which is a property of the amplicon's sequence context,
  * a minority subpopulation already present in the parental plasmid, which
    every well inherited.

The second and third are not separable by strand balance either. Reads are
reverse-complemented to the reference before alignment, so an alignment
artifact appears on both strands exactly as a real molecule does; strand
balance excludes the basecaller and nothing further. That correction, and the
refusal to call position 1232 (1248 in the 16 bp longer reference the note
used) a confirmed variant or a confirmed artifact, are recorded in the
2026-08-10 investigation this module is built on top of rather than against.

Nothing here grades, scores or emits a severity, and no verdict reads it. That
is not caution for its own sake: a recurrence-rate sweep over the same three
replicates put every candidate cut between "one well" and the top tier on
different sides of the line in different replicates of the SAME DNA (0.50
splits position 831 at 0.63/0.47/0.65; 0.25 splits 1229 at 0.42/0.25/0.32;
0.70 holds but discards 1491, which recurs on all three plates at a median
fraction reproducible to 0.002). A number that disagrees with itself across
technical replicates is not a threshold, which is the same conclusion
``summarise_position_recurrence`` reached on its own two runs.

The one restriction on the table is definitional rather than a cut: a position
reported by a single well has not RECURRED, so it is not a row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from collections.abc import Iterable, Sequence
from typing import Protocol

from kuma_core.mame.models import NoisyPosition

#: A position reported by one well has not recurred. This is what "recurrence"
#: means rather than a tuned cut, and it is the rule
#: ``summarise_position_recurrence`` already applies.
_MIN_WELLS_TO_RECUR = 2

#: Strand could not be measured, because every read on the plate aligned to the
#: forward strand. Distinct from "measured and one-sided", which is 0.0.
STRAND_ABSENT = "absent"
#: Strand was measured: at least one reported minor allele had a minus read.
STRAND_PRESENT = "present"
#: No well reported a position at all, so there was nothing to measure.
STRAND_NO_DATA = "no_data"


class _ScoredWell(Protocol):
    """A scored well, as ``BarcodeRecord`` and ``ConsensusCall`` both present it.

    Read structurally because it is TWO classes and not one, and the second of
    them lives beside the pileup and pulls in numpy and the aligner, which a
    leaf like this module must not reach for. ``NoisyPosition`` itself IS named,
    because it is the one definition of that record and ``models`` is a leaf on
    the standard library alone; naming it also keeps the weak-strand formula in
    its single home rather than growing a copy here.
    """

    @property
    def n_eligible_positions(self) -> int: ...

    @property
    def noisy_positions(self) -> Sequence[NoisyPosition]: ...


@dataclass(frozen=True, slots=True)
class RecurrentPosition:
    """One reference position and the fractions the plate read it at."""

    #: 1-based reference coordinate, the convention ``NoisyPosition`` states.
    position: int
    #: Scored records that reported this position. Replicate plates contribute
    #: one record per plate, so this counts SCORED RECORDS and not distinct
    #: physical wells.
    wells: int
    #: ``wells`` over the records that reported ANY position, precomputed here
    #: so a caller cannot divide by the wrong denominator.
    recurrence_rate: float
    #: The minor-allele fraction across those records. The spread is carried
    #: because the median alone cannot distinguish a plate-wide low-fraction
    #: site from one well in genuine mixture at the same position (measured:
    #: position 1654, 18 wells at median 0.018, one well at 0.476).
    median_minor_fraction: float
    min_minor_fraction: float
    max_minor_fraction: float
    #: Weak-strand share of the minor allele across those records, or ``None``
    #: for all three when the plate carried no strand information at all. Never
    #: 0.0 by default: that value means "read off one strand only", a real and
    #: very different measurement.
    median_weak_strand_share: float | None
    min_weak_strand_share: float | None
    max_weak_strand_share: float | None
    #: How many of ``wells`` contributed a share. The rest are LEFT OUT of the
    #: median rather than entered as 0.0.
    shares_known: int
    shares_unknown: int


@dataclass
class CrossWellRecurrence:
    """The recurrence table, and everything needed to read it as a lower bound."""

    positions: list[RecurrentPosition] = field(default_factory=list)
    #: Records that reported at least one mix-eligible position. The
    #: denominator behind every ``recurrence_rate``.
    wells_contributing: int = 0
    #: Of those, how many had ``noisy_positions`` truncated to the per-well
    #: reporting budget. On the three plates measured here this equalled
    #: ``wells_contributing`` exactly (93/93, 92/92, 95/95), so every count in
    #: this table is a LOWER BOUND.
    wells_truncated: int = 0
    #: Distinct positions seen at all, and how many the "recurrence means more
    #: than once" rule left out, so the table never hides its own remainder.
    positions_seen: int = 0
    positions_single_well: int = 0
    #: Whether strand could be measured on this plate at all. ``absent`` means
    #: every reported minor allele was read off the forward strand, which
    #: happens when reads were normalised to the reference upstream; the shares
    #: are then ``None`` rather than the 0.0 that would read as "one strand
    #: only" and be taken for a basecaller artifact.
    strand_information: str = STRAND_NO_DATA


def summarise_cross_well_recurrence(
    wells: Iterable[_ScoredWell],
) -> CrossWellRecurrence:
    """Tally the positions that recur across wells, with their fraction spread.

    NOTHING here grades. A position reported by ninety wells is handed over
    exactly as one reported by two, and the operator applies their own reading.
    See the module docstring for the replicate sweep behind that refusal.

    Every count is a LOWER BOUND: each well contributes a top-K sample of its
    mix-eligible positions ranked by minor fraction, and a position that ranked
    below the budget in a well is absent from that well's tally here.
    ``wells_truncated`` is what says so.

    The strand determination is PLATE-LEVEL and not per-position. A genuinely
    one-sided artifact at a single site still has minus reads elsewhere on the
    plate; a plate with no minus read anywhere carried no strand information to
    begin with, and the difference is not visible one position at a time.
    """
    fractions: dict[int, list[float]] = {}
    shares: dict[int, list[float]] = {}
    wells_contributing = 0
    wells_truncated = 0
    any_minus = False
    any_position = False

    for well in wells:
        positions = tuple(well.noisy_positions)
        if not positions:
            continue
        wells_contributing += 1
        if len(positions) < well.n_eligible_positions:
            wells_truncated += 1
        for entry in positions:
            any_position = True
            key = int(entry.position)
            fractions.setdefault(key, []).append(float(entry.minor_fraction))
            bucket = shares.setdefault(key, [])
            if entry.minus_count > 0:
                any_minus = True
            share = entry.weak_strand_share
            if share is not None:
                bucket.append(share)

    if not any_position:
        strand_information = STRAND_NO_DATA
    elif any_minus:
        strand_information = STRAND_PRESENT
    else:
        # Every reported minor allele was read off the forward strand. Each
        # individual share is therefore 0.0, which the record defines as "one
        # strand only" and a reader would take for a basecaller artifact. The
        # plate carried no strand information, so none is reported.
        strand_information = STRAND_ABSENT

    rows: list[RecurrentPosition] = []
    positions_single_well = 0
    for key, values in fractions.items():
        if len(values) < _MIN_WELLS_TO_RECUR:
            positions_single_well += 1
            continue
        known = shares[key]
        if strand_information == STRAND_PRESENT and known:
            share_median: float | None = median(known)
            share_min: float | None = min(known)
            share_max: float | None = max(known)
            shares_known = len(known)
        else:
            share_median = share_min = share_max = None
            shares_known = 0
        rows.append(
            RecurrentPosition(
                position=key,
                wells=len(values),
                recurrence_rate=len(values) / wells_contributing,
                median_minor_fraction=median(values),
                min_minor_fraction=min(values),
                max_minor_fraction=max(values),
                median_weak_strand_share=share_median,
                min_weak_strand_share=share_min,
                max_weak_strand_share=share_max,
                shares_known=shares_known,
                shares_unknown=len(values) - shares_known,
            )
        )

    # Most recurrent first, then by position so the table is deterministic.
    rows.sort(key=lambda row: (-row.wells, row.position))
    return CrossWellRecurrence(
        positions=rows,
        wells_contributing=wells_contributing,
        wells_truncated=wells_truncated,
        positions_seen=len(fractions),
        positions_single_well=positions_single_well,
        strand_information=strand_information,
    )


__all__ = [
    "CrossWellRecurrence",
    "RecurrentPosition",
    "STRAND_ABSENT",
    "STRAND_NO_DATA",
    "STRAND_PRESENT",
    "summarise_cross_well_recurrence",
]
