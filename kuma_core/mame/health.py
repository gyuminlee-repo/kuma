"""Run health metrics for the MAME UI panel (A8 milestone).

``RunHealthData`` is a lighter-weight counterpart to ``RunReportData`` — it
carries only the metrics the frontend health panel needs and adds optional
MinKNOW-specific diagnostics (pore yield, throughput timeline, barcode counts)
parsed from raw run CSV files.

MinKNOW CSV column names accepted (extend this list as formats evolve):

pore_activity_*.csv
  time columns: "experiment_time (min)", "time_min", "Experiment Time (minutes)"
  active columns: "pore_active_%", "active_pores_%", "% Active Pores"

throughput_*.csv
  time columns: "experiment_time (min)", "time_min", "Experiment Time (minutes)"
  reads columns: "reads_per_second", "Reads per second", "reads/s"

barcode_alignment.tsv / barcode_alignment_passed.tsv
  barcode columns: "barcode_arrangement", "barcode_name", "barcode"
  count columns: "num_reads", "read_count", "count"
"""

from __future__ import annotations

import csv
import io
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from kuma_core.mame.models import VerdictClass
from kuma_core.mame.detected import compute_recovery

if TYPE_CHECKING:
    from kuma_core.mame.ingest.run_meta import NgsRunMeta


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class CrossTalkCandidate:
    """A well suspected of barcode cross-talk based on spatial neighbor analysis."""

    well: str
    """Well label, e.g. "A1", "B6"."""

    custom_barcode: str
    """Custom barcode label assigned to the well, e.g. "1_1", "1_2"."""

    read_count: int
    """Observed read count for this well."""

    neighbor_avg: float
    """Mean read count of orthogonal (up/down/left/right) neighbors."""

    z_score: float
    """Z-score of read_count vs the entire plate-wide distribution (mean ± std)."""

    severity: str
    """One of "low", "medium", or "high"."""

    note: str
    """Human-readable explanation."""


@dataclass
class RunHealthData:
    """Lightweight run-health metrics for the frontend health panel.

    All MinKNOW-derived fields (``pore_yield_pct``, ``throughput_timeline``,
    ``barcode_distribution``) are ``None`` when ``run_meta.raw_run_dir`` is
    absent or the corresponding CSV files cannot be parsed.
    """

    # ── Per-plate verdict breakdown ───────────────────────────────────────
    per_plate_summary: dict[str, dict[str, int]]
    """Plate (e.g. "sort_barcode06") → per-verdict-class counts keyed by the
    lower-cased VerdictClass value (pass, ambiguous, mixed, frameshift, many,
    lowdepth, no_call, wrong_aa; these sum to "total"), plus the aggregate
    "fail" (non-PASS/AMBIGUOUS) and the replicate-level "fallback" overlay."""

    # ── File-size distribution ────────────────────────────────────────────
    file_size_distribution: dict[str, float]
    """Keys: min, p05, p25, median, p75, p95, max, mean, std"""
    suggested_cutoff_kb: float
    bimodal: bool
    suggested_method: str

    # ── MinKNOW-derived (optional) ────────────────────────────────────────
    pore_yield_pct: float | None = None
    """Final active-pore % from the last row of pore_activity_*.csv."""

    throughput_timeline: list[dict[str, float]] | None = None
    """[{"time_h": 0.5, "reads_per_sec": 12345}, …] from throughput_*.csv"""

    barcode_distribution: dict[str, int] | None = None
    """{"barcode06": 124000, …} from barcode_alignment*.tsv"""

    cross_talk_candidates: list[CrossTalkCandidate] = field(default_factory=list)
    """Wells flagged as potential cross-talk sources (A9 milestone).
    Empty list when detection is skipped or no anomalies are found."""
    recovered_mutants: int | None = None
    total_mutants: int | None = None
    recovery_rate: float | None = None
    """Run-level reproduction (재현율) over the designed-mutant set: recovered /
    total designed mutants. ``None`` when the designed-mutant set was unavailable
    (callers render n/a, not 0%)."""


# ---------------------------------------------------------------------------
# Internal CSV / TSV parsers (best-effort, all errors silently absorbed)
# ---------------------------------------------------------------------------

# Candidate column names in order of preference ──────────────────────────────

_TIME_COLS = [
    "experiment_time (min)",
    "time_min",
    "Experiment Time (minutes)",
]
_ACTIVE_COLS = [
    "pore_active_%",
    "active_pores_%",
    "% Active Pores",
]
_READS_PER_SEC_COLS = [
    "reads_per_second",
    "Reads per second",
    "reads/s",
]
_BARCODE_COLS = [
    "barcode_arrangement",
    "barcode_name",
    "barcode",
]
_COUNT_COLS = [
    "num_reads",
    "read_count",
    "count",
]


def _first_col(header: list[str], candidates: list[str]) -> str | None:
    """Return the first candidate that appears in *header* (case-insensitive match)."""
    lower_map = {h.strip().lower(): h.strip() for h in header}
    for cand in candidates:
        if cand.strip().lower() in lower_map:
            return lower_map[cand.strip().lower()]
    return None


def _read_csv_rows(path: Path, delimiter: str = ",") -> tuple[list[str], list[dict[str, str]]]:
    """Read a CSV/TSV and return (header, rows). Never raises."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, rows
    except (OSError, csv.Error):
        return [], []


def _parse_pore_activity(run_dir: Path) -> float | None:
    """Return the last active-pore % value from pore_activity_*.csv, or None."""
    try:
        files = sorted(run_dir.glob("pore_activity_*.csv"))
        if not files:
            return None
        _, rows = _read_csv_rows(files[0])
        if not rows:
            return None
        last = rows[-1]
        header_keys = list(last.keys())
        col = _first_col(header_keys, _ACTIVE_COLS)
        if col is None:
            return None
        raw = last.get(col, "").strip()
        return float(raw) if raw else None
    except (ValueError, KeyError, IndexError):
        return None


def _parse_throughput(run_dir: Path) -> list[dict[str, float]] | None:
    """Parse throughput_*.csv into timeline points, or return None."""
    try:
        files = sorted(run_dir.glob("throughput_*.csv"))
        if not files:
            return None
        header, rows = _read_csv_rows(files[0])
        if not rows:
            return None
        time_col = _first_col(header, _TIME_COLS)
        reads_col = _first_col(header, _READS_PER_SEC_COLS)
        if time_col is None or reads_col is None:
            return None
        timeline: list[dict[str, float]] = []
        for row in rows:
            try:
                t_min = float(row.get(time_col, "").strip())
                rps = float(row.get(reads_col, "").strip())
                timeline.append({"time_h": round(t_min / 60.0, 4), "reads_per_sec": rps})
            except (ValueError, AttributeError):
                continue
        return timeline if timeline else None
    except (OSError, csv.Error):
        return None


def _parse_barcode_alignment(run_dir: Path) -> dict[str, int] | None:
    """Parse barcode_alignment*.tsv into {barcode: read_count}, or return None."""
    try:
        # Prefer the *_passed variant when available
        files = sorted(run_dir.glob("barcode_alignment_passed*.tsv"))
        if not files:
            files = sorted(run_dir.glob("barcode_alignment*.tsv"))
        if not files:
            return None
        header, rows = _read_csv_rows(files[0], delimiter="\t")
        if not rows:
            return None
        bc_col = _first_col(header, _BARCODE_COLS)
        cnt_col = _first_col(header, _COUNT_COLS)
        if bc_col is None or cnt_col is None:
            return None
        dist: dict[str, int] = {}
        for row in rows:
            try:
                bc = row.get(bc_col, "").strip()
                cnt_raw = row.get(cnt_col, "").strip()
                if bc and cnt_raw:
                    dist[bc] = int(float(cnt_raw))
            except (ValueError, AttributeError):
                continue
        return dist if dist else None
    except (OSError, csv.Error):
        return None


# ---------------------------------------------------------------------------
# Cross-talk detection (A9)
# ---------------------------------------------------------------------------

# 96-well plate: rows A-H (8), columns 1-12 (12)
_ROWS = "ABCDEFGH"
_COLS = tuple(range(1, 13))


def _well_neighbors(well: str) -> list[str]:
    """Return up to 4 orthogonal neighbors for an A1..H12 well label.

    Boundary wells have fewer neighbors (e.g. A1 has A2 and B1 only).
    Returns an empty list for unrecognised well labels.
    """
    if len(well) < 2:
        return []
    row_char = well[0].upper()
    try:
        col = int(well[1:])
    except ValueError:
        return []
    if row_char not in _ROWS or col not in _COLS:
        return []

    row_idx = _ROWS.index(row_char)
    neighbors: list[str] = []
    # Up / Down
    for dr in (-1, 1):
        nr = row_idx + dr
        if 0 <= nr < len(_ROWS):
            neighbors.append(f"{_ROWS[nr]}{col}")
    # Left / Right
    for dc in (-1, 1):
        nc = col + dc
        if nc in _COLS:
            neighbors.append(f"{row_char}{nc}")
    return neighbors


def detect_cross_talk(
    barcode_distribution: dict[str, int] | None,
    z_threshold: float = 2.5,
) -> list[CrossTalkCandidate]:
    """Detect wells with abnormally high read counts compared with their plate neighbors.

    The algorithm has two metrics per well:

    1. **neighbor_avg**: mean read count of orthogonal neighbors (up/down/left/right).
       Provides spatial context but is *not* used in the z-score formula.
    2. **z_score**: (well_count − population_mean) / population_std, where the
       population is the entire ``barcode_distribution``.  A well whose z_score
       exceeds ``z_threshold`` (default 2.5) is flagged as a candidate.

    Severity thresholds (z_score-based):
      - z > 4.0  → "high"
      - z > 3.0  → "medium"
      - z > 2.5  → "low"

    Parameters
    ----------
    barcode_distribution:
        Mapping of well/barcode label → read count.  Keys are expected to follow
        the ``A1``–``H12`` convention but any string key is tolerated (wells that
        don't match the 96-well grid will have an empty neighbor list and
        ``neighbor_avg`` of 0.0).
    z_threshold:
        Minimum z-score required to report a candidate.  Defaults to 2.5.

    Returns
    -------
    list[CrossTalkCandidate]
        Candidates sorted by z_score descending.  Empty list when
        ``barcode_distribution`` is ``None`` or has fewer than 5 entries.
    """
    if barcode_distribution is None or len(barcode_distribution) < 5:
        return []

    counts = list(barcode_distribution.values())
    mean = statistics.mean(counts)
    try:
        std = statistics.stdev(counts)
    except statistics.StatisticsError:
        return []
    if std == 0:
        return []

    candidates: list[CrossTalkCandidate] = []

    for well, count in barcode_distribution.items():
        z = (count - mean) / std
        if z <= z_threshold:
            continue

        # Neighbor average (informational)
        neighbor_labels = _well_neighbors(well)
        neighbor_counts = [
            barcode_distribution[nb] for nb in neighbor_labels if nb in barcode_distribution
        ]
        neighbor_avg = statistics.mean(neighbor_counts) if neighbor_counts else 0.0

        # Severity
        if z > 4.0:
            severity = "high"
        elif z > 3.0:
            severity = "medium"
        else:
            severity = "low"

        note = (
            f"Read count {count:,} is {z:.2f} SD above the plate mean "
            f"({mean:,.0f} ± {std:,.0f}); neighbor avg {neighbor_avg:,.0f}."
        )

        candidates.append(
            CrossTalkCandidate(
                well=well,
                custom_barcode=well,  # caller may override if a mapping is available
                read_count=count,
                neighbor_avg=round(neighbor_avg, 2),
                z_score=round(z, 4),
                severity=severity,
                note=note,
            )
        )

    candidates.sort(key=lambda c: c.z_score, reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_run_health(
    verdicts: list,
    replicates: list,
    run_meta: "NgsRunMeta | None",
    distribution_stats=None,
    designed_mutant_ids: frozenset[str] | None = None,
) -> RunHealthData:
    """Compute run-health metrics from pipeline artefacts.

    Parameters
    ----------
    verdicts:
        List of ``VerdictRecord`` objects from ``run_analyze``.
    replicates:
        List of ``ReplicateResult`` objects from ``run_analyze``.
    run_meta:
        ``NgsRunMeta`` discovered at analyze time, or ``None``.  When ``None``
        all MinKNOW-derived fields in the result are ``None``.
    distribution_stats:
        Pre-computed ``DistributionStats``, or ``None`` to recompute.
    """
    from kuma_core.mame.distribution import compute_distribution_stats

    # ── Distribution stats ────────────────────────────────────────────────
    if distribution_stats is None:
        file_sizes: list[float] = [v.translated.barcode.file_size_kb for v in verdicts]
        dist = compute_distribution_stats(file_sizes)
    else:
        dist = distribution_stats

    # ── Per-plate breakdown ───────────────────────────────────────────────
    plates: dict[str, dict[str, int]] = {}
    # Granular per-verdict-class keys (lower-cased class value: pass, ambiguous,
    # mixed, frameshift, many, lowdepth, no_call, wrong_aa) sum to "total". The
    # aggregate "fail" (everything that is not PASS/AMBIGUOUS) is retained for
    # backward-compatible consumers. "fallback" is a separate replicate-level
    # overlay and is NOT a verdict class.
    _granular_keys = [v.value.lower() for v in VerdictClass]
    for vr in verdicts:
        plate = vr.translated.barcode.native_barcode
        if plate not in plates:
            plates[plate] = {k: 0 for k in _granular_keys}
            plates[plate].update(fail=0, fallback=0, total=0)
        pb = plates[plate]
        pb["total"] += 1
        pb[vr.verdict.value.lower()] += 1
        if vr.verdict.value not in ("PASS", "AMBIGUOUS"):
            pb["fail"] += 1

    # ── Fallback tracking ─────────────────────────────────────────────────
    for rr in replicates:
        if rr.selected_plate and not rr.failed and getattr(rr, "is_fallback", False):
            pb = plates.get(rr.selected_plate)
            if pb is not None:
                pb["fallback"] += 1

    # ── MinKNOW CSV parsing (best-effort) ─────────────────────────────────
    pore_yield_pct: float | None = None
    throughput_timeline: list[dict[str, float]] | None = None
    barcode_distribution: dict[str, int] | None = None

    if run_meta is not None and run_meta.raw_run_dir is not None:
        run_dir = Path(run_meta.raw_run_dir)
        if run_dir.is_dir():
            # These MinKNOW sidecar CSV/TSV summaries are independent files.
            # Parse them concurrently so large raw-run metadata does not delay
            # the health panel behind three serial file scans.
            with ThreadPoolExecutor(max_workers=3) as pool:
                pore_future = pool.submit(_parse_pore_activity, run_dir)
                throughput_future = pool.submit(_parse_throughput, run_dir)
                barcode_future = pool.submit(_parse_barcode_alignment, run_dir)
                pore_yield_pct = pore_future.result()
                throughput_timeline = throughput_future.result()
                barcode_distribution = barcode_future.result()

    # ── Cross-talk detection (A9) ─────────────────────────────────────────
    cross_talk_candidates = detect_cross_talk(barcode_distribution)

    # ── Recovery (재현율) overlay — designed-set dependent ─────────────────
    _recovery = compute_recovery(replicates, designed_mutant_ids)

    return RunHealthData(
        per_plate_summary=plates,
        file_size_distribution=dist.file_size_kb,
        suggested_cutoff_kb=dist.suggested_cutoff_kb,
        bimodal=dist.bimodal,
        suggested_method=dist.suggested_method,
        pore_yield_pct=pore_yield_pct,
        throughput_timeline=throughput_timeline,
        barcode_distribution=barcode_distribution,
        cross_talk_candidates=cross_talk_candidates,
        recovered_mutants=_recovery.recovered_mutants if _recovery else None,
        total_mutants=_recovery.total_mutants if _recovery else None,
        recovery_rate=_recovery.recovery_rate if _recovery else None,
    )


__all__ = [
    "CrossTalkCandidate",
    "RunHealthData",
    "build_run_health",
    "detect_cross_talk",
    "_well_neighbors",
]
