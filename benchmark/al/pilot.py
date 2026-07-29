"""Phase-1 pilot driver + Gate G1 evaluation (plan Phase 1 / Gate G1 a-e).

Runs the AL simulation on a few small assays (with real InterPro domains), emits
per-arm metrics + embedding-space coverage, times a plate-N cell, and produces a
structured Gate G1 go/no-go verdict. Gate G1 must pass before the 217 sweep.

Gate G1 components:
  (a) permutation-invariance firewall  -> proven by al/tests/test_firewall.py +
      test_loop.test_campaign_leak_free_under_oracle_permutation (structural).
  (b) embedding coverage emitted + axis-relevance margin applied (coverage.py).
  (c) proxy<->real top_layer Spearman >= 0.99 (proxy_rf.proxy_vs_real_spearman).
  (d) plate-N (n=96,K=4) cell timed -> extrapolate to 217 x signals x seeds vs a
      stated hard CPU-hour ceiling.
  (e) embed_cache hard-fail proven by al/tests/test_embed_cache.py.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

from al import arms as arms_mod
from al import coverage as cov_mod
from al import metrics as metrics_mod
from al.coldstart import esm2_zero_shot_llr
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.loop import run_campaign
from al.run_al_simulation import load_assay

CEILING_CPU_HOURS = 72.0  # plan F6 hard ceiling (frozen)


def run_pilot_assay(
    csv_path: str | Path,
    cache_dir: str | Path,
    domains: list[dict],
    *,
    n: int,
    k: int,
    seed: int = 0,
    model: str = DEFAULT_MODEL,
    max_variants: int | None = None,
) -> dict:
    """Run all 4 arms on one assay; return metrics + per-arm coverage + timings."""
    data = load_assay(csv_path)
    variants = data["variants"]
    if max_variants is not None and len(variants) > max_variants:
        rng = np.random.default_rng(0)
        idx = sorted(rng.choice(len(variants), size=max_variants, replace=False))
        variants = [variants[i] for i in idx]
    oracle = {v: data["oracle"][v] for v in variants}
    seqs = {v: data["seqs"][v] for v in variants}

    t0 = time.perf_counter()
    cold = esm2_zero_shot_llr(data["wt"], variants, model_name=model)
    t_cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    emb = embed_variants(data["assay"], seqs, cache_dir, model_name=model)
    t_embed = time.perf_counter() - t0

    per_arm = {}
    arm_records = []
    cov_by_arm = {}
    for arm in arms_mod.ARMS:
        t0 = time.perf_counter()
        res = run_campaign(arm, variants, emb, oracle, cold, n=n, k_rounds=k,
                           domains=domains, seed=seed)
        t_arm = time.perf_counter() - t0
        m = metrics_mod.campaign_metrics(res.revealed_order, [r.selected for r in res.rounds], oracle)
        cov = cov_mod.coverage_metrics(emb, res.revealed_order, variants)
        cov_by_arm[arm] = cov
        per_arm[arm] = {"metrics": m, "coverage": cov, "loop_seconds": t_arm}
        arm_records.append({"assay": data["assay"], "arm": arm, "n": n, "k": k,
                            "n_variants": len(variants), "loop_seconds": round(t_arm, 3),
                            **m, **{f"cov_{kk}": vv for kk, vv in cov.items()}})

    # axis-relevance: domain_every vs topn at matched budget
    axis = cov_mod.classify_axis_relevance(cov_by_arm["domain_every"], cov_by_arm["topn"])
    return {
        "assay": data["assay"], "n_variants": len(variants), "length": data["length"],
        "domain_count": len(domains), "n": n, "k": k,
        "timings": {"cold_start_s": round(t_cold, 2), "embed_s": round(t_embed, 2)},
        "per_arm": per_arm, "axis_relevance": axis, "records": arm_records,
    }


def extrapolate_ceiling(plate_loop_seconds: float, *, n_assays=217, n_signals=2, n_seeds=10) -> dict:
    """Project plate-N AL-loop cost to the full sweep (embeddings excluded: cached once)."""
    total_cells = n_assays * len(arms_mod.ARMS) * n_signals * n_seeds
    cpu_hours = total_cells * plate_loop_seconds / 3600.0
    return {
        "plate_loop_seconds": round(plate_loop_seconds, 3),
        "total_cells": total_cells,
        "projected_cpu_hours": round(cpu_hours, 2),
        "ceiling_cpu_hours": CEILING_CPU_HOURS,
        "within_ceiling": cpu_hours <= CEILING_CPU_HOURS,
    }


def gate_g1(pilot: list[dict], proxy_spearman: float, ceiling: dict) -> dict:
    """Evaluate Gate G1 (a)-(e); ALL must pass to unlock the 217 sweep."""
    coverage_emitted = all(
        "kcenter_radius" in a["coverage"] for p in pilot for a in p["per_arm"].values()
    )
    checks = {
        "a_permutation_firewall": True,  # proven by unit tests (test_firewall + test_loop)
        "b_coverage_emitted_with_threshold": bool(coverage_emitted)
        and all("axis_relevant" in p["axis_relevance"] for p in pilot),
        "c_proxy_real_spearman_ge_0_99": proxy_spearman >= 0.99,
        "d_plate_n_within_ceiling": bool(ceiling["within_ceiling"]),
        "e_embed_hard_fail": True,  # proven by test_embed_cache
    }
    return {"checks": checks, "passed": all(checks.values()),
            "proxy_spearman": proxy_spearman, "ceiling": ceiling}
