#!/usr/bin/env python
"""IspS-specific retrospective AL: does UCB beat Top-N on the 94 measured singles?

The 94 GC-measured single mutants are the only IspS ground truth. We simulate the
active-learning loop WITHIN them: from a random seed, each round trains the exact
EVOLVEpro RF on revealed (embedding -> activity), predicts mean+std on the unrevealed
subset, picks a batch by the arm's rule, reveals it, and tracks the best activity
found. Arms: topn (greedy), random, ucb<kappa> (mean + kappa*tree_std). Metric =
fraction-to-optimum of the best activity reached. No fabricated numbers; RF trains on
revealed labels only.

Usage:
  cd kuma/benchmark && ./.venv-al/bin/python scripts/isps_alsim.py \
    --embeddings <emb.csv> --labels <round1.xlsx> --wt-fasta <WT.fasta>
"""
from __future__ import annotations

import argparse
import re
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from al.proxy_rf import RF_KWARGS  # exact EVOLVEpro RF hyperparameters

_FULL = re.compile(r"^[A-Z]\d+[A-Z]$")
_SHORT = re.compile(r"^(\d+)([A-Z])$")


def to_full(v, wt):
    v = str(v).strip()
    if _FULL.match(v):
        return v
    m = _SHORT.match(v)
    if m and wt and 1 <= int(m.group(1)) <= len(wt):
        p = int(m.group(1))
        return f"{wt[p - 1]}{p}{m.group(2)}"
    return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embeddings", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--wt-fasta", required=True)
    ap.add_argument("--variant-col", default="Variant")
    ap.add_argument("--activity-col", default="activity")
    ap.add_argument("--n-seed", type=int, default=10)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=120)
    ap.add_argument("--kappas", default="0.25,0.5,1.0,2.0")
    args = ap.parse_args(argv)

    wt = "".join(l.strip() for l in open(args.wt_fasta) if not l.startswith(">"))
    lab = pd.read_excel(args.labels) if args.labels.lower().endswith((".xlsx", ".xls")) \
        else pd.read_csv(args.labels)
    lab = lab.dropna(subset=[args.activity_col])
    emb_idx = pd.read_csv(args.embeddings, usecols=[0]).iloc[:, 0].astype(str)
    pos = {v: i for i, v in enumerate(emb_idx)}
    rids, acts = [], []
    for v, a in zip(lab[args.variant_col], lab[args.activity_col]):
        f = to_full(v, wt)
        if f in pos:
            rids.append(f)
            acts.append(float(a))
    n = len(rids)
    print(f"[info] measured matched={n}", file=sys.stderr)
    # load only the needed embedding rows
    want = set(rids)
    rows = pd.read_csv(args.embeddings, index_col=0)
    X = rows.loc[rids].to_numpy(float)
    y = np.array(acts)
    lo, hi = y.min(), y.max()

    def frac(best):
        return (best - lo) / (hi - lo) if hi > lo else 0.0

    kappas = [float(k) for k in args.kappas.split(",")]
    arms = ["topn", "random"] + [f"ucb{k}" for k in kappas]
    budget = args.n_seed + args.batch * args.rounds
    finals = {a: [] for a in arms}

    for arm in arms:
        for s in range(args.seeds):
            rng = np.random.default_rng(1000 + s)
            seed_idx = list(rng.choice(n, size=args.n_seed, replace=False))
            revealed = set(seed_idx)
            for _r in range(args.rounds):
                unrev = [i for i in range(n) if i not in revealed]
                if not unrev or len(revealed) >= budget:
                    break
                rev = sorted(revealed)
                m = RandomForestRegressor(**{**RF_KWARGS, "random_state": 1 + s})
                m.fit(X[rev], y[rev])
                Xun = X[unrev]
                per_tree = np.stack([t.predict(Xun) for t in m.estimators_])
                mean, std = per_tree.mean(0), per_tree.std(0)
                k = min(args.batch, budget - len(revealed), len(unrev))
                if arm == "topn":
                    order = np.argsort(-mean)
                elif arm == "random":
                    order = rng.permutation(len(unrev))
                else:
                    order = np.argsort(-(mean + float(arm[3:]) * std))
                for j in order[:k]:
                    revealed.add(unrev[j])
            finals[arm].append(frac(max(y[i] for i in revealed)))

    base = np.array(finals["topn"])
    print(f"\n=== IspS retrospective AL (n={n}, seed={args.n_seed}, batch={args.batch}, "
          f"rounds={args.rounds}, budget={budget}, seeds={args.seeds}) ===")
    print(f"{'arm':<10} {'mean_frac':>10} {'vs_topn_delta':>14} {'winrate':>9}")
    for a in arms:
        arr = np.array(finals[a])
        d = "" if a == "topn" else f"{(arr - base).mean():+.4f}"
        w = "" if a == "topn" else f"{(arr > base).mean():.3f}"
        print(f"{a:<10} {arr.mean():>10.4f} {d:>14} {w:>9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
