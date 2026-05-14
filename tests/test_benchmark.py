"""Tests for kuro.benchmark module."""

from __future__ import annotations

import random

import pytest

from kuma_core.kuro.benchmark import evaluate_selection, run_benchmark, simulate_selection
from kuma_core.kuro.evolvepro import (
    _grantham_dist,
    _position_filter_with_tiebreak,
    _rho_from_cumulative,
    load_evolvepro_csv,
    sigma_adaptive_params,
)


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

    def test_pareto_3d_alias(self):
        land = _make_landscape(50)
        sel = simulate_selection(land, 10, "pareto_3d")
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

    def test_domain_overlap_policy_largest(self):
        land = [("A15C", 1.0), ("A35D", 0.9)]
        domains = [
            {"name": "Small", "start": 10, "end": 20},
            {"name": "Large", "start": 1, "end": 40},
        ]
        sel = simulate_selection(
            land,
            1,
            "domain",
            domains=domains,
            domain_strategy="equal",
            domain_overlap_policy="largest",
        )
        assert sel == [("A15C", 1.0)]

    def test_domain_separate_linker_bin(self):
        land = [("A10C", 1.0), ("A90D", 0.9), ("A110E", 0.8)]
        domains = [{"name": "Core", "start": 1, "end": 20}]
        sel = simulate_selection(
            land,
            2,
            "domain",
            domains=domains,
            domain_strategy="equal",
            linker_handling="separate-bin",
        )
        assert len(sel) == 2
        assert ("A90D", 0.9) in sel or ("A110E", 0.8) in sel

    def test_domain_quota_min(self):
        land = [("A10C", 1.0), ("A40D", 0.95), ("A80E", 0.9)]
        domains = [
            {"name": "N", "start": 1, "end": 20},
            {"name": "M", "start": 21, "end": 60},
            {"name": "C", "start": 61, "end": 100},
        ]
        sel = simulate_selection(
            land,
            3,
            "domain",
            domains=domains,
            domain_strategy="proportional",
            domain_quota_min=1,
        )
        assert len(sel) == 3

    def test_position_cap(self):
        land = [
            ("A10C", 1.0),
            ("A10D", 0.95),
            ("A20E", 0.9),
            ("A20F", 0.85),
            ("A30G", 0.8),
        ]
        sel = simulate_selection(land, 5, "position_cap", max_per_position=1)
        assert len(sel) == 3
        assert [variant for variant, _ in sel] == ["A10C", "A20E", "A30G"]

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

    def test_pareto_3d_mode_falls_back_without_coords(self):
        land = _make_landscape(50)
        sel = simulate_selection(land, 10, "pareto_3d", distance_mode="3d", ca_coords=None)
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
        gt = {"A10C": 1.0, "A20D": 0.9, "A30E": 0.5}
        sel = [("A10C", 1.0), ("A20D", 0.9)]
        domains = [
            {"name": "N-term", "start": 1, "end": 15},
            {"name": "Mid", "start": 16, "end": 25},
            {"name": "C-term", "start": 26, "end": 40},
        ]
        metrics = evaluate_selection(sel, gt, domains=domains)
        assert "domain_coverage" in metrics
        assert abs(metrics["domain_coverage"] - 2 / 3 * 100) < 0.1

    def test_domain_coverage_full(self):
        gt = {"A10C": 1.0, "A20D": 0.9}
        sel = [("A10C", 1.0), ("A20D", 0.9)]
        domains = [
            {"name": "N-term", "start": 1, "end": 15},
            {"name": "C-term", "start": 16, "end": 25},
        ]
        metrics = evaluate_selection(sel, gt, domains=domains)
        assert abs(metrics["domain_coverage"] - 100.0) < 0.1

    def test_domain_coverage_empty_ground_truth(self):
        sel = [("A10C", 1.0)]
        metrics = evaluate_selection(sel, {})
        assert metrics["domain_coverage"] == 0.0

    def test_structural_spread_without_coords(self):
        gt = {"A10C": 1.0, "A20D": 0.9, "A40E": 0.8}
        sel = [("A10C", 1.0), ("A20D", 0.9), ("A40E", 0.8)]
        metrics = evaluate_selection(sel, gt)
        assert metrics["structural_spread"] > 0.0


class TestRunBenchmark:
    """Integration tests for run_benchmark."""

    def test_default_strategies(self):
        land = _make_landscape(100)
        gt = _make_ground_truth(land)
        bench = run_benchmark(land, gt, n_select=20, n_random_trials=5)
        assert "topn" in bench
        assert "random" in bench
        assert "position_cap" in bench
        assert "domain" in bench
        assert "pareto_1d" in bench
        assert "pareto_3d" in bench
        assert "pareto_entropy" in bench
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
        """Pareto 3D should cover more unique positions than Top-N."""
        # Create landscape with many variants at same positions
        land = []
        for pos in [10, 10, 10, 20, 20, 20, 30, 30, 30, 100, 200, 300]:
            aa = "ACDEFGHIKLM"[len(land) % 11]
            land.append((f"A{pos}{aa}", 1.0 - len(land) * 0.01))
        gt = {v: f for v, f in land}
        bench = run_benchmark(
            land, gt, n_select=6, strategies=["topn", "pareto_3d"],
        )
        assert bench["pareto_3d"]["unique_positions"] >= bench["topn"]["unique_positions"]

    def test_random_seed_is_reproducible(self):
        land = _make_landscape(100)
        gt = _make_ground_truth(land)
        bench_a = run_benchmark(
            land,
            gt,
            n_select=20,
            n_random_trials=10,
            strategies=["random"],
            random_seed=123,
        )
        bench_b = run_benchmark(
            land,
            gt,
            n_select=20,
            n_random_trials=10,
            strategies=["random"],
            random_seed=123,
        )
        assert bench_a == bench_b

    def test_top_percentile_changes_threshold(self):
        land = _make_landscape(100)
        gt = _make_ground_truth(land)
        bench_10 = run_benchmark(land, gt, n_select=10, top_percentile=10, strategies=["topn"])
        bench_20 = run_benchmark(land, gt, n_select=10, top_percentile=20, strategies=["topn"])
        assert bench_10["topn"]["threshold"] > bench_20["topn"]["threshold"]


class TestSigmaAdaptivePool:
    """Unit tests for σ-adaptive pool K / entropy weight computation."""

    def test_rho_from_cumulative_boundaries(self):
        assert _rho_from_cumulative(1) == 0.40
        assert _rho_from_cumulative(96) == 0.40
        assert _rho_from_cumulative(97) == 0.50
        assert _rho_from_cumulative(192) == 0.50
        assert _rho_from_cumulative(193) == 0.60
        assert _rho_from_cumulative(384) == 0.60
        assert _rho_from_cumulative(385) == 0.70
        assert _rho_from_cumulative(1000) == 0.70

    def test_sigma_adaptive_params_round1(self):
        """Round 1 × 96 = cumulative 96 → K=0.50, ew=0.30."""
        k, ew = sigma_adaptive_params(1, 96)
        assert k == pytest.approx(0.50)
        assert ew == pytest.approx(0.30)

    def test_sigma_adaptive_params_round2(self):
        """Round 2 × 96 = cumulative 192 → K=0.40, ew=0.25."""
        k, ew = sigma_adaptive_params(2, 96)
        assert k == pytest.approx(0.40)
        assert ew == pytest.approx(0.25)

    def test_sigma_adaptive_params_round4(self):
        """Round 4 × 96 = cumulative 384 → K=0.30, ew=0.20."""
        k, ew = sigma_adaptive_params(4, 96)
        assert k == pytest.approx(0.30)
        assert ew == pytest.approx(0.20)

    def test_sigma_adaptive_params_round5(self):
        """Round 5 × 96 = cumulative 480 → K=0.25, ew=0.15."""
        k, ew = sigma_adaptive_params(5, 96)
        assert k == pytest.approx(0.25)
        assert ew == pytest.approx(0.15)

    def test_sigma_adaptive_pool_wider_at_round1(self, tmp_path):
        """σ-adaptive pool (round=1) should select at least top_n variants."""
        import csv
        csv_path = tmp_path / "test.csv"
        # 200 variants with linearly decreasing scores
        rows = [(f"A{10 + i * 2}C", 1.0 - i * 0.005) for i in range(200)]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["variant", "y_pred"])
            writer.writeheader()
            for v, y in rows:
                writer.writerow({"variant": v, "y_pred": y})

        result = load_evolvepro_csv(
            csv_path,
            top_n=48,
            pareto_diversity=True,
            evolvepro_round=1,
            round_size=96,
        )
        # Pool is σ-adaptive: selected_count should equal top_n
        assert result["selected_count"] == 48

    def test_sigma_adaptive_entropy_auto_override(self, tmp_path):
        """When round > 0, entropy_weight is auto-set; manual value is ignored."""
        import csv
        csv_path = tmp_path / "test.csv"
        rows = [(f"A{10 + i * 2}V", 1.0 - i * 0.01) for i in range(100)]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["variant", "y_pred"])
            writer.writeheader()
            for v, y in rows:
                writer.writerow({"variant": v, "y_pred": y})

        # With round=1, entropy_weight should be auto 0.30 (not manual 0.0)
        result = load_evolvepro_csv(
            csv_path,
            top_n=20,
            pareto_diversity=True,
            entropy_weight=0.0,  # manual — should be overridden
            evolvepro_round=1,
            round_size=96,
        )
        assert result["selected_count"] == 20


class TestGranthamTieBreak:
    """Unit tests for Grantham-distance tie-break in position filter."""

    def test_grantham_dist_same_aa(self):
        assert _grantham_dist("A10A") == 0

    def test_grantham_dist_conservative(self):
        # I→L is 5, one of the most conservative substitutions
        assert _grantham_dist("I10L") == 5

    def test_grantham_dist_radical(self):
        # C→W is 215, the most radical substitution
        assert _grantham_dist("C10W") == 215

    def test_grantham_dist_unknown_variant(self):
        # Non-standard format → fallback 215
        assert _grantham_dist("multi_mut") == 215

    def test_tiebreak_prefers_conservative_substitution(self):
        """When two variants score within 2%, pick the more conservative one."""
        # A10L (Grantham 96) vs A10G (Grantham 60)
        # Both score ~1.0 (within 2% threshold)
        rows = [("A10G", 1.0), ("A10L", 0.995)]  # already sorted desc
        result = _position_filter_with_tiebreak(rows, max_per_position=1)
        assert len(result) == 1
        # A10G has lower Grantham distance (60 < 96) → preferred
        assert result[0][0] == "A10G"

    def test_tiebreak_ignores_grantham_when_clear_winner(self):
        """When top score is clearly better (> 2%), pick it regardless of Grantham."""
        # A10L scores 1.0, A10G scores 0.95 → 5% gap → top1 wins
        rows = [("A10L", 1.0), ("A10G", 0.95)]
        result = _position_filter_with_tiebreak(rows, max_per_position=1)
        assert result[0][0] == "A10L"

    def test_tiebreak_alphabetical_fallback(self):
        """Equal Grantham distance → alphabetical order."""
        # I→L (5) vs L→I (5) — same distance; use variant name alphabetically
        rows = [("L10I", 1.0), ("I10L", 1.0)]
        result = _position_filter_with_tiebreak(rows, max_per_position=1)
        assert len(result) == 1
        # "I10L" < "L10I" alphabetically
        assert result[0][0] == "I10L"

    def test_position_filter_respects_max_per_position(self):
        """max_per_position=2 allows 2 variants per position."""
        rows = [("A10C", 1.0), ("A10D", 0.99), ("A10E", 0.98), ("A20F", 0.97)]
        result = _position_filter_with_tiebreak(rows, max_per_position=2)
        pos10_variants = [v for v, _ in result if "10" in v]
        assert len(pos10_variants) == 2

    def test_position_filter_no_pos_variants_pass_through(self):
        """Variants without standard format (e.g. multi-mutants) pass through."""
        rows = [("A10C_B20D", 1.0), ("A10C", 0.9)]
        result = _position_filter_with_tiebreak(rows, max_per_position=1)
        # A10C_B20D has no position → passes through; A10C is the only pos-10 variant
        assert len(result) == 2


class TestPoolVariants:
    """Tests for pool_variants returned by load_evolvepro_csv."""

    def test_pool_variants_returned(self, tmp_path):
        """load_evolvepro_csv should return pool_variants list."""
        import csv
        csv_path = tmp_path / "test.csv"
        rows = [(f"A{10 + i}C", 1.0 - i * 0.01) for i in range(50)]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["variant", "y_pred"])
            writer.writeheader()
            for v, y in rows:
                writer.writerow({"variant": v, "y_pred": y})

        result = load_evolvepro_csv(csv_path, top_n=10)
        assert "pool_variants" in result
        assert len(result["pool_variants"]) == 10
        # pool_variants should be the top-scoring variants
        assert result["pool_variants"][0] == "A10C"

    def test_pool_variants_with_pareto(self, tmp_path):
        """With pareto_diversity, pool_variants should be larger than selected."""
        import csv
        csv_path = tmp_path / "test.csv"
        rows = [(f"A{10 + i * 2}C", 1.0 - i * 0.01) for i in range(100)]
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["variant", "y_pred"])
            writer.writeheader()
            for v, y in rows:
                writer.writerow({"variant": v, "y_pred": y})

        result = load_evolvepro_csv(csv_path, top_n=20, pareto_diversity=True, pool_multiplier=2.0)
        assert len(result["pool_variants"]) >= 20
        assert len(result["pool_variants"]) <= 40  # top_n * pool_multiplier


class TestAutoRelaxTolMax:
    """Tests for tol_max parameter in design_single_sdm."""

    def test_tol_max_parameter_accepted(self):
        """design_single_sdm should accept tol_max parameter without error."""
        import inspect
        from kuma_core.kuro.sdm_engine import design_single_sdm
        sig = inspect.signature(design_single_sdm)
        assert "tol_max" in sig.parameters
        assert sig.parameters["tol_max"].default == 4.0
