"""Cross-talk detection for MAME barcode demux (A9 milestone).

Two independent signals are evaluated:

1. **Barcode score** (requires sequencing_summary_*.txt / .tsv):
   Per-label fraction of reads with ``barcode_front_score < threshold``.
   When ≥ ``low_score_well_threshold`` fraction of reads are low-score,
   a warning is emitted.

2. **Neighbor ratio** (requires barcode_distribution with well-format keys A1–H12):
   For each well, the right (same row, col+1) and below (row+1, same col)
   neighbours are checked.  When count_well / count_neighbour ≥
   ``neighbor_ratio_threshold``, a warning is emitted.  Wraps are not applied
   (H12 has no below/right neighbour).

If the key format of ``barcode_distribution`` is not 96-well
(e.g. ``barcode01`` / ``NB01`` labels from MinKNOW native demux),
neighbor-ratio analysis is silently skipped.

When no data source is available the function returns an empty
``CrossTalkAnalysis`` with ``n_wells_checked = 0``.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from kuma_core.mame.ingest.run_meta import NgsRunMeta

# ---------------------------------------------------------------------------
# Well grid helpers
# ---------------------------------------------------------------------------

_ROW_LABELS = list("ABCDEFGH")  # 8 rows
_COL_RANGE = range(1, 13)  # 12 columns


def _is_well_key(key: str) -> bool:
    """Return True iff *key* matches the 96-well format, e.g. ``A1`` or ``H12``."""
    return bool(re.fullmatch(r"[A-H](1[0-2]|[1-9])", key))


def _neighbour_keys(well: str) -> list[str]:
    """Return the right and below neighbour well labels (if they exist)."""
    row = well[0]
    col = int(well[1:])
    neighbours: list[str] = []
    # Right: same row, col+1
    if col < 12:
        neighbours.append(f"{row}{col + 1}")
    # Below: next row letter, same col
    row_idx = _ROW_LABELS.index(row)
    if row_idx < 7:
        neighbours.append(f"{_ROW_LABELS[row_idx + 1]}{col}")
    return neighbours


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class CrossTalkAlert:
    """Single cross-talk suspicion event for one well / barcode label."""

    well: str
    """Well label (e.g. ``A1``) or barcode label (e.g. ``barcode01``)."""

    native_barcode: str
    """Native MinKNOW barcode label (``NB01``/``NB02``/…).

    Set to empty string when the mapping is not available.
    """

    severity: Literal["info", "warning"]

    reason: str
    """Human-readable description of the detected anomaly."""


@dataclass
class CrossTalkAnalysis:
    """Aggregated cross-talk detection result."""

    alerts: list[CrossTalkAlert]
    n_wells_checked: int
    method: Literal["barcode_score", "neighbor_ratio", "both", "none"]


# ---------------------------------------------------------------------------
# Sequencing-summary parsing
# ---------------------------------------------------------------------------

# Candidate column names (MinKNOW versions vary)
_SUMMARY_BARCODE_COLS = [
    "barcode_arrangement",
    "alias",
    "barcode",
]
_SUMMARY_SCORE_COLS = [
    "barcode_front_score",
    "barcode_score",
    "front_score",
]


def _first_col(header: list[str], candidates: list[str]) -> str | None:
    lower_map = {h.strip().lower(): h.strip() for h in header}
    for cand in candidates:
        if cand.strip().lower() in lower_map:
            return lower_map[cand.strip().lower()]
    return None


def _parse_sequencing_summary(path: Path) -> dict[str, list[float]] | None:
    """Parse a MinKNOW sequencing_summary file.

    Returns mapping ``{barcode_label: [scores]}`` or ``None`` on failure.
    """
    try:
        # MinKNOW summaries are tab-separated
        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter="\t")
        rows = list(reader)
        if not rows:
            return None
        header = list(reader.fieldnames or [])
        bc_col = _first_col(header, _SUMMARY_BARCODE_COLS)
        score_col = _first_col(header, _SUMMARY_SCORE_COLS)
        if bc_col is None or score_col is None:
            return None
        result: dict[str, list[float]] = {}
        for row in rows:
            bc = row.get(bc_col, "").strip()
            raw_score = row.get(score_col, "").strip()
            if not bc or not raw_score:
                continue
            try:
                score = float(raw_score)
            except ValueError:
                continue
            result.setdefault(bc, []).append(score)
        return result if result else None
    except (OSError, csv.Error):
        return None


def _find_sequencing_summary(run_dir: Path) -> Path | None:
    """Locate the sequencing_summary file in *run_dir*, or return ``None``."""
    # Prefer passed variant
    for pattern in (
        "sequencing_summary*_passed*.txt",
        "sequencing_summary*.txt",
        "sequencing_summary*_passed*.tsv",
        "sequencing_summary*.tsv",
    ):
        found = sorted(run_dir.glob(pattern))
        if found:
            return found[0]
    return None


# ---------------------------------------------------------------------------
# Core detection functions
# ---------------------------------------------------------------------------


def _detect_barcode_score(
    barcode_distribution: dict[str, int],
    sequencing_summary_path: Path,
    score_threshold: float,
    low_score_well_threshold: float,
) -> list[CrossTalkAlert]:
    """Emit warnings for labels with high fraction of low-score reads."""
    scores_by_label = _parse_sequencing_summary(sequencing_summary_path)
    if scores_by_label is None:
        return []

    alerts: list[CrossTalkAlert] = []
    for label in barcode_distribution:
        scores = scores_by_label.get(label)
        if not scores:
            continue
        total = len(scores)
        low_count = sum(1 for s in scores if s < score_threshold)
        fraction = low_count / total
        if fraction >= low_score_well_threshold:
            pct = round(fraction * 100, 1)
            alerts.append(
                CrossTalkAlert(
                    well=label,
                    native_barcode="",
                    severity="warning",
                    reason=(
                        f"Low barcode score (<{score_threshold:.0f}) on "
                        f"{pct}% of reads ({low_count}/{total})"
                    ),
                )
            )
    return alerts


def _detect_neighbor_ratio(
    barcode_distribution: dict[str, int],
    ratio_threshold: float,
) -> list[CrossTalkAlert]:
    """Emit warnings when a well count is ≥ ratio_threshold × a neighbour count.

    Silently returns ``[]`` if the key format is not 96-well.
    """
    # Check whether the distribution uses well-format keys
    well_keys = [k for k in barcode_distribution if _is_well_key(k)]
    if not well_keys:
        return []

    alerts: list[CrossTalkAlert] = []
    checked_pairs: set[frozenset[str]] = set()

    for well in well_keys:
        count = barcode_distribution[well]
        for nbr in _neighbour_keys(well):
            if nbr not in barcode_distribution:
                continue
            pair = frozenset([well, nbr])
            if pair in checked_pairs:
                continue
            checked_pairs.add(pair)
            nbr_count = barcode_distribution[nbr]
            if nbr_count == 0:
                continue
            ratio = count / nbr_count
            inverse = nbr_count / count if count > 0 else float("inf")
            high, low, actual_ratio = (
                (well, nbr, ratio) if ratio >= ratio_threshold
                else (nbr, well, inverse) if inverse >= ratio_threshold
                else (None, None, 0.0)
            )
            if high is not None:
                high_count = barcode_distribution[high]
                low_count_val = barcode_distribution[low]  # type: ignore[index]
                alerts.append(
                    CrossTalkAlert(
                        well=high,
                        native_barcode="",
                        severity="warning",
                        reason=(
                            f"High count vs neighbor: {high} has "
                            f"{high_count:,} reads, neighbour {low} has "
                            f"{low_count_val:,} reads "
                            f"(ratio {actual_ratio:.0f}x)"
                        ),
                    )
                )
    return alerts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_cross_talk(
    run_meta: "NgsRunMeta | None",
    barcode_distribution: dict[str, int] | None,
    sequencing_summary_path: Path | None = None,
    barcode_score_threshold: float = 60.0,
    low_score_well_threshold: float = 0.15,
    neighbor_ratio_threshold: float = 50.0,
) -> CrossTalkAnalysis:
    """Detect potential cross-talk via two independent signals.

    Parameters
    ----------
    run_meta:
        ``NgsRunMeta`` for the run.  When ``raw_run_dir`` is set, the function
        will auto-discover a sequencing_summary file inside it (unless
        ``sequencing_summary_path`` is provided explicitly).
    barcode_distribution:
        ``{label: read_count}`` mapping from ``RunHealthData``.  ``None`` means
        the data is unavailable — returns empty analysis.
    sequencing_summary_path:
        Explicit path to sequencing_summary file.  Overrides auto-discovery.
    barcode_score_threshold:
        Reads with ``barcode_front_score`` below this value are "low-score".
    low_score_well_threshold:
        Fraction of low-score reads per label that triggers a warning (0–1).
    neighbor_ratio_threshold:
        Ratio of adjacent-well counts that triggers a warning.

    Returns
    -------
    CrossTalkAnalysis
        Always returns a valid object; never raises.
    """
    if barcode_distribution is None or len(barcode_distribution) == 0:
        return CrossTalkAnalysis(alerts=[], n_wells_checked=0, method="none")

    # ── Resolve sequencing summary path ──────────────────────────────────────
    summary_path = sequencing_summary_path
    if summary_path is None and run_meta is not None and run_meta.raw_run_dir is not None:
        run_dir = Path(run_meta.raw_run_dir)
        if run_dir.is_dir():
            summary_path = _find_sequencing_summary(run_dir)

    # ── Determine applicable methods ─────────────────────────────────────────
    has_summary = summary_path is not None and summary_path.is_file()
    has_well_keys = any(_is_well_key(k) for k in barcode_distribution)

    score_alerts: list[CrossTalkAlert] = []
    ratio_alerts: list[CrossTalkAlert] = []

    if has_summary:
        score_alerts = _detect_barcode_score(
            barcode_distribution,
            summary_path,  # type: ignore[arg-type]
            barcode_score_threshold,
            low_score_well_threshold,
        )

    if has_well_keys:
        ratio_alerts = _detect_neighbor_ratio(barcode_distribution, neighbor_ratio_threshold)

    # ── Method label ─────────────────────────────────────────────────────────
    if has_summary and has_well_keys:
        method: Literal["barcode_score", "neighbor_ratio", "both", "none"] = "both"
    elif has_summary:
        method = "barcode_score"
    elif has_well_keys:
        method = "neighbor_ratio"
    else:
        method = "none"

    # ── Merge and de-duplicate by well ───────────────────────────────────────
    # Severity: warning > info.  Keep all distinct (well, reason) pairs.
    all_alerts = score_alerts + ratio_alerts

    # Sort: warnings first, then by well label alphabetically
    all_alerts.sort(
        key=lambda a: (0 if a.severity == "warning" else 1, a.well)
    )

    return CrossTalkAnalysis(
        alerts=all_alerts,
        n_wells_checked=len(barcode_distribution),
        method=method,
    )


__all__ = ["CrossTalkAlert", "CrossTalkAnalysis", "analyze_cross_talk"]
