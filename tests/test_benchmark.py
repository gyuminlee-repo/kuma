"""Tests for kuro.benchmark module."""

from __future__ import annotations

import random

import pytest

from kuro.benchmark import evaluate_selection, run_benchmark, simulate_selection


def _make_landscape(n: int = 200) -> list[tuple[str, float]]:
    """Create a synthetic fitness landscape for testing."""
    variants = []
    for i in range(n):
        pos = 10 + i * 2
        aa = "ACDEFGHIKLMNPQRSTVWY"[i % 20]
        variant = f"A{pos}{aa}"
        fitness = 1.0 - (i / n)
        variants.append((variant, fitness))
    return variants


def _make_ground_truth(landscape: list[tuple[str, float]]) -> dict[str, float]:
    """Ground truth = actual fitness (use predicted as proxy for testing)."""
    return {v: f for v, f in landscape}


class TestSimulateSelection:
    """Unit tests for simulate_selection."""

    def test_topn(self):
        land = _make_landscape(50)
        sel = simulate_selection(land, 10, "topn")
        assert len(sel) == 10
        assert sel == land[:10]

    def test_random(self):
        land = _make_landscape(50)
        sel = simulate_selection(land, 10, "random")
        assert len(sel) == 10

    def test_pareto(self):
        land = _make_landscape(50)
        sel = simulate_selection(land, 10, "pareto")
        assert len(sel) == 10
        # First selected should be the best fitness
        assert sel[0] == land[0]

    def test_unknown_strategy_raises(self):
        land = _make_landscape(10)
        with pytest.raises(ValueError, match="Unknown strategy"):
            simulate_selection(land, 5, "nonexistent")

    def test_select_more_than_available(self):
        land = _make_landscape(5)
        sel = simulate_selection(land, 10, "topn")
        assert len(sel) == 5

    def test_domain_strategy(self):
        land = _make_landscape(50)
        domains = [
            {"name": "N-term", "start": 10, "end": 50},
            {"name": "C-term", "start": 51, "end": 110},
        ]
        sel = simulate_selection(
            land, 10, "domain", domains=domains, domain_strategy="equal"
        )
        assert len(sel) <= 10

    def test_pareto_entropy(self):
        land = _make_landscape(50)
        sel = simulate_selection(land, 10, "pareto_entropy")
        assert len(sel) == 10
        # First selected should be the best fitness
        assert sel[0] == land[0]

    def test_pareto_entropy_custom_weight(self):
        land = _make_landscape(50)
        sel = simulate_selection(land, 10, "pareto_entropy", entropy_weight=0.5)
        assert len(sel) == 10


class TestEvaluateSelection:
    """Unit tests for evaluate_selection."""

    def test_perfect_selection(self):
        land = _make_landscape(100)
        gt = _make_ground_truth(land)
        # Select top 10 (all should be hits at top 10%)
        sel = land[:10]
        metrics = evaluate_selection(sel, gt, top_percentile=10.0)
        assert metrics["n_selected"] == 10
        assert metrics["hit_rate"] == 100.0
        assert metrics["hits"] == 10

    def test_empty_selection(self):
        gt = {"A10C": 1.0, "A20D": 0.5}
        metrics = evaluate_selection([], gt)
        assert metrics["n_selected"] == 0
        assert metrics["hit_rate"] == 0.0

    def test_empty_ground_truth(self):
        sel = [("A10C", 1.0)]
        metrics = evaluate_selection(sel, {})
        assert metrics["n_selected"] == 1
        assert metrics["hit_rate"] == 0.0

    def test_position_coverage(self):
        sel = [("A10C", 1.0), ("A20D", 0.9), ("A10E", 0.8)]
        gt = {"A10C": 1.0, "A20D": 0.9, "A10E": 0.8}
        metrics = evaluate_selection(sel, gt)
        # 2 unique positions (10 and 20) out of 3 selected
        assert metrics["unique_positions"] == 2
        assert abs(metrics["position_coverage"] - 2 / 3 * 100) < 0.1

    def test_domain_coverage(self):
        # ground_truth has positions 10, 20, 30 → max_positions = 3
        # selected covers positions 10 and 20 → domain_coverage = 2/3 * 100
        gt = {"A10C": 1.0, "A20D": 0.9, "A30E": 0.5}
        sel = [("A10C", 1.0), ("A20D", 0.9)]
        metrics = evaluate_selection(sel, gt)
        assert "domain_coverage" in metrics
        assert abs(metrics["domain_coverage"] - 2 / 3 * 100) < 0.1

    def test_domain_coverage_full(self):
        # Selected covers all positions present in ground_truth
        gt = {"A10C": 1.0, "A20D": 0.9}
        sel = [("A10C", 1.0), ("A20D", 0.9)]
        metrics = evaluate_selection(sel, gt)
        assert abs(metrics["domain_coverage"] - 100.0) < 0.1

    def test_domain_coverage_empty_ground_truth(self):
        sel = [("A10C", 1.0)]
        metrics = evaluate_selection(sel, {})
        assert metrics["domain_coverage"] == 0.0


class TestRunBenchmark:
    """Integration tests for run_benchmark."""

    def test_default_strategies(self):
        land = _make_landscape(100)
        gt = _make_ground_truth(land)
        bench = run_benchmark(land, gt, n_select=20, n_random_trials=5)
        assert "topn" in bench
        assert "random" in bench
        assert "pareto" in bench
        # Random should have n_trials
        assert bench["random"]["n_trials"] == 5

    def test_single_strategy(self):
        land = _make_landscape(50)
        gt = _make_ground_truth(land)
        bench = run_benchmark(land, gt, n_select=10, strategies=["topn"])
        assert "topn" in bench
        assert "random" not in bench

    def test_topn_beats_random_on_hit_rate(self):
        """Top-N should generally have a higher hit rate than random."""
        random.seed(42)
        land = _make_landscape(200)
        gt = _make_ground_truth(land)
        bench = run_benchmark(
            land, gt, n_select=20, n_random_trials=50,
            strategies=["topn", "random"],
        )
        assert bench["topn"]["hit_rate"] >= bench["random"]["hit_rate"]

    def test_pareto_more_diverse_than_topn(self):
        """Pareto should cover more unique positions than Top-N."""
        # Create landscape with many variants at same positions
        land = []
        for pos in [10, 10, 10, 20, 20, 20, 30, 30, 30, 100, 200, 300]:
            aa = "ACDEFGHIKLM"[len(land) % 11]
            land.append((f"A{pos}{aa}", 1.0 - len(land) * 0.01))
        gt = {v: f for v, f in land}
        bench = run_benchmark(
            land, gt, n_select=6, strategies=["topn", "pareto"],
        )
        assert bench["pareto"]["unique_positions"] >= bench["topn"]["unique_positions"]
