"""JSON-RPC handler: read __kuma_meta__ from an xlsx file."""
from __future__ import annotations

from pathlib import Path

from kuma_core.mame.io.kuma_meta import read_kuma_meta


def handle_read_kuma_meta(params: dict) -> dict | None:
    """Return meta dict if present else None."""
    path = params.get("path") or params.get("filepath")
    if not path:
        raise ValueError("'path' parameter required")
    meta = read_kuma_meta(Path(path))
    if meta is None:
        return None
    return meta.to_dict()
