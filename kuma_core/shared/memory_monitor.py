"""RSS-based memory monitor for sidecar processes.

Provides threshold constants and helpers used by dispatcher periodic checks
to emit JSON-RPC ``memory_warning`` notifications.
"""

from __future__ import annotations

import os

import psutil

WARN_THRESHOLD = 0.50
BLOCK_THRESHOLD = 0.70


def get_self_rss_bytes() -> int:
    """Return current process RSS in bytes."""
    return psutil.Process(os.getpid()).memory_info().rss


def get_system_total_bytes() -> int:
    """Return total physical memory in bytes."""
    return psutil.virtual_memory().total


def memory_usage_ratio() -> float:
    """Return self RSS / system total in the range [0.0, 1.0]."""
    total = get_system_total_bytes()
    if total == 0:
        return 0.0
    return get_self_rss_bytes() / total
