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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kuma_core.mame.ingest.run_meta import NgsRunMeta


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RunHealthData:
    """Lightweight run-health metrics for the frontend health panel.

    All MinKNOW-derived fields (``pore_yield_pct``, ``throughput_timeline``,
    ``barcode_distribution``) are ``None`` when ``run_meta.raw_run_dir`` is
    absent or the corresponding CSV files cannot be parsed.
    """

    # ── Per-plate verdict breakdown ───────────────────────────────────────
    per_plate_summary: dict[str, dict[str, int]]
    """Keys: plate (e.g. "NB01") → {"pass", "ambiguous", "fail", "fallback", "total"}"""

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
# Public API
# ---------------------------------------------------------------------------


def build_run_health(
    verdicts: list,
    replicates: list,
    run_meta: "NgsRunMeta | None",
    distribution_stats=None,
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
    for vr in verdicts:
        plate = vr.translated.barcode.native_barcode
        if plate not in plates:
            plates[plate] = {"pass": 0, "ambiguous": 0, "fail": 0, "fallback": 0, "total": 0}
        pb = plates[plate]
        pb["total"] += 1
        verdict_val = vr.verdict.value
        if verdict_val == "PASS":
            pb["pass"] += 1
        elif verdict_val == "AMBIGUOUS":
            pb["ambiguous"] += 1
        else:
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
            pore_yield_pct = _parse_pore_activity(run_dir)
            throughput_timeline = _parse_throughput(run_dir)
            barcode_distribution = _parse_barcode_alignment(run_dir)

    return RunHealthData(
        per_plate_summary=plates,
        file_size_distribution=dist.file_size_kb,
        suggested_cutoff_kb=dist.suggested_cutoff_kb,
        bimodal=dist.bimodal,
        suggested_method=dist.suggested_method,
        pore_yield_pct=pore_yield_pct,
        throughput_timeline=throughput_timeline,
        barcode_distribution=barcode_distribution,
    )


__all__ = ["RunHealthData", "build_run_health"]
