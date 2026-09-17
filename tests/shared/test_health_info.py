"""Tests for health_info handler logic.

Validates that health_info returns sensible PID and RSS values
without invoking the full dispatcher machinery.
"""

from __future__ import annotations

import importlib
import os
import sys

from kuma_core.shared.memory_monitor import get_self_rss_bytes
import pytest


@pytest.mark.parametrize("sidecar", ["sidecar_kuro", "sidecar_mame"])
def test_health_info_pid(sidecar: str) -> None:
    """PID returned by health_info matches the current process."""
    result = importlib.import_module(f"{sidecar}.dispatcher")._METHODS["health_info"]({})
    assert result["pid"] == os.getpid()


def test_health_info_rss_positive() -> None:
    """RSS returned by memory_monitor is positive (sidecar is alive)."""
    rss = get_self_rss_bytes()
    assert rss > 0, f"Expected positive RSS bytes, got {rss}"


@pytest.mark.parametrize("sidecar", ["sidecar_kuro", "sidecar_mame"])
def test_health_info_py_version(sidecar: str) -> None:
    """Python version string is non-empty and starts with a digit."""
    result = importlib.import_module(f"{sidecar}.dispatcher")._METHODS["health_info"]({})
    assert result["py_version"] == sys.version.split()[0]
    assert result["rss_bytes"] > 0
