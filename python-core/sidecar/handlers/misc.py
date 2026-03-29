"""Handlers: polymerase list, organism list, EVOLVEpro CSV, benchmark."""

from kuro.evolvepro import load_evolvepro_csv

from sidecar.core import (
    _state,
    _validate_filepath,
    _poly_registry,
    _codon_registry,
    _ALLOWED_CSV_EXTENSIONS,
)

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
    filepath = params.get("filepath", "")
    if not filepath:
        raise ValueError("filepath is required")
    resolved = _validate_filepath(filepath, allowed_extensions=_ALLOWED_CSV_EXTENSIONS)

    return load_evolvepro_csv(
        filepath=str(resolved),
        top_n=int(params.get("top_n", 96)),
        max_per_position=int(params.get("max_per_position", 0)),
        domains=params.get("domains", []),
        domain_diversity=params.get("domain_diversity", False),
        domain_strategy=params.get("domain_strategy", "proportional"),
        pareto_diversity=params.get("pareto_diversity", False),
        entropy_weight=float(params.get("entropy_weight", 0.0)),
        esm_embedding=_state.esm_embedding,
    )


def handle_run_benchmark(params: dict) -> dict:
    """Run benchmark simulation on provided fitness landscape."""
    from kuro.benchmark import run_benchmark

    landscape_data = params.get("landscape", [])
    ground_truth = params.get("ground_truth", {})
    n_select = int(params.get("n_select", 95))
    strategies = params.get("strategies", ["topn", "random", "pareto"])

    if not landscape_data:
        raise ValueError("landscape data is required")

    landscape = [(v["variant"], v["fitness"]) for v in landscape_data]

    bench_results = run_benchmark(
        landscape, ground_truth, n_select, strategies=strategies
    )
    return {"results": bench_results}
