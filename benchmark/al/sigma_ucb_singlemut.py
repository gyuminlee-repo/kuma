"""Step-1 validation (IspS proxy): does UCB beat Top-N in the SINGLE-MUTANT regime?

Round-1 of the IspS campaign is single mutants on a single-active-site enzyme with
~1 plate of labels. The combinatorial benchmark does not cover this regime. Here we
run a retrospective active-learning simulation on real single-mutant ENZYME DMS
assays (IspS proxies), comparing acquisition arms:
  - topn   : greedy exploitation (current EVOLVEpro/KURO default)
  - ucb    : mu + kappa * sigma, sigma = RF per-tree std (the proposed upgrade)
  - random : explore baseline

Honesty: DMS_score is revealed ONLY for picked variants; the RF trains on revealed
labels only. No fabricated numbers. sigma is the same RF-tree-std discussed in the
note (computed from the fitted forest on the unrevealed pool).

Run:  cd kuma/benchmark && ./.venv-al/bin/python -m al.sigma_ucb_singlemut
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from al.acquisition import rf_mean_std, select_indices
from al.embed_cache import DEFAULT_MODEL, embed_variants
from al.real_epistatic import combo_zero_shot_prior
from al.proxy_rf import RF_KWARGS

_HERE = Path(__file__).resolve().parent.parent
_DMS = _HERE / "data/DMS_substitutions/DMS_ProteinGym_substitutions"
_CACHE = _HERE / "results/embeddings"
_OUT = _HERE / "results/qa/sigma_ucb_singlemut.json"

# Single-mutant ENZYME DMS assays = IspS (single-active-site enzyme) proxies.
ASSAYS = [
    "Q59976_STRSQ_Romero_2015",        # beta-glucosidase (Arnold-lab directed evolution)
    "MTH3_HAEAE_RockahShmuel_2015",    # DNA methyltransferase
    "HXK4_HUMAN_Gersing_2022_activity",# glucokinase ACTIVITY readout (enzyme activity)
]


def load_single(csv_path: str) -> tuple[dict[str, float], dict[str, str], str]:
    """(id->DMS_score, id->mutated_seq, wt_seq) for SINGLE-mutant rows only."""
    df = pd.read_csv(csv_path, usecols=lambda c: c in {"mutant", "mutated_sequence", "DMS_score"})
    df = df.dropna(subset=["DMS_score"])
    df = df[~df["mutant"].astype(str).str.contains(":")]  # singles only
    raw = dict(zip(df["mutant"].astype(str), df["DMS_score"].astype(float)))
    seqs = dict(zip(df["mutant"].astype(str), df["mutated_sequence"].astype(str)))
    # reconstruct WT by reverting one single mutant (e.g. 'A123V' -> put 'A' at pos 123)
    v0 = next(iter(seqs))
    wt_aa, pos = v0[0], int(v0[1:-1])
    s = seqs[v0]
    wt = s[: pos - 1] + wt_aa + s[pos:]
    return raw, seqs, wt


def frac_to_opt(best: float, lo: float, hi: float) -> float:
    return (best - lo) / (hi - lo) if hi > lo else 0.0


def run_one(name, *, pool=400, n_seed=10, batch=10, rounds=4, seeds=40,
            kappas=(0.5, 1.0, 2.0), model=DEFAULT_MODEL):
    csv = str(_DMS / f"{name}.csv")
    raw_all, seqs_all, wt = load_single(csv)
    all_ids = sorted(raw_all)
    rng0 = np.random.default_rng(0)
    sub = sorted(rng0.choice(all_ids, size=min(pool, len(all_ids)), replace=False).tolist())
    raw = {i: raw_all[i] for i in sub}
    seqs = {i: seqs_all[i] for i in sub}
    lo, hi = min(raw.values()), max(raw.values())

    assay_id = f"{name}_single{len(sub)}"
    emb = embed_variants(assay_id, seqs, str(_CACHE), model_name=model).loc[sub]
    emb_np = {i: emb.loc[i].to_numpy(dtype=float) for i in sub}

    # informed seed (SCANEER-like): top-n_seed by zero-shot ESM prior
    zs = combo_zero_shot_prior(wt, sub, model_name=model)
    seed_ids = [i for i, _ in sorted(zs.items(), key=lambda kv: (-kv[1], kv[0]))[:n_seed]]

    budget = n_seed + batch * rounds
    arms = ["topn", "random"] + [f"ucb{k}" for k in kappas]
    # final fraction-to-optimum reached, per arm per seed
    finals = {a: [] for a in arms}

    for arm in arms:
        for s in range(seeds):
            rng = np.random.default_rng(1000 + s)
            revealed = {i: raw[i] for i in seed_ids}
            for _r in range(rounds):
                unrev = [i for i in sub if i not in revealed]
                if not unrev or len(revealed) >= budget:
                    break
                Xtr = np.vstack([emb_np[i] for i in revealed])
                ytr = np.array([revealed[i] for i in revealed], dtype=float)
                Xun = np.vstack([emb_np[i] for i in unrev])
                m = __import__("sklearn.ensemble", fromlist=["RandomForestRegressor"]).RandomForestRegressor(
                    **{**RF_KWARGS, "random_state": 1 + s}
                )
                m.fit(Xtr, ytr)
                mean, std = rf_mean_std(m, Xun)
                k = min(batch, budget - len(revealed), len(unrev))
                if arm.startswith("ucb"):
                    idx = select_indices("ucb", mean=mean, std=std, n=k, rng=rng,
                                         kappa=float(arm[3:]))
                else:
                    idx = select_indices(arm, mean=mean, std=std, n=k, rng=rng)
                for j in idx:
                    revealed[unrev[j]] = raw[unrev[j]]
            finals[arm].append(frac_to_opt(max(revealed.values()), lo, hi))

    # aggregate: mean fraction-to-opt + paired win-rate of each ucb vs topn
    base = np.array(finals["topn"])
    out = {"assay": name, "pool": len(sub), "n_total_single": len(all_ids),
           "budget": budget, "seeds": seeds, "lo": lo, "hi": hi,
           "mean_frac": {a: float(np.mean(finals[a])) for a in arms}}
    out["vs_topn_paired_winrate"] = {
        a: float(np.mean(np.array(finals[a]) > base)) for a in arms if a != "topn"
    }
    out["vs_topn_mean_delta"] = {
        a: float(np.mean(np.array(finals[a]) - base)) for a in arms if a != "topn"
    }
    return out


def main():
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    results = {}
    for name in ASSAYS:
        t0 = time.perf_counter()
        print(f"[singlemut] {name} ...", flush=True)
        try:
            results[name] = run_one(name)
            r = results[name]
            print(f"  done {time.perf_counter()-t0:.0f}s  mean_frac={r['mean_frac']}", flush=True)
            print(f"  vs_topn winrate={r['vs_topn_paired_winrate']} delta={r['vs_topn_mean_delta']}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  FAILED: {type(e).__name__}: {e}", flush=True)
            results[name] = {"assay": name, "error": f"{type(e).__name__}: {e}"}
    _OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"[singlemut] wrote {_OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
