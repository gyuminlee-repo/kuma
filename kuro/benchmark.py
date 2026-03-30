"""Benchmark framework for KURO diversity selection strategies."""

from __future__ import annotations

import random
import re

from .evolvepro import domain_aware_select, pareto_diversity_select


def simulate_selection(
    fitness_landscape: list[tuple[str, float]],
    n_select: int,
    strategy: str = "topn",
    **kwargs,
) -> list[tuple[str, float]]:
    """Simulate variant selection with different strategies.

    Parameters
    ----------
    fitness_landscape : list[tuple[str, float]]
        [(variant, fitness), ...] sorted by fitness desc.
    n_select : int
        Number of variants to select.
    strategy : str
        "topn", "random", "pareto", or "domain".

    Returns
    -------
    list[tuple[str, float]]
        Selected variants.
    """
    if strategy == "topn":
        return fitness_landscape[:n_select]
    elif strategy == "random":
        return random.sample(
            fitness_landscape, min(n_select, len(fitness_landscape))
        )
    elif strategy == "pareto":
        ca = kwargs.get("ca_coords")
        selected, _ = pareto_diversity_select(
            fitness_landscape,
            n_select,
            pool_multiplier=kwargs.get("pool_multiplier", 2.0),
            ca_coords=ca,
        )
        return selected
    elif strategy == "domain":
        selected, _ = domain_aware_select(
            fitness_landscape,
            kwargs.get("domains", []),
            n_select,
            kwargs.get("domain_strategy", "proportional"),
        )
        return selected
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


def evaluate_selection(
    selected: list[tuple[str, float]],
    ground_truth: dict[str, float],
    top_percentile: float = 10.0,
) -> dict:
    """Evaluate selection quality against ground truth fitness.

    Parameters
    ----------
    selected : list[tuple[str, float]]
        [(variant, predicted_fitness), ...]
    ground_truth : dict[str, float]
        {variant: actual_fitness}
    top_percentile : float
        What counts as a "hit" (top X% of actual fitness).

    Returns
    -------
    dict
        hit_rate, diversity_score, mean_fitness, coverage metrics.
    """
    # Calculate hit threshold
    all_fitness = sorted(ground_truth.values(), reverse=True)
    if not all_fitness:
        return {
            "n_selected": len(selected),
            "hit_rate": 0.0,
            "mean_fitness": 0.0,
            "unique_positions": 0,
            "position_coverage": 0.0,
            "hits": 0,
            "threshold": 0.0,
        }

    threshold_idx = max(1, int(len(all_fitness) * top_percentile / 100))
    hit_threshold = all_fitness[threshold_idx - 1]

    # Calculate metrics
    hits = 0
    total_fitness = 0.0
    positions: set[int] = set()

    for variant, _ in selected:
        actual = ground_truth.get(variant)
        if actual is not None:
            if actual >= hit_threshold:
                hits += 1
            total_fitness += actual
        # Extract position
        m = re.search(r"[A-Z](\d+)[A-Z]", variant)
        if m:
            positions.add(int(m.group(1)))

    n = len(selected)
    return {
        "n_selected": n,
        "hit_rate": hits / n * 100 if n > 0 else 0.0,
        "mean_fitness": total_fitness / n if n > 0 else 0.0,
        "unique_positions": len(positions),
        "position_coverage": len(positions) / n * 100 if n > 0 else 0.0,
        "hits": hits,
        "threshold": hit_threshold,
    }


def run_benchmark(
    fitness_landscape: list[tuple[str, float]],
    ground_truth: dict[str, float],
    n_select: int = 95,
    n_random_trials: int = 100,
    strategies: list[str] | None = None,
    **kwargs,
) -> dict[str, dict]:
    """Run full benchmark comparing multiple strategies.

    Parameters
    ----------
    fitness_landscape : list[tuple[str, float]]
        [(variant, fitness), ...] sorted by fitness desc.
    ground_truth : dict[str, float]
        {variant: actual_fitness}
    n_select : int
        Number of variants to select per strategy.
    n_random_trials : int
        Number of random trials for averaging.
    strategies : list[str] | None
        Strategy names to benchmark.

    Returns
    -------
    dict[str, dict]
        {strategy_name: evaluation_metrics}
    """
    if strategies is None:
        strategies = ["topn", "random", "pareto"]

    result_map: dict[str, dict] = {}

    for strategy in strategies:
        if strategy == "random":
            # Average over multiple trials
            trial_data: list[dict] = []
            for _ in range(n_random_trials):
                sel = simulate_selection(fitness_landscape, n_select, "random")
                trial_data.append(evaluate_selection(sel, ground_truth))
            # Average
            avg: dict = {}
            for key in trial_data[0]:
                values = [t[key] for t in trial_data]
                avg[key] = sum(values) / len(values)
            avg["n_trials"] = n_random_trials
            result_map[strategy] = avg
        else:
            sel = simulate_selection(
                fitness_landscape, n_select, strategy, **kwargs
            )
            result_map[strategy] = evaluate_selection(sel, ground_truth)

    return result_map
