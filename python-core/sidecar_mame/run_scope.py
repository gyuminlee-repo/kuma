"""Serialize cache consumers and keep independent run artefacts disjoint."""

from collections.abc import Callable
from pathlib import Path
from tempfile import mkdtemp
from threading import Lock
from typing import Literal

from pydantic import BaseModel

from sidecar_mame.core import get_state, run_scope


class RunScopeParams(BaseModel):
    run_scope: Literal["primary", "resequence"] = "primary"


_operation_lock = Lock()
_CACHE_METHODS = frozenset({
    "analyze", "load_analyze_result", "apply_selection_overrides",
    "export_excel", "get_plate_data", "export_janus_mapping",
    "export_janus_mapping_dry_run", "export_run_report", "get_run_health",
    "reset_state", "mame.run_combinatorial_demux",
})


def call_in_run_scope(method: str, handler: Callable, params: dict) -> dict:
    """One cache operation owns the sidecar until it finishes or fails.

    A busy request is rejected, never queued to run against a later cache.
    Cancel still terminates the process through the host, outside this lock.
    """
    scope = RunScopeParams.model_validate(params).run_scope
    if method not in _CACHE_METHODS:
        return handler(params)
    if not _operation_lock.acquire(blocking=False):
        raise RuntimeError("MAME analysis or export is busy. Finish or cancel it first.")
    token = run_scope.set(scope)
    try:
        request = dict(params)
        snapshot = request.pop("result_snapshot", None)
        if method == "analyze" and scope == "resequence":
            output = Path(request["output"]).resolve()
            if not output.parent.is_dir():
                raise ValueError("Resequencing output parent must be an existing directory")
            # Always a new directory, even when the operator picks the primary
            # destination. Demux, workbook, picks and manifests stay together.
            folder = Path(mkdtemp(prefix="resequence-", dir=output.parent))
            request["output"] = str(folder / output.name)
            request["demux_output_dir"] = str(folder / "demux_filtered")
        # Restore and re-export must not point at the other run's workbook or
        # siblings (including the primary pick list).
        target = request.get("output_path") if method == "load_analyze_result" else request.get("output")
        other_token = run_scope.set("primary" if scope == "resequence" else "resequence")
        try:
            other_path = get_state().last_output_path
        finally:
            run_scope.reset(other_token)
        if target and other_path and Path(target).resolve().parent == Path(other_path).resolve().parent:
            raise ValueError("Independent runs must use separate output directories")
        if snapshot is not None:
            from sidecar_mame.handlers.load import LoadAnalyzeResultParams, handle_load_analyze_result

            restored = LoadAnalyzeResultParams.model_validate(snapshot)
            if other_path and Path(restored.output_path).resolve().parent == Path(other_path).resolve().parent:
                raise ValueError("Independent runs must use separate output directories")
            handle_load_analyze_result(restored.model_dump())
        return handler(request)
    finally:
        run_scope.reset(token)
        _operation_lock.release()
