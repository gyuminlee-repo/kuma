"""JSON-RPC handlers for EVOLVEpro GUI wrapper.

KUMA does not bundle EVOLVEpro. These handlers shell out to the user's
own conda installation. Users accept the MIT TLO Internal Research EULA
directly when installing EVOLVEpro.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kuma_core.kuro import evolvepro_runner
from sidecar_kuro import core
from sidecar_kuro.models import (
    EvolveProCancelRequest,
    EvolveProDetectResponse,
    EvolveProRunRequest,
    EvolveProRunStartResponse,
)


def handle_evolvepro_detect(params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Detect user's EVOLVEpro conda environment."""
    status = evolvepro_runner.detect_env()
    response = EvolveProDetectResponse(
        env_found=status.env_found,
        env_path=status.env_path,
        evolvepro_version=status.evolvepro_version,
        weights_cached=status.weights_cached,
        weights_path=status.weights_path,
    )
    return response.model_dump()


def handle_evolvepro_run(
    params: dict[str, Any],
    progress_send: Callable[[str, str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Start EVOLVEpro subprocess. Returns run_id; progress streams over notifications.

    progress_send: optional callable injected by dispatcher to publish progress.
    Signature: progress_send(run_id, stage, current, total, message) -> None.
    """
    req = EvolveProRunRequest(**params)

    callback: Callable[[str, str, int, int, str], None] | None = None
    if progress_send is not None:
        _send = progress_send

        def _cb(run_id: str, stage: str, current: int, total: int, message: str) -> None:
            _send(run_id, stage, current, total, message)

        callback = _cb

    handle = evolvepro_runner.run(
        input_csv=req.input_csv,
        wt_sequence=req.wt_sequence,
        n_rounds=req.n_rounds,
        output_dir=req.output_dir,
        top_n=req.top_n,
        env_name=req.env_name,
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


__all__ = [
    "handle_evolvepro_detect",
    "handle_evolvepro_run",
    "handle_evolvepro_cancel",
]
