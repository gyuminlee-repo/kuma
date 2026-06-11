"""JSON-RPC dispatcher: method registry, main loop, parent watchdog."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
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
from sidecar_mame.handlers.load import handle_load_analyze_result
from sidecar_mame.handlers.export import (
    handle_export_excel,
    handle_export_janus_mapping,
    handle_get_plate_data,
)
from sidecar_mame.handlers.kuma_meta import handle_read_kuma_meta
from sidecar_mame.handlers.report import handle_export_run_report
from sidecar_mame.handlers.demux import handle_demux_and_filter
from sidecar_mame.handlers.health import handle_get_run_health
from sidecar_mame.handlers.activity import (
    ExportBlockedError,
    handle_activity_export_evolvepro_csv,
    handle_activity_export_evolvepro_xlsx,
    handle_activity_merge,
    handle_activity_set_plate_meta,
    handle_activity_upload,
    handle_build_evolvepro_input,
    handle_merge_for_evolvepro,
)
from sidecar_mame.handlers.barcode_package import handle_generate_mame_package
from sidecar_mame.handlers.build_well_layout import handle_build_well_layout
from sidecar_mame.handlers.ingest import handle_parse_reference
from sidecar_mame.handlers.combinatorial_demux import handle_run_combinatorial_demux
from sidecar_mame.handlers.detect_native_barcodes import handle_detect_native_barcodes
from sidecar_mame.handlers.classify_round import handle_classify_round

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


# Phase A handler registry.
# ``translate`` is deferred to Phase B per the reconciled scope.
# NOTE: ``export_run_report`` is owned by A14 — do not rename or remove.
_METHODS = {
    "ping": lambda _: {"ok": True},
    "health_info": _handle_health_info,
    "analyze": handle_analyze,
    "validate_inputs": handle_validate_inputs,
    # Phase 1: re-inject a serialized analyze payload so get_plate_data /
    # export_excel work after an app restart drops the in-memory SidecarState.
    "load_analyze_result": handle_load_analyze_result,
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
    # Phase 2 Task 2.1: activity integration RPC
    "activity.upload": handle_activity_upload,
    "activity.set_plate_meta": handle_activity_set_plate_meta,
    "activity.merge": handle_activity_merge,
    "activity.export_evolvepro_csv": handle_activity_export_evolvepro_csv,
    "activity.export_evolvepro_xlsx": handle_activity_export_evolvepro_xlsx,
    # Phase B: replicate merge + label-swap guard
    "mame.activity.merge_for_evolvepro": handle_merge_for_evolvepro,
    # A-pipeline: 4-file EVOLVEpro input build (layout + GC + rep-batch + prev EP)
    "mame.activity.build_evolvepro_input": handle_build_evolvepro_input,
    # Feature B: MAME Barcode Setup
    "generate_mame_package": handle_generate_mame_package,
    # Analyze-phase CDS picker: parse reference (FASTA / GenBank / SnapGene)
    "mame.ingest.parse_reference": handle_parse_reference,
    # PR-A: alignment-anchored combinatorial demux pipeline
    "mame.run_combinatorial_demux": handle_run_combinatorial_demux,
    # Native-barcode usage detection (stat-only, synchronous)
    "mame.detect_native_barcodes": handle_detect_native_barcodes,
    # Draft 96-well layout from KURO expected_mutations (stat-only, synchronous)
    "mame.build_well_layout": handle_build_well_layout,
    # v0.3 advisory: read-only classify() call (partial slice, plumbing pending)
    "strategy.classify_round": handle_classify_round,
    # §22 graceful shutdown — ack immediately; main() breaks on this method
    "shutdown": lambda _: {"ok": True, "message": "shutdown_acked"},
}

# Long-running handlers run on a worker thread so stdin keeps draining.
# "shutdown" is intentionally excluded — it must run on the main thread so the
# ack flushes to stdout before the loop exits.
_ASYNC_METHODS = {"analyze", "demux_and_filter", "mame.run_combinatorial_demux"}


def _dispatch_handler(
    req_id: int | None, method: str, handler, params: dict
) -> None:
    """Run a handler and emit its JSON-RPC response (sync or threaded)."""
    try:
        result = handler(params)
        _ok(req_id, result)
    except ExportBlockedError as exc:
        # ExportBlockedError is a RuntimeError subclass — must be caught before
        # the generic RuntimeError branch so it maps to -32004 (not -32002).
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        _error(req_id, -32004, str(exc))
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
    except Exception as exc:
        logger.exception("Unhandled error in %s", method)
        _append_crash_log(method, str(params)[:200], traceback.format_exc())
        # Surface the exception type + message instead of an opaque
        # "Internal error". The full traceback stays in crash.log only; the
        # short form (e.g. "ImportError: edlib is required ...") lets the UI
        # show an actionable cause. The -32603 code is preserved so the
        # frontend errorClassifier still buckets this as a sidecar error.
        _error(req_id, -32603, f"{type(exc).__name__}: {exc}")


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
                    # PermissionError means the process exists but is owned by
                    # a different user — parent is alive, no action needed.
                    pass

    threading.Thread(target=_check, daemon=True).start()


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
    """Read JSON-RPC requests from stdin, dispatch, respond on stdout.

    `emit_ready` defaults to True for direct invocation; the PyInstaller entry
    script passes False since it already sent the ready notification before
    triggering this module's heavy imports.
    """
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    _start_parent_watchdog()
    _start_memory_monitor()
    logger.info("MAME sidecar started (pid=%d)", os.getpid())
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
            logger.info("MAME sidecar shutdown requested, exiting cleanly")
            break

        dispatch(request)

    logger.info("Sidecar stdin closed, exiting")
