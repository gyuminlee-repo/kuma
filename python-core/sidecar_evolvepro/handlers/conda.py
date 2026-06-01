"""Conda environment management JSON-RPC handlers.

Ported from evolvepro-gui/python-core/sidecar/handlers.py.
"""
from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from typing import Any

from sidecar_evolvepro.models import (
    CondaCreateEnvResponse,
    CondaStatusResponse,
    CondaVerifyResponse,
    EnvStatusResponse,
)

from kuma_core.shared import conda_setup as _conda


def handle_conda_detect(params: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG001
    """Return installed/version/path of the system conda."""
    status = _conda.detect_conda()
    return CondaStatusResponse(
        installed=status.installed,
        conda_exe=status.conda_exe,
        version=status.version,
    ).model_dump()


def handle_conda_detect_env(params: dict[str, Any]) -> dict[str, Any]:
    """Check whether the named EVOLVEpro conda env exists and list package versions."""
    env_name = params.get("env_name", "evolvepro")
    status = _conda.detect_evolvepro_env(env_name=env_name)
    return EnvStatusResponse(
        exists=status.exists,
        env_path=status.env_path,
        packages=status.packages,
    ).model_dump()


def handle_conda_verify_env(params: dict[str, Any]) -> dict[str, Any]:
    """Run import test (evolvepro, esm, Bio) inside the named env."""
    env_name = params.get("env_name", "evolvepro")
    conda_exe = params.get("conda_exe", "")
    result = _conda.verify_env(env_name=env_name, conda_exe=conda_exe)
    return CondaVerifyResponse(ok=result["ok"], error=result.get("error")).model_dump()


def handle_conda_create_env(
    params: dict[str, Any],
    progress_send: Callable[[str, str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Start conda env creation in a background thread and return immediately.

    Progress streams via progress_send(run_id, stage, current, total, message).
    Terminal events use stage "complete" (ok) or "create_error" (failure) so the
    frontend can distinguish them from intermediate generator stages.
    """
    env_name = params.get("env_name", "evolvepro")
    conda_exe = params.get("conda_exe", "")
    python_version = params.get("python_version", "3.11")

    def _run() -> None:
        try:
            for event in _conda.create_env_stream(
                env_name=env_name,
                conda_exe=conda_exe,
                python_version=python_version,
            ):
                if progress_send is not None:
                    progress_send(
                        "conda_create",
                        event.get("stage", ""),
                        event.get("current", 0),
                        event.get("total", 0),
                        event.get("line", ""),
                        event.get("current_package"),
                        event.get("indeterminate", False),
                    )
            if progress_send is not None:
                progress_send("conda_create", "complete", 0, 0, "")
        except BaseException as exc:  # noqa: BLE001
            # Broad catch is intentional: ANY uncaught exception in this
            # background thread (UnicodeDecodeError, OSError, MemoryError, etc.)
            # would silently kill the reader, leaving the conda child blocked
            # on a full stdout PIPE buffer (idle hang with no GUI feedback).
            # Forward full traceback so the frontend can show actionable error.
            tb = traceback.format_exc()
            if progress_send is not None:
                progress_send(
                    "conda_create",
                    "create_error",
                    0,
                    0,
                    f"sidecar reader crashed: {exc!r}\n{tb}",
                )

    threading.Thread(target=_run, daemon=True).start()
    return CondaCreateEnvResponse(ok=True).model_dump()


def handle_conda_cancel_create_env(params: dict[str, Any]) -> dict[str, Any]:
    """Cancel a running conda env creation. Best-effort kill + partial env cleanup."""
    env_name = params.get("env_name", "evolvepro")
    conda_exe = params.get("conda_exe", "")
    return _conda.cancel_create_env(env_name=env_name, conda_exe=conda_exe)


def handle_conda_delete_env(params: dict[str, Any]) -> dict[str, Any]:
    """Remove the named conda env."""
    env_name = params.get("env_name", "evolvepro")
    conda_exe = params.get("conda_exe", "")
    ok = _conda.delete_env(env_name=env_name, conda_exe=conda_exe)
    return {"ok": ok}


def handle_conda_init_shell(params: dict[str, Any]) -> dict[str, Any]:
    """Run `conda init <shell>` to register conda activation in user shell.

    Modifies user shell profile permanently (PowerShell $PROFILE, ~/.bashrc, etc.).
    UI must confirm with user before calling.
    """
    conda_exe = params.get("conda_exe", "")
    shell = params.get("shell")
    return _conda.init_shell(conda_exe=conda_exe, shell=shell)


__all__ = [
    "handle_conda_detect",
    "handle_conda_detect_env",
    "handle_conda_verify_env",
    "handle_conda_create_env",
    "handle_conda_cancel_create_env",
    "handle_conda_delete_env",
    "handle_conda_init_shell",
]
