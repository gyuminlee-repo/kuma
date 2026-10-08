"""Shared config path helpers for the kuma ecosystem."""
from __future__ import annotations

import os
from pathlib import Path


def kuma_home() -> Path:
    """User kuma config directory (~/.kuma). Respects HOME env var."""
    home = os.environ.get("HOME") or str(Path.home())
    return Path(home) / ".kuma"


def kuma_logs_dir() -> Path:
    return kuma_home() / "logs"


def kuma_cache_dir() -> Path:
    return kuma_home() / "cache"
