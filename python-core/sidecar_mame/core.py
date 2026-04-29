"""Core shared state, I/O helpers, and validation for the MAME sidecar.

Imports the existing ``mame`` package (under ``src/``) as a library and
exposes a thread-safe ``SidecarState`` that persists the most recent analyze
results for downstream ``export_excel`` / ``get_plate_data`` calls.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# sys.path shim: make the existing ``mame`` package importable.
# Directory layout (060 §6-1):
#   mame/
#     python-core/sidecar/core.py   <-- this file
#     src/mame/             <-- target package
# ``_PROJECT_ROOT`` is ``mame/``. We also append ``src/`` so that
# ``import mame.*`` resolves in both editable-installed and PyInstaller
# frozen modes.
# ---------------------------------------------------------------------------
_HERE = Path(__file__).parent.resolve()                 # python-core/sidecar/
_PYCORE_DIR = _HERE.parent                              # python-core/
_PROJECT_ROOT = _PYCORE_DIR.parent                      # mame/
_SRC_DIR = _PROJECT_ROOT / "src"                        # mame/src/

for _p in (_PROJECT_ROOT, _SRC_DIR):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from kuma_core.shared.config_paths import kuma_home  # noqa: E402
from kuma_core.shared.errors import jsonrpc_error  # noqa: E402
from kuma_core.shared.logging import get_logger  # noqa: E402

logger = get_logger("sidecar_mame")

# ---------------------------------------------------------------------------
# Crash log (FIFO, capped at 50 entries). Stored under ~/.mame/.
# ---------------------------------------------------------------------------
_CRASH_LOG_MAX = 50


def _get_crash_log_path() -> Path:
    base = kuma_home() / "mame"
    base.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            os.chmod(base, 0o700)
        except OSError:
            pass
    return base / "crash.log"


def _append_crash_log(method: str, params_summary: str, tb: str) -> None:
    """Append an error entry to the crash log. Never raises."""
    try:
        log_path = _get_crash_log_path()
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "method": method,
            "params": params_summary[:200],
            "traceback": tb[:2000],
        }
        entries: list[dict] = []
        if log_path.exists():
            try:
                raw = log_path.read_text(encoding="utf-8").strip()
                if raw:
                    entries = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                entries = []
        entries.append(entry)
        while len(entries) > _CRASH_LOG_MAX:
            entries.pop(0)
        log_path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        # Crash logging itself must never raise.
        pass


# ---------------------------------------------------------------------------
# Sidecar state — holds the most recent analyze artefacts for downstream RPCs.
# Fields hold raw objects (``VerdictRecord`` / ``ReplicateResult``) so that
# ``write_excel`` and ``WellMapper`` can consume them without re-parsing.
# ---------------------------------------------------------------------------
@dataclass
class SidecarState:
    last_verdicts: list | None = None        # list[VerdictRecord]
    last_replicates: list | None = None      # list[ReplicateResult]
    last_output_path: str | None = None
    last_run_meta: object | None = None      # NgsRunMeta | None — discovered at analyze time


_state = SidecarState()
_state_lock = threading.Lock()


def get_state() -> SidecarState:
    """Return the module-level state (callers must use ``_state_lock`` for writes)."""
    return _state


def set_last_analyze(
    verdicts: list,
    replicates: list,
    output_path: str,
    run_meta: object | None = None,
) -> None:
    with _state_lock:
        _state.last_verdicts = verdicts
        _state.last_replicates = replicates
        _state.last_output_path = output_path
        _state.last_run_meta = run_meta


# ---------------------------------------------------------------------------
# stdout JSON-RPC framing. Thread-safe writer.
# ---------------------------------------------------------------------------
_stdout_lock = threading.Lock()


def _send(obj: dict) -> None:
    line = json.dumps(obj, ensure_ascii=False)
    with _stdout_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _ok(req_id, result) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": jsonrpc_error(code, message)})


def _progress(value: int, message: str = "") -> None:
    _send(
        {
            "jsonrpc": "2.0",
            "method": "progress",
            "params": {"value": value, "message": message},
        }
    )


# ---------------------------------------------------------------------------
# Path validation — resolves symlinks and blocks traversal tokens.
# ---------------------------------------------------------------------------
_ALLOWED_FASTA_EXTENSIONS = {".fa", ".fasta", ".fna"}
_ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}


def _validate_filepath(
    filepath: str | None, *, allowed_extensions: set[str] | None = None
) -> Path:
    """Validate and resolve an *existing* input file path."""
    if not filepath:
        raise FileNotFoundError("filepath is required")

    original = Path(filepath)
    if original.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {filepath}")
    if ".." in original.parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {filepath}")

    resolved = original.resolve()
    if resolved.is_symlink():
        raise FileNotFoundError(
            f"Symbolic links are not allowed (resolved): {filepath}"
        )
    if not resolved.exists():
        raise FileNotFoundError(f"File does not exist: {filepath}")
    if resolved.is_dir():
        raise FileNotFoundError(f"Path is a directory, not a file: {filepath}")

    if allowed_extensions is not None:
        ext = resolved.suffix.lower()
        if ext not in allowed_extensions:
            raise ValueError(
                f"Unsupported file extension '{ext}'. Allowed: {sorted(allowed_extensions)}"
            )

    return resolved


def _validate_dirpath(dirpath: str | None) -> Path:
    if not dirpath:
        raise FileNotFoundError("dirpath is required")
    original = Path(dirpath)
    if original.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {dirpath}")
    if ".." in original.parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {dirpath}")
    resolved = original.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Directory does not exist: {dirpath}")
    if not resolved.is_dir():
        raise FileNotFoundError(f"Path is not a directory: {dirpath}")
    return resolved


def _validate_output_path(
    filepath: str | None, *, allowed_extensions: set[str]
) -> Path:
    """Validate an output file path. Parent directory must exist; file may not."""
    if not filepath:
        raise FileNotFoundError("filepath is required")
    original = Path(filepath)
    if original.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {filepath}")
    if ".." in original.parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {filepath}")
    resolved = original.resolve()
    if not resolved.parent.exists():
        raise FileNotFoundError(
            f"Parent directory does not exist: {resolved.parent}"
        )
    ext = resolved.suffix.lower()
    if ext not in allowed_extensions:
        raise ValueError(
            f"Unsupported file extension '{ext}'. Allowed: {sorted(allowed_extensions)}"
        )
    return resolved
