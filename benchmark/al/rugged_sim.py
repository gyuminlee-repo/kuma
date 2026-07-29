"""Exploration-vs-exploitation AL benchmark on rugged NK landscapes.

This is the test the PI's local-minima rationale actually targets (REPORT.md §3.1):
on landscapes with real local optima, does diversity-aware acquisition reach the
global optimum more reliably than greedy Top-N — and does the gap grow with
ruggedness K? Surrogate = sklearn RandomForest on one-hot genotype features
(faithful to EVOLVEpro's RF; ESM-2 is irrelevant for a synthetic genotype space).
Round-0 is a random seed batch (honest cold start). Exploration metrics, with
random as the primary baseline.
"""

from __future__ import annotations

import numpy as np

from al.landscape import NKLandscape, hamming, onehot
from al.acquisition import ACQUISITION_ARMS, UCB_KAPPA_GRID

ARMS = ("greedy", "diverse", "random")  # LEGACY compat shim (older tests only)
# Plan Phase A round-2+ acquisition factor (the decisive arm set):
ACQ_ARMS = ACQUISITION_ARMS  # single source of truth: acquisition.ACQUISITION_ARMS
_LEGACY_ARMS = frozenset(ARMS)
N_BOOT = 10_000  # bootstrap iterations for the CVaR-difference CI (plan pre-reg)
# Baseline arms KURO is benchmarked against (random is the null control, excluded).
_BASELINE_ARMS = ("topn", "ucb", "thompson", "embdiv")


def _rf():
    from sklearn.ensemble import RandomForestRegressor
    # EVOLVEpro-faithful hyperparameters. Serial trees: n_jobs>1 only adds joblib
    # overhead on the small per-round training sets and is slower here.
    return RandomForestRegressor(
        n_estimators=100, criterion="friedman_mse", max_features=1.0, random_state=1
    )


def _select(arm, pool, revealed, surrogate_pred, n_alleles, n, seed):
    """LEGACY compatibility shim for ARMS (greedy/diverse/random); older tests only.

    The Phase A deliverable selects via acquisition.select_indices (ACQ_ARMS); this
    path is retained so test_landscape/test_loop keep passing. Do not extend it.
    """
    rng = np.random.default_rng(seed)
    if arm == "random":
        idx = rng.permutation(len(pool))[:n]
        return [pool[i] for i in idx]
    if arm == "greedy":
        return [g for g, _ in sorted(zip(pool, surrogate_pred), key=lambda t: -t[1])][:n]
    if arm == "diverse":
        # greedy maximin Hamming distance to the already-revealed+selected set,
        # tie-broken by surrogate prediction (exploration with a fitness prior).
        pred = dict(zip(pool, surrogate_pred))
        chosen: list = []
        anchor = list(revealed)
        remaining = list(pool)
        while remaining and len(chosen) < n:
            ref = anchor + chosen
            def score(g):
                d = min((hamming(g, r) for r in ref), default=len(g))
                return (d, pred[g])
            best = max(remaining, key=score)
            chosen.append(best)
            remaining.remove(best)
        return chosen
    raise ValueError(arm)


def _select_acq(arm, model, pool, revealed_genos, land, n, evolvepro_round, seed, kappa):
    """Select via the plan acquisition arms (acquisition.select_indices).

    New arms need the surrogate MODEL (per-tree variance for UCB/Thompson) and the
    one-hot features (embdiv maximin / sigma_kuro positions), not just point preds.
    """
    from al import acquisition

    rng = np.random.default_rng(seed)
    x_pool = np.vstack([onehot(g, land.n_alleles) for g in pool])
    # Only the variance arms pay the per-tree cost; the rest use the forest mean.
    std = None
    sample = None
    if arm == "ucb":
        mean, std = acquisition.rf_mean_std(model, x_pool)
    elif arm == "thompson":
        mean = model.predict(x_pool)
        sample = acquisition.rf_thompson_sample(model, x_pool, rng)
    else:
        mean = model.predict(x_pool)
    needs_features = arm in ("embdiv",)
    anchor_features = (
        np.vstack([onehot(g, land.n_alleles) for g in revealed_genos])
        if needs_features and revealed_genos
        else None
    )
    features = x_pool if needs_features else None
    idx = acquisition.select_indices(
        arm,
        mean=mean,
        std=std,
        sample=sample,
        features=features,
        anchor_features=anchor_features,
        positions=pool,
        anchor_positions=revealed_genos,
        n=n,
        n_alleles=land.n_alleles,
        evolvepro_round=evolvepro_round,
        round_size=n,
        rng=rng,
        kappa=kappa,
    )
    return [pool[i] for i in idx]


def run_campaign_nk(
    land: NKLandscape, arm: str, *, n: int, k_rounds: int, seed: int, kappa: float = 1.0
) -> dict:
    """One AL campaign on an NK landscape; returns best-found trajectory + outcome."""
    genos = land.all_genotypes()
    oracle = land.fitness_map()  # cached on the landscape; reused across arms
    gopt, gmax = land.global_optimum()
    rng = np.random.default_rng(1000 + seed)

    revealed: dict[tuple, float] = {}
    best_traj: list[float] = []
    # round 0: random seed batch (honest cold start; no surrogate yet)
    seed_batch = [genos[i] for i in rng.permutation(len(genos))[:n]]
    for g in seed_batch:
        revealed[g] = oracle[g]
    best_traj.append(max(revealed.values()))

    for r in range(1, k_rounds):
        pool = [g for g in genos if g not in revealed]
        if not pool:
            break
        # fit surrogate on revealed (one-hot -> fitness)
        Xtr = np.vstack([onehot(g, land.n_alleles) for g in revealed])
        ytr = np.array([revealed[g] for g in revealed])
        model = _rf()
        model.fit(Xtr, ytr)
        pred = model.predict(np.vstack([onehot(g, land.n_alleles) for g in pool]))
        if arm in _LEGACY_ARMS:
            picks = _select(
                arm, pool, list(revealed.keys()), pred, land.n_alleles, n, seed=seed * 100 + r
            )
        else:
            picks = _select_acq(
                arm, model, pool, list(revealed.keys()), land, n, r, seed * 100 + r, kappa
            )
        for g in picks:
            revealed[g] = oracle[g]
        best_traj.append(max(revealed.values()))

    best = max(revealed.values())
    return {
        "arm": arm, "seed": seed, "K": land.K, "n_sites": land.n_sites,
        "best_found": best, "global_max": gmax,
        "norm_best": best / gmax if gmax > 0 else 0.0,
        "found_global": bool(gopt in revealed),
        "regret": gmax - best, "n_revealed": len(revealed),
        "best_traj": best_traj,
    }


def run_rugged_sweep(
    *, n_sites: int = 6, n_alleles: int = 4, k_values=(0, 2, 4),
    n: int = 8, k_rounds: int = 6, seeds=range(20), landscape_seed_base: int = 0,
    arms=ARMS, kappa: float = 1.0,
) -> list[dict]:
    """Sweep arms x ruggedness K x seeds. Each (K, seed) gets its own landscape.

    ``arms`` defaults to the legacy ARMS for backward compatibility; pass
    ``ACQ_ARMS`` for the plan's round-2+ acquisition factor.
    """
    records: list[dict] = []
    for K in k_values:
        for seed in seeds:
            land = NKLandscape(n_sites, n_alleles, K=K, seed=landscape_seed_base + seed)
            for arm in arms:
                rec = run_campaign_nk(land, arm, n=n, k_rounds=k_rounds, seed=seed, kappa=kappa)
                rec.pop("best_traj")  # keep records compact
                records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Regime-map analysis + CLI (plan Phase A: scaffold + hypothesis generator)
# ---------------------------------------------------------------------------
def regime_decision_table(
    records, *, arm_a: str = "sigma_kuro", arm_b: str = "topn", q: float = 0.20, seed: int = 0
) -> list[dict]:
    """Per-K decision cell of arm_a (KURO) vs arm_b on norm_best.

    The per-K Wilcoxon p-values are ONE multiple-comparison family across the K
    strata and are Holm-adjusted (plan pre-registration: "Holm-adjusted p<=0.05")
    BEFORE driving mean_verdict. Phase A is a HYPOTHESIS GENERATOR only
    (A-retract-not-average gate): these cells must NOT be reported as headline;
    Phase B real-epistatic must reproduce them.
    """
    from al import metrics, stats

    by_k: dict[int, dict[str, list[dict]]] = {}
    for r in records:
        by_k.setdefault(r["K"], {}).setdefault(r["arm"], []).append(r)

    # Pass 1: per-K paired comparison + paired CVaR-difference bootstrap CI.
    cells: dict[int, dict] = {}
    for K in sorted(by_k):
        arms_here = by_k[K]
        if arm_a not in arms_here or arm_b not in arms_here:
            continue
        a = sorted(arms_here[arm_a], key=lambda x: x["seed"])
        b = sorted(arms_here[arm_b], key=lambda x: x["seed"])
        a_nb = [x["norm_best"] for x in a]
        b_nb = [x["norm_best"] for x in b]
        cmp = stats.paired_comparison(a_nb, b_nb, seed=seed)
        cvar_a = metrics.cvar(a_nb, q=q)
        cvar_b = metrics.cvar(b_nb, q=q)
        # bootstrap CI of the difference of CVaRs (resample seeds paired)
        rng = np.random.default_rng(seed)
        a_arr, b_arr = np.asarray(a_nb), np.asarray(b_nb)
        idxs = np.arange(a_arr.size)
        diffs = np.empty(N_BOOT)
        for i in range(N_BOOT):
            samp = rng.choice(idxs, size=idxs.size, replace=True)
            diffs[i] = metrics.cvar(b_arr[samp], q=q) - metrics.cvar(a_arr[samp], q=q)
        ci_lo = float(np.percentile(diffs, 2.5))
        ci_hi = float(np.percentile(diffs, 97.5))
        cells[K] = {
            "cmp": cmp,
            "n_seeds": len(a_nb),
            "cvar_a": cvar_a,
            "cvar_b": cvar_b,
            "tail_ci": (ci_lo, ci_hi),
        }

    # Pass 2: Holm-adjust the per-K raw Wilcoxon p across the K family, THEN verdict.
    raw_p = {str(K): cells[K]["cmp"]["wilcoxon_p"] for K in cells}
    holm_p = stats.holm_correction(raw_p) if raw_p else {}

    out: list[dict] = []
    for K in sorted(cells):
        c = cells[K]
        cmp = dict(c["cmp"])
        p_raw = float(cmp["wilcoxon_p"])
        p_adj = float(holm_p[str(K)])
        cmp["wilcoxon_p"] = p_adj  # mean_verdict consumes the Holm-adjusted p
        mean_v = stats.mean_verdict(cmp)
        ci_lo, ci_hi = c["tail_ci"]
        tail_v = stats.tail_outcome(ci_lo, ci_hi)
        out.append({
            "K": K,
            "arm_a": arm_a,
            "arm_b": arm_b,
            "n_seeds": c["n_seeds"],
            "median_delta": cmp["median_delta"],
            "cliffs_delta": cmp["cliffs_delta"],
            "wilcoxon_p": p_adj,
            "wilcoxon_p_raw": p_raw,
            "wilcoxon_p_holm": p_adj,
            "bootstrap_ci_median": c["cmp"]["bootstrap_ci_median"],
            "mean_verdict": mean_v,
            "cvar_a": c["cvar_a"],
            "cvar_b": c["cvar_b"],
            "tail_ci": (ci_lo, ci_hi),
            "tail_outcome": tail_v,
            "decision_cell": stats.decision_cell(mean_v, tail_v),
        })
    return out


def _strongest_baseline(
    records, *, baselines: tuple[str, ...] = _BASELINE_ARMS
) -> str | None:
    """Baseline arm with the highest pooled mean norm_best (the real bar to beat).

    Lets the regime report also show KURO vs its STRONGEST competitor, not only vs
    greedy Top-N — a Top-N-only framing could understate the bar (architect P3).
    """
    means: dict[str, float] = {}
    for arm in baselines:
        vals = [r["norm_best"] for r in records if r["arm"] == arm]
        if vals:
            means[arm] = float(np.mean(vals))
    return max(means, key=means.get) if means else None


def run_ucb_kappa_grid(
    *, n_sites: int, n_alleles: int, k_values, n: int, k_rounds: int, seeds,
    kappas=UCB_KAPPA_GRID,
) -> list[dict]:
    """Exercise the pre-registered UCB kappa grid {0.5,1.0,2.0} (robustness arm).

    The regime headline uses kappa=1.0; this sweeps the full grid so the
    pre-registered constant is a live, tested arm rather than dead documentation.
    Returns mean norm_best per (kappa, K).
    """
    out: list[dict] = []
    for kappa in kappas:
        for K in k_values:
            nbs = []
            for seed in seeds:
                land = NKLandscape(n_sites, n_alleles, K=K, seed=seed)
                rec = run_campaign_nk(land, "ucb", n=n, k_rounds=k_rounds, seed=seed, kappa=kappa)
                nbs.append(rec["norm_best"])
            out.append({
                "kappa": float(kappa),
                "K": int(K),
                "n_seeds": len(nbs),
                "norm_best_mean": float(np.mean(nbs)) if nbs else float("nan"),
            })
    return out


def load_records_csv(path: str) -> list[dict]:
    """Load per-campaign records written by the CLI --out (for --from-csv regen)."""
    import csv

    out: list[dict] = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            out.append({
                "arm": row["arm"],
                "seed": int(row["seed"]),
                "K": int(row["K"]),
                "norm_best": float(row["norm_best"]),
            })
    return out


_REGIME_CONFIG = dict(n_sites=12, n_alleles=2, k_values=(0, 1, 2, 4, 8, 11), n=16, k_rounds=6)
_SMOKE_CONFIG = dict(n_sites=6, n_alleles=2, k_values=(0, 2), n=6, k_rounds=4)


def main(argv=None) -> int:
    import argparse
    import csv
    import json
    import sys

    p = argparse.ArgumentParser(description="NK rugged-landscape acquisition regime map")
    p.add_argument("--sweep", choices=("smoke", "regime"), default="smoke")
    p.add_argument("--seeds", type=int, default=None, help="seed count (default 5 smoke / 200 regime)")
    p.add_argument("--kappa", type=float, default=1.0, help="UCB exploration coefficient (headline)")
    p.add_argument("--kappa-grid", action="store_true", help="also sweep UCB_KAPPA_GRID {0.5,1.0,2.0}")
    p.add_argument("--from-csv", type=str, default=None,
                   help="regenerate the decision table from a saved --out CSV (skip the sweep)")
    p.add_argument("--out", type=str, default=None, help="write per-campaign records CSV here")
    p.add_argument("--table-out", type=str, default=None, help="write decision-table JSON here")
    args = p.parse_args(argv)

    cfg = dict(_REGIME_CONFIG if args.sweep == "regime" else _SMOKE_CONFIG)
    n_seeds = args.seeds if args.seeds is not None else (200 if args.sweep == "regime" else 5)

    if args.from_csv:
        records = load_records_csv(args.from_csv)
        print(f"loaded {len(records)} records from {args.from_csv}")
    else:
        records = run_rugged_sweep(seeds=range(n_seeds), arms=ACQ_ARMS, kappa=args.kappa, **cfg)

    table = regime_decision_table(records)  # pivotal: KURO vs Top-N (Holm across K)
    strongest = _strongest_baseline(records)
    table_strong = (
        regime_decision_table(records, arm_b=strongest)
        if strongest and strongest != "topn"
        else []
    )
    kappa_grid = run_ucb_kappa_grid(seeds=range(n_seeds), **cfg) if (args.kappa_grid and not args.from_csv) else []

    if args.out and not args.from_csv:
        keys = ["arm", "seed", "K", "n_sites", "best_found", "global_max",
                "norm_best", "found_global", "regret", "n_revealed"]
        with open(args.out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            for rec in records:
                w.writerow({k: rec[k] for k in keys})
    if args.table_out:
        with open(args.table_out, "w") as fh:
            json.dump({
                "pivotal_vs_topn": table,
                "vs_strongest_baseline": {"arm_b": strongest, "table": table_strong},
                "ucb_kappa_grid": kappa_grid,
            }, fh, indent=2)

    print(f"sweep={args.sweep} seeds={n_seeds} arms={ACQ_ARMS} records={len(records)}")
    print("# pivotal: sigma_kuro vs topn (Holm-adjusted p across K family)")
    for row in table:
        print(
            f"K={row['K']:>2} {row['arm_a']} vs {row['arm_b']}: "
            f"md={row['median_delta']:+.3f} cliff={row['cliffs_delta']:+.3f} "
            f"p_raw={row['wilcoxon_p_raw']:.3g} p_holm={row['wilcoxon_p_holm']:.3g} "
            f"tail={row['tail_outcome']} -> {row['decision_cell']}"
        )
    if table_strong:
        print(f"# vs strongest baseline ({strongest})")
        for row in table_strong:
            print(
                f"K={row['K']:>2} {row['arm_a']} vs {row['arm_b']}: "
                f"md={row['median_delta']:+.3f} cliff={row['cliffs_delta']:+.3f} "
                f"p_holm={row['wilcoxon_p_holm']:.3g} tail={row['tail_outcome']} -> {row['decision_cell']}"
            )
    if kappa_grid:
        print("# UCB kappa-grid robustness (mean norm_best)")
        for row in kappa_grid:
            print(f"kappa={row['kappa']:>4} K={row['K']:>2} norm_best_mean={row['norm_best_mean']:.4f}")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())