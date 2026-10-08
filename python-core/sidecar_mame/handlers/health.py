"""``get_run_health`` JSON-RPC handler (A8 — run health panel)."""

from __future__ import annotations

from sidecar_mame.core import get_state, _state_lock


def handle_get_run_health(_params: dict) -> dict:
    """Compute and return ``RunHealthData`` from the cached analyze artefacts.

    Raises ``RuntimeError`` (-32002) when no analysis has been run yet.
    """
    from typing import cast

    from kuma_core.mame.health import build_run_health
    from kuma_core.mame.ingest.run_meta import NgsRunMeta

    with _state_lock:
        state = get_state()
        verdicts = state.last_verdicts
        replicates = state.last_replicates
        run_meta = cast("NgsRunMeta | None", state.last_run_meta)
        designed_mutant_ids = state.last_designed_mutant_ids

    if verdicts is None or replicates is None:
        raise RuntimeError("No analysis results available. Run 'analyze' first.")

    health = build_run_health(
        verdicts, replicates, run_meta, designed_mutant_ids=designed_mutant_ids
    )

    # Serialise cross_talk_candidates (A9 — always a list, may be empty)
    cross_talk_payload = [
        {
            "well": c.well,
            "custom_barcode": c.custom_barcode,
            "read_count": c.read_count,
            "neighbor_avg": c.neighbor_avg,
            "z_score": c.z_score,
            "severity": c.severity,
            "note": c.note,
        }
        for c in health.cross_talk_candidates
    ]

    return {
        "per_plate_summary": health.per_plate_summary,
        "file_size_distribution": health.file_size_distribution,
        "suggested_cutoff_kb": health.suggested_cutoff_kb,
        "bimodal": health.bimodal,
        "suggested_method": health.suggested_method,
        "pore_yield_pct": health.pore_yield_pct,
        "throughput_timeline": health.throughput_timeline,
        "barcode_distribution": health.barcode_distribution,
        "cross_talk_candidates": cross_talk_payload,
        # "not_run" | "insufficient_data" | "ok", an empty candidate list means
        # "no anomalies" only when this is "ok".
        "cross_talk_status": health.cross_talk_status,
        "recovered_mutants": health.recovered_mutants,
        "total_mutants": health.total_mutants,
        "recovery_rate": health.recovery_rate,
    }


__all__ = ["handle_get_run_health"]
