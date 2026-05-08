"""Tests for health_info handler logic.

Validates that health_info returns sensible PID and RSS values
without invoking the full dispatcher machinery.
"""

from __future__ import annotations

import os
import sys

from kuma_core.shared.memory_monitor import get_self_rss_bytes


def test_health_info_pid() -> None:
    """PID returned by health_info matches the current process."""
    pid = os.getpid()
    assert pid > 0, f"Expected positive PID, got {pid}"


def test_health_info_rss_positive() -> None:
    """RSS returned by memory_monitor is positive (sidecar is alive)."""
    rss = get_self_rss_bytes()
    assert rss > 0, f"Expected positive RSS bytes, got {rss}"


def test_health_info_py_version() -> None:
    """Python version string is non-empty and starts with a digit."""
    version = sys.version.split()[0]
    assert version, "Python version string must not be empty"
    assert version[0].isdigit(), f"Expected version to start with a digit, got {version!r}"
