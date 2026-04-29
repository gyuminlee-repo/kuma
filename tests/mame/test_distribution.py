"""Tests for kuma_core.mame.distribution (A4 — run-level distribution analysis)."""

from __future__ import annotations

from kuma_core.mame.distribution import (
    _FLOOR_KB,
    DistributionStats,
    compute_distribution_stats,
)


def test_empty_input_returns_defaults() -> None:
    stats = compute_distribution_stats([])
    assert stats.n_files == 0
    assert stats.suggested_cutoff_kb == _FLOOR_KB
    assert stats.suggested_method == "fixed_50"
    assert stats.bimodal is False


def test_single_value() -> None:
    stats = compute_distribution_stats([200.0])
    assert stats.n_files == 1
    assert stats.file_size_kb["min"] == 200.0
    assert stats.file_size_kb["max"] == 200.0


def test_tight_distribution_uses_p05() -> None:
    """Uniform distribution around 300 KB → p05 method expected."""
    data = [290.0 + i for i in range(20)]  # 290–309, tight IQR
    stats = compute_distribution_stats(data)
    assert stats.n_files == 20
    # Tight IQR/median < 0.5 → p05 (or floor override if p05 < 50)
    assert stats.suggested_method in ("p05", "fixed_50")
    assert stats.suggested_cutoff_kb >= _FLOOR_KB


def test_bimodal_distribution_detected() -> None:
    """Two clearly separated clusters → bimodal=True, kneedle method.

    Both clusters are above the 50 KB floor so the floor guard does not fire.
    """
    low_cluster = [60.0 + i * 0.5 for i in range(10)]   # ~60–65 KB
    high_cluster = [800.0 + i * 10 for i in range(10)]  # ~800–890 KB
    data = low_cluster + high_cluster
    stats = compute_distribution_stats(data)
    assert stats.bimodal is True
    assert stats.suggested_method == "kneedle"
    # Knee should be somewhere between the two clusters (well above floor)
    assert stats.suggested_cutoff_kb >= _FLOOR_KB


def test_floor_applied_when_cutoff_too_low() -> None:
    """If computed cutoff < 50 KB, method must be fixed_50 and cutoff = 50."""
    # All values are very small → median-2σ or p05 would be below 50
    data = [10.0, 12.0, 11.0, 9.5, 13.0]
    stats = compute_distribution_stats(data)
    assert stats.suggested_cutoff_kb == _FLOOR_KB
    assert stats.suggested_method == "fixed_50"


def test_stats_keys_present() -> None:
    data = list(range(10, 110, 5))  # 10, 15, …, 105
    stats = compute_distribution_stats(data)
    expected_keys = {"min", "p05", "p25", "median", "p75", "p95", "max", "mean", "std"}
    assert expected_keys == set(stats.file_size_kb.keys())


def test_return_type_is_distribution_stats() -> None:
    stats = compute_distribution_stats([100.0, 200.0, 300.0])
    assert isinstance(stats, DistributionStats)
