#!/usr/bin/env python
"""Standalone sigma/UCB helper for the IspS (or any) EVOLVEpro round.

Self-contained: needs only numpy, pandas, scipy, scikit-learn. Does NOT touch
EVOLVEpro/model.py and does NOT re-embed or re-measure. It re-fits the exact same
RandomForest EVOLVEpro uses (deterministic, random_state=1 -> identical y_pred) on
your cached embeddings + measured labels, then ADDS the two uncertainty signals that
EVOLVEpro leaves empty for candidates:

  - y_std      : RF per-tree disagreement  = np.std([t.predict(X) for t in rf.estimators_], 0)
  - dist_metric: distance to nearest measured variant in embedding space (OOD signal)

and writes an enriched candidate table + UCB-ranked pick lists so you can compare
Top-N vs UCB selection for the NEXT round WITHOUT re-running EVOLVEpro.

Usage:
  python isps_sigma_ucb.py \
      --embeddings PtIspS_single_mutants_esm2_t33_650M_UR50D.csv \
      --labels     isps_round1.xlsx \
      --variant-col Variant --activity-col activity \
      --batch 95 --beta 1.0 --out df_test_with_sigma.csv

Notes:
  * --embeddings: CSV indexed by variant id (first column), 1280 feature columns
    for ESM2-650M. Must contain BOTH measured and unmeasured variants.
  * --labels: CSV or XLSX with a variant-id column and a numeric activity column,
    listing the MEASURED variants only (defines the train set).
  * Variant-id strings in labels must match the embedding index exactly.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from sklearn.ensemble import RandomForestRegressor

# Exact EVOLVEpro randomforest hyperparameters (evolvepro/src/model.py:198-216).
RF_KWARGS = dict(
    n_estimators=100, criterion="friedman_mse", max_depth=None,
    min_samples_split=2, min_samples_leaf=1, min_weight_fraction_leaf=0.0,
    max_features=1.0, max_leaf_nodes=None, min_impurity_decrease=0.0,
    bootstrap=True, oob_score=False, n_jobs=None, random_state=1, verbose=0,
    warm_start=False, ccp_alpha=0.0, max_samples=None,
)


def read_table(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--embeddings", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--variant-col", default="Variant")
    ap.add_argument("--activity-col", default="activity")
    ap.add_argument("--batch", type=int, default=95, help="next-round pick count")
    ap.add_argument("--beta", type=float, default=1.0, help="UCB exploration weight kappa")
    ap.add_argument("--out", default="df_test_with_sigma.csv")
    args = ap.parse_args(argv)

    emb = pd.read_csv(args.embeddings, index_col=0)
    emb.index = emb.index.astype(str)
    lab = read_table(args.labels)
    lab[args.variant_col] = lab[args.variant_col].astype(str)
    lab = lab.dropna(subset=[args.activity_col])

    train_ids = [v for v in lab[args.variant_col] if v in emb.index]
    missing = sorted(set(lab[args.variant_col]) - set(emb.index))
    if missing:
        print(f"[warn] {len(missing)} labelled variants absent from embeddings "
              f"(id mismatch?), e.g. {missing[:5]}", file=sys.stderr)
    if not train_ids:
        print("[error] no labelled variant matches the embedding index. "
              "Check --variant-col formatting (e.g. '34F' vs 'Y34F').", file=sys.stderr)
        return 2

    y = lab.set_index(args.variant_col)[args.activity_col].astype(float)
    X_tr = emb.loc[train_ids].to_numpy(float)
    y_tr = y.loc[train_ids].to_numpy(float)
    test_ids = [v for v in emb.index if v not in set(train_ids)]
    X_te = emb.loc[test_ids].to_numpy(float)

    print(f"[info] train(measured)={len(train_ids)}  test(candidates)={len(test_ids)}  "
          f"dim={X_tr.shape[1]}", file=sys.stderr)

    rf = RandomForestRegressor(**RF_KWARGS).fit(X_tr, y_tr)
    per_tree = np.stack([t.predict(X_te) for t in rf.estimators_])  # (100, n_test)
    y_pred = per_tree.mean(0)
    y_std = per_tree.std(0)
    dist_metric = cdist(X_te, X_tr, metric="euclidean").min(axis=1)

    # normalise sigma signals to the y_pred scale for an interpretable UCB blend
    def z(a):
        s = a.std()
        return (a - a.mean()) / s if s > 0 else np.zeros_like(a)

    yp_s = y_pred.std() or 1.0
    ucb_treestd = y_pred + args.beta * z(y_std) * yp_s
    ucb_dist = y_pred + args.beta * z(dist_metric) * yp_s

    out = pd.DataFrame({
        "variant": test_ids, "y_pred": y_pred, "y_std": y_std,
        "dist_metric": dist_metric,
        "ucb_treestd": ucb_treestd, "ucb_dist": ucb_dist,
    }).sort_values("y_pred", ascending=False).reset_index(drop=True)
    out.to_csv(args.out, index=False)
    print(f"[info] wrote {args.out} ({len(out)} candidates)", file=sys.stderr)

    b = args.batch
    topn = set(out.nlargest(b, "y_pred")["variant"])
    ucb_t = set(out.nlargest(b, "ucb_treestd")["variant"])
    ucb_d = set(out.nlargest(b, "ucb_dist")["variant"])
    print(f"\n=== next-round pick comparison (batch={b}, beta={args.beta}) ===")
    print(f"Top-N vs UCB(tree-std): overlap {len(topn & ucb_t)}/{b}  "
          f"-> {b - len(topn & ucb_t)} different picks")
    print(f"Top-N vs UCB(dist)    : overlap {len(topn & ucb_d)}/{b}  "
          f"-> {b - len(topn & ucb_d)} different picks")
    print("\nIf overlap ~= batch, UCB changes little (surrogate already covers the pool).")
    print("If overlap is much smaller, UCB diverts budget to uncertain candidates;")
    print("whether that helps is decided by the retrospective AL sim on labelled data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
