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


def memory_usage_ratio() -> float | None:
    """Return self RSS / system total in the range [0.0, 1.0], or None.

    None means the ratio could not be computed because the system total came
    back as zero. That is distinct from 0.0, which means the process is using
    no measurable share of a total that was read successfully.

    The distinction matters because every caller compares the result against
    :data:`WARN_THRESHOLD` and :data:`BLOCK_THRESHOLD`. Returning 0.0 for an
    unreadable total silences the warning and the block for the life of the
    process, with nothing to say the guard is off. A caller that cannot act on
    None has to say so rather than inherit a benign-looking number.
    """
    total = get_system_total_bytes()
    if total == 0:
        return None
    return get_self_rss_bytes() / total
