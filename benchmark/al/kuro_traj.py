# Per-round learning-curve trajectories for the structural-vs-Top-N figure.
from __future__ import annotations
import json, time
from pathlib import Path
import numpy as np
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.acquisition import select_indices
from al.real_epistatic import CombinatorialOracle, combo_zero_shot_prior
from al.kuro_real_bench import _load_multimut
from al.proxy_rf import RF_KWARGS
from kuma_core.kuro.alphafold import fetch_ca_coords
from kuma_core.kuro.evolvepro import structural_diversity_select
_HERE = Path(__file__).resolve().parent.parent
_DMS = _HERE / "data/DMS_substitutions/DMS_ProteinGym_substitutions"
_CACHE = _HERE / "results/embeddings"
_OUT = _HERE / "figures/structural_vs_topn/data/trajectories.json"
ASSAYS = [
    {"name": "F7YBW8_MESOW_Aakre_2015", "accession": "F7YBW8", "role": "win"},
    {"name": "A4_HUMAN_Seuma_2022", "accession": "P05067", "role": "kappa-split"},
    {"name": "HIS7_YEAST_Pokusaeva_2019", "accession": "P40545", "role": "loss"},
]
ARMS = ("topn", "kuro_struct", "kuro_struct_blend")
def run_one(assay_csv, acc, *, pool=400, n_seed=10, batch=10, rounds=4, seeds=50, model=DEFAULT_MODEL):
    from sklearn.ensemble import RandomForestRegressor
    raw_all, seqs_all, wt = _load_multimut(assay_csv)
    rng0 = np.random.default_rng(0)
    all_ids = sorted(raw_all)
    sub = sorted(rng0.choice(all_ids, size=min(pool, len(all_ids)), replace=False).tolist())
    raw = {i: raw_all[i] for i in sub}; seqs = {i: seqs_all[i] for i in sub}
    assay_id = Path(assay_csv).stem + f"_multimut{len(sub)}"
    emb = embed_variants(assay_id, seqs, str(_CACHE), model_name=model).loc[sub]
    ca = None; ca_resolved = 0
    try:
        ca = fetch_ca_coords(acc)
        if ca is not None: ca_resolved = sum(1 for c in ca if c is not None)
    except Exception:
        ca = None
    zs = combo_zero_shot_prior(wt, sub, model_name=model)
    r1 = [i for i, _ in sorted(zs.items(), key=lambda kv: (-kv[1], kv[0]))[:n_seed]]
    pool_ids = sub
    emb_np = {i: emb.loc[i].to_numpy(dtype=float) for i in pool_ids}
    budget = n_seed + batch * rounds
    traj = {a: [] for a in ARMS}
    for arm in ARMS:
        for seed in range(seeds):
            oracle = CombinatorialOracle.from_dict(raw, wt)
            rng = np.random.default_rng(1000 + seed)
            revealed = dict(oracle.reveal(r1))
            curve = [max(revealed.values())]
            for _r in range(rounds):
                rev_ids = list(revealed)
                unrev = [i for i in pool_ids if i not in revealed]
                if not unrev or len(revealed) >= budget:
                    curve.append(max(revealed.values())); continue
                Xtr = np.vstack([emb_np[i] for i in rev_ids])
                ytr = np.array([revealed[i] for i in rev_ids], dtype=float)
                Xun = np.vstack([emb_np[i] for i in unrev])
                m = RandomForestRegressor(**{**RF_KWARGS, "random_state": 1 + seed})
                m.fit(Xtr, ytr)
                mean = m.predict(Xun); std = np.zeros_like(mean)
                k = min(batch, budget - len(revealed), len(unrev))
                if arm == "topn":
                    idx = select_indices("topn", mean=mean, std=std, sample=mean, n=k, rng=rng)
                    picks = [unrev[j] for j in idx]
                else:
                    kappa = 0.0 if arm == "kuro_struct" else 0.3
                    rows = [(unrev[j], float(mean[j])) for j in range(len(unrev))]
                    sel, _ = structural_diversity_select(rows, k, ca_coords=ca, anchor_variants=list(revealed), kappa=kappa)
                    picks = [v for v, _ in sel]
                revealed.update(oracle.reveal(picks))
                curve.append(max(revealed.values()))
            traj[arm].append(curve)
    return {"assay": Path(assay_csv).name, "accession": acc, "pool_size": len(sub),
            "n_seed": n_seed, "batch": batch, "rounds": rounds, "seeds": seeds,
            "budget": budget, "ca_resolved": ca_resolved,
            "x_measured": [n_seed + batch * r for r in range(rounds + 1)], "traj": traj}
def main():
    out = {}
    for entry in ASSAYS:
        csv = str(_DMS / f"{entry['name']}.csv"); t0 = time.perf_counter()
        print(f"[kuro_traj] {entry['name']} ...", flush=True)
        res = run_one(csv, entry["accession"]); res["role"] = entry["role"]
        out[entry["name"]] = res
        print(f"  done {time.perf_counter()-t0:.0f}s ca={res['ca_resolved']}", flush=True)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"[kuro_traj] wrote {_OUT}", flush=True)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
