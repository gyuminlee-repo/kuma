"""JSON-RPC dispatcher: method registry, main loop, parent watchdog."""

import json
import logging
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
    handle_inspect_prediction_bundle,
    handle_preview_evolvepro_source,
    handle_run_benchmark,
)
from sidecar_kuro.handlers.codon import (
    handle_compute_codon_table,
    handle_import_codon_table,
    handle_export_codon_table,
)
from sidecar_kuro.handlers.domain import (
    handle_domain_runtime_status,
    handle_get_domain_annotation_attempt,
    handle_cancel_domain_annotation_attempt,
    handle_domain_runtime_install,
    handle_domain_runtime_remove,
    handle_start_domain_annotation,
    handle_poll_domain_annotation,
    handle_cancel_domain_annotation,
    handle_import_domain_annotation_result,
    handle_import_domain_annotation_file,
    stop_domain_jobs,
)
from sidecar_kuro.handlers.settings import (
    handle_load as handle_settings_load,
    handle_save as handle_settings_save,
)
from kuma_core.shared.dispatcher_runtime import (
    exit_after_shutdown as _exit_after_shutdown,
    start_memory_monitor,
    start_parent_watchdog as _start_parent_watchdog,
)
from kuma_core.shared.sidecar import loads_rpc_request

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
    "domain_runtime_status": handle_domain_runtime_status,
    "get_domain_annotation_attempt": handle_get_domain_annotation_attempt,
    "cancel_domain_annotation_attempt": handle_cancel_domain_annotation_attempt,
    "domain_runtime_install": handle_domain_runtime_install,
    "domain_runtime_remove": handle_domain_runtime_remove,
    "start_domain_annotation": handle_start_domain_annotation,
    "poll_domain_annotation": handle_poll_domain_annotation,
    "cancel_domain_annotation": handle_cancel_domain_annotation,
    "import_domain_annotation_result": handle_import_domain_annotation_result,
    "import_domain_annotation_file": handle_import_domain_annotation_file,
    "health_info": _handle_health_info,
    "list_polymerases": handle_list_polymerases,
    "get_polymerase_details": handle_get_polymerase_details,
    "save_custom_polymerase": handle_save_custom_polymerase,
    "list_organisms": handle_list_organisms,
    "compute_codon_table": handle_compute_codon_table,
    "import_codon_table": handle_import_codon_table,
    "export_codon_table": handle_export_codon_table,
    "load_fasta": handle_load_fasta,
    "parse_mutations_text": handle_parse_mutations_text,
    "design_sdm_primers": handle_design_sdm_primers,
    "load_evolvepro_csv": handle_load_evolvepro_csv,
    "inspect_prediction_bundle": handle_inspect_prediction_bundle,
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
    # §22 graceful shutdown — ack immediately; main() exits on this method
    "shutdown": lambda _: {"ok": True, "message": "shutdown_acked"},
}

# Long-running methods (network I/O, heavy computation) run in a background thread.
# "shutdown" is intentionally excluded — it must run on the main thread so the
# ack flushes to stdout before the loop exits.
_DOMAIN_ASYNC_METHODS = {
    "domain_runtime_status", "domain_runtime_install", "domain_runtime_remove",
    "start_domain_annotation", "import_domain_annotation_result", "import_domain_annotation_file",
}

_ASYNC_METHODS = {
    *_DOMAIN_ASYNC_METHODS,
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
# Domain I/O may dispatch asynchronously on frozen Windows only after main()
# establishes a native GIL-releasing pipe reader. Legacy scientific policy stays.
_DOMAIN_ASYNC_READY = False



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

    if method in _DOMAIN_ASYNC_METHODS and _SYNC_DISPATCH and not _DOMAIN_ASYNC_READY:
        _error(req_id, -32002, "Optional domain actions require the native asynchronous RPC pipe reader")
        return

    if method in _ASYNC_METHODS and (not _SYNC_DISPATCH or method in _DOMAIN_ASYNC_METHODS):
        t = threading.Thread(
            target=_dispatch_handler, args=(req_id, method, handler, params), daemon=True
        )
        t.start()
        return

    _dispatch_handler(req_id, method, handler, params)


def _start_memory_monitor() -> None:
    """Start the shared RSS monitor with this sidecar's stdout writer."""
    start_memory_monitor(_send)


def main(emit_ready: bool = True) -> None:
    """Main loop: read JSON-RPC requests from stdin, dispatch, respond on stdout.

    `emit_ready` defaults to True for backwards compatibility (direct invocation
    or tests). The frozen PyInstaller entry script sets it to False because it
    has already emitted the ready notification before triggering the heavy
    imports that bring this module to life.
    """
    if sys.platform == "win32":
        # typeshed declares the std streams as TextIO, which omits reconfigure;
        # the runtime objects are TextIOWrapper and carry it.
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    from kuma_core.shared.windows_rpc import RpcLineError, windows_stdin_reader
    global _DOMAIN_ASYNC_READY
    native_reader = None
    _DOMAIN_ASYNC_READY = False
    if _SYNC_DISPATCH:
        try:
            native_reader = windows_stdin_reader(sys.stdin.fileno())
        except (OSError, ValueError) as exc:
            # Preserve legacy sync RPCs, but never pretend cancel/poll remain
            # responsive during new domain I/O when native initialization failed.
            logger.error("Optional domain async RPC unavailable: %s", exc)
        else:
            _DOMAIN_ASYNC_READY = True

    _start_parent_watchdog()
    _start_memory_monitor()
    logger.info("KURO sidecar started (pid=%d)", os.getpid())
    if emit_ready:
        _send({"jsonrpc": "2.0", "method": "ready", "params": {}})

    # NOTE: use readline() in a loop, NOT `for line in sys.stdin` — the latter's
    # read-ahead buffering can withhold a request until the NEXT one arrives,
    # which on Windows stalled each RPC until the following request was sent.
    while True:
        try:
            line = native_reader.readline() if native_reader is not None else sys.stdin.readline()
        except RpcLineError as exc:
            _error(None, -32700, str(exc))
            continue
        except OSError as exc:
            logger.error("Sidecar input pipe closed with an error: %s", exc)
            break
        if not line:  # EOF — stdin closed
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = loads_rpc_request(line)
        except json.JSONDecodeError as exc:
            _error(None, -32700, f"Parse error: {exc}")
            continue

        if not isinstance(request, dict) or not isinstance(request.get("method"), str):
            _error(None, -32600, "Invalid Request: expected an object with a string method")
            continue

        # §22 graceful shutdown: send ack then exit the main loop cleanly.
        if request.get("method") == "shutdown":
            dispatch(request)
            logger.info("KURO sidecar shutdown requested, exiting cleanly")
            # Never leave a managed child alive during an orderly shutdown.
            # The host may still enforce its own deadline after acknowledging.
            while not stop_domain_jobs():
                logger.warning("Waiting for optional domain process termination before shutdown")
            _exit_after_shutdown()

        dispatch(request)

    while not stop_domain_jobs():
        logger.warning("Waiting for optional domain process termination after stdin closed")
    logger.info("Sidecar stdin closed, exiting")
