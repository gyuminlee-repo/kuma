"""JSON-RPC dispatcher for the EVOLVEpro sidecar.

Ported from evolvepro-gui/python-core/sidecar/dispatcher.py. Preserves the
progress-injection wiring (evolvepro.run + conda.create_env stream over
method="progress" notifications) which is the load-bearing difference from the
kuro sidecar's _ok/_error model. The ready emit + main(emit_ready=...) shape
mirrors sidecar_kuro for host consistency.
"""
from __future__ import annotations

import json
import sys
import threading
from typing import Any

from sidecar_evolvepro.core import _send
from sidecar_evolvepro.handlers.conda import (
    handle_conda_cancel_create_env,
    handle_conda_create_env,
    handle_conda_delete_env,
    handle_conda_detect,
    handle_conda_detect_env,
    handle_conda_init_shell,
    handle_conda_verify_env,
)
from sidecar_evolvepro.handlers.esm2 import handle_esm2_recommend
from sidecar_evolvepro.handlers.evolvepro import (
    handle_evolvepro_cancel,
    handle_evolvepro_detect,
    handle_evolvepro_run,
)


def _send_evolvepro_progress(
    run_id: str, stage: str, current: int, total: int, message: str
) -> None:
    _send(
        {
            "jsonrpc": "2.0",
            "method": "progress",
            "params": {
                "type": "evolvepro_progress",
                "run_id": run_id,
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
            },
        }
    )


def _evolvepro_run_with_progress(params: dict[str, Any]) -> dict[str, Any]:
    return handle_evolvepro_run(params, progress_send=_send_evolvepro_progress)


def _send_conda_create_progress(
    run_id: str,
    stage: str,
    current: int,
    total: int,
    message: str,
    current_package: str | None = None,
    indeterminate: bool = False,
) -> None:
    _send(
        {
            "jsonrpc": "2.0",
            "method": "progress",
            "params": {
                "type": "conda_create_progress",
                "run_id": run_id,
                "stage": stage,
                "current": current,
                "total": total,
                "message": message,
                "current_package": current_package,
                "indeterminate": indeterminate,
            },
        }
    )


def _conda_create_env_with_progress(params: dict[str, Any]) -> dict[str, Any]:
    return handle_conda_create_env(params, progress_send=_send_conda_create_progress)


_METHODS = {
    "ping": lambda _: {"ok": True},
    "esm2.recommend": handle_esm2_recommend,
    "evolvepro.detect": handle_evolvepro_detect,
    "evolvepro.run": _evolvepro_run_with_progress,
    "evolvepro.cancel": handle_evolvepro_cancel,
    "conda.detect": handle_conda_detect,
    "conda.detect_env": handle_conda_detect_env,
    "conda.verify_env": handle_conda_verify_env,
    "conda.create_env": _conda_create_env_with_progress,
    "conda.cancel_create_env": handle_conda_cancel_create_env,
    "conda.delete_env": handle_conda_delete_env,
    "conda.init_shell": handle_conda_init_shell,
}

_ASYNC_METHODS = {"evolvepro.run", "conda.create_env"}


def _dispatch_one(line: str) -> None:
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return
    method = msg.get("method")
    params = msg.get("params", {})
    msg_id = msg.get("id")
    handler = _METHODS.get(method)
    if handler is None:
        _send(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": "method not found"},
            }
        )
        return

    def run() -> None:
        try:
            result = handler(params)
            _send({"jsonrpc": "2.0", "id": msg_id, "result": result})
        except Exception as exc:  # noqa: BLE001
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32603, "message": str(exc)},
                }
            )

    if method in _ASYNC_METHODS:
        threading.Thread(target=run, daemon=True).start()
    else:
        run()


def main(emit_ready: bool = True) -> None:
    """Read newline-delimited JSON-RPC requests from stdin and dispatch.

    `emit_ready` defaults to True for direct invocation / tests. The frozen
    entry script sets it False because it emits ready before heavy imports.
    """
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    if emit_ready:
        _send({"jsonrpc": "2.0", "method": "ready", "params": {}})

    for line in sys.stdin:
        _dispatch_one(line.strip())


if __name__ == "__main__":
    main()
