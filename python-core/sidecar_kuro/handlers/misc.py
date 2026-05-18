"""Handlers: polymerase list, organism list, EVOLVEpro CSV, benchmark."""

from dataclasses import asdict

from kuma_core.kuro.evolvepro import load_evolvepro_csv
from kuma_core.kuro.polymerase import _dict_to_profile

import sidecar_kuro.core as _core
from sidecar_kuro.core import (
    _validate_filepath,
    _poly_registry,
    _codon_registry,
    _CUSTOM_POLYMERASE_PATH,
    _ALLOWED_CSV_EXTENSIONS,
    _get_cached_ca_coords,
)
from sidecar_kuro.models import (
    LoadEvolveproParams,
    PolymeraseProfileModel,
    RunBenchmarkParams,
    SaveCustomPolymeraseResultModel,
)

_POLYMERASE_META = {
    "Benchling": {"manufacturer": "SantaLucia 1998", "fidelity": "standard"},
    "Q5": {"manufacturer": "NEB", "fidelity": "high"},
    "Phusion": {"manufacturer": "Thermo", "fidelity": "high"},
    "Taq": {"manufacturer": "Various", "fidelity": "low"},
    "DreamTaq": {"manufacturer": "Thermo", "fidelity": "low"},
    "KOD": {"manufacturer": "Toyobo", "fidelity": "high"},
    "TAKARA_GXL": {"manufacturer": "Takara", "fidelity": "high"},
    "Q5 SDM": {"manufacturer": "NEB", "fidelity": "high"},
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


def handle_get_polymerase_details(params: dict) -> dict:
    """Return full polymerase profile for the selected name."""
    name = params.get("name", "")
    profile = PolymeraseProfileModel.model_validate(asdict(_poly_registry.get(name)))
    return profile.to_rpc_dict()


def handle_save_custom_polymerase(params: dict) -> dict:
    """Persist a custom polymerase profile and keep it available after restart."""
    profile = _dict_to_profile(params)
    _CUSTOM_POLYMERASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _poly_registry.save_custom(profile, _CUSTOM_POLYMERASE_PATH)
    return SaveCustomPolymeraseResultModel(name=profile.name).to_rpc_dict()


def handle_list_organisms(_params: dict) -> list[dict]:
    """Return available organism codon tables for the UI dropdown."""
    return _codon_registry.list_organisms_detailed()


def handle_load_evolvepro_csv(params: dict) -> dict:
    """Load EVOLVEpro df_test.csv, sort by y_pred descending, return top-N variants."""
    p = LoadEvolveproParams(**params)
    if not p.filepath:
        raise ValueError("filepath is required")
    resolved = _validate_filepath(p.filepath, allowed_extensions=_ALLOWED_CSV_EXTENSIONS)

    ca_coords = _get_cached_ca_coords(p.structure_accession)

    return load_evolvepro_csv(
        filepath=str(resolved),
        top_n=p.top_n,
        max_per_position=p.max_per_position,
        domains=p.domains,
        excluded_ranges=[{"start": r.start, "end": r.end} for r in p.excluded_ranges],
        domain_diversity=p.domain_diversity,
        domain_strategy=p.domain_strategy,
        domain_overlap_policy=p.domain_overlap_policy,
        linker_handling=p.linker_handling,
        domain_quota_min=p.domain_quota_min,
        pareto_diversity=p.pareto_diversity,
        entropy_weight=p.entropy_weight,
        pool_multiplier=p.pool_multiplier,
        distance_mode=p.distance_mode,
        ca_coords=ca_coords,
        evolvepro_round=p.evolvepro_round,
        round_size=p.round_size,
        ref_seq=p.ref_seq,
    )


def handle_run_benchmark(params: dict) -> dict:
    """Run benchmark simulation on provided fitness landscape."""
    from kuma_core.kuro.benchmark import run_benchmark

    p = RunBenchmarkParams(**params)

    if not p.landscape:
        raise ValueError("landscape data is required")

    landscape = [(v.variant, v.fitness) for v in p.landscape]

    ca_coords = _get_cached_ca_coords(p.structure_accession)

    bench_results = run_benchmark(
        landscape,
        p.ground_truth,
        p.n_select,
        n_random_trials=p.n_random_trials,
        top_percentile=p.top_percentile,
        strategies=p.strategies,
        domains=p.domains,
        domain_strategy=p.domain_strategy,
        max_per_position=p.max_per_position,
        entropy_weight=p.entropy_weight,
        pool_multiplier=p.pool_multiplier,
        distance_mode=p.distance_mode,
        random_seed=p.random_seed,
        ca_coords=ca_coords,
    )
    return {"results": bench_results}
