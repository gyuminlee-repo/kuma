"""Fold-change and log2 normalization for MAME activity data.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §3.4 step 5–7
"""

import math
from typing import Optional


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
