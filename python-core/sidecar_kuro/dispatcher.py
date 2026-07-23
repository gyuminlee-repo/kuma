"""JSON-RPC dispatcher: method registry, main loop, parent watchdog."""

import json
import os
import sys
import threading
import time
import traceback

from sidecar_kuro.core import (
    _append_crash_log,
    _cancel_active_design,
    _error,
    _ok,
    _send,
    logger,
)
from sidecar_kuro.handlers.sequence import handle_load_fasta, handle_parse_mutations_text
from sidecar_kuro.handlers.design import (
    handle_commit_design_result,
    handle_design_sdm_primers,
    handle_retry_failed,
    handle_swap_primer,
    handle_evaluate_primer,
    handle_get_alternatives,
)
from sidecar_kuro.handlers.export import (
    handle_export_all,
    handle_export_benchmark_csv,
    handle_export_echo_mapping_dry_run,
    handle_export_excel,
    handle_export_janus_mapping_dry_run,
    handle_export_macrogen,
    handle_export_mapping,
    handle_export_order,
    handle_get_plate_map,
    handle_save_json,
    handle_save_workspace,
    handle_load_workspace,
)
from sidecar_kuro.handlers.external import (
    handle_annotate_domains_by_sequence,
    handle_predict_structure_esmfold,
    handle_check_structures_available,
    handle_fetch_domains,
    handle_search_uniprot,
    handle_fetch_structure,
    handle_load_structure_file,
    handle_fetch_interface_residues,
    handle_fetch_pdb_text,
    handle_fetch_active_site,
    handle_compute_dispersion,
)
from sidecar_kuro.handlers.misc import (
    handle_list_polymerases,
    handle_get_polymerase_details,
    handle_save_custom_polymerase,
    handle_list_organisms,
    handle_load_evolvepro_csv,
    handle_preview_evolvepro_source,
    handle_run_benchmark,
)
from sidecar_kuro.handlers.settings import (
    handle_load as handle_settings_load,
    handle_save as handle_settings_save,
)

def _handle_health_info(_params: dict) -> dict:
    """Return PID, RSS, and Python version for the status bar tooltip."""
    import sys as _sys
    rss_bytes = 0
    try:
        from kuma_core.shared.memory_monitor import get_self_rss_bytes
        rss_bytes = get_self_rss_bytes()
    except ImportError as exc:
        logger.warning("memory_monitor unavailable for health_info: %s", exc)
    return {
        "pid": os.getpid(),
        "rss_bytes": rss_bytes,
        "py_version": _sys.version.split()[0],
    }


_METHODS = {
    "ping": lambda _: {"ok": True},
    "health_info": _handle_health_info,
    "list_polymerases": handle_list_polymerases,
    "get_polymerase_details": handle_get_polymerase_details,
    "save_custom_polymerase": handle_save_custom_polymerase,
    "list_organisms": handle_list_organisms,
    "load_fasta": handle_load_fasta,
    "parse_mutations_text": handle_parse_mutations_text,
    "design_sdm_primers": handle_design_sdm_primers,
    "load_evolvepro_csv": handle_load_evolvepro_csv,
    "preview_evolvepro_source": handle_preview_evolvepro_source,
    "get_plate_map": handle_get_plate_map,
    "get_alternatives": handle_get_alternatives,
    "swap_primer": handle_swap_primer,
    "commit_design_result": handle_commit_design_result,
    "export_excel": handle_export_excel,
    "export_order": handle_export_order,
    "export_mapping": handle_export_mapping,
    "export_echo_mapping_dry_run": handle_export_echo_mapping_dry_run,
    "export_janus_mapping_dry_run": handle_export_janus_mapping_dry_run,
    "export_macrogen": handle_export_macrogen,
    "export_all": handle_export_all,
    "export_benchmark_csv": handle_export_benchmark_csv,
    "evaluate_primer": handle_evaluate_primer,
    "retry_failed_mutation": handle_retry_failed,
    "save_json": handle_save_json,
    "save_workspace": handle_save_workspace,
    "load_workspace": handle_load_workspace,
    "fetch_domains": handle_fetch_domains,
    "search_uniprot": handle_search_uniprot,
    "check_structures_available": handle_check_structures_available,
    "fetch_structure": handle_fetch_structure,
    "load_structure_file": handle_load_structure_file,
    "fetch_interface_residues": handle_fetch_interface_residues,
    # G001: 3D Analysis panel RPCs
    "fetch_pdb_text": handle_fetch_pdb_text,
    "fetch_active_site_residues": handle_fetch_active_site,
    "compute_dispersion": handle_compute_dispersion,
    "annotate_domains_by_sequence": handle_annotate_domains_by_sequence,
    "predict_structure_esmfold": handle_predict_structure_esmfold,
    "run_benchmark": handle_run_benchmark,
    "cancel_design": lambda _: {
        "cancelled": True,
        "active_design": _cancel_active_design(),
    },
    # Phase 3: Settings
    "settings_load": handle_settings_load,
    "settings_save": handle_settings_save,
    # §22 graceful shutdown — ack immediately; main() breaks on this method
    "shutdown": lambda _: {"ok": True, "message": "shutdown_acked"},
}

# Long-running methods (network I/O, heavy computation) run in a background thread.
# "shutdown" is intentionally excluded — it must run on the main thread so the
# ack flushes to stdout before the loop exits.
_ASYNC_METHODS = {
    "design_sdm_primers",
    "search_uniprot",
    "check_structures_available",
    "fetch_structure",
    "load_structure_file",
    "fetch_interface_residues",
    "fetch_domains",
    "run_benchmark",
    # G001: 3D Analysis panel RPCs
    "fetch_pdb_text",
    "fetch_active_site_residues",
    "compute_dispersion",
    "annotate_domains_by_sequence",
    "predict_structure_esmfold",
}

# Frozen-Windows worker dispatch starves the worker thread while the main loop
# blocks on stdin, so async responses are not delivered until the client's NEXT
# request. Run handlers synchronously on the main thread there (same rationale
# and fix as the MAME dispatcher).
_SYNC_DISPATCH = sys.platform == "win32" and getattr(sys, "frozen", False)



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
        # Surface the exception type + message instead of an opaque
        # "Internal error". The full traceback stays in crash.log only; the
        # short form (e.g. "ImportError: primer3 is required ...") lets the UI
        # show an actionable cause. The -32603 code is preserved so the
        # frontend errorClassifier still buckets this as a sidecar error.
        # Mirrors sidecar_mame/dispatcher.py.
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

    if method in _ASYNC_METHODS and not _SYNC_DISPATCH:
        t = threading.Thread(
            target=_dispatch_handler, args=(req_id, method, handler, params), daemon=True
        )
        t.start()
        return

    _dispatch_handler(req_id, method, handler, params)




def _start_parent_watchdog() -> None:
    """Exit if parent process dies (prevents orphan sidecar on Windows)."""
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
                    # PermissionError means the process exists but is owned by
                    # a different user — parent is alive, no action needed.
                    pass

    t = threading.Thread(target=_check, daemon=True)
    t.start()


# §19 Performance Guardrails: RSS-based memory monitor
_MEMORY_CHECK_INTERVAL = 30  # seconds


def _start_memory_monitor() -> None:
    """Emit memory_warning progress notifications at 30-second intervals.

    Runs in a daemon thread so it does not block the main stdin loop.
    Uses method="progress" so the Rust sidecar forwards it via sidecar://progress.
    Params include type="memory_warning" so the frontend can distinguish it.

    Levels:
      - "warn"  when ratio >= WARN_THRESHOLD (0.50)
      - "block" when ratio >= BLOCK_THRESHOLD (0.70)
    """
    try:
        from kuma_core.shared.memory_monitor import (
            BLOCK_THRESHOLD,
            WARN_THRESHOLD,
            memory_usage_ratio,
            get_self_rss_bytes,
        )
    except ImportError:
        logger.warning("memory_monitor unavailable — skipping RSS monitoring")
        return

    def _check() -> None:
        while True:
            time.sleep(_MEMORY_CHECK_INTERVAL)
            try:
                ratio = memory_usage_ratio()
                if ratio >= WARN_THRESHOLD:
                    rss_mb = get_self_rss_bytes() / (1024 * 1024)
                    level = "block" if ratio >= BLOCK_THRESHOLD else "warn"
                    _send({
                        "jsonrpc": "2.0",
                        "method": "progress",
                        "params": {
                            "type": "memory_warning",
                            "ratio": round(ratio, 4),
                            "rss_mb": round(rss_mb, 1),
                            "level": level,
                        },
                    })
            except Exception:
                logger.debug("memory monitor check failed", exc_info=True)

    threading.Thread(target=_check, daemon=True).start()




def main(emit_ready: bool = True) -> None:
    """Main loop: read JSON-RPC requests from stdin, dispatch, respond on stdout.

    `emit_ready` defaults to True for backwards compatibility (direct invocation
    or tests). The frozen PyInstaller entry script sets it to False because it
    has already emitted the ready notification before triggering the heavy
    imports that bring this module to life.
    """
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    _start_parent_watchdog()
    _start_memory_monitor()
    logger.info("KURO sidecar started (pid=%d)", os.getpid())
    if emit_ready:
        _send({"jsonrpc": "2.0", "method": "ready", "params": {}})

    # NOTE: use readline() in a loop, NOT `for line in sys.stdin` — the latter's
    # read-ahead buffering can withhold a request until the NEXT one arrives,
    # which on Windows stalled each RPC until the following request was sent.
    while True:
        line = sys.stdin.readline()
        if not line:  # EOF — stdin closed
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _error(None, -32700, f"Parse error: {exc}")
            continue

        # §22 graceful shutdown: send ack then exit the main loop cleanly.
        if request.get("method") == "shutdown":
            dispatch(request)
            logger.info("KURO sidecar shutdown requested, exiting cleanly")
            break

        dispatch(request)

    logger.info("Sidecar stdin closed, exiting")
