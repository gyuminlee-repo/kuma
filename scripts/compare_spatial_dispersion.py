#!/usr/bin/env python3
"""Offline, deterministic synthetic comparison; no biological inputs or models.

Run from a repository checkout. Prints JSON; redirects are explicitly caller-owned.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import math
import platform
from pathlib import Path
import statistics
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kuma_core.kuro.evolvepro import pareto_diversity_select, structural_diversity_select
from kuma_core.kuro.spatial_dispersion import (
    ResidueIdentity, ResiduePoint, SpatialInput, prepare_trusted_residues,
    select_farthest_first, select_random, select_top_score, measure_dispersion,
)


def _points(xs: list[tuple[float, float, float]]) -> list[ResiduePoint]:
    return [ResiduePoint(i+1, ResidueIdentity("1", "A", i+1), xyz, float(len(xs)-i)) for i, xyz in enumerate(xs)]


def fixtures() -> dict[str, tuple[list[ResiduePoint], int, int | None]]:
    core = _points([(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(2.,1.,0.),(1.,2.,0.),(2.,2.,0.)])
    return {
        "line_score_cluster": (_points([(x,0.,0.) for x in (0.,1.,2.,3.,10.,11.,20.,21.)]), 3, None),
        "two_lobes": (_points([(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(10.,0.,0.),(11.,0.,0.),(10.,1.,0.),(5.,2.,0.)]), 3, None),
        "core_without_outlier": (core, 3, None),
        "core_with_outlier": (core+[ResiduePoint(7,ResidueIdentity("1","A",7),(100.,0.,0.),-5.)], 3, 7),
        "core_with_moved_outlier": (core+[ResiduePoint(7,ResidueIdentity("1","A",7),(1000.,0.,0.),-5.)], 3, 7),
        "folded_hairpin": ([ResiduePoint(p,ResidueIdentity("1","A",p),xyz,s) for p,xyz,s in [(1,(0.,0.,0.),3.),(100,(.1,0.,0.),2.),(2,(8.,0.,0.),1.)]],2,None),
        "duplicate_and_missing": (core+[core[0],ResiduePoint(9,ResidueIdentity("1","A",9),None,8.)],3,None),
    }


def _reference_fps(data: SpatialInput, k: int) -> tuple[int, ...]:
    """Isolated standard FPS oracle for synthetic comparison, not production."""
    by_pos={p.position:p for p in data.eligible}
    chosen=list(select_top_score(data,1)) if k else []
    while len(chosen)<k:
        remaining=[p for p in data.eligible if p.position not in chosen]
        def key(p: ResiduePoint) -> tuple[float, float, int]:
            if p.coordinate is None:
                raise ValueError("reference FPS requires eligible coordinates")
            distances=[]
            for pos in chosen:
                coordinate=by_pos[pos].coordinate
                if coordinate is None:
                    raise ValueError("reference FPS requires eligible coordinates")
                distances.append(math.dist(p.coordinate,coordinate))
            return (min(distances),p.score,-p.position)
        chosen.append(max(remaining,key=key).position)
    return tuple(chosen)


def _legacy(data: SpatialInput, k: int, structural: bool) -> tuple[int, ...]:
    # This adapter is only for bounded synthetic fixtures, not a production map.
    ordered = sorted(data.eligible, key=lambda p: (-p.score, p.position))
    rows = [(f"A{p.position}G",p.score) for p in ordered]
    ids = {f"A{p.position}G":p.position for p in ordered}
    coords: list[tuple[float, float, float] | None] = [None] * (max((p.position for p in ordered), default=0)+1)
    for p in ordered:
        coords[p.position] = p.coordinate
    if structural:
        picked, _ = structural_diversity_select(rows,k,ca_coords=coords,kappa=0.,anchor_variants=())
    else:
        picked, _ = pareto_diversity_select(rows,k,ca_coords=coords,pool_multiplier=2.,entropy_weight=0.,distance_mode="3d",position_mode="first")
    positions = tuple(ids[row[0]] for row in picked)
    if len(positions) != k or len(set(positions)) != k:
        raise ValueError("legacy baseline returned incomparable cardinality; no top-up applied")
    return positions


def _result(data: SpatialInput, selected: tuple[int, ...], outlier: int | None) -> dict[str, Any]:
    return {
        "selected_positions": list(selected),
        "contains_labelled_synthetic_outlier": outlier in selected if outlier is not None else None,
        "metrics": asdict(measure_dispersion(data,selected)),
    }


def run_comparison() -> dict[str, Any]:
    output: dict[str, Any] = {"contract": {
        "version": 1, "python_version": platform.python_version(), "unit": "angstrom", "universe": "same finite-coordinate unique reference positions per fixture",
        "score_direction": "larger is higher; synthetic only", "k_policy": "same exact k; fail rather than top-up",
        "fps_implementation": "existing structural_diversity_select via trusted single-point dense-index adapter",
        "reference_fps": "independent standard traversal in synthetic comparison only",
        "fps_seed": "highest score then smallest position", "fps_ties": "exact computed distance then score then smallest position",
        "random_seeds": list(range(32)), "random_order": "canonical reference position before sampling",
        "legacy_pareto": "first mode; pool_multiplier=2; entropy_weight=0; distance_mode=3d",
        "legacy_structural": "full eligible pool; kappa=0; no anchors; single positions only",
        "coverage": "all eligible points including selected self-distance zero",
        "limits": "no mapping inference, centroid, imputed coordinates, biological outcome or approximation guarantee",
    }, "fixtures": {}}
    for name,(points,k,outlier) in fixtures().items():
        data=prepare_trusted_residues(points,frame_id="synthetic:"+name)
        methods={
            "fps":select_farthest_first(data,k), "reference_fps":_reference_fps(data,k), "top_score":select_top_score(data,k),
            "legacy_pareto_pool2":_legacy(data,k,False), "legacy_structural_fullpool":_legacy(data,k,True),
        }
        trials=[_result(data,select_random(data,k,seed=seed),outlier) for seed in range(32)]
        summary={}
        for metric in ("min_pair_distance","coverage_mean","coverage_max","total_score_loss"):
            values=[float(t["metrics"][metric]) for t in trials]
            summary[metric]={"min":min(values),"mean":statistics.fmean(values),"max":max(values)}
        output["fixtures"][name]={
            "k":k,"n_eligible":len(data.eligible),"excluded":data.excluded,"duplicate_rows":data.duplicate_rows,
            "inputs":[asdict(p) for p in data.points],
            "methods":{method:_result(data,selected,outlier) for method,selected in methods.items()},
            "random_32":{
                "summary":summary,
                "pooled_selected_nearest_neighbor_distances":[d for t in trials for _,d in t["metrics"]["selected_nearest_neighbor"]],
                "selected_positions_by_seed":[t["selected_positions"] for t in trials],
                "labelled_outlier_fraction":statistics.fmean(float(t["contains_labelled_synthetic_outlier"]) for t in trials) if outlier is not None else None,
            },
        }
    return output


if __name__ == "__main__":
    print(json.dumps(run_comparison(),indent=2,allow_nan=False))
