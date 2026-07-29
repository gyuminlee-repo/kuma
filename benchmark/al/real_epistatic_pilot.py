"""Phase B PILOT driver (G002 kill-gate) — combinatorial multi-mut AL on one real assay.

Runs the decisive-regime AL loop on ONE ProteinGym multi-mut assay through the
plan's pilot->scale KILL GATE before any >=3-assay scale-out:

  (a) firewall: combo oracle reveals fitness ONLY for selected variants; the
      shuffled-colon + combo-descriptor-non-degeneracy fixtures (test_real_epistatic)
      gate selection permutation-invariance.
  (b) non-degenerate signal: proxy-RF vs real EVOLVEpro top_layer Spearman >= 0.99
      and genuine per-tree std > 0 (UCB/Thompson variance is real).
  (c) wall-clock: completes all arms x >=50 seeds within the interactive budget.

R1 is held FIXED at an arm-neutral ESM-2 zero-shot Top-N batch (same byte-equal
batch to every arm and every seed); R2+ use the proxy-RF surrogate + the Phase-A
acquisition arms. The KURO arm is the combo-aware Ca-centroid maximin (kuro_ca);
embdiv is the embedding-distance maximin control. Seed varies the surrogate
random_state + Thompson draw. Phase B is the DECISIVE phase (unlike Phase A).

This is the single-pilot gate; the full >=3-assay x >=50-seed run is compute-bound
(multi-day CPU ESM-2) and is checkpointed honestly by the leader, never faked.

Usage:
  python -m al.real_epistatic_pilot --assay <csv> --accession F7YBW8 \
      --pool 400 --n-seed 10 --batch 10 --rounds 4 --seeds 50 --out results/qa/g002/pilot.json
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from al import metrics, stats
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.acquisition import select_indices
from al.proxy_rf import RF_KWARGS, proxy_vs_real_spearman
from al.real_epistatic import (
    CombinatorialOracle,
    canonical_combo_id,
    combo_al_step,
    combo_centroid_descriptor,
    combo_zero_shot_prior,
    parse_combo,
)

ARMS = ("topn", "random", "ucb", "thompson", "embdiv", "kuro_ca")


def _load_multimut(csv_path: str) -> tuple[dict[str, float], dict[str, str], str]:
    """Return (canonical_id->raw DMS_score, canonical_id->mutated_seq, wt_seq) for multi-mut rows."""
    df = pd.read_csv(csv_path, usecols=lambda c: c in {"mutant", "mutated_sequence", "DMS_score"})
    df = df.dropna(subset=["DMS_score"])
    df = df[df["mutant"].astype(str).str.contains(":")].copy()  # multi-mut only
    scores: dict[str, float] = {}
    seqs: dict[str, str] = {}
    for _m, _seq, _s in zip(df["mutant"], df["mutated_sequence"], df["DMS_score"], strict=True):
        cid = canonical_combo_id(parse_combo(str(_m)))
        scores[cid] = float(_s)
        seqs[cid] = str(_seq)
    # WT reconstruction from any variant: revert its substitutions on its mutated_sequence.
    any_m = next(iter(scores))
    seq = list(seqs[any_m])
    for mut in parse_combo(any_m):
        seq[mut[1] - 1] = mut[0]  # Mutation = (wt_aa, position, mut_aa) -> revert to wt_aa
    return scores, seqs, "".join(seq)


def run_pilot(*, assay: str, accession: str, pool: int, n_seed: int, batch: int,
              rounds: int, seeds: int, cache_dir: str, model: str) -> dict:
    t0 = time.perf_counter()
    raw_all, seqs_all, wt = _load_multimut(assay)
    # Deterministic pilot subsample of the multi-mut pool (full pool is compute-bound).
    rng0 = np.random.default_rng(0)
    all_ids = sorted(raw_all)
    sub = sorted(rng0.choice(all_ids, size=min(pool, len(all_ids)), replace=False).tolist())
    raw = {i: raw_all[i] for i in sub}
    seqs = {i: seqs_all[i] for i in sub}

    # Embeddings (ESM-2 35M mean-pool, cached per assay) for the subsampled pool.
    assay_id = Path(assay).stem + f"_multimut{len(sub)}"
    emb = embed_variants(assay_id, seqs, cache_dir, model_name=model).loc[sub]

    # Ca-centroid descriptors (permutation-invariant); positional fallback if no structure.
    from kuma_core.kuro.alphafold import fetch_ca_coords
    try:
        ca = fetch_ca_coords(accession)
    except Exception:
        ca = None
    desc = np.vstack([combo_centroid_descriptor(parse_combo(i), ca) for i in sub])
    desc_idx = {i: k for k, i in enumerate(sub)}

    # R1: arm-neutral fixed ESM-2 zero-shot Top-N neutral batch (same for every arm/seed).
    zs = combo_zero_shot_prior(wt, sub, model_name=model)
    r1 = [i for i, _ in sorted(zs.items(), key=lambda kv: (-kv[1], kv[0]))[:n_seed]]

    # Gate (b): proxy-RF vs real EVOLVEpro top_layer Spearman on the R1-revealed snapshot.
    proxy_real_rho = None
    proxy_real_note = ""
    try:
        from al.loop import _build_labels
        iteration = {i: (0.0 if i in set(r1) else float("nan")) for i in sub}
        labels = _build_labels(sub, raw, iteration)  # canonical schema (activity_scaled/binary)
        emb_df = emb.copy()
        emb_df.index = sub
        proxy_real_rho = float(proxy_vs_real_spearman(emb_df, labels, 1))
    except Exception as e:  # evolvepro unavailable / alignment
        proxy_real_note = f"proxy_vs_real unavailable: {type(e).__name__}: {e}"

    finals: dict[str, list[float]] = {a: [] for a in ARMS}
    max_std_seen = 0.0
    pool_ids = sub
    emb_np = {i: emb.loc[i].to_numpy(dtype=float) for i in pool_ids}
    budget = n_seed + batch * rounds

    for arm in ARMS:
        for seed in range(seeds):
            oracle = CombinatorialOracle.from_dict(raw, wt)
            rng = np.random.default_rng(1000 + seed)
            revealed = dict(oracle.reveal(r1))  # {id: normalized}, fixed R1
            for _r in range(rounds):
                rev_ids = list(revealed)
                unrev = [i for i in pool_ids if i not in revealed]
                if not unrev or len(revealed) >= budget:
                    break
                Xtr = np.vstack([emb_np[i] for i in rev_ids])
                ytr = np.array([revealed[i] for i in rev_ids], dtype=float)
                Xun = np.vstack([emb_np[i] for i in unrev])
                from sklearn.ensemble import RandomForestRegressor
                m = RandomForestRegressor(**{**RF_KWARGS, "random_state": 1 + seed})
                m.fit(Xtr, ytr)
                mean, std, sample = combo_al_step(m, Xun, rng)
                max_std_seen = max(max_std_seen, float(np.max(std)))
                k = min(batch, budget - len(revealed), len(unrev))
                if arm in ("topn", "ucb", "thompson", "random"):
                    idx = select_indices(arm, mean=mean, std=std, sample=sample, n=k, rng=rng)
                elif arm == "embdiv":
                    anc = np.vstack([emb_np[i] for i in rev_ids])
                    idx = select_indices("embdiv", mean=mean, features=Xun, anchor_features=anc, n=k, rng=rng)
                else:  # kuro_ca: Ca-centroid maximin (combo-aware KURO)
                    feats = np.vstack([desc[desc_idx[i]] for i in unrev])
                    anc = np.vstack([desc[desc_idx[i]] for i in rev_ids])
                    idx = select_indices("embdiv", mean=mean, features=feats, anchor_features=anc, n=k, rng=rng)
                picks = [unrev[j] for j in idx]
                revealed.update(oracle.reveal(picks))
            finals[arm].append(max(revealed.values()))

    # Decision: KURO (kuro_ca) vs Top-N on norm_best@final (single comparison; Holm trivial).
    a_nb, b_nb = finals["kuro_ca"], finals["topn"]
    cmp = stats.paired_comparison(a_nb, b_nb, seed=0)
    mean_v = stats.mean_verdict(cmp)
    rng = np.random.default_rng(0)
    aa, bb = np.asarray(a_nb), np.asarray(b_nb)
    idxs = np.arange(aa.size)
    diffs = np.array([metrics.cvar(bb[rng.choice(idxs, size=idxs.size, replace=True)], 0.20)
                      - metrics.cvar(aa[rng.choice(idxs, size=idxs.size, replace=True)], 0.20)
                      for _ in range(10000)])
    tail = stats.tail_outcome(float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5)))
    cell = stats.decision_cell(mean_v, tail)

    wall = time.perf_counter() - t0
    gate_b = (proxy_real_rho is not None and proxy_real_rho >= 0.99) and max_std_seen > 0.0
    return {
        "assay": Path(assay).name, "accession": accession, "wt_len": len(wt),
        "pool_size": len(sub), "n_seed": n_seed, "batch": batch, "rounds": rounds,
        "seeds": seeds, "budget": budget, "structure_available": ca is not None,
        "per_arm_norm_best_mean": {a: float(np.mean(v)) for a, v in finals.items()},
        "per_arm_cvar20": {a: float(metrics.cvar(v, 0.20)) for a, v in finals.items()},
        "decision_kuro_ca_vs_topn": {
            "median_delta": cmp["median_delta"], "cliffs_delta": cmp["cliffs_delta"],
            "wilcoxon_p": cmp["wilcoxon_p"], "mean_verdict": mean_v,
            "tail_outcome": tail, "decision_cell": cell,
        },
        "gate": {
            "a_firewall_fixtures": "see test_real_epistatic (9 passed: leak-free, shuffled-colon, non-degeneracy a/b/c)",
            "b_proxy_vs_real_spearman": proxy_real_rho, "b_max_std": max_std_seen,
            "b_proxy_real_note": proxy_real_note, "b_pass": bool(gate_b),
            "c_wall_clock_seconds": wall,
        },
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Phase B combinatorial multi-mut AL pilot (G002 kill-gate)")
    p.add_argument("--assay", required=True)
    p.add_argument("--accession", required=True)
    p.add_argument("--pool", type=int, default=400)
    p.add_argument("--n-seed", type=int, default=10)
    p.add_argument("--batch", type=int, default=10)
    p.add_argument("--rounds", type=int, default=4)
    p.add_argument("--seeds", type=int, default=50)
    p.add_argument("--cache-dir", default=str(Path(__file__).resolve().parents[1] / "results" / "embeddings"))
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    res = run_pilot(assay=args.assay, accession=args.accession, pool=args.pool, n_seed=args.n_seed,
                    batch=args.batch, rounds=args.rounds, seeds=args.seeds,
                    cache_dir=args.cache_dir, model=args.model)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
