"""Reproducibility manifest generation for kuma pipeline runs.

Each export operation writes a ``{output_basename}.run.json`` file alongside
the exported file. The manifest records:

- kuma/kuro/python/platform version
- input file SHA-256 hashes + sizes
- call parameters (sanitised to JSON-serialisable form)
- ISO-8601 UTC timestamps + duration

Usage::

    from kuma_core.shared.run_manifest import (
        compute_input_sha256,
        build_run_manifest,
        write_run_manifest,
        load_run_manifest,
    )

Schema version history:
    1.0  Initial release (2026-05-07)
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kuma_core.shared.atomic_write import atomic_write_text
from kuma_core.shared.version import KUMA_VERSION, KURO_MODULE_VERSION

SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def compute_input_sha256(path: Path) -> str:
    """Return the hex-encoded SHA-256 digest of *path*.

    Reads the file in 1 MiB chunks so large files do not exhaust memory.

    Raises:
        FileNotFoundError: *path* does not exist.
        IsADirectoryError: *path* is a directory.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _serialise_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy of *params*.

    Path objects are converted to strings. Non-serialisable objects fall
    back to their ``str()`` representation (no silent data loss — the string
    is always present).
    """
    return json.loads(json.dumps(params, default=str))


def build_run_manifest(
    *,
    method: str,
    inputs: dict[str, Path],
    params: dict[str, Any],
    started_at: datetime,
    finished_at: datetime,
    seed: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct the run-manifest dict (not yet written to disk).

    Args:
        method: RPC method name, e.g. ``"design_sdm_primers"``.
        inputs: Mapping from logical name to file ``Path``. Missing or
            non-existent paths are silently omitted from the manifest
            (spec: "입력 파일 부재 시 해당 키 생략").
        params: Handler call parameters. Serialised via ``json.dumps`` with
            ``default=str``; paths within params are normalised to strings.
        started_at: UTC datetime recorded at handler entry.
        finished_at: UTC datetime recorded after export write completes.
        seed: Optional RNG seed for reproducibility.
        extra: Optional free-form dict for handler-specific metadata.

    Returns:
        dict conforming to schema version 1.0.
    """
    # Validate timestamps have timezone info
    if started_at.tzinfo is None:
        raise ValueError("started_at must be timezone-aware (UTC)")
    if finished_at.tzinfo is None:
        raise ValueError("finished_at must be timezone-aware (UTC)")

    # Build inputs section — silently skip absent files.
    inputs_section: dict[str, Any] = {}
    for key, path in inputs.items():
        if not isinstance(path, Path):
            path = Path(path)
        if not path.exists():
            continue
        try:
            sha = compute_input_sha256(path)
            size = path.stat().st_size
        except (OSError, PermissionError):
            continue
        inputs_section[key] = {
            "path": str(path),
            "sha256": sha,
            "size_bytes": size,
        }

    duration = (finished_at - started_at).total_seconds()

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "method": method,
        "kuma_version": KUMA_VERSION,
        "kuro_module_version": KURO_MODULE_VERSION,
        "python_version": sys.version,
        "platform": platform.system().lower(),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration, 3),
        "inputs": inputs_section,
        "params": _serialise_params(params),
        "seed": seed,
    }

    if extra is not None:
        manifest["extra"] = _serialise_params(extra)

    return manifest


def write_run_manifest(output_path: Path, manifest: dict[str, Any]) -> Path:
    """Write *manifest* as JSON to *output_path*.

    The parent directory must already exist (same contract as other kuma
    export helpers — directory creation is the caller's responsibility).

    Args:
        output_path: Destination path; must end in ``.json``.
        manifest: Dict returned by :func:`build_run_manifest`.

    Returns:
        The resolved absolute path that was written.

    Raises:
        ValueError: *output_path* does not have a ``.json`` extension.
        FileNotFoundError: Parent directory does not exist.
    """
    output_path = Path(output_path).resolve()
    if output_path.suffix.lower() != ".json":
        raise ValueError(
            f"Manifest path must end in .json, got: {output_path.suffix!r}"
        )
    if not output_path.parent.exists():
        raise FileNotFoundError(
            f"Parent directory does not exist: {output_path.parent}"
        )
    # Atomic (temp + os.replace) so an interrupted write never leaves a
    # truncated manifest behind the final path.
    atomic_write_text(
        output_path,
        json.dumps(manifest, ensure_ascii=False, indent=2),
    )
    return output_path


def load_run_manifest(path: Path) -> dict[str, Any]:
    """Load and return the manifest dict from *path*.

    Raises:
        FileNotFoundError: *path* does not exist.
        json.JSONDecodeError: File content is not valid JSON.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest file not found: {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


__all__ = [
    "SCHEMA_VERSION",
    "compute_input_sha256",
    "build_run_manifest",
    "write_run_manifest",
    "load_run_manifest",
]
