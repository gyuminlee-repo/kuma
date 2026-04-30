"""Build RunReportData from cached analyze artefacts (A14 milestone).

``build_run_report_data`` accepts the raw VerdictRecord / ReplicateResult
lists held in SidecarState and derives all statistics needed by the HTML
renderer. Distribution stats are recomputed here so this module has no
dependency on the R6-owned analyze handler.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kuma_core.mame.ingest.run_meta import NgsRunMeta


@dataclass
class PlateBreakdown:
    """Per-plate verdict counts."""

    plate: str
    total: int = 0
    pass_count: int = 0
    ambiguous_count: int = 0
    fail_count: int = 0
    fallback_count: int = 0


@dataclass
class RunReportData:
    """Unified run report payload.

    Aggregates NgsRunMeta + analysis artefacts into a single flat dataclass
    that the HTML renderer can consume without further computation.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    project_name: str | None
    analyzed_at: str  # ISO 8601

    # ── Run metadata (from MinKNOW) ───────────────────────────────────────
    run_meta: "NgsRunMeta | None"

    # ── Top-level verdict summary ─────────────────────────────────────────
    total_wells: int
    pass_count: int
    ambiguous_count: int
    fail_count: int
    fallback_count: int

    # ── Plate breakdown (NB01, NB02, …) ──────────────────────────────────
    per_plate: dict[str, PlateBreakdown] = field(default_factory=dict)

    # ── Final 96-well selection ───────────────────────────────────────────
    final_96_filled: int = 0  # distinct mutants with a selected plate

    # ── Distribution stats ────────────────────────────────────────────────
    file_size_distribution: dict[str, float] = field(default_factory=dict)
    suggested_cutoff_kb: float = 50.0
    bimodal: bool = False
    suggested_method: str = "fixed_50"

    # ── Tool provenance ───────────────────────────────────────────────────
    kuma_version: str = ""


def build_run_report_data(
    verdicts: list,
    replicates: list,
    run_meta: "NgsRunMeta | None" = None,
    project_name: str | None = None,
    kuma_version: str = "",
) -> RunReportData:
    """Derive RunReportData from raw pipeline artefacts.

    Parameters
    ----------
    verdicts:
        List of ``VerdictRecord`` objects from ``run_analyze``.
    replicates:
        List of ``ReplicateResult`` objects from ``run_analyze``.
    run_meta:
        ``NgsRunMeta`` discovered at analyze time, or ``None``.
    project_name:
        Display name for the project (typically from Tauri project context).
    kuma_version:
        ``KUMA_VERSION`` string from ``kuma_core.shared.version``.
    """
    from kuma_core.mame.distribution import compute_distribution_stats

    analyzed_at = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )

    # ── Distribution (recomputed to avoid R6 dependency) ──────────────────
    file_sizes: list[float] = [
        v.translated.barcode.file_size_kb for v in verdicts
    ]
    dist = compute_distribution_stats(file_sizes)

    # ── Per-plate breakdown ───────────────────────────────────────────────
    plates: dict[str, PlateBreakdown] = {}
    for vr in verdicts:
        plate = vr.translated.barcode.native_barcode
        if plate not in plates:
            plates[plate] = PlateBreakdown(plate=plate)
        pb = plates[plate]
        pb.total += 1
        verdict_val = vr.verdict.value
        if verdict_val == "PASS":
            pb.pass_count += 1
        elif verdict_val == "AMBIGUOUS":
            pb.ambiguous_count += 1
        else:
            pb.fail_count += 1

    # ── Fallback tracking (from replicates) ──────────────────────────────
    fallback_total = 0
    final_96_filled = 0
    for rr in replicates:
        if rr.selected_plate and not rr.failed:
            final_96_filled += 1
            if getattr(rr, "is_fallback", False):
                fallback_total += 1
                pb = plates.get(rr.selected_plate)
                if pb is not None:
                    pb.fallback_count += 1

    # ── Top-level counts ──────────────────────────────────────────────────
    total_wells = len(verdicts)
    pass_count = sum(1 for v in verdicts if v.verdict.value == "PASS")
    ambiguous_count = sum(1 for v in verdicts if v.verdict.value == "AMBIGUOUS")
    fail_count = total_wells - pass_count - ambiguous_count

    return RunReportData(
        project_name=project_name,
        analyzed_at=analyzed_at,
        run_meta=run_meta,
        total_wells=total_wells,
        pass_count=pass_count,
        ambiguous_count=ambiguous_count,
        fail_count=fail_count,
        fallback_count=fallback_total,
        per_plate=plates,
        final_96_filled=final_96_filled,
        file_size_distribution=dist.file_size_kb,
        suggested_cutoff_kb=dist.suggested_cutoff_kb,
        bimodal=dist.bimodal,
        suggested_method=dist.suggested_method,
        kuma_version=kuma_version,
    )


__all__ = ["RunReportData", "PlateBreakdown", "build_run_report_data"]
