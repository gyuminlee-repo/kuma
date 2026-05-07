"""Tests for kuma_core.shared.memory_monitor."""

from kuma_core.shared.memory_monitor import (
    BLOCK_THRESHOLD,
    WARN_THRESHOLD,
    get_self_rss_bytes,
    get_system_total_bytes,
    memory_usage_ratio,
)


def test_get_self_rss_bytes_positive() -> None:
    rss = get_self_rss_bytes()
    assert rss > 0, f"Expected positive RSS, got {rss}"


def test_get_system_total_bytes_positive() -> None:
    total = get_system_total_bytes()
    assert total > 0, f"Expected positive total memory, got {total}"


def test_memory_usage_ratio_range() -> None:
    ratio = memory_usage_ratio()
    assert 0.0 <= ratio <= 1.0, f"Expected ratio in [0.0, 1.0], got {ratio}"


def test_warn_threshold_defined() -> None:
    assert WARN_THRESHOLD == 0.50


def test_block_threshold_defined() -> None:
    assert BLOCK_THRESHOLD == 0.70


def test_block_threshold_greater_than_warn() -> None:
    assert BLOCK_THRESHOLD > WARN_THRESHOLD
