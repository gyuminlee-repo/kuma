"""Fold-change, log2, and relative-activity normalization for MAME activity data.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §3.4 step 5–7
v0.3 Phase B-3 addition:
  - WT_PATTERN module constant
  - compute_relative_activity (slide 10 spec: relative = area / mean(WT_areas))
"""

import math
import re
from typing import Optional


# Module-level constant for WT sample name matching.
# Covers both 'WT_1' and 'WT1' variants found in real data (spec §11-B).
# NOTE: evolvepro_xlsx.py (Phase A) will declare the same constant.
# TODO(phase-A): consolidate into a shared constants.py or models.py.
WT_PATTERN = re.compile(r"^WT_?\d+$")


def compute_relative_activity(
    area: float,
    wt_areas: list[float],
) -> float:
    """Compute relative activity as area / mean(wt_areas).

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
    wt_mean = sum(wt_areas) / len(wt_areas)
    if wt_mean <= 0:
        raise ValueError(
            f"WT mean area must be > 0 (computed {wt_mean:.6g} "
            f"from wt_areas={wt_areas})"
        )
    return area / wt_mean


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
