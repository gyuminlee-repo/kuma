"""Faithful sklearn-RF proxy for EVOLVEpro's randomforest surrogate (plan O3 / Gate G1(c)).

EVOLVEpro ``top_layer(regression_type='randomforest')`` instantiates a plain
sklearn ``RandomForestRegressor`` with these exact hyperparameters and fits it on
raw mean-pooled ESM-2 embeddings (no scaling, no PCA), target = raw measured
activity, then ranks the unlabeled pool by predicted value. This module replicates
that regressor exactly so we can cross-check the real ``top_layer`` y_pred ordering
(Gate G1(c): Spearman >= 0.99). It is a CROSS-CHECK / ceiling contingency only —
never the primary regressor (spec Non-Goal).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

# Exact EVOLVEpro randomforest hyperparameters (evolvepro/src/model.py:198-211).
RF_KWARGS = dict(
    n_estimators=100,
    criterion="friedman_mse",
    max_depth=None,
    min_samples_split=2,
    min_samples_leaf=1,
    max_features=1.0,
    bootstrap=True,
    random_state=1,
)


def proxy_surrogate(
    embeddings_df: pd.DataFrame, labels_pd: pd.DataFrame, n_revealed_rounds: int
) -> dict[str, float]:
    """Drop-in for loop._evolvepro_surrogate using a faithful sklearn RF.

    Trains on rows whose ``iteration`` is in range(n_revealed_rounds); predicts the
    rows with NaN iteration (the un-revealed pool). Returns {pool_variant: y_pred}.
    """
    from sklearn.ensemble import RandomForestRegressor

    emb = embeddings_df.reset_index(drop=True)
    lab = labels_pd.reset_index(drop=True)
    it = lab["iteration"]
    train_idx = it[it.isin(list(range(n_revealed_rounds)))].index.to_numpy()
    pool_idx = it[it.isna()].index.to_numpy()
    X_train = emb.iloc[train_idx].to_numpy(dtype=float)
    y_train = lab.iloc[train_idx]["activity"].to_numpy(dtype=float)
    X_pool = emb.iloc[pool_idx].to_numpy(dtype=float)

    model = RandomForestRegressor(**RF_KWARGS)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_pool)
    pool_variants = lab.iloc[pool_idx]["variant"].astype(str).tolist()
    return dict(zip(pool_variants, (float(v) for v in y_pred), strict=True))


def spearman(a: Sequence[float], b: Sequence[float]) -> float:
    """Spearman rank correlation between two equally-ordered score sequences."""
    from scipy.stats import spearmanr

    if len(a) < 2:
        return 1.0
    rho = spearmanr(np.asarray(a, dtype=float), np.asarray(b, dtype=float)).correlation
    return float(rho) if np.isfinite(rho) else 0.0


def proxy_vs_real_spearman(
    embeddings_df: pd.DataFrame, labels_pd: pd.DataFrame, n_revealed_rounds: int
) -> float:
    """Gate G1(c): Spearman of proxy vs real top_layer y_pred over the same pool.

    Both use identical embeddings, train set, and random_state=1, so a faithful
    proxy must reach Spearman >= 0.99; lower indicates a plumbing bug.
    """
    from evolvepro.src.model import top_layer

    proxy = proxy_surrogate(embeddings_df, labels_pd, n_revealed_rounds)
    out = top_layer(
        iter_train=list(range(n_revealed_rounds)),
        iter_test=None,
        embeddings_pd=embeddings_df,
        labels_pd=labels_pd,
        measured_var="activity",
        regression_type="randomforest",
        experimental=True,
    )
    if out is None:
        raise RuntimeError("top_layer returned None (alignment)")
    _tr, df_test, _all = out
    real = dict(zip(df_test["variant"].astype(str), df_test["y_pred"].astype(float), strict=True))
    common = [v for v in proxy if v in real]
    return spearman([proxy[v] for v in common], [real[v] for v in common])
