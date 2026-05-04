"""Replicate aggregation utilities for MAME activity data.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §3.4 step 4
"""

import statistics
from typing import Optional


def aggregate_replicates(
    values: list[float],
) -> tuple[Optional[float], Optional[float], int]:
    """Compute mean, standard deviation, and count from a list of replicate values.

    Args:
        values: List of numeric replicate measurements.

    Returns:
        (mean, sd, n) where sd is None when n < 2, and both mean and sd are
        None when n == 0.
    """
    n = len(values)
    if n == 0:
        return None, None, 0
    mean = sum(values) / n
    sd = statistics.stdev(values) if n > 1 else None
    return mean, sd, n
