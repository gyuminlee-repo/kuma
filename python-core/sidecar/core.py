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

# ensure kuro package is importable from any working directory
_SCRIPT_DIR = Path(__file__).parent.parent.resolve()  # python-core/
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from kuro.sdm_engine import SdmPrimerResult  # noqa: E402
from kuro.plate_mapper import PlateMapping  # noqa: E402
from kuro.polymerase import PolymeraseRegistry  # noqa: E402
from kuro.codon_table import CodonTableRegistry  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sidecar")

_CUSTOM_POLYMERASE_PATH = Path.home() / ".kuro" / "custom_polymerases.json"
_CONFIG_PATH = Path.home() / ".kuro" / "config.json"
_poly_registry = PolymeraseRegistry(custom_path=_CUSTOM_POLYMERASE_PATH)
_codon_registry = CodonTableRegistry()
_config_cache: dict | None = None

_CRASH_LOG_MAX = 50


def _get_crash_log_path() -> Path:
    kuro_dir = Path.home() / ".kuro"
    kuro_dir.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chmod(kuro_dir, 0o700)
    return kuro_dir / "crash.log"


def _append_crash_log(method: str, params_summary: str, tb: str) -> None:
    """Append an error entry to the crash log (FIFO, max 50 entries)."""
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


_ALLOWED_FASTA_EXTENSIONS = {".fa", ".fasta", ".fna", ".dna", ".gb", ".gbff", ".gbk"}
_ALLOWED_CSV_EXTENSIONS = {".csv", ".tsv", ".txt"}
_ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}
_VALID_DNA_BASES = re.compile(r"^[ATGC]+$")

_ssl_ctx = None


def _get_ssl_ctx():
    global _ssl_ctx
    if _ssl_ctx is None:
        import ssl
        _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx


def _get_config() -> dict[str, object]:
    global _config_cache
    if _config_cache is None:
        try:
            loaded = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            _config_cache = loaded if isinstance(loaded, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            _config_cache = {}
    return _config_cache


_DEFAULT_CONTACT_EMAIL = "kuro-app@example.com"


def _get_contact_email() -> str:
    """Return user-configured contact email or a placeholder.

    EBI BLAST REST requires an email parameter; omitting it causes job
    submissions to fail with ERROR status. Users can override via the
    KURO_CONTACT_EMAIL env var or contact_email in ~/.kuro/config.json.
    """
    raw = os.environ.get("KURO_CONTACT_EMAIL", "").strip()
    if raw:
        return raw
    config_email = str(_get_config().get("contact_email", "")).strip()
    return config_email or _DEFAULT_CONTACT_EMAIL


@dataclass
class SidecarState:
    """Mutable session state shared across RPC handlers."""

    results: list[SdmPrimerResult] = field(default_factory=list)
    candidates: dict[str, list[SdmPrimerResult]] = field(default_factory=dict)
    plate_mappings: list[PlateMapping] = field(default_factory=list)
    dedup_info: dict[str, list[str]] = field(default_factory=dict)
    template: tuple[str, str] = ("", "")  # (fasta_path, sequence)
    ca_coords: list[tuple[float, float, float] | None] | None = None  # AlphaFold Cα coordinates
    ca_coords_accession: str | None = None
    active_design_cancel: threading.Event | None = None


_state = SidecarState()
_state_lock = threading.Lock()


def _begin_design_job() -> threading.Event:
    with _state_lock:
        if _state.active_design_cancel is not None:
            raise ValueError("A primer design job is already in progress")
        cancel_event = threading.Event()
        _state.active_design_cancel = cancel_event
        return cancel_event


def _finish_design_job(cancel_event: threading.Event) -> None:
    with _state_lock:
        if _state.active_design_cancel is cancel_event:
            _state.active_design_cancel = None


def _cancel_active_design() -> bool:
    with _state_lock:
        cancel_event = _state.active_design_cancel
    if cancel_event is None:
        return False
    cancel_event.set()
    return True


def _get_cached_ca_coords(structure_accession: str | None) -> list | None:
    """Return cached Cα coordinates if accession matches, else None. Thread-safe."""
    with _state_lock:
        if structure_accession and _state.ca_coords_accession == structure_accession:
            return _state.ca_coords
        return None


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
# Path validation — uses Path.resolve() to catch symlink-based traversal
# ---------------------------------------------------------------------------


def _validate_filepath(
    filepath: str | None, *, allowed_extensions: set[str] | None = None
) -> Path:
    """Validate and resolve an input file path.

    Raises FileNotFoundError on traversal, symlinks, or missing parent.
    Raises ValueError on disallowed extension.
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

    Raises FileNotFoundError on traversal, symlinks, or missing parent.
    Raises ValueError on disallowed extension.
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
