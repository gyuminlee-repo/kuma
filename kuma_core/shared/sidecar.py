"""Shared helpers for Python sidecar processes."""

from __future__ import annotations

import datetime
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from kuma_core.shared.errors import jsonrpc_error

CRASH_LOG_MAX_ENTRIES = 50


def ensure_private_dir(path: Path) -> Path:
    """Create a user-private directory where platforms support chmod."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def append_crash_log(
    log_path: Path,
    method: str,
    params_summary: str,
    tb: str,
    *,
    max_entries: int = CRASH_LOG_MAX_ENTRIES,
) -> None:
    """Append one bounded crash-log entry. Logging failures are intentionally ignored."""
    try:
        ensure_private_dir(log_path.parent)
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "method": method,
            "params": params_summary[:200],
            "traceback": tb[:2000],
        }
        entries: list[dict[str, Any]] = []
        if log_path.exists():
            try:
                raw = log_path.read_text(encoding="utf-8").strip()
                if raw:
                    loaded = json.loads(raw)
                    entries = loaded if isinstance(loaded, list) else []
            except (json.JSONDecodeError, OSError):
                entries = []
        entries.append(entry)
        del entries[:-max_entries]
        log_path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


class JsonRpcWriter:
    """Thread-safe stdout writer for JSON-RPC sidecar messages."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def send(self, obj: dict[str, Any]) -> None:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        with self._lock:
            if getattr(sys, "frozen", False):
                # Frozen builds (PyInstaller): bypass the TextIOWrapper buffer and
                # write straight to the stdout fd. On Windows the buffered writer
                # withheld messages emitted from worker threads (async analyze/demux
                # responses + progress) until the main thread next touched stdout,
                # so the client only saw a response after sending its NEXT request.
                # A direct os.write delivers each message immediately from any thread.
                data = line.encode("utf-8")
                fd = sys.stdout.fileno()
                while data:
                    data = data[os.write(fd, data):]
            else:
                sys.stdout.write(line)
                sys.stdout.flush()

    def ok(self, req_id: Any, result: Any) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id, "result": result})

    def error(self, req_id: Any, code: int, message: str) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id, "error": jsonrpc_error(code, message)})

    def progress(self, value: int, message: str = "") -> None:
        self.send(
            {
                "jsonrpc": "2.0",
                "method": "progress",
                "params": {"value": value, "message": message},
            }
        )


def _validate_path_common(path_value: str | None, *, value_name: str) -> tuple[Path, Path]:
    if not path_value:
        raise FileNotFoundError(f"{value_name} is required")

    original = Path(path_value)
    if original.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {path_value}")
    if ".." in original.parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {path_value}")

    resolved = original.resolve()
    if resolved.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed (resolved): {path_value}")
    return original, resolved


def _validate_extension(resolved: Path, allowed_extensions: set[str] | None) -> None:
    if allowed_extensions is None:
        return
    ext = resolved.suffix.lower()
    if ext not in allowed_extensions:
        raise ValueError(
            f"Unsupported file extension '{ext}'. Allowed: {sorted(allowed_extensions)}"
        )


def validate_filepath(
    filepath: str | None,
    *,
    allowed_extensions: set[str] | None = None,
    must_exist: bool = True,
) -> Path:
    """Validate and resolve an input file path."""
    _, resolved = _validate_path_common(filepath, value_name="filepath")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"File does not exist: {filepath}")
    if resolved.is_dir():
        raise FileNotFoundError(f"Path is a directory, not a file: {filepath}")
    _validate_extension(resolved, allowed_extensions)
    return resolved


def validate_dirpath(dirpath: str | None) -> Path:
    """Validate and resolve an existing directory path."""
    _, resolved = _validate_path_common(dirpath, value_name="dirpath")
    if not resolved.exists():
        raise FileNotFoundError(f"Directory does not exist: {dirpath}")
    if not resolved.is_dir():
        raise FileNotFoundError(f"Path is not a directory: {dirpath}")
    return resolved


def validate_output_path(filepath: str | None, *, allowed_extensions: set[str]) -> Path:
    """Validate an output path whose parent must already exist."""
    _, resolved = _validate_path_common(filepath, value_name="filepath")
    if not resolved.parent.exists():
        raise FileNotFoundError(f"Parent directory does not exist: {resolved.parent}")
    _validate_extension(resolved, allowed_extensions)
    return resolved
