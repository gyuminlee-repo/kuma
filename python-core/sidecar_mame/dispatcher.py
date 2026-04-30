"""JSON-RPC dispatcher: method registry, main loop, parent watchdog."""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback

from sidecar_mame.core import (
    _append_crash_log,
    _error,
    _ok,
    _send,
    logger,
)
from sidecar_mame.handlers.analyze import (
    handle_analyze,
    handle_validate_inputs,
)
from sidecar_mame.handlers.export import (
    handle_export_excel,
    handle_export_janus_mapping,
    handle_get_plate_data,
)
from sidecar_mame.handlers.kuma_meta import handle_read_kuma_meta
from sidecar_mame.handlers.report import handle_export_run_report
from sidecar_mame.handlers.demux import handle_demux_and_filter
from sidecar_mame.handlers.health import handle_get_run_health

# Phase A handler registry.
# ``translate`` is deferred to Phase B per the reconciled scope.
# NOTE: ``export_run_report`` is owned by A14 — do not rename or remove.
_METHODS = {
    "ping": lambda _: {"ok": True},
    "analyze": handle_analyze,
    "validate_inputs": handle_validate_inputs,
    "export_excel": handle_export_excel,
    "get_plate_data": handle_get_plate_data,
    "export_janus_mapping": handle_export_janus_mapping,
    "read_kuma_meta": handle_read_kuma_meta,
    "export_run_report": handle_export_run_report,
    "cancel_analyze": lambda _: {"cancelled": True},
    # A1/A3: raw-run demux + quality filter (R6)
    "demux_and_filter": handle_demux_and_filter,
    # A8: run health panel
    "get_run_health": handle_get_run_health,
}

# Long-running handlers run on a worker thread so stdin keeps draining.
_ASYNC_METHODS = {"analyze", "demux_and_filter"}


def _dispatch_handler(
    req_id: int | None, method: str, handler, params: dict
) -> None:
    """Run a handler and emit its JSON-RPC response (sync or threaded)."""
    try:
        result = handler(params)
        _ok(req_id, result)
    except FileNotFoundError as exc:
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32001, str(exc))
    except RuntimeError as exc:
        # Reserved for "no prior analyze" style preconditions.
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32002, str(exc))
    except (KeyError, ValueError) as exc:
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32602, str(exc))
    except Exception:
        logger.exception("Unhandled error in %s", method)
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32603, "Internal error")


def dispatch(request: dict) -> None:
    """Process a single JSON-RPC request."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {}) or {}

    handler = _METHODS.get(method)
    if handler is None:
        _error(req_id, -32601, f"Method not found: {method}")
        return

    if method in _ASYNC_METHODS:
        t = threading.Thread(
            target=_dispatch_handler,
            args=(req_id, method, handler, params),
            daemon=True,
        )
        t.start()
        return

    _dispatch_handler(req_id, method, handler, params)


def _start_parent_watchdog() -> None:
    """Exit if the parent process dies (prevents orphan sidecars on Windows)."""
    import time

    ppid = os.getppid()
    if ppid <= 1:
        return

    def _check() -> None:
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = ctypes.c_void_p
            SYNCHRONIZE = 0x00100000
            parent_handle = kernel32.OpenProcess(SYNCHRONIZE, False, ppid)
            if not parent_handle:
                return
            while True:
                time.sleep(5)
                ret = kernel32.WaitForSingleObject(
                    ctypes.c_void_p(parent_handle), 0
                )
                if ret == 0:
                    logger.info("Parent process %d died, exiting", ppid)
                    kernel32.CloseHandle(ctypes.c_void_p(parent_handle))
                    os._exit(0)
        else:
            while True:
                time.sleep(5)
                try:
                    os.kill(ppid, 0)
                except ProcessLookupError:
                    logger.info("Parent process %d died, exiting", ppid)
                    os._exit(0)
                except PermissionError:
                    pass

    threading.Thread(target=_check, daemon=True).start()


def main() -> None:
    """Read JSON-RPC requests from stdin, dispatch, respond on stdout."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    _start_parent_watchdog()
    logger.info("MAME sidecar started (pid=%d)", os.getpid())
    _send({"jsonrpc": "2.0", "method": "ready", "params": {}})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _error(None, -32700, f"Parse error: {exc}")
            continue

        dispatch(request)

    logger.info("Sidecar stdin closed, exiting")
