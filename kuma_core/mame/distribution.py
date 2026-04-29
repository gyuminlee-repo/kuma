"""Run-level file-size distribution analysis and cutoff recommendation.

A4 milestone: given a list of file_size_kb values collected from all FASTA
files in an input run, compute descriptive statistics and suggest an
appropriate ``min_file_size_kb`` cutoff for the verdict classifier.

Design goals
------------
- No heavy dependencies: uses only ``statistics`` (stdlib) + ``numpy`` when
  numpy is already installed (optional).  scipy is intentionally avoided.
- Bimodal detection: a simplified Hartigans' dip heuristic based on the
  gap ratio between the two modal clusters.
- Knee detection: pure slope-change maximisation over the sorted CDF.  No
  external library required.

Decision tree for ``suggested_method``
---------------------------------------
1. ``bimodal=True``  →  ``kneedle``   (gap-point between the two modes)
2. ``bimodal=False``, IQR/median < 0.5  →  ``p05``  (tight distribution)
3. Otherwise  →  ``median_minus_2sigma``
4. If the resulting cutoff < 50 KB floor  →  ``fixed_50``
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

_FLOOR_KB: float = 50.0
_BIMODAL_GAP_RATIO: float = 3.0  # gap must be this many times the smaller cluster std


@dataclass
class DistributionStats:
    """Summary statistics + recommended cutoff for a single analysis run."""

    n_files: int
    file_size_kb: dict[str, float] = field(default_factory=dict)
    """Keys: min, p05, p25, median, p75, p95, max, mean, std"""
    suggested_cutoff_kb: float = _FLOOR_KB
    suggested_method: str = "fixed_50"
    bimodal: bool = False


# ── internal helpers ────────────────────────────────────────────────────────


def _percentile(sorted_data: list[float], pct: float) -> float:
    """Linear interpolation percentile on a pre-sorted list."""
    if not sorted_data:
        return 0.0
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    idx = (pct / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])


def _detect_bimodal(sorted_data: list[float]) -> bool:
    """Return True when the distribution shows a clear two-cluster gap.

    Heuristic: find the largest gap between consecutive sorted values and
    check whether it exceeds ``_BIMODAL_GAP_RATIO * std`` of the smaller
    cluster on either side of the gap.
    """
    n = len(sorted_data)
    if n < 4:
        return False
    gaps = [(sorted_data[i + 1] - sorted_data[i], i) for i in range(n - 1)]
    max_gap, split_idx = max(gaps, key=lambda t: t[0])
    lower = sorted_data[: split_idx + 1]
    upper = sorted_data[split_idx + 1 :]
    if len(lower) < 2 or len(upper) < 2:
        return False
    lower_std = statistics.stdev(lower) if len(lower) >= 2 else 0.0
    upper_std = statistics.stdev(upper) if len(upper) >= 2 else 0.0
    ref_std = min(lower_std, upper_std) if min(lower_std, upper_std) > 0 else 1.0
    return max_gap > _BIMODAL_GAP_RATIO * ref_std


def _kneedle_cutoff(sorted_data: list[float]) -> float:
    """Return the knee point (maximum slope change) in the sorted data.

    Maps the data to a unit square [0,1] × [0,1] then finds the point with
    the maximum perpendicular distance from the diagonal.
    """
    n = len(sorted_data)
    if n < 3:
        return sorted_data[0] if sorted_data else _FLOOR_KB
    min_v, max_v = sorted_data[0], sorted_data[-1]
    span = max_v - min_v
    if span == 0:
        return sorted_data[0]
    # Normalise to [0,1]
    xs = [i / (n - 1) for i in range(n)]
    ys = [(v - min_v) / span for v in sorted_data]
    # Perpendicular distance to diagonal y=x
    dists = [abs(ys[i] - xs[i]) / math.sqrt(2) for i in range(n)]
    knee_idx = dists.index(max(dists))
    return sorted_data[knee_idx]


# ── public API ───────────────────────────────────────────────────────────────


def compute_distribution_stats(file_size_kb_values: list[float]) -> DistributionStats:
    """Compute distribution statistics and recommend a cutoff.

    Parameters
    ----------
    file_size_kb_values:
        Raw file_size_kb values from all FASTA files in the run.
        Empty list is handled gracefully (returns defaults).
    """
    if not file_size_kb_values:
        return DistributionStats(n_files=0)

    data = sorted(file_size_kb_values)
    n = len(data)

    mean = statistics.mean(data)
    std = statistics.pstdev(data) if n >= 2 else 0.0
    median = statistics.median(data)
    p25 = _percentile(data, 25)
    p75 = _percentile(data, 75)
    iqr = p75 - p25

    stats_dict: dict[str, float] = {
        "min": data[0],
        "p05": _percentile(data, 5),
        "p25": p25,
        "median": median,
        "p75": p75,
        "p95": _percentile(data, 95),
        "max": data[-1],
        "mean": round(mean, 2),
        "std": round(std, 2),
    }

    # ── Bimodal detection ──────────────────────────────────────────────────
    bimodal = _detect_bimodal(data)

    # ── Cutoff recommendation decision tree ───────────────────────────────
    if bimodal:
        method = "kneedle"
        cutoff = _kneedle_cutoff(data)
    elif median > 0 and (iqr / median) < 0.5:
        # Tight distribution — p05 is a conservative but safe floor
        method = "p05"
        cutoff = stats_dict["p05"]
    else:
        method = "median_minus_2sigma"
        cutoff = median - 2 * std

    # Floor guard
    if cutoff < _FLOOR_KB:
        cutoff = _FLOOR_KB
        method = "fixed_50"

    return DistributionStats(
        n_files=n,
        file_size_kb=stats_dict,
        suggested_cutoff_kb=round(cutoff, 2),
        suggested_method=method,
        bimodal=bimodal,
    )
