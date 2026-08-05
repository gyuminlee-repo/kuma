"""Per-replicate purity evidence, and how a run judges its own outliers.

Three independent things can make a well unusable, and MAME measured only some
of them where a reader could see them.

* A substitution the consensus calls can rest on a thin majority. Verdict class
  never sees this: the only purity input to the verdict is the mixed-position
  gate, and everything below it reads PASS.
* Reads can carry an indel the substitution view is blind to. Well G3 (G104E) on
  the 260729 run reads 97 to 99% designed substitution at codon 104 and still
  carries a 1 bp deletion in 22% of reads, which is a frameshifted
  subpopulation. Substitution purity and indel purity are separate axes.
* Both of the above can sit just under whatever fixed gate is in place.

Rather than invent another fixed gate, a run is judged against itself. Each
plate supplies its own baseline through the median and the median absolute
deviation of its wells, and a well is called out when it sits more than three
MAD from that median. Median and MAD are the standard robust pair: a handful of
bad wells cannot drag the baseline the way a mean and a standard deviation
would, and the threshold is expressed in units the run itself defines rather
than in a number chosen off a plot.

Nothing here changes a verdict or removes a clone from the pick list. It reports.
The operator decides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from kuma_core.mame.models import BarcodeRecord

# Two-sided 95% z, read one-sided: the question is how low the support could
# plausibly be, which is the conservative direction for a pick.
_Z_95 = 1.959963984540054

# Distance from the plate median, in MAD, past which a well is reported. Three
# is the conventional robust-outlier cut and is deliberately not tuned to this
# dataset; the point of a self-calibrating baseline is that the number does not
# have to encode what a clean run looks like.
_MAD_MULTIPLE = 3.0


def support_lower_bound(record: BarcodeRecord) -> float | None:
    """Wilson score lower bound on the weakest called-substitution support.

    ``None`` when the consensus calls no substitution, when the metric predates
    this release, or when no depth was recorded. That is unknown, not zero, and
    callers must not order it as if it were zero.
    """
    support = record.min_variant_support
    depth = record.min_variant_support_depth
    if support is None or record.n_variant_positions <= 0 or depth <= 0:
        return None
    z2 = _Z_95 * _Z_95
    centre = support + z2 / (2 * depth)
    spread = _Z_95 * math.sqrt(
        support * (1.0 - support) / depth + z2 / (4 * depth * depth)
    )
    return (centre - spread) / (1.0 + z2 / depth)


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


@dataclass(frozen=True)
class PlateBaseline:
    """What a normal well looks like on one plate, measured on that plate."""

    support_median: float | None
    support_spread: float
    indel_median: float | None
    indel_spread: float

    def support_is_low(self, bound: float | None) -> bool:
        if bound is None or self.support_median is None or self.support_spread <= 0:
            return False
        return bound < self.support_median - _MAD_MULTIPLE * self.support_spread

    def indel_is_high(self, fraction: float | None) -> bool:
        if fraction is None or self.indel_median is None or self.indel_spread <= 0:
            return False
        return fraction > self.indel_median + _MAD_MULTIPLE * self.indel_spread


def _baseline_pair(values: Sequence[float]) -> tuple[float | None, float]:
    """Return (median, spread) or (None, 0.0) when there is nothing to compare to.

    Spread is the median absolute deviation, falling back to the mean absolute
    deviation when the MAD is zero. A MAD of zero is the ordinary situation for a
    clean plate carrying one bad well: more than half the wells agree exactly, so
    the median deviation is zero and the outlier would be invisible to a MAD-only
    rule (the Iglewicz and Hoaglin fallback, for the same reason).

    A spread of zero after both means every well agreed exactly, so no well can
    be an outlier and the caller reports none. Silence is the right answer there,
    not a flag on whichever well differs in the last decimal.
    """
    if len(values) < 3:
        return None, 0.0
    med = _median(values)
    deviations = [abs(v - med) for v in values]
    mad = _median(deviations)
    if mad > 0:
        return med, mad
    return med, sum(deviations) / len(deviations)


def plate_baseline(records: Iterable[BarcodeRecord]) -> PlateBaseline:
    """Build the self-calibrating baseline for one plate."""
    bounds: list[float] = []
    indels: list[float] = []
    for record in records:
        bound = support_lower_bound(record)
        if bound is not None:
            bounds.append(bound)
        indels.append(float(record.max_indel_event_fraction))
    support_median, support_spread = _baseline_pair(bounds)
    indel_median, indel_spread = _baseline_pair(indels)
    return PlateBaseline(
        support_median=support_median,
        support_spread=support_spread,
        indel_median=indel_median,
        indel_spread=indel_spread,
    )


def review_reason(record: BarcodeRecord, baseline: PlateBaseline) -> str:
    """Return why this well deserves a second look, or an empty string.

    The text carries the measured value and the baseline it was judged against,
    so a reader can disagree with the call without rerunning anything.
    """
    parts: list[str] = []
    bound = support_lower_bound(record)
    if baseline.support_is_low(bound) and bound is not None:
        assert baseline.support_median is not None
        parts.append(
            f"substitution support {bound:.3f} below plate baseline "
            f"{baseline.support_median:.3f} (MAD {baseline.support_spread:.3f})"
        )
    indel = float(record.max_indel_event_fraction)
    if baseline.indel_is_high(indel):
        assert baseline.indel_median is not None
        parts.append(
            f"indel reads {indel:.3f} above plate baseline "
            f"{baseline.indel_median:.3f} (MAD {baseline.indel_spread:.3f})"
        )
    return "; ".join(parts)


__all__ = [
    "PlateBaseline",
    "plate_baseline",
    "review_reason",
    "support_lower_bound",
]
