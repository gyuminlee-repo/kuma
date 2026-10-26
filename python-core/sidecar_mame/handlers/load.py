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

from kuma_core.mame.export.analysis_meta import AnalysisConditions
from sidecar_mame.core import (
    _ALLOWED_EXCEL_EXTENSIONS,
    _validate_reloaded_output_path,
    set_last_analyze,
)
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
    barcode_prefix_note: str | None = None
    analysis_conditions: AnalysisConditions | None = None
    # Distinct designed mutant_ids (sorted list in the analyze response). Absent
    # in pre-recovery workspaces → None → recovery renders "n/a", not "0%".
    designed_mutant_ids: list[str] | None = None
    # Accepted so Phase 2 can persist + replay the analyze response verbatim,
    # but NOT stored: SidecarState holds no summary/distribution_stats and
    # get_plate_data does not read them. ``extra="ignore"`` would drop unknown
    # keys anyway; these are declared for an explicit, self-documenting contract.
    summary: dict[str, Any] | None = None
    distribution_stats: dict[str, Any] | None = None
    # Thresholds the original run was judged against (analyze response
    # ``compare_params``). Same treatment as the two above: accepted so the
    # analyze response can be replayed verbatim, but NOT stored, because
    # re-injecting state does not re-run the classifier and SidecarState holds
    # no CompareParams. Declared rather than left to ``extra="ignore"`` so a
    # caller replaying a full response can see the key is understood: silence
    # here reads as "this key is unknown", which is how a replay starts
    # dropping fields it was meant to carry.
    compare_params: dict[str, Any] | None = None


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


def _reloaded_output_path(raw: str) -> str:
    """Validate the replayed workbook path before it becomes a write target.

    ``output_path`` arrives in the payload and goes straight into
    ``state.last_output_path``, which ``apply_selection_overrides`` later hands
    to ``_rewrite_result_workbook``. Two RPCs with no file argument between them
    therefore wrote an ``.xlsx`` wherever the payload pointed. The same symlink,
    traversal and extension rules every other MAME output path goes through now
    apply here, so the replayed path can only name a workbook.

    Blank is kept as blank rather than rejected. The restore that rebuilds state
    from the input snapshot alone sends ``""`` when the snapshot records no
    output path (``injectSnapshotResultsIntoSidecar`` in
    ``src/hooks/useAutosaveHydration.ts`` passes ``fromPortablePath(..., "")``),
    and an empty ``last_output_path`` is already the "nothing to rewrite" case
    every writer checks for. Refusing it would break that restore and guard
    nothing: no path means no write.

    The returned string is the resolved path, which is the form
    ``handle_analyze`` stores, so a reload leaves state looking exactly as the
    original run left it.
    """
    if not raw or not raw.strip():
        return ""
    return str(
        _validate_reloaded_output_path(raw, allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS)
    )


def handle_load_analyze_result(params: dict) -> dict:
    """Re-inject a serialized analyze payload into ``SidecarState``.

    Returns an ack with the restored verdict count. After a successful call,
    ``get_plate_data`` returns the same result as immediately post-analyze.
    """
    p = LoadAnalyzeResultParams.model_validate(params)

    verdicts = [_deserialize_verdict(v) for v in p.verdicts]
    replicates = [_deserialize_replicate(r) for r in p.replicates]
    run_meta = _rebuild_run_meta(p.run_meta)
    designed = (
        frozenset(p.designed_mutant_ids)
        if p.designed_mutant_ids is not None
        else None
    )

    set_last_analyze(
        verdicts,
        replicates,
        _reloaded_output_path(p.output_path),
        run_meta=run_meta,
        designed_mutant_ids=designed,
        barcode_prefix_note=p.barcode_prefix_note,
        analysis_conditions=p.analysis_conditions,
    )

    return {
        "restored": True,
        "verdict_count": len(verdicts),
        "replicate_count": len(replicates),
    }


__all__ = ["LoadAnalyzeResultParams", "handle_load_analyze_result"]
