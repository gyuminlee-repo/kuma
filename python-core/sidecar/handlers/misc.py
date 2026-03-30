"""Handlers: polymerase list, organism list, EVOLVEpro CSV, benchmark."""

from kuro.evolvepro import load_evolvepro_csv

import sidecar.core as _core
from sidecar.core import (
    _validate_filepath,
    _poly_registry,
    _codon_registry,
    _ALLOWED_CSV_EXTENSIONS,
)
from sidecar.models import LoadEvolveproParams, RunBenchmarkParams

_POLYMERASE_META = {
    "Benchling": {"manufacturer": "SantaLucia 1998", "fidelity": "standard"},
    "Q5": {"manufacturer": "NEB", "fidelity": "high"},
    "Phusion": {"manufacturer": "Thermo", "fidelity": "high"},
    "Taq": {"manufacturer": "Various", "fidelity": "low"},
    "DreamTaq": {"manufacturer": "Thermo", "fidelity": "low"},
    "KOD": {"manufacturer": "Toyobo", "fidelity": "high"},
}


def handle_list_polymerases(_params: dict) -> list[dict]:
    """Return available polymerase profiles."""
    names = _poly_registry.list_names()
    result = []
    for name in names:
        meta = _POLYMERASE_META.get(name, {"manufacturer": "", "fidelity": ""})
        result.append(
            {
                "name": name,
                "manufacturer": meta["manufacturer"],
                "fidelity": meta["fidelity"],
            }
        )
    return result


def handle_list_organisms(_params: dict) -> list[dict]:
    """Return available organism codon tables for the UI dropdown."""
    return _codon_registry.list_organisms_detailed()


def handle_load_evolvepro_csv(params: dict) -> dict:
    """Load EVOLVEpro df_test.csv, sort by y_pred descending, return top-N variants."""
    p = LoadEvolveproParams(**params)
    if not p.filepath:
        raise ValueError("filepath is required")
    resolved = _validate_filepath(p.filepath, allowed_extensions=_ALLOWED_CSV_EXTENSIONS)

    with _core._state_lock:
        ca_coords = _core._state.ca_coords

    return load_evolvepro_csv(
        filepath=str(resolved),
        top_n=p.top_n,
        max_per_position=p.max_per_position,
        domains=p.domains,
        domain_diversity=p.domain_diversity,
        domain_strategy=p.domain_strategy,
        pareto_diversity=p.pareto_diversity,
        entropy_weight=p.entropy_weight,
        ca_coords=ca_coords,
    )


def handle_run_benchmark(params: dict) -> dict:
    """Run benchmark simulation on provided fitness landscape."""
    from kuro.benchmark import run_benchmark

    p = RunBenchmarkParams(**params)

    if not p.landscape:
        raise ValueError("landscape data is required")

    landscape = [(v.variant, v.fitness) for v in p.landscape]

    bench_results = run_benchmark(
        landscape, p.ground_truth, p.n_select, strategies=p.strategies
    )
    return {"results": bench_results}
