"""Core shared state, I/O helpers, and validation for the KURO sidecar."""

import json
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

from kuma_core.kuro.sdm_engine import SdmPrimerResult  # noqa: E402
from kuma_core.kuro.plate_mapper import PlateMapping  # noqa: E402
from kuma_core.kuro.polymerase import PolymeraseRegistry  # noqa: E402
from kuma_core.kuro.codon_table import CodonTableRegistry  # noqa: E402
from kuma_core.shared.config_paths import kuma_home  # noqa: E402
from kuma_core.shared.logging import get_logger  # noqa: E402
from kuma_core.shared.sidecar import (  # noqa: E402
    JsonRpcWriter,
    append_crash_log,
    ensure_private_dir,
    validate_filepath,
    validate_output_path,
)

logger = get_logger("sidecar_kuro")

_KURO_DIR = kuma_home() / "kuro"
_CUSTOM_POLYMERASE_PATH = _KURO_DIR / "custom_polymerases.json"
_CONFIG_PATH = _KURO_DIR / "config.json"
_poly_registry = PolymeraseRegistry(custom_path=_CUSTOM_POLYMERASE_PATH)
_codon_registry = CodonTableRegistry()
_config_cache: dict | None = None

def _get_crash_log_path() -> Path:
    return ensure_private_dir(kuma_home() / "kuro") / "crash.log"


def _append_crash_log(method: str, params_summary: str, tb: str) -> None:
    """Append an error entry to the crash log (FIFO, max 50 entries)."""
    append_crash_log(_get_crash_log_path(), method, params_summary, tb)


# FASTA 미허용. annotated sequence formats only (CDS 메타데이터 필요).
_ALLOWED_FASTA_EXTENSIONS = {".dna", ".gb", ".gbff", ".gbk"}
_ALLOWED_CSV_EXTENSIONS = {".csv", ".tsv", ".txt"}
_ALLOWED_EXCEL_EXTENSIONS = {".xlsx"}
_VALID_DNA_BASES = re.compile(r"^[ATGC]+$")

def _get_ssl_ctx():
    from kuma_core.shared.net import get_ssl_context
    return get_ssl_context()


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


_rpc_writer = JsonRpcWriter()


def _send(obj: dict) -> None:
    """Write a JSON object to stdout (one line). Thread-safe."""
    _rpc_writer.send(obj)


def _ok(req_id, result) -> None:
    _rpc_writer.ok(req_id, result)


def _error(req_id, code: int, message: str) -> None:
    _rpc_writer.error(req_id, code, message)


def _progress(value: int, message: str = "") -> None:
    _rpc_writer.progress(value, message)


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
    return validate_filepath(
        filepath,
        allowed_extensions=allowed_extensions,
        must_exist=False,
    )


def _validate_output_path(
    filepath: str | None, *, allowed_extensions: set[str]
) -> Path:
    """Validate an output file path (file may not exist yet).

    Raises FileNotFoundError on traversal, symlinks, or missing parent.
    Raises ValueError on disallowed extension.
    """
    return validate_output_path(filepath, allowed_extensions=allowed_extensions)
