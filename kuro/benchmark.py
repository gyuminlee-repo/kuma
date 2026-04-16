"""Benchmark framework for KURO Step 1-3 selection strategies."""

from __future__ import annotations

import random
import re
from itertools import combinations
from typing import TypedDict

from .alphafold import ca_max_dist, pairwise_ca_distance
from .evolvepro import domain_aware_select, pareto_diversity_select


class SelectionMetrics(TypedDict, total=False):
    """Metrics returned by evaluate_selection() for a single strategy trial."""
    n_selected: int
    hit_rate: float
    mean_fitness: float
    unique_positions: int
    position_coverage: float
    domain_coverage: float
    structural_spread: float
    hits: int
    threshold: float
    n_trials: int

_POS_RE = re.compile(r"[A-Z](\d+)[A-Z]")


def _variant_pos(variant: str) -> int | None:
    match = _POS_RE.search(variant)
    return int(match.group(1)) if match else None


def _apply_position_cap(
    fitness_landscape: list[tuple[str, float]],
    max_per_position: int,
) -> list[tuple[str, float]]:
    counts: dict[int, int] = {}
    selected: list[tuple[str, float]] = []
    for variant, fitness in fitness_landscape:
        pos = _variant_pos(variant)
        if pos is None:
            selected.append((variant, fitness))
            continue
        used = counts.get(pos, 0)
        if used >= max_per_position:
            continue
        counts[pos] = used + 1
        selected.append((variant, fitness))
    return selected


def _structural_spread(
    selected: list[tuple[str, float]],
    ca_coords: list[tuple[float, float, float] | None] | None = None,
) -> float:
    positions = [pos for variant, _ in selected if (pos := _variant_pos(variant)) is not None]
    if len(positions) < 2:
        return 0.0

    if ca_coords:
        max_dist = ca_max_dist(ca_coords)
        distances = [
            pairwise_ca_distance(ca_coords, a, b, max_dist)
            for a, b in combinations(positions, 2)
        ]
    else:
        max_pos = max(positions)
        scale = max(max_pos, 1)
        distances = [abs(a - b) / scale for a, b in combinations(positions, 2)]

    return sum(distances) / len(distances) * 100 if distances else 0.0


def simulate_selection(
    fitness_landscape: list[tuple[str, float]],
    n_select: int,
    strategy: str = "topn",
    *,
    rng: random.Random | None = None,
    max_per_position: int = 1,
    domains: list[dict] | None = None,
    domain_strategy: str = "proportional",
    domain_overlap_policy: str = "first",
    linker_handling: str = "include",
    domain_quota_min: int = 1,
    ca_coords: list[tuple[float, float, float] | None] | None = None,
    entropy_weight: float = 0.0,
    pool_multiplier: float = 2.0,
    distance_mode: str = "auto",
) -> list[tuple[str, float]]:
    """Simulate variant selection with KURO-style strategies."""
    _domains: list[dict] = domains or []
    if strategy == "topn":
        return fitness_landscape[:n_select]
    if strategy == "random":
        sampler = rng.sample if rng is not None else random.sample
        return sampler(fitness_landscape, min(n_select, len(fitness_landscape)))
    if strategy == "position_cap":
        capped = _apply_position_cap(fitness_landscape, max_per_position)
        return capped[:n_select]
    if strategy == "domain":
        selected, _ = domain_aware_select(
            fitness_landscape,
            _domains,
            n_select,
            domain_strategy,
            domain_overlap_policy=domain_overlap_policy,
            linker_handling=linker_handling,
            domain_quota_min=domain_quota_min,
        )
        return selected
    if strategy == "domain_pareto":
        selected, _ = domain_aware_select(
            fitness_landscape,
            _domains,
            n_select,
            domain_strategy,
            domain_overlap_policy=domain_overlap_policy,
            linker_handling=linker_handling,
            domain_quota_min=domain_quota_min,
            use_pareto=True,
            ca_coords=ca_coords,
            entropy_weight=entropy_weight,
            pool_multiplier=pool_multiplier,
            distance_mode=distance_mode,
        )
        return selected
    if strategy == "pareto_3d":
        selected, _ = pareto_diversity_select(
            fitness_landscape,
            n_select,
            pool_multiplier=pool_multiplier,
            ca_coords=ca_coords,
            distance_mode=distance_mode,
        )
        return selected
    if strategy == "pareto_1d":
        selected, _ = pareto_diversity_select(
            fitness_landscape,
            n_select,
            pool_multiplier=pool_multiplier,
            ca_coords=None,
            distance_mode="1d",
        )
        return selected
    if strategy == "pareto_entropy":
        selected, _ = pareto_diversity_select(
            fitness_landscape,
            n_select,
            pool_multiplier=pool_multiplier,
            ca_coords=ca_coords,
            entropy_weight=entropy_weight,
            distance_mode=distance_mode,
        )
        return selected
    raise ValueError(f"Unknown strategy: {strategy}")


def evaluate_selection(
    selected: list[tuple[str, float]],
    ground_truth: dict[str, float],
    top_percentile: float = 10.0,
    domains: list[dict] | None = None,
    ca_coords: list[tuple[float, float, float] | None] | None = None,
) -> SelectionMetrics:
    """Evaluate selection quality against ground truth fitness."""
    all_fitness = sorted(ground_truth.values(), reverse=True)
    if not all_fitness:
        return {
            "n_selected": len(selected),
            "hit_rate": 0.0,
            "mean_fitness": 0.0,
            "unique_positions": 0,
            "position_coverage": 0.0,
            "domain_coverage": 0.0,
            "structural_spread": 0.0,
            "hits": 0,
            "threshold": 0.0,
        }

    threshold_idx = max(1, int(len(all_fitness) * top_percentile / 100))
    hit_threshold = all_fitness[threshold_idx - 1]

    known_positions = {
        pos
        for variant in ground_truth
        if (pos := _variant_pos(variant)) is not None
    }

    hits = 0
    total_fitness = 0.0
    positions: set[int] = set()
    covered_domains: set[str] = set()

    for variant, _ in selected:
        actual = ground_truth.get(variant)
        if actual is not None:
            if actual >= hit_threshold:
                hits += 1
            total_fitness += actual

        pos = _variant_pos(variant)
        if pos is None:
            continue
        positions.add(pos)
        for domain in domains or []:
            if domain["start"] <= pos <= domain["end"]:
                covered_domains.add(domain["name"])
                break

    n = len(selected)
    total_domains = len(domains or [])
    return {
        "n_selected": n,
        "hit_rate": hits / n * 100 if n > 0 else 0.0,
        "mean_fitness": total_fitness / n if n > 0 else 0.0,
        "unique_positions": len(positions),
        "position_coverage": len(positions) / n * 100 if n > 0 else 0.0,
        "domain_coverage": len(covered_domains) / total_domains * 100 if total_domains > 0 else 0.0,
        "structural_spread": _structural_spread(selected, ca_coords=ca_coords),
        "hits": hits,
        "threshold": hit_threshold,
    }


def run_benchmark(
    fitness_landscape: list[tuple[str, float]],
    ground_truth: dict[str, float],
    n_select: int = 95,
    n_random_trials: int = 100,
    top_percentile: float = 10.0,
    strategies: list[str] | None = None,
    *,
    domains: list[dict] | None = None,
    domain_strategy: str = "proportional",
    max_per_position: int = 1,
    entropy_weight: float = 0.3,
    pool_multiplier: float = 2.0,
    distance_mode: str = "auto",
    random_seed: int | None = None,
    ca_coords: list[tuple[float, float, float] | None] | None = None,
) -> dict[str, SelectionMetrics]:
    """Run full benchmark comparing KURO selection strategies."""
    rng = random.Random(random_seed) if random_seed is not None else None
    if strategies is None:
        strategies = [
            "topn",
            "random",
            "position_cap",
            "domain",
            "pareto_1d",
            "pareto_3d",
            "pareto_entropy",
        ]

    result_map: dict[str, SelectionMetrics] = {}

    for strategy in strategies:
        if strategy == "random":
            trial_data: list[SelectionMetrics] = []
            for _ in range(n_random_trials):
                sel = simulate_selection(fitness_landscape, n_select, "random", rng=rng)
                trial_data.append(
                    evaluate_selection(
                        sel,
                        ground_truth,
                        top_percentile=top_percentile,
                        domains=domains,
                        ca_coords=ca_coords,
                    )
                )
            avg_metrics: SelectionMetrics = {
                key: sum(t[key] for t in trial_data) / len(trial_data)  # type: ignore[misc]
                for key in trial_data[0]
            }
            avg_metrics["n_trials"] = n_random_trials  # type: ignore[typeddict-unknown-key]
            result_map[strategy] = avg_metrics
            continue

        sel = simulate_selection(
            fitness_landscape,
            n_select,
            strategy,
            domains=domains,
            domain_strategy=domain_strategy,
            max_per_position=max_per_position,
            entropy_weight=entropy_weight,
            pool_multiplier=pool_multiplier,
            distance_mode=distance_mode,
            ca_coords=ca_coords,
        )
        result_map[strategy] = evaluate_selection(
            sel,
            ground_truth,
            top_percentile=top_percentile,
            domains=domains,
            ca_coords=ca_coords if strategy != "pareto_1d" else None,
        )

    return result_map
