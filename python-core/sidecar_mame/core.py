"""Core shared state, I/O helpers, and validation for the MAME sidecar.

Imports the existing ``mame`` package (under ``src/``) as a library and
exposes a thread-safe ``SidecarState`` that persists the most recent analyze
results for downstream ``export_excel`` / ``get_plate_data`` calls.
"""

from __future__ import annotations

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
from kuma_core.shared.logging import get_logger  # noqa: E402
from kuma_core.shared.sidecar import (  # noqa: E402
    JsonRpcWriter,
    append_crash_log,
    ensure_private_dir,
    validate_dirpath,
    validate_filepath,
    validate_output_path,
)

logger = get_logger("sidecar_mame")

# ---------------------------------------------------------------------------
# Crash log (FIFO, capped at 50 entries). Stored under kuma_home()/mame.
# ---------------------------------------------------------------------------
def _get_crash_log_path() -> Path:
    return ensure_private_dir(kuma_home() / "mame") / "crash.log"


def _append_crash_log(method: str, params_summary: str, tb: str) -> None:
    """Append an error entry to the crash log. Never raises."""
    append_crash_log(_get_crash_log_path(), method, params_summary, tb)


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
_rpc_writer = JsonRpcWriter()


def _send(obj: dict) -> None:
    _rpc_writer.send(obj)


def _ok(req_id, result) -> None:
    _rpc_writer.ok(req_id, result)


def _error(req_id, code: int, message: str) -> None:
    _rpc_writer.error(req_id, code, message)


def _progress(value: int, message: str = "") -> None:
    _rpc_writer.progress(value, message)


# ---------------------------------------------------------------------------
# Path validation — resolves symlinks and blocks traversal tokens.
# ---------------------------------------------------------------------------
_ALLOWED_FASTA_EXTENSIONS = {".fa", ".fasta", ".fna"}
_ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}


def _validate_filepath(
    filepath: str | None, *, allowed_extensions: set[str] | None = None
) -> Path:
    """Validate and resolve an *existing* input file path."""
    return validate_filepath(filepath, allowed_extensions=allowed_extensions)


def _validate_dirpath(dirpath: str | None) -> Path:
    return validate_dirpath(dirpath)


def _validate_output_path(
    filepath: str | None, *, allowed_extensions: set[str]
) -> Path:
    """Validate an output file path. Parent directory must exist; file may not."""
    return validate_output_path(filepath, allowed_extensions=allowed_extensions)
