"""Every benchmarked strategy is scored on one spread metric.

``run_benchmark`` dropped the Cα coordinates for ``pareto_1d`` only at the
evaluation step, so its ``structural_spread`` was a normalized sequence
distance while every other strategy reported a normalized Cα distance. The
dialog puts those numbers in one column, so the same selection looked far more
spread out under that one strategy.
"""
from __future__ import annotations

from kuma_core.kuro.benchmark import run_benchmark

_STRATEGIES = ["topn", "pareto_1d", "pareto_3d"]
_LANDSCAPE = [("A2V", 0.9), ("A3V", 0.8)]
_TRUTH = {"A2V": 0.9, "A3V": 0.8}
# Two residues 100 units apart in space but adjacent in sequence: a sequence
# metric and a coordinate metric cannot agree by accident here.
_COORDS: list[tuple[float, float, float] | None] = [
    None,
    (0.0, 0.0, 0.0),
    (0.0, 0.0, 0.0),
    (100.0, 0.0, 0.0),
]


def test_spread_is_the_same_metric_for_every_strategy() -> None:
    bench = run_benchmark(
        _LANDSCAPE,
        _TRUTH,
        n_select=2,
        strategies=_STRATEGIES,
        ca_coords=_COORDS,
    )
    metrics = {s: dict(bench[s]) for s in _STRATEGIES}
    selections = {s: metrics[s]["n_selected"] for s in _STRATEGIES}
    assert set(selections.values()) == {2}, selections
    spreads = {s: metrics[s]["structural_spread"] for s in _STRATEGIES}
    assert len(set(spreads.values())) == 1, spreads


def test_spread_falls_back_to_sequence_distance_without_coordinates() -> None:
    """With no coordinates at all every strategy still shares one metric."""
    bench = run_benchmark(
        _LANDSCAPE, _TRUTH, n_select=2, strategies=_STRATEGIES, ca_coords=None,
    )
    spreads = {s: dict(bench[s])["structural_spread"] for s in _STRATEGIES}
    assert len(set(spreads.values())) == 1, spreads
