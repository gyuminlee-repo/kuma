"""Single-mutation AL bench — evaluates kuma_core KURO production selectors on
single-sub ProteinGym assays.

Domain of validity: SINGLE-MUTATION ProteinGym assays (one substitution per variant).
Each variant has exactly ONE position, so KURO's _POS_RE first-position extraction
(re.compile(r'[A-Z](\\d+)[A-Z]').search(variant)) is CORRECT — there is no combo-
reduction artefact that affects the combinatorial bench.

Arms:
  topn         — greedy top-N by RF prediction (baseline)
  kuro_domain  — REAL domain_aware_select (domain-proportional quota + position binning)
  kuro_pareto  — REAL pareto_diversity_select (greedy maximin in position / Ca space)
  embdiv       — greedy maximin in ESM-2 embedding space (Ca-free diversity reference)

Single-mut landscape properties:
  No epistatic traps → diversity-based selection (kuro_pareto, embdiv) may not add
  value for a different reason than in the combinatorial regime.  Results are reported
  honestly regardless of outcome.

Assays used (DEFAULT_ASSAYS):
  1. A0A1I9GEU1_NEIME_Kennouche_2019  acc=A0A1I9GEU1   (~51% emb cache hit)
  2. TCRG1_MOUSE_Tsuboyama_2023_1E0L  acc=P20748        (100% emb cache hit; 37-AA)
  3. F7YBW8_MESOW_Ding_2023           acc=F7YBW8        (100% emb cache hit; 80 vars)

Substitutions from suggested (A4GRB6, BLAT):
  * A4GRB6_PSEAI_Chen_2020 → F7YBW8_MESOW_Ding_2023:
      A4GRB6 domain lookup returned empty (cached as annotated=false); no embeddings
      cached. F7YBW8_MESOW_Ding_2023 has all 80 single-sub variants embedded and 2
      domain annotations cached.
  * BLAT_ECOLX_Stiffler_2015 → TCRG1_MOUSE_Tsuboyama_2023_1E0L:
      BLAT requires ~400 fresh 286-AA ESM-2 embeddings (~10 min CPU). TCRG1 has all
      621 single-sub variants pre-embedded (37 AA, trivial).

Usage:
    python -m al.kuro_singlemut_bench                       # 3 assays (seeds=50)
    python -m al.kuro_singlemut_bench --smoke               # synthetic, exits 0
    python -m al.kuro_singlemut_bench --assay <csv> --accession <acc>
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from al import metrics, stats
from al.coldstart import esm2_zero_shot_llr
from al.domains import fetch_domains
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.proxy_rf import RF_KWARGS
from al.acquisition import select_indices
from al.run_al_simulation import load_assay

from kuma_core.kuro.alphafold import fetch_ca_coords
from kuma_core.kuro.evolvepro import domain_aware_select, pareto_diversity_select

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent.parent  # benchmark/

ARMS = ("topn", "kuro_domain", "kuro_pareto", "embdiv")
COMPARISON_ARMS = ("kuro_domain", "kuro_pareto", "embdiv")  # each vs topn

SINGLE_MUT_NOTE = (
    "In the single-mutation regime, each variant has exactly one position; "
    "KURO's _POS_RE first-position extraction is CORRECT (no combo-reduction "
    "artefact).  Single-mut landscapes lack epistatic structure, so diversity-based "
    "selection (kuro_pareto, embdiv) may not add value for a different structural "
    "reason than in the combinatorial regime."
)

DEFAULT_ASSAYS = [
    {
        "name": "A0A1I9GEU1_NEIME_Kennouche_2019",
        "csv": str(
            _HERE / "data/DMS_substitutions/DMS_ProteinGym_substitutions"
            / "A0A1I9GEU1_NEIME_Kennouche_2019.csv"
        ),
        "accession": "A0A1I9GEU1",
        "substitution": None,
    },
    {
        "name": "TCRG1_MOUSE_Tsuboyama_2023_1E0L",
        "csv": str(
            _HERE / "data/DMS_substitutions/DMS_ProteinGym_substitutions"
            / "TCRG1_MOUSE_Tsuboyama_2023_1E0L.csv"
        ),
        "accession": "P20748",
        "substitution": (
            "Substituted for BLAT_ECOLX_Stiffler_2015 (P62593): BLAT requires ~400 "
            "fresh 286-AA ESM-2 embeddings; TCRG1 has all 621 single-sub variants "
            "pre-embedded."
        ),
    },
    {
        "name": "F7YBW8_MESOW_Ding_2023",
        "csv": str(
            _HERE / "data/DMS_substitutions/DMS_ProteinGym_substitutions"
            / "F7YBW8_MESOW_Ding_2023.csv"
        ),
        "accession": "F7YBW8",
        "substitution": (
            "Substituted for A4GRB6_PSEAI_Chen_2020 (A4GRB6): A4GRB6 domain lookup "
            "cached as empty (annotated=false) and no embeddings cached; F7YBW8 has "
            "all 80 single-sub variants embedded and 2 domain annotations cached."
        ),
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Core bench runner (one assay)
# ──────────────────────────────────────────────────────────────────────────────

def run_singlemut_bench(
    assay_csv: str,
    uniprot_acc: str,
    *,
    pool: int = 400,
    n_seed: int = 10,
    batch: int = 10,
    rounds: int = 4,
    seeds: int = 50,
    cache_dir: str,
    domain_cache_dir: str,
    model: str = DEFAULT_MODEL,
) -> dict:
    """Run single-mut AL loop with all KURO arms on one assay.

    Parameters
    ----------
    assay_csv:
        Path to a ProteinGym single-substitution DMS CSV.
    uniprot_acc:
        UniProt accession for domain/Ca annotation lookup.
    pool:
        Maximum single-sub variants to subsample (deterministic seed=0).
    n_seed:
        R1 zero-shot Top-N batch size (shared across arms and seeds).
    batch:
        Variants selected per AL round (R2+).
    rounds:
        Number of AL rounds per seed.
    seeds:
        Number of independent seeds.
    cache_dir:
        ESM-2 embedding cache directory.
    domain_cache_dir:
        Domain JSON cache directory.
    model:
        ESM-2 model name (35M default; 650M prohibited).

    Returns
    -------
    dict
        Per-arm norm_best means, CVaR@20%, 9-cell decisions, metadata.
    """
    t0 = time.perf_counter()

    # ── Load single-sub variants via existing infrastructure ─────────────────
    data = load_assay(assay_csv)
    all_variants = data["variants"]
    all_seqs = data["seqs"]
    oracle_full = data["oracle"]
    wt = data["wt"]
    assay_id = data["assay"]  # CSV stem — reuses existing embedding cache

    # ── Deterministic pool subsample ─────────────────────────────────────────
    rng0 = np.random.default_rng(0)
    sorted_all = sorted(all_variants)
    if len(sorted_all) > pool:
        idx_arr = rng0.choice(len(sorted_all), size=pool, replace=False)
        sub: list[str] = sorted([sorted_all[i] for i in idx_arr])
    else:
        sub = sorted_all

    oracle: dict[str, float] = {v: oracle_full[v] for v in sub}
    seqs: dict[str, str] = {v: all_seqs[v] for v in sub}

    # Within-pool min-max normalize DMS_score to [0, 1] for norm_best
    raw_vals = np.array([oracle[v] for v in sub], dtype=float)
    raw_min, raw_max = float(raw_vals.min()), float(raw_vals.max())
    span = (raw_max - raw_min) if raw_max > raw_min else 1.0
    norm_oracle: dict[str, float] = {v: (oracle[v] - raw_min) / span for v in sub}

    # ── Embeddings: 35M ESM-2, cached per assay_id ──────────────────────────
    emb_df = embed_variants(assay_id, seqs, cache_dir, model_name=model)
    emb_np: dict[str, np.ndarray] = {v: emb_df.loc[v].to_numpy(dtype=float) for v in sub}

    # ── Ca coordinates (1-based); None = structure unavailable ───────────────
    ca: list | None = None
    ca_resolved: int = 0
    ca_error: str | None = None
    try:
        ca = fetch_ca_coords(uniprot_acc)
        if ca is not None:
            ca_resolved = sum(1 for c in ca if c is not None)
    except Exception as exc:
        ca_error = f"{type(exc).__name__}: {exc}"

    # ── Domain annotations (for kuro_domain arm) ─────────────────────────────
    domains: list[dict] | None = None
    domains_error: str | None = None
    domains_resolved: int = 0
    try:
        domains = fetch_domains(uniprot_acc, domain_cache_dir, allow_network=True)
        domains_resolved = len(domains)
    except Exception as exc:
        domains_error = f"{type(exc).__name__}: {exc}"

    domain_arm_skip = not domains  # skip kuro_domain when no annotation

    # ── R1: ESM-2 zero-shot LLR Top-n_seed (shared across all arms/seeds) ───
    zs = esm2_zero_shot_llr(wt, sub, model_name=model)
    r1: list[str] = [v for v, _ in sorted(zs.items(), key=lambda kv: (-kv[1], kv[0]))[:n_seed]]

    pool_ids = sub
    budget = n_seed + batch * rounds

    finals: dict[str, list[float]] = {a: [] for a in ARMS}

    from sklearn.ensemble import RandomForestRegressor  # deferred import

    for arm in ARMS:
        if arm == "kuro_domain" and domain_arm_skip:
            continue  # leave finals["kuro_domain"] empty; recorded in decision

        for seed in range(seeds):
            rng = np.random.default_rng(1000 + seed)
            # Firewall: revealed dict accumulates ONLY selected variants' labels
            revealed: dict[str, float] = {}

            # R1 reveal — zero-shot top-n_seed (oracle labels, normalized)
            for v in r1:
                revealed[v] = norm_oracle[v]

            for _r in range(rounds):
                rev_ids = list(revealed)
                unrev = [v for v in pool_ids if v not in revealed]
                if not unrev or len(revealed) >= budget:
                    break

                Xtr = np.vstack([emb_np[v] for v in rev_ids])
                ytr = np.array([revealed[v] for v in rev_ids], dtype=float)
                Xun = np.vstack([emb_np[v] for v in unrev])

                rf = RandomForestRegressor(**{**RF_KWARGS, "random_state": 1 + seed})
                rf.fit(Xtr, ytr)

                per_tree = np.stack([est.predict(Xun) for est in rf.estimators_])
                mean = per_tree.mean(axis=0)
                std = per_tree.std(axis=0)
                sample = per_tree[
                    rng.integers(0, len(rf.estimators_), size=len(unrev)),
                    np.arange(len(unrev)),
                ]

                k = min(batch, budget - len(revealed), len(unrev))
                if k <= 0:
                    break

                if arm == "topn":
                    idx = select_indices(
                        "topn", mean=mean, std=std, sample=sample, n=k, rng=rng
                    )
                    picks = [unrev[j] for j in idx]

                elif arm == "kuro_domain":
                    # rows: list[tuple[str, float]] sorted DESC by y_pred — KURO contract.
                    rows: list[tuple[str, float]] = sorted(
                        [(unrev[j], float(mean[j])) for j in range(len(unrev))],
                        key=lambda x: -x[1],
                    )
                    # REAL call: first-position extraction is CORRECT for single-sub.
                    selected_rows, _dom_stats = domain_aware_select(
                        rows, domains, top_n=k, ca_coords=ca
                    )
                    picks = [v for v, _ in selected_rows[:k]]

                elif arm == "kuro_pareto":
                    rows = sorted(
                        [(unrev[j], float(mean[j])) for j in range(len(unrev))],
                        key=lambda x: -x[1],
                    )
                    # REAL call: first-position extraction is CORRECT for single-sub.
                    selected_rows, _replaced = pareto_diversity_select(
                        rows, top_n=k, ca_coords=ca
                    )
                    picks = [v for v, _ in selected_rows[:k]]

                elif arm == "embdiv":
                    anc = np.vstack([emb_np[v] for v in rev_ids])
                    idx = select_indices(
                        "embdiv", mean=mean, features=Xun, anchor_features=anc, n=k, rng=rng
                    )
                    picks = [unrev[j] for j in idx]

                else:
                    raise ValueError(f"unknown arm: {arm}")

                # Firewall: reveal selected only (oracle labels, normalized)
                for v in picks:
                    revealed[v] = norm_oracle[v]

            # norm_best over revealed only — no oracle leak
            finals[arm].append(max(revealed.values()))

    # ── Per-arm summary ───────────────────────────────────────────────────────
    per_arm_mean: dict[str, float | None] = {}
    per_arm_cvar: dict[str, float | None] = {}
    for a in ARMS:
        v = finals[a]
        per_arm_mean[a] = float(np.mean(v)) if v else None
        per_arm_cvar[a] = float(metrics.cvar(v, 0.20)) if v else None

    # ── 9-cell decisions ──────────────────────────────────────────────────────
    decisions: dict[str, dict] = {}
    topn_nb = finals["topn"]

    for cmp_arm in COMPARISON_ARMS:
        key = f"{cmp_arm}_vs_topn"
        arm_nb = finals[cmp_arm]

        if not arm_nb:
            decisions[key] = {
                "skipped": True,
                "reason": domains_error or "kuro_domain arm skipped (no domain annotation)",
            }
            continue

        cmp = stats.paired_comparison(arm_nb, topn_nb, seed=0)
        mean_v = stats.mean_verdict(cmp)

        # CVaR bootstrap: diff = cvar(topn) - cvar(arm); positive → topn tail better.
        # tail_outcome convention: ci of (topn_cvar - arm_cvar).
        # TAIL-ADV means arm (KURO/embdiv) has better worst-case (ci_hi < 0).
        boot_rng = np.random.default_rng(0)
        aa = np.asarray(arm_nb)
        bb = np.asarray(topn_nb)
        idxs = np.arange(aa.size)
        diffs = np.array([
            metrics.cvar(bb[boot_rng.choice(idxs, size=idxs.size, replace=True)], 0.20)
            - metrics.cvar(aa[boot_rng.choice(idxs, size=idxs.size, replace=True)], 0.20)
            for _ in range(10_000)
        ])
        tail = stats.tail_outcome(
            float(np.percentile(diffs, 2.5)),
            float(np.percentile(diffs, 97.5)),
        )
        cell = stats.decision_cell(mean_v, tail)

        decisions[key] = {
            "median_delta": cmp["median_delta"],
            "cliffs_delta": cmp["cliffs_delta"],
            "wilcoxon_p": cmp["wilcoxon_p"],
            "mean_verdict": mean_v,
            "tail_outcome": tail,
            "decision_cell": cell,
        }

    wall = time.perf_counter() - t0
    return {
        "assay": Path(assay_csv).name,
        "accession": uniprot_acc,
        "pool_size": len(sub),
        "n_seed": n_seed,
        "batch": batch,
        "rounds": rounds,
        "seeds_run": seeds,
        "budget": budget,
        "ca_available": ca is not None,
        "ca_resolved": ca_resolved,
        "ca_error": ca_error,
        "domains_available": bool(domains),
        "domains_resolved": domains_resolved,
        "domains_error": domains_error,
        "domain_arm_skip": domain_arm_skip,
        "per_arm_norm_best_mean": per_arm_mean,
        "per_arm_cvar20": per_arm_cvar,
        "decisions": decisions,
        "single_mut_note": SINGLE_MUT_NOTE,
        "wall_seconds": wall,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Smoke test (synthetic, no ESM-2)
# ──────────────────────────────────────────────────────────────────────────────

def _smoke_test() -> int:
    """Synthetic cheap validation: KURO single-mut arm wiring compiles and runs."""
    # 20 synthetic single-sub variant rows, sorted DESC by predicted fitness
    variants = [f"A{i}V" for i in range(1, 21)]
    rows: list[tuple[str, float]] = [(v, float(20 - i)) for i, v in enumerate(variants)]

    # Two synthetic domains covering the 20 positions
    domains = [
        {"name": "d1", "start": 1, "end": 10},
        {"name": "d2", "start": 11, "end": 20},
    ]

    # kuro_domain arm (no Ca)
    sel1, stats_dict = domain_aware_select(rows, domains, top_n=5, ca_coords=None)
    assert len(sel1) <= 5, f"domain_aware_select returned {len(sel1)} > 5"
    ids1 = [v for v, _ in sel1]
    assert len(set(ids1)) == len(ids1), "domain_aware_select returned duplicates"
    pool_set = {v for v, _ in rows}
    assert set(ids1) <= pool_set, "domain_aware_select returned out-of-pool variants"
    assert isinstance(stats_dict, dict)

    # kuro_pareto arm (no Ca)
    sel2, replaced = pareto_diversity_select(rows, top_n=5, ca_coords=None)
    assert len(sel2) <= 5, f"pareto_diversity_select returned {len(sel2)} > 5"
    ids2 = [v for v, _ in sel2]
    assert len(set(ids2)) == len(ids2), "pareto_diversity_select returned duplicates"
    assert set(ids2) <= pool_set, "pareto_diversity_select returned out-of-pool variants"
    assert isinstance(replaced, int)

    # Verify single-mut position extraction is correct (no combo-reduction artefact)
    import re
    _POS_RE = re.compile(r"[A-Z](\d+)[A-Z]")
    for v in variants:
        m = _POS_RE.search(v)
        assert m is not None, f"_POS_RE failed for {v}"
        pos = int(m.group(1))
        expected = int(v[1:-1])  # e.g. 'A5V' -> 5
        assert pos == expected, f"position mismatch for {v}: {pos} != {expected}"

    print("[smoke] domain_aware_select OK, pareto_diversity_select OK, pos extraction OK")
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Single-mut AL bench — real KURO domain_aware_select + pareto_diversity_select"
    )
    p.add_argument("--smoke", action="store_true", help="Synthetic quick smoke test; exits 0")
    p.add_argument("--assay", default=None, help="Path to single-sub DMS CSV (overrides default run)")
    p.add_argument("--accession", default=None, help="UniProt accession for --assay")
    p.add_argument("--pool", type=int, default=400)
    p.add_argument("--n-seed", type=int, default=10)
    p.add_argument("--batch", type=int, default=10)
    p.add_argument("--rounds", type=int, default=4)
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument(
        "--cache-dir",
        default=str(Path(__file__).resolve().parents[1] / "results" / "embeddings"),
    )
    p.add_argument(
        "--domain-cache-dir",
        default=str(Path(__file__).resolve().parents[1] / "results" / "domain_cache"),
    )
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument(
        "--out",
        default=str(
            Path(__file__).resolve().parents[1] / "results" / "qa" / "kuro_singlemut" / "bench.json"
        ),
    )
    args = p.parse_args(argv)

    if args.smoke:
        return _smoke_test()

    if args.assay:
        if not args.accession:
            p.error("--accession required when --assay is given")
        assay_list = [
            {"name": Path(args.assay).stem, "csv": args.assay, "accession": args.accession,
             "substitution": None}
        ]
    else:
        assay_list = DEFAULT_ASSAYS

    results: dict[str, dict] = {}
    for entry in assay_list:
        sub_note = entry.get("substitution")
        print(
            f"[kuro_singlemut_bench] running {entry['name']} (acc={entry['accession']})"
            + (f"\n  substitution: {sub_note}" if sub_note else "")
        )
        res = run_singlemut_bench(
            assay_csv=entry["csv"],
            uniprot_acc=entry["accession"],
            pool=args.pool,
            n_seed=args.n_seed,
            batch=args.batch,
            rounds=args.rounds,
            seeds=args.seeds,
            cache_dir=args.cache_dir,
            domain_cache_dir=args.domain_cache_dir,
            model=args.model,
        )
        if sub_note:
            res["substitution"] = sub_note
        results[entry["name"]] = res
        print(f"  done in {res['wall_seconds']:.1f}s")
        for dec_key, dec in res["decisions"].items():
            if dec.get("skipped"):
                print(f"  {dec_key}: SKIPPED ({dec.get('reason', '')})")
            else:
                print(
                    f"  {dec_key}: {dec['decision_cell']} "
                    f"(mean={dec['mean_verdict']}, tail={dec['tail_outcome']})"
                )
        for arm, mean_nb in res["per_arm_norm_best_mean"].items():
            cvar_val = res["per_arm_cvar20"].get(arm)
            if mean_nb is not None:
                print(f"  {arm}: mean_nb={mean_nb:.4f}  cvar20={cvar_val:.4f}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[kuro_singlemut_bench] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
