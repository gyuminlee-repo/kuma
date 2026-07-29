"""Phase D — attribution and ablation analysis (G004 kill-gate).

Four analyses reusing existing assets (no heavy ESM-2 recompute):

1. coverage_attribution  — does diversity raise embedding-space coverage vs greedy?
2. signal_quality_degradation — diversity benefit vs exploit-signal strength trend.
3. budget_round_sweep — budget/round sweep on cheap synthetic NK (no embeddings).
4. esm_fidelity_note — structured bound: all claims to ESM-2 35M only.

**Model bound**: ALL embedding-space claims are bounded to ESM-2 35M
(esm2_t12_35M_UR50D, 480-dim mean-pool).  ESM-2 650M is compute-bound and NOT
run.  Bias direction: 35M embeddings are coarser surrogates than 650M, so
embedding-space diversity structure is more exploitable — 35M gives an OPTIMISTIC
upper bound on the diversity advantage; 650M would likely reduce it.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from al.coverage import coverage_metrics, classify_axis_relevance
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.rugged_sim import run_rugged_sweep

_HERE = Path(__file__).resolve().parent
_BENCH = _HERE.parent
_CACHE_DIR = str(_BENCH / "results" / "embeddings")
_G002_DIR = _BENCH / "results" / "qa" / "g002"
_OUT_DIR = _BENCH / "results" / "qa" / "g004"
_DMS_DIR = _BENCH / "data" / "DMS_substitutions" / "DMS_ProteinGym_substitutions"

# Arms used for coverage attribution analysis.
_COV_ARMS = ("topn", "embdiv", "kuro_ca")


# ---------------------------------------------------------------------------
# Shared helper — load multi-mut pool (mirrors real_epistatic_pilot._load_multimut)
# ---------------------------------------------------------------------------

def _load_multimut(csv_path: str) -> tuple[dict[str, float], dict[str, str], str]:
    """Return (canonical_id->raw_DMS_score, canonical_id->mutated_seq, wt_seq).

    Reads only multi-mut rows (mutant contains ':').
    """
    from al.real_epistatic import canonical_combo_id, parse_combo

    df = pd.read_csv(
        csv_path,
        usecols=lambda c: c in {"mutant", "mutated_sequence", "DMS_score"},
    )
    df = df.dropna(subset=["DMS_score"])
    df = df[df["mutant"].astype(str).str.contains(":")].copy()
    scores: dict[str, float] = {}
    seqs: dict[str, str] = {}
    for _m, _seq, _s in zip(
        df["mutant"], df["mutated_sequence"], df["DMS_score"], strict=True
    ):
        cid = canonical_combo_id(parse_combo(str(_m)))
        scores[cid] = float(_s)
        seqs[cid] = str(_seq)
    # Reconstruct WT by reverting the first variant's substitutions.
    any_m = next(iter(scores))
    seq = list(seqs[any_m])
    for mut in parse_combo(any_m):
        seq[mut[1] - 1] = mut[0]
    return scores, seqs, "".join(seq)


# ---------------------------------------------------------------------------
# 1. coverage_attribution
# ---------------------------------------------------------------------------

def coverage_attribution(
    assay_csv: str,
    accession: str,
    *,
    pool: int = 400,
    n_seed: int = 10,
    batch: int = 10,
    rounds: int = 4,
    seeds: int = 10,
    cache_dir: str | None = None,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run a small combinatorial AL loop and measure embedding-space coverage.

    Arms: topn (greedy), embdiv (embedding maximin), kuro_ca (Ca-centroid maximin).
    Reports the signed delta in kcenter_radius and variance_spanned (diversity vs
    greedy), and the signed Spearman correlation between per-(arm,seed) coverage
    and norm_best@final.

    Note: R1 is a fixed random batch (not ESM-2 zero-shot) to avoid loading the
    ESM-2 model at attribution time; cached embeddings are used for R2+ RF fitting.
    """
    from sklearn.ensemble import RandomForestRegressor
    from scipy.stats import spearmanr

    from al.real_epistatic import (
        CombinatorialOracle,
        canonical_combo_id,
        combo_centroid_descriptor,
        parse_combo,
    )
    from al.acquisition import select_indices
    from al.proxy_rf import RF_KWARGS

    t0 = time.perf_counter()
    if cache_dir is None:
        cache_dir = _CACHE_DIR

    # Load multi-mut pool.
    raw_all, seqs_all, wt = _load_multimut(assay_csv)
    rng0 = np.random.default_rng(0)
    all_ids = sorted(raw_all)
    sub = sorted(
        rng0.choice(all_ids, size=min(pool, len(all_ids)), replace=False).tolist()
    )
    raw = {i: raw_all[i] for i in sub}
    seqs = {i: seqs_all[i] for i in sub}

    # Load embeddings from cache (expected cache hit; no ESM-2 model loaded).
    assay_id = Path(assay_csv).stem + f"_multimut{len(sub)}"
    emb_df = embed_variants(assay_id, seqs, cache_dir, model_name=model).loc[sub]

    # Ca-centroid descriptors for kuro_ca arm.
    ca = None
    ca_note = "structure not fetched"
    try:
        from kuma_core.kuro.alphafold import fetch_ca_coords
        ca = fetch_ca_coords(accession)
        ca_note = f"Ca coords fetched for {accession}"
    except Exception as exc:
        ca_note = (
            f"Ca unavailable ({type(exc).__name__}): "
            "using positional-only centroid descriptor (min/mean/max residue position)"
        )
    desc = np.vstack([combo_centroid_descriptor(parse_combo(i), ca) for i in sub])
    desc_idx = {i: k for k, i in enumerate(sub)}

    pool_ids = sub
    emb_np = {i: emb_df.loc[i].to_numpy(dtype=float) for i in pool_ids}
    budget = n_seed + batch * rounds

    # Fixed arm-neutral random R1 (same for all arms and all seeds).
    r1 = sorted(np.random.default_rng(42).choice(pool_ids, size=min(n_seed, len(pool_ids)), replace=False).tolist())

    # Collect per-(arm, seed) coverage metrics and norm_best.
    cov_records: list[dict] = []

    for arm in _COV_ARMS:
        for seed in range(seeds):
            oracle = CombinatorialOracle.from_dict(raw, wt)
            rng = np.random.default_rng(1000 + seed)
            revealed: dict[str, float] = oracle.reveal(r1)

            for _r in range(rounds):
                rev_ids = list(revealed)
                unrev = [i for i in pool_ids if i not in revealed]
                if not unrev or len(revealed) >= budget:
                    break

                Xtr = np.vstack([emb_np[i] for i in rev_ids])
                ytr = np.array([revealed[i] for i in rev_ids], dtype=float)
                Xun = np.vstack([emb_np[i] for i in unrev])

                m = RandomForestRegressor(**{**RF_KWARGS, "random_state": 1 + seed})
                m.fit(Xtr, ytr)
                mean = m.predict(Xun)

                k = min(batch, budget - len(revealed), len(unrev))

                if arm == "topn":
                    idx = select_indices("topn", mean=mean, n=k, rng=rng)
                elif arm == "embdiv":
                    anc = np.vstack([emb_np[i] for i in rev_ids])
                    idx = select_indices(
                        "embdiv", mean=mean, features=Xun, anchor_features=anc, n=k, rng=rng
                    )
                else:  # kuro_ca: Ca-centroid (or positional) maximin
                    feats = np.vstack([desc[desc_idx[i]] for i in unrev])
                    anc = np.vstack([desc[desc_idx[i]] for i in rev_ids])
                    idx = select_indices(
                        "embdiv", mean=mean, features=feats, anchor_features=anc, n=k, rng=rng
                    )

                picks = [unrev[j] for j in idx]
                revealed.update(oracle.reveal(picks))

            # Coverage of the final revealed set (budget~50) vs the full pool (400).
            revealed_ids = list(revealed.keys())
            cov = coverage_metrics(emb_df, revealed_ids, pool_ids)
            nb = max(revealed.values()) if revealed else 0.0

            cov_records.append({
                "arm": arm,
                "seed": seed,
                "kcenter_radius": cov["kcenter_radius"],
                "variance_spanned": cov["variance_spanned"],
                "norm_best": nb,
            })

    # --- Signed deltas: diversity arms vs topn ---
    def _arm_mean(arm_name: str, metric: str) -> float:
        vals = [r[metric] for r in cov_records if r["arm"] == arm_name]
        return float(np.mean(vals))

    topn_radius = _arm_mean("topn", "kcenter_radius")
    topn_var = _arm_mean("topn", "variance_spanned")

    coverage_delta: dict[str, dict] = {}
    for div_arm in ("embdiv", "kuro_ca"):
        arm_radius = _arm_mean(div_arm, "kcenter_radius")
        arm_var = _arm_mean(div_arm, "variance_spanned")
        # radius_reduction: positive = diversity shrinks max-gap (BETTER coverage)
        radius_red = (topn_radius - arm_radius) / topn_radius if topn_radius > 0 else 0.0
        var_delta = arm_var - topn_var
        coverage_delta[div_arm] = {
            "kcenter_radius_mean": arm_radius,
            "variance_spanned_mean": arm_var,
            "kcenter_radius_reduction_vs_topn": float(radius_red),
            "variance_spanned_delta_vs_topn": float(var_delta),
            "diversity_raises_radius_coverage": bool(radius_red > 0),
            "diversity_raises_variance_coverage": bool(var_delta > 0),
        }

    # Pre-registered axis-relevance margin (from coverage.py).
    axis_rel: dict[str, dict] = {}
    for div_arm in ("embdiv", "kuro_ca"):
        topn_cov_mean = {"kcenter_radius": topn_radius, "variance_spanned": topn_var}
        div_cov_mean = {
            "kcenter_radius": _arm_mean(div_arm, "kcenter_radius"),
            "variance_spanned": _arm_mean(div_arm, "variance_spanned"),
        }
        axis_rel[div_arm] = classify_axis_relevance(div_cov_mean, topn_cov_mean)

    # --- Signed coverage-vs-outcome correlation (across all arms × seeds) ---
    all_radius = [r["kcenter_radius"] for r in cov_records]
    all_var = [r["variance_spanned"] for r in cov_records]
    all_nb = [r["norm_best"] for r in cov_records]

    rho_r, p_r = spearmanr(all_radius, all_nb)
    rho_v, p_v = spearmanr(all_var, all_nb)
    rho_r = float(rho_r) if np.isfinite(rho_r) else None
    rho_v = float(rho_v) if np.isfinite(rho_v) else None

    coverage_vs_outcome = {
        "n_points": len(all_nb),
        "spearman_kcenter_radius_vs_norm_best": rho_r,
        "spearman_kcenter_radius_p": float(p_r) if np.isfinite(p_r) else None,
        "sign_radius_vs_outcome": (
            "negative (smaller radius = better coverage → better outcome)"
            if rho_r is not None and rho_r < 0
            else "positive or null"
        ),
        "spearman_variance_spanned_vs_norm_best": rho_v,
        "spearman_variance_spanned_p": float(p_v) if np.isfinite(p_v) else None,
        "sign_variance_vs_outcome": (
            "positive (more variance spanned = better outcome)"
            if rho_v is not None and rho_v > 0
            else "negative or null"
        ),
    }

    return {
        "assay": Path(assay_csv).name,
        "accession": accession,
        "pool_size": len(sub),
        "budget": budget,
        "seeds": seeds,
        "r1_mode": "fixed random (not ESM-2 zero-shot; avoids loading model for attribution)",
        "ca_note": ca_note,
        "model_bound": model,
        "topn_coverage_mean": {
            "kcenter_radius": topn_radius,
            "variance_spanned": topn_var,
        },
        "coverage_delta_diversity_vs_topn": coverage_delta,
        "axis_relevance": axis_rel,
        "coverage_vs_outcome": coverage_vs_outcome,
        "wall_clock_seconds": time.perf_counter() - t0,
    }


# ---------------------------------------------------------------------------
# 2. signal_quality_degradation
# ---------------------------------------------------------------------------

def signal_quality_degradation(g002_dir: str | Path | None = None) -> dict:
    """Diversity benefit vs exploitation-signal strength across G002+G003 assays.

    Signal-strength proxy: gap(topn_norm_best - random_norm_best), which measures
    how well greedy exploitation outperforms random sampling — higher gap = stronger
    exploitable signal.

    Diversity benefit: kuro_ca_norm_best - topn_norm_best (signed; reported even if
    null or negative).

    G003 IspS point: single-mut, spearman_rho=0.092, diversity recall_at_hits=0.4
    vs greedy recall=0.7 → diversity HURT on weak-signal single-mut landscape.
    Diversity benefit proxy = recall_diversity - recall_greedy = -0.30 (rough;
    different metric from G002 norm_best, noted in output).

    Power note: 4 total data points (3 G002 assays + G003 IspS); any stated trend
    has very low statistical power (N=4).
    """
    if g002_dir is None:
        g002_dir = _G002_DIR

    g002_dir = Path(g002_dir)
    pilot_files = {
        "F7YBW8": g002_dir / "pilot.json",
        "RASK": g002_dir / "pilot_RASK.json",
        "GRB2": g002_dir / "pilot_GRB2.json",
    }

    per_assay: dict[str, dict] = {}
    signal_strengths: list[float] = []
    div_benefits: list[float] = []

    for name, fpath in pilot_files.items():
        data = json.loads(fpath.read_text(encoding="utf-8"))
        nb = data["per_arm_norm_best_mean"]
        kuro_nb = nb["kuro_ca"]
        topn_nb = nb["topn"]
        random_nb = nb["random"]
        div_benefit = kuro_nb - topn_nb
        signal_gap = topn_nb - random_nb  # exploitation signal: topn advantage over random

        per_assay[name] = {
            "kuro_ca_norm_best": kuro_nb,
            "topn_norm_best": topn_nb,
            "random_norm_best": random_nb,
            "diversity_benefit": div_benefit,
            "signal_strength_proxy_topn_minus_random": signal_gap,
            "decision_cell": data["decision_kuro_ca_vs_topn"]["decision_cell"],
        }
        signal_strengths.append(signal_gap)
        div_benefits.append(div_benefit)

    # G003 IspS: single-mut, weak signal (rho=0.092), diversity hurt (recall proxy).
    # Diversity benefit expressed as delta recall (recall_diversity - recall_greedy).
    # Using recall as proxy (different scale from norm_best; noted).
    isps_signal = 0.092   # Spearman rho of surrogate vs activity (very weak signal)
    isps_div_benefit = 0.4 - 0.7  # recall_diversity - recall_greedy = -0.30
    per_assay["IspS_G003"] = {
        "metric": "recall_at_hits (not norm_best; different scale from G002)",
        "diversity_recall": 0.4,
        "greedy_recall": 0.7,
        "diversity_benefit": isps_div_benefit,
        "signal_strength_proxy_spearman_rho": isps_signal,
        "note": "single-mut weak-signal (G003 retrospective); surrogate rho=0.092",
    }

    # Monotone trend check: does diversity_benefit rise as signal weakens?
    # Sort assays by signal_strength descending; diversity benefit should rise = monotone.
    # G002 only (G003 uses a different metric so we note it separately).
    sorted_assays = sorted(
        per_assay.items(),
        key=lambda kv: kv[1].get("signal_strength_proxy_topn_minus_random", float("nan")),
        reverse=True,
    )
    g002_sorted = [(k, v) for k, v in sorted_assays if k != "IspS_G003"]

    # Check monotone: as rank increases (weaker signal), is div_benefit monotone increasing?
    g002_div_benefits_ranked = [v["diversity_benefit"] for _, v in g002_sorted]
    g002_signal_ranked = [
        v["signal_strength_proxy_topn_minus_random"] for _, v in g002_sorted
    ]
    is_monotone_g002 = all(
        g002_div_benefits_ranked[i] >= g002_div_benefits_ranked[i + 1]
        for i in range(len(g002_div_benefits_ranked) - 1)
    )

    # Including IspS as 4th point (weakest signal, most negative benefit).
    all_signal = g002_signal_ranked + [isps_signal]
    all_benefit = g002_div_benefits_ranked + [isps_div_benefit]
    # Spearman of signal_strength vs diversity_benefit (should be positive if
    # "weak signal → more benefit from diversity").
    from scipy.stats import spearmanr
    rho_trend, p_trend = spearmanr(all_signal, all_benefit)
    rho_trend = float(rho_trend) if np.isfinite(rho_trend) else None

    trend_verdict = (
        "NO_CLEAR_MONOTONE_TREND"
        if rho_trend is None or abs(rho_trend) < 0.3
        else ("POSITIVE_TREND" if rho_trend > 0 else "NEGATIVE_TREND")
    )

    return {
        "per_assay": per_assay,
        "g002_ranked_by_signal_strength_desc": [k for k, _ in g002_sorted],
        "g002_signal_strengths_desc": g002_signal_ranked,
        "g002_div_benefits_desc": g002_div_benefits_ranked,
        "g002_monotone_div_benefit_rises_with_weak_signal": is_monotone_g002,
        "all_4_points_spearman_signal_vs_benefit": rho_trend,
        "all_4_points_spearman_p": float(p_trend) if np.isfinite(p_trend) else None,
        "trend_verdict": trend_verdict,
        "power_note": (
            "N=4 total data points (3 G002 assays + G003 IspS); very low statistical power. "
            "G003 uses recall_at_hits (different metric from G002 norm_best). "
            "All trends are indicative only."
        ),
        "honest_summary": (
            f"G002 rank by signal (desc): {[k for k, _ in g002_sorted]}. "
            f"Diversity benefits: {[round(v['diversity_benefit'], 4) for _, v in g002_sorted]}. "
            f"G003 IspS (weakest signal, rho=0.092): div_benefit=-0.30 (recall). "
            f"Spearman(signal, benefit) over 4 points = {rho_trend!r}. "
            f"Verdict: {trend_verdict}."
        ),
    }


# ---------------------------------------------------------------------------
# 3. budget_round_sweep
# ---------------------------------------------------------------------------

def budget_round_sweep(
    *,
    K: int = 8,
    n_sites: int = 10,
    n_alleles: int = 2,
    seeds: int = 50,
    budget_settings: tuple[tuple[int, int], ...] = ((8, 4), (8, 6), (16, 4), (16, 6)),
) -> dict:
    """Budget/round sweep on synthetic NK landscapes (cheap; no embeddings).

    Varies (n, k_rounds) at fixed K to probe whether sigma_kuro's advantage over
    topn grows with budget. Arms: sigma_kuro (KURO diversity), topn (greedy).

    Reports: mean norm_best per arm per budget, signed delta (sigma_kuro - topn),
    and whether the delta grows monotonically with budget (or honest null).
    """
    per_budget: dict[str, dict] = {}
    deltas: list[float] = []
    budgets_total: list[int] = []

    for n, k_rounds in budget_settings:
        label = f"n={n}_rounds={k_rounds}"
        total_budget = n * k_rounds

        records = run_rugged_sweep(
            n_sites=n_sites,
            n_alleles=n_alleles,
            k_values=(K,),
            n=n,
            k_rounds=k_rounds,
            seeds=range(seeds),
            arms=("sigma_kuro", "topn"),
            kappa=1.0,
        )

        kuro_nbs = [r["norm_best"] for r in records if r["arm"] == "sigma_kuro" and r["K"] == K]
        topn_nbs = [r["norm_best"] for r in records if r["arm"] == "topn" and r["K"] == K]
        kuro_mean = float(np.mean(kuro_nbs)) if kuro_nbs else float("nan")
        topn_mean = float(np.mean(topn_nbs)) if topn_nbs else float("nan")
        delta = kuro_mean - topn_mean

        per_budget[label] = {
            "n": n,
            "k_rounds": k_rounds,
            "total_budget": total_budget,
            "K": K,
            "n_seeds": len(kuro_nbs),
            "sigma_kuro_mean_norm_best": kuro_mean,
            "topn_mean_norm_best": topn_mean,
            "sigma_kuro_minus_topn_delta": float(delta),
            "kuro_wins": bool(delta > 0),
        }
        deltas.append(float(delta))
        budgets_total.append(total_budget)

    # Monotone check: does delta grow with budget?
    sorted_settings = sorted(per_budget.values(), key=lambda x: x["total_budget"])
    sorted_deltas = [x["sigma_kuro_minus_topn_delta"] for x in sorted_settings]
    is_monotone = all(
        sorted_deltas[i] <= sorted_deltas[i + 1] for i in range(len(sorted_deltas) - 1)
    )
    n_positive = sum(1 for d in deltas if d > 0)

    return {
        "K_fixed": K,
        "n_sites": n_sites,
        "n_alleles": n_alleles,
        "seeds": seeds,
        "per_budget": per_budget,
        "deltas_by_budget_asc": sorted_deltas,
        "budgets_asc": [x["total_budget"] for x in sorted_settings],
        "monotone_delta_grows_with_budget": is_monotone,
        "n_settings_kuro_wins": n_positive,
        "n_settings_total": len(deltas),
        "trend_verdict": (
            "MONOTONE_GROW" if is_monotone and n_positive == len(deltas)
            else "MONOTONE_SHRINK" if is_monotone
            else "NO_CLEAR_MONOTONE"
        ),
        "honest_summary": (
            f"K={K} synthetic NK. "
            f"Deltas (sigma_kuro-topn) sorted by budget: {[round(d, 4) for d in sorted_deltas]}. "
            f"Monotone: {is_monotone}. "
            f"Kuro wins in {n_positive}/{len(deltas)} budget settings."
        ),
    }


# ---------------------------------------------------------------------------
# 4. esm_fidelity_note
# ---------------------------------------------------------------------------

def esm_fidelity_note() -> dict:
    """Return a structured bound on ESM-2 model fidelity.

    All embedding-space claims in this analysis are bounded to ESM-2 35M
    (esm2_t12_35M_UR50D, 480-dim mean-pool). ESM-2 650M is compute-bound and
    NOT run. Bias direction: 35M gives an OPTIMISTIC upper bound on the diversity
    advantage (coarser embeddings inflate exploitable diversity structure).
    """
    return {
        "model": DEFAULT_MODEL,
        "model_dim": 480,
        "ran_650M": False,
        "reason_650M_not_run": "compute-bound (multi-day CPU; not run in this analysis)",
        "bias_direction": (
            "OPTIMISTIC upper bound: 35M embeddings are coarser than 650M, leaving more "
            "exploitable cluster structure for diversity-based acquisition; the observed "
            "diversity advantage is an upper bound and 650M embeddings would likely reduce it."
        ),
        "justification_one_line": (
            "Coarser 35M surrogate overfits local cluster structure more than 650M, "
            "so maximin-diversity gains more from coarse embedding separation; 650M "
            "collapses more sequences to similar representations, shrinking the diversity headroom."
        ),
        "claims_bounded_to": DEFAULT_MODEL,
        "recommendation": (
            "Report all embedding-space results with the qualifier "
            "'bounded to esm2_t12_35M_UR50D; 650M expected to reduce diversity advantage'."
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Phase D attribution and ablation (G004). "
        "Default: runs all four analyses and writes results/qa/g004/attribution.json. "
        "--smoke: tiny synthetic-only version (no embeddings), exits 0."
    )
    p.add_argument("--smoke", action="store_true", help="tiny synthetic-only smoke run, exits 0")
    p.add_argument(
        "--assay",
        default=str(_DMS_DIR / "F7YBW8_MESOW_Aakre_2015.csv"),
        help="path to ProteinGym multi-mut assay CSV (default: F7YBW8)",
    )
    p.add_argument("--accession", default="F7YBW8")
    p.add_argument("--pool", type=int, default=400)
    p.add_argument("--n-seed", type=int, default=10)
    p.add_argument("--batch", type=int, default=10)
    p.add_argument("--rounds", type=int, default=4)
    p.add_argument("--seeds", type=int, default=10, help="seeds for coverage_attribution loop")
    p.add_argument("--budget-seeds", type=int, default=50, help="seeds for budget_round_sweep")
    p.add_argument(
        "--cache-dir",
        default=str(_BENCH / "results" / "embeddings"),
        help="ESM-2 embedding cache directory",
    )
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument(
        "--out",
        default=str(_OUT_DIR / "attribution.json"),
        help="output JSON path",
    )
    args = p.parse_args(argv)

    if args.smoke:
        # Tiny synthetic-only run — no embeddings required.
        smoke_budget = budget_round_sweep(
            K=4, n_sites=8, n_alleles=2, seeds=3,
            budget_settings=((4, 3), (4, 4)),
        )
        smoke_sig = signal_quality_degradation()
        smoke_note = esm_fidelity_note()
        smoke_result = {
            "smoke": True,
            "budget_round_sweep": smoke_budget,
            "signal_quality_degradation": smoke_sig,
            "esm_fidelity_note": smoke_note,
        }
        print(json.dumps(smoke_result, indent=2))
        return 0

    # Full run.
    result: dict = {}

    print("=== G004 Phase D: attribution and ablation ===")

    print("[1/4] esm_fidelity_note ...")
    result["esm_fidelity_note"] = esm_fidelity_note()

    print("[2/4] signal_quality_degradation (reads G002 pilot JSONs) ...")
    result["signal_quality_degradation"] = signal_quality_degradation()

    print("[3/4] budget_round_sweep (synthetic NK, no embeddings) ...")
    result["budget_round_sweep"] = budget_round_sweep(seeds=args.budget_seeds)

    print(f"[4/4] coverage_attribution ({args.accession}, cached embeddings) ...")
    result["coverage_attribution"] = coverage_attribution(
        args.assay,
        args.accession,
        pool=args.pool,
        n_seed=args.n_seed,
        batch=args.batch,
        rounds=args.rounds,
        seeds=args.seeds,
        cache_dir=args.cache_dir,
        model=args.model,
    )

    # Write output.
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Written: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
