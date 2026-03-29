"""JSON-RPC dispatcher: method registry, main loop, parent watchdog."""

import json
import logging
import os
import sys
import threading
import traceback
from pathlib import Path

from sidecar.core import (
    _append_crash_log,
    _cancel_event,
    _error,
    _ok,
    _send,
    logger,
)
from sidecar.handlers.sequence import handle_load_fasta, handle_parse_mutations_text
from sidecar.handlers.design import (
    handle_design_sdm_primers,
    handle_retry_failed,
    handle_swap_primer,
    handle_evaluate_primer,
    handle_get_alternatives,
)
from sidecar.handlers.export import (
    handle_export_excel,
    handle_export_order,
    handle_get_plate_map,
    handle_save_workspace,
    handle_load_workspace,
)
from sidecar.handlers.external import (
    handle_fetch_domains,
    handle_search_uniprot,
    handle_fetch_esm_embedding,
)
from sidecar.handlers.misc import (
    handle_list_polymerases,
    handle_list_organisms,
    handle_load_evolvepro_csv,
    handle_run_benchmark,
)

# ---------------------------------------------------------------------------
# Method registry
# ---------------------------------------------------------------------------

_METHODS = {
    "list_polymerases": handle_list_polymerases,
    "list_organisms": handle_list_organisms,
    "load_fasta": handle_load_fasta,
    "parse_mutations_text": handle_parse_mutations_text,
    "design_sdm_primers": handle_design_sdm_primers,
    "load_evolvepro_csv": handle_load_evolvepro_csv,
    "get_plate_map": handle_get_plate_map,
    "get_alternatives": handle_get_alternatives,
    "swap_primer": handle_swap_primer,
    "export_excel": handle_export_excel,
    "export_order": handle_export_order,
    "evaluate_primer": handle_evaluate_primer,
    "retry_failed_mutation": handle_retry_failed,
    "save_workspace": handle_save_workspace,
    "load_workspace": handle_load_workspace,
    "fetch_domains": handle_fetch_domains,
    "search_uniprot": handle_search_uniprot,
    "fetch_esm_embedding": handle_fetch_esm_embedding,
    "run_benchmark": handle_run_benchmark,
    "cancel_design": lambda _: (_cancel_event.set(), {"cancelled": True})[1],
}

# Methods that run in a background thread to avoid blocking the main loop.
# These are long-running operations (network I/O, heavy computation).
_ASYNC_METHODS = {"search_uniprot", "fetch_esm_embedding", "fetch_domains", "run_benchmark"}


# ---------------------------------------------------------------------------
# Dispatch helpers
# ---------------------------------------------------------------------------


def _dispatch_handler(req_id: int | None, method: str, handler, params: dict) -> None:
    """Run a handler and send its JSON-RPC response. Used by both sync and threaded dispatch."""
    try:
        result = handler(params)
        _ok(req_id, result)
    except FileNotFoundError as exc:
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32001, str(exc))
    except (KeyError, ValueError) as exc:
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32602, str(exc))
    except Exception as exc:
        logger.exception("Unhandled error in %s", method)
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32603, f"{type(exc).__name__}: {exc}")


def dispatch(request: dict) -> None:
    """Process a single JSON-RPC request."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    handler = _METHODS.get(method)
    if handler is None:
        _error(req_id, -32601, f"Method not found: {method}")
        return

    if method in _ASYNC_METHODS:
        t = threading.Thread(
            target=_dispatch_handler, args=(req_id, method, handler, params), daemon=True
        )
        t.start()
        return

    _dispatch_handler(req_id, method, handler, params)


# ---------------------------------------------------------------------------
# Parent watchdog
# ---------------------------------------------------------------------------


def _start_parent_watchdog() -> None:
    """Exit if parent process dies (prevents orphan sidecar on Windows)."""
    import time
    ppid = os.getppid()
    if ppid <= 1:
        return

    def _check() -> None:
        if sys.platform == "win32":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = ctypes.c_void_p
            # Get parent handle at startup to avoid PID reuse false negatives
            SYNCHRONIZE = 0x00100000
            parent_handle = kernel32.OpenProcess(SYNCHRONIZE, False, ppid)
            if not parent_handle:
                return  # can't monitor
            while True:
                time.sleep(5)
                # WAIT_TIMEOUT=0x102, WAIT_OBJECT_0=0 (process exited)
                ret = kernel32.WaitForSingleObject(ctypes.c_void_p(parent_handle), 0)
                if ret == 0:  # WAIT_OBJECT_0 = parent exited
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
                    pass  # process exists but different user

    t = threading.Thread(target=_check, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    """Main loop: read JSON-RPC requests from stdin, dispatch, respond on stdout."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    _start_parent_watchdog()
    logger.info("KURO sidecar started (pid=%d)", os.getpid())
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
