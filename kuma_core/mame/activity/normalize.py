"""Fold-change, log2, and relative-activity normalization for MAME activity data.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §3.4 step 5–7
v0.3 Phase B-3 addition:
  - WT_PATTERN module constant
  - compute_relative_activity (slide 10 spec: relative = area / mean(WT_areas))
"""

import math
from collections.abc import Sequence
from typing import Optional

from .constants import WT_PATTERN


def require_measurement(value: float, context: str) -> float:
    """A measured activity or GC area: finite and not negative. Zero is a value.

    The one rule every activity reader applies to a number it is about to use.
    An infinite area is the largest value on the plate and a negative one has
    no physical reading; either would rank or flip every relative activity
    derived from it. A mutant with no activity measures zero, which is data.
    """
    if not math.isfinite(value):
        raise ValueError(f"{context}: value {value!r} is not finite")
    if value < 0:
        raise ValueError(f"{context}: value {value!r} is negative")
    return value


def wt_denominator(areas: Sequence[float], source: str) -> float:
    """The WT mean every relative activity of *source* is divided by.

    Shared by every reader that normalises by a WT block or WT well, so the
    rule cannot drift between them again: at least one area, a mean above zero
    (an all-zero baseline used to raise ZeroDivisionError on some paths and a
    negative one silently flipped every sign), and each area a valid
    measurement (:func:`require_measurement`). Callers that have a more
    specific message for a missing WT state it before calling.
    """
    values = list(areas)
    if not values:
        raise ValueError(f"{source} has no WT areas to divide by")
    # Finite values can still overflow the sum, so the mean itself is checked
    # for finiteness as well as sign.
    mean = sum(values) / len(values)
    if not (math.isfinite(mean) and mean > 0):
        raise ValueError(
            f"{source} WT mean area must be > 0 and finite (computed {mean:.6g} from {values})"
        )
    for value in values:
        require_measurement(value, f"{source} WT area")
    return mean


def compute_relative_activity(
    area: float,
    wt_areas: list[float],
) -> float:
    """Compute relative activity as area / mean(wt_areas).

    Scope: reports-mode callers only (build_evolvepro_input.py family). The
    ``MergedRow`` join/export path does not call this; it uses
    :func:`compute_fold_change`, which yields the same quantity.

    Implements slide 10 specification:
      relative_activity = mutant_area / mean(WT_replicate_areas)

    Args:
        area:      Raw GC-FID area for the mutant well.
        wt_areas:  List of raw areas for all WT replicate wells.

    Returns:
        Relative activity (float >= 0).

    Raises:
        ValueError: wt_areas is empty.
        ValueError: Computed WT mean is <= 0 (non-positive mean is
                    physically invalid for GC-FID area values).
    """
    if not wt_areas:
        raise ValueError(
            f"wt_areas is empty (got {len(wt_areas)} entries); "
            "at least one WT replicate area is required"
        )
    return require_measurement(area, "area") / wt_denominator(wt_areas, "wt_areas")


def compute_fold_change(
    activity_mean: Optional[float],
    wt_mean: Optional[float],
) -> Optional[float]:
    """Compute fold-change relative to WT mean.

    Returns None if either input is None or wt_mean is 0.
    """
    if activity_mean is None or wt_mean is None or wt_mean == 0:
        return None
    return activity_mean / wt_mean


def compute_log2_fc(
    fold_change: Optional[float],
    is_wt: bool = False,
) -> Optional[float]:
    """Compute log2 fold-change.

    Args:
        fold_change: Fold-change value; None if unavailable.
        is_wt: If True, returns 0.0 regardless of fold_change (WT is baseline).

    Returns:
        0.0 for WT wells, log2(fold_change) for variants, None when
        fold_change is None, 0, or negative.
    """
    if is_wt:
        return 0.0
    if fold_change is None or fold_change <= 0:
        return None
    return math.log2(fold_change)
