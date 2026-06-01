"""EVOLVEpro run/detect/cancel/embedding_cache_status JSON-RPC handlers.

Ported from evolvepro-gui/python-core/sidecar/handlers.py. KUMA does not bundle
EVOLVEpro; these handlers shell out to the user's own conda installation.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sidecar_evolvepro import core
from sidecar_evolvepro.models import (
    EvolveProCancelRequest,
    EvolveProDetectResponse,
    EvolveProEmbeddingCacheStatusRequest,
    EvolveProEmbeddingCacheStatusResponse,
    EvolveProRunRequest,
    EvolveProRunStartResponse,
)

from kuma_core.evolvepro import embedding_cache, runner as evolvepro_runner, timing
from kuma_core.shared import system_info


def handle_evolvepro_detect(params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Detect user's EVOLVEpro conda environment."""
    status = evolvepro_runner.detect_env()
    response = EvolveProDetectResponse(
        env_found=status.env_found,
        env_path=status.env_path,
        evolvepro_version=status.evolvepro_version,
        weights_cached=status.weights_cached,
        weights_path=status.weights_path,
        cached_models=status.cached_models,
    )
    return response.model_dump()


def handle_evolvepro_run(
    params: dict[str, Any],
    progress_send: Callable[[str, str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Start EVOLVEpro subprocess. Returns run_id; progress streams over notifications."""
    req = EvolveProRunRequest(**params)

    callback: Callable[[str, str, int, int, str], None] | None = None
    if progress_send is not None:
        _send = progress_send

        def _cb(run_id: str, stage: str, current: int, total: int, message: str) -> None:
            _send(run_id, stage, current, total, message)

        callback = _cb

    handle = evolvepro_runner.run(
        input_csv=req.input_csv,
        round_files=req.round_files,
        wt_sequence=req.wt_sequence,
        wt_fasta=req.wt_fasta,
        n_rounds=req.n_rounds,
        output_dir=req.output_dir,
        top_n=req.top_n,
        env_name=req.env_name,
        esm2_model_id=req.esm2_model_id,
        progress_callback=callback,
    )
    with core._state_lock:
        core._state.evolvepro_runs[handle.run_id] = handle
    return EvolveProRunStartResponse(run_id=handle.run_id).model_dump()


def handle_evolvepro_cancel(params: dict[str, Any]) -> dict[str, Any]:
    """Cancel a running EVOLVEpro subprocess."""
    req = EvolveProCancelRequest(**params)
    with core._state_lock:
        handle = core._state.evolvepro_runs.get(req.run_id)
    if handle is None:
        return {"ok": False, "reason": "run_id not found"}
    ok = evolvepro_runner.cancel(handle)
    return {"ok": ok}


def handle_evolvepro_embedding_cache_status(params: dict[str, Any]) -> dict[str, Any]:
    """Return embedding cache hit status and time estimate for a given wt_sequence + model."""
    req = EvolveProEmbeddingCacheStatusRequest(**params)

    cache_dir = embedding_cache.resolve_cache_dir()
    cached = embedding_cache.is_cached(cache_dir, req.wt_sequence, req.esm2_model_id)
    wl = timing.workload(req.wt_sequence)

    if cached:
        estimate_seconds = None
        estimate_basis = None
    else:
        hw = system_info.recommend_esm2_model()
        gpu = hw["gpu_available"]
        measured = embedding_cache.read_throughput(
            cache_dir,
            embedding_cache.machine_fingerprint(),
            req.esm2_model_id,
        )
        est = timing.estimate_seconds(
            wl,
            model_id=req.esm2_model_id,
            gpu=gpu,
            measured_tok_per_sec=measured,
        )
        estimate_seconds = est["seconds"]
        estimate_basis = est["basis"]

    return EvolveProEmbeddingCacheStatusResponse(
        cached=cached,
        n_variants=wl["n_variants"],
        estimate_seconds=estimate_seconds,
        estimate_basis=estimate_basis,
        cache_dir=str(cache_dir),
    ).model_dump()


__all__ = [
    "handle_evolvepro_detect",
    "handle_evolvepro_run",
    "handle_evolvepro_cancel",
    "handle_evolvepro_embedding_cache_status",
]
