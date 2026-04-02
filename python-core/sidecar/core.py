"""Core shared state, I/O helpers, and validation for the KURO sidecar."""

import datetime
import json
import logging
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — ensure kuro package is importable from any working directory
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent.parent.resolve()  # python-core/
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from kuro.sdm_engine import SdmPrimerResult  # noqa: E402
from kuro.plate_mapper import PlateMapping  # noqa: E402
from kuro.polymerase import PolymeraseRegistry  # noqa: E402
from kuro.codon_table import CodonTableRegistry  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sidecar")

# ---------------------------------------------------------------------------
# Global registries (initialised once at import time)
# ---------------------------------------------------------------------------
_CUSTOM_POLYMERASE_PATH = Path.home() / ".kuro" / "custom_polymerases.json"
_poly_registry = PolymeraseRegistry(custom_path=_CUSTOM_POLYMERASE_PATH)
_codon_registry = CodonTableRegistry()

# ---------------------------------------------------------------------------
# Crash log
# ---------------------------------------------------------------------------
_CRASH_LOG_MAX = 50


def _get_crash_log_path() -> Path:
    """Return the crash log path (~/.kuro/crash.log)."""
    kuro_dir = Path.home() / ".kuro"
    kuro_dir.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(kuro_dir, 0o700)
    return kuro_dir / "crash.log"


def _append_crash_log(method: str, params_summary: str, tb: str) -> None:
    """Append an error entry to the local crash log file (FIFO, max 50 entries)."""
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
        log_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # crash logging itself must never raise


# ---------------------------------------------------------------------------
# Allowed extension sets
# ---------------------------------------------------------------------------
_ALLOWED_FASTA_EXTENSIONS = {".fa", ".fasta", ".fna", ".dna", ".gb", ".gbff", ".gbk"}
_ALLOWED_CSV_EXTENSIONS = {".csv", ".tsv", ".txt"}
_ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}
_VALID_DNA_BASES = re.compile(r"^[ATGC]+$")

# ---------------------------------------------------------------------------
# Lazy SSL context
# ---------------------------------------------------------------------------
_ssl_ctx = None


def _get_ssl_ctx():
    global _ssl_ctx
    if _ssl_ctx is None:
        import ssl
        _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx


# ---------------------------------------------------------------------------
# Cancel event for long-running operations
# ---------------------------------------------------------------------------
_cancel_event = threading.Event()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------


@dataclass
class SidecarState:
    """Mutable session state shared across RPC handlers."""

    results: list[SdmPrimerResult] = field(default_factory=list)
    candidates: dict[str, list[SdmPrimerResult]] = field(default_factory=dict)
    plate_mappings: list[PlateMapping] = field(default_factory=list)
    dedup_info: dict[str, list[str]] = field(default_factory=dict)
    template: tuple[str, str] = ("", "")  # (fasta_path, sequence)
    ca_coords: list[tuple[float, float, float] | None] | None = None  # AlphaFold Cα coordinates


_state = SidecarState()
_state_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Stdout lock and wire helpers
# ---------------------------------------------------------------------------
_stdout_lock = threading.Lock()


def _send(obj: dict) -> None:
    """Write a JSON object to stdout (one line). Thread-safe."""
    line = json.dumps(obj, ensure_ascii=False)
    with _stdout_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _ok(req_id, result) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str) -> None:
    _send(
        {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    )


def _progress(value: int, message: str = "") -> None:
    _send(
        {
            "jsonrpc": "2.0",
            "method": "progress",
            "params": {"value": value, "message": message},
        }
    )


# ---------------------------------------------------------------------------
# Path validation
# Security fix: use Path.resolve() to catch symlink-based traversal instead
# of the weak `".." in Path(filepath).parts` check.
# ---------------------------------------------------------------------------


def _validate_filepath(
    filepath: str | None, *, allowed_extensions: set[str] | None = None
) -> Path:
    """Validate and resolve an input file path.

    Uses Path.resolve() to normalise the path and detect traversal via
    symlinks or redundant '..' components.
    """
    if not filepath:
        raise FileNotFoundError("filepath is required")

    original = Path(filepath)

    if original.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {filepath}")

    resolved = original.resolve()

    if resolved.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed (resolved): {filepath}")

    if ".." in original.parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {filepath}")

    if resolved.is_dir():
        raise FileNotFoundError(f"Path is a directory, not a file: {filepath}")

    if allowed_extensions is not None:
        ext = resolved.suffix.lower()
        if ext not in allowed_extensions:
            raise ValueError(
                f"Unsupported file extension '{ext}'. Allowed: {sorted(allowed_extensions)}"
            )

    return resolved


def _validate_output_path(
    filepath: str | None, *, allowed_extensions: set[str]
) -> Path:
    """Validate an output file path (file may not exist yet).

    Uses Path.resolve() to normalise the path and detect traversal via
    symlinks or redundant '..' components.
    """
    if not filepath:
        raise FileNotFoundError("filepath is required")

    original = Path(filepath)

    if original.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {filepath}")

    if ".." in original.parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {filepath}")

    resolved = original.resolve()

    if resolved.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed (resolved): {filepath}")

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
