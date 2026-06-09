"""``load_analyze_result`` JSON-RPC handler.

Phase 1 of MAME analyze-result persistence. The analyze artefacts
(``verdicts`` / ``replicates`` / ``run_meta``) live only in the sidecar's
in-memory ``SidecarState`` and are lost when the process exits on app restart.
This handler re-injects a previously-serialized analyze payload back into
``SidecarState`` so that ``get_plate_data`` / ``export_excel`` /
``export_janus_mapping`` / ``export_run_report`` work without re-running the
multi-minute pipeline.

The accepted payload mirrors the ``analyze`` response shape exactly
(``_serialize_verdict`` / ``_serialize_replicate``) and is reconstructed via
their inverses (``_deserialize_verdict`` / ``_deserialize_replicate``), so the
round-trip is lossless for every field carried by the analyze response (and
thus every field the downstream consumers read; ``consensus_seq`` is neither
serialized by analyze nor consumed by any export module).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from sidecar_mame.core import set_last_analyze
from sidecar_mame.handlers.analyze import (
    _deserialize_replicate,
    _deserialize_verdict,
)


class LoadAnalyzeResultParams(BaseModel):
    """Parameters for the ``load_analyze_result`` RPC method.

    Field shapes mirror the ``analyze`` response: ``verdicts`` and
    ``replicates`` are the same dicts emitted by ``_serialize_verdict`` /
    ``_serialize_replicate``; ``output_path`` is the cached Excel path; and
    ``run_meta`` is the flat ``NgsRunMeta`` field map (all-optional).

    The dict entries are validated structurally at the dataclass-rebuild step
    rather than via nested Pydantic models, keeping this in lockstep with the
    hand-written serializers (single source of truth = analyze.py).
    """

    model_config = ConfigDict(extra="ignore")

    verdicts: list[dict[str, Any]]
    replicates: list[dict[str, Any]]
    output_path: str
    run_meta: dict[str, Any] | None = None
    # Accepted so Phase 2 can persist + replay the analyze response verbatim,
    # but NOT stored: SidecarState holds no summary/distribution_stats and
    # get_plate_data does not read them. ``extra="ignore"`` would drop unknown
    # keys anyway; these are declared for an explicit, self-documenting contract.
    summary: dict[str, Any] | None = None
    distribution_stats: dict[str, Any] | None = None


def _rebuild_run_meta(run_meta: dict[str, Any] | None) -> Any | None:
    """Rebuild an ``NgsRunMeta`` from its flat field map, or ``None``."""
    if not run_meta:
        return None
    from kuma_core.mame.ingest.run_meta import NgsRunMeta

    fields = (
        "instrument",
        "position",
        "flow_cell_id",
        "sample_id",
        "kit",
        "started",
        "basecalling_enabled",
        "raw_run_dir",
    )
    return NgsRunMeta(**{f: run_meta.get(f) for f in fields})


def handle_load_analyze_result(params: dict) -> dict:
    """Re-inject a serialized analyze payload into ``SidecarState``.

    Returns an ack with the restored verdict count. After a successful call,
    ``get_plate_data`` returns the same result as immediately post-analyze.
    """
    p = LoadAnalyzeResultParams.model_validate(params)

    verdicts = [_deserialize_verdict(v) for v in p.verdicts]
    replicates = [_deserialize_replicate(r) for r in p.replicates]
    run_meta = _rebuild_run_meta(p.run_meta)

    set_last_analyze(verdicts, replicates, p.output_path, run_meta=run_meta)

    return {
        "restored": True,
        "verdict_count": len(verdicts),
        "replicate_count": len(replicates),
    }


__all__ = ["LoadAnalyzeResultParams", "handle_load_analyze_result"]
