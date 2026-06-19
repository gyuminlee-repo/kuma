"""Round-2+ acquisition functions — the benchmark's decisive factor (plan Phase A/B).

The KURO justification question lives entirely in round-2+ (a surrogate is now
trained on revealed labels). Each arm selects ``n`` items from the un-revealed
candidate pool given the surrogate's predictions over that pool:

- ``topn``      : greedy exploitation — sort by surrogate mean, descending.
- ``random``    : floor.
- ``ucb``       : mean + kappa * std, where std is the RandomForest per-tree
                  predictive std (``estimators_``). kappa grid {0.5, 1.0, 2.0},
                  headline 1.0.
- ``thompson``  : per-point posterior sample drawn from the per-tree predictions.
- ``embdiv``    : greedy maximin diversity in the surrogate's FEATURE space
                  (Euclidean), tie-broken by mean — a rule-level diversity control
                  aligned to the surrogate substrate.
- ``sigma_kuro``: KURO's REAL sigma-adaptive schedule via
                  ``kuma_core.kuro.evolvepro.sigma_adaptive_params``. The
                  exploration pool fraction (K = K_max*(1-rho)) and the
                  position-entropy weight (0.30 -> 0.15) DECREASE as cumulative
                  revealed data grows; selection is maximin position diversity
                  blended with per-position entropy, tie-broken by mean. This is
                  the deployed round-2+ KURO, NOT a static entropy_weight=0.3
                  strawman.

UCB/Thompson variance is computed from ``RandomForestRegressor.estimators_``
because EVOLVEpro ``top_layer`` exposes ``std_predictions`` as a hardcoded
``np.zeros`` placeholder (verified). They are therefore labelled COUNTERFACTUAL
baselines: what EVOLVEpro *could* do if it surfaced its own tree variance.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

ACQUISITION_ARMS = ("topn", "random", "ucb", "thompson", "embdiv", "sigma_kuro")
UCB_KAPPA_GRID = (0.5, 1.0, 2.0)
DEFAULT_UCB_KAPPA = 1.0


# ---------------------------------------------------------------------------
# RandomForest predictive distribution (tree variance) — UCB / Thompson source
# ---------------------------------------------------------------------------
def rf_per_tree_predictions(model, X: np.ndarray) -> np.ndarray:
    """Stack per-tree predictions for a fitted RandomForestRegressor -> (T, N)."""
    X = np.asarray(X, dtype=float)
    return np.stack([est.predict(X) for est in model.estimators_])


def rf_mean_std(model, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-point mean and std across the forest's trees (real predictive variance)."""
    per_tree = rf_per_tree_predictions(model, X)
    return per_tree.mean(axis=0), per_tree.std(axis=0)


def rf_thompson_sample(model, X: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One posterior draw per point: sample a random tree's prediction per point.

    Sampling per point from the empirical per-tree distribution is a Thompson
    posterior sample over the RF's implied function distribution.
    """
    per_tree = rf_per_tree_predictions(model, X)  # (T, N)
    t, num = per_tree.shape
    idx = rng.integers(0, t, size=num)
    return per_tree[idx, np.arange(num)]


# ---------------------------------------------------------------------------
# Generic greedy maximin (shared by embdiv and sigma_kuro diversity)
# ---------------------------------------------------------------------------
def _greedy_maximin(
    cand: Sequence[int],
    distance: Callable[[int, int], float],
    anchor: Sequence[int],
    n: int,
    tiebreak: np.ndarray,
    *,
    entropy: np.ndarray | None = None,
    entropy_weight: float = 0.0,
) -> list[int]:
    """Greedily pick ``n`` candidates maximizing min-distance to the chosen+anchor set.

    Score = (1 - entropy_weight) * min_distance(normalized) + entropy_weight *
    entropy[cand] (when provided), tie-broken by ``tiebreak`` (surrogate mean).
    ``distance(i, j)`` operates on candidate/anchor indices in the SAME index space.
    """
    remaining = list(cand)
    chosen: list[int] = []
    ref = list(anchor)
    # normalize entropy to [0,1] for a comparable blend
    if entropy is not None and entropy.size:
        e = entropy.astype(float)
        rng_span = float(e.max() - e.min())
        e_norm = (e - e.min()) / rng_span if rng_span > 1e-12 else np.zeros_like(e)
    else:
        e_norm = None
    while remaining and len(chosen) < n:
        ref_set = ref + chosen
        best_i = None
        best_key = None
        # precompute a distance normalizer (max possible) lazily via observed max
        dists = {}
        for i in remaining:
            d = min((distance(i, j) for j in ref_set), default=0.0) if ref_set else 0.0
            dists[i] = d
        dmax = max(dists.values()) if dists else 1.0
        dmax = dmax if dmax > 1e-12 else 1.0
        for i in remaining:
            div = dists[i] / dmax
            if e_norm is not None and entropy_weight > 0.0:
                score = (1.0 - entropy_weight) * div + entropy_weight * float(e_norm[i])
            else:
                score = div
            key = (score, float(tiebreak[i]))
            if best_key is None or key > best_key:
                best_key = key
                best_i = i
        chosen.append(best_i)
        remaining.remove(best_i)
    return chosen


def _position_entropy(positions: Sequence[tuple[int, ...]], n_alleles: int) -> np.ndarray:
    """Per-candidate exploration bonus from the pool's per-site allele distribution.

    For each site the Shannon entropy of the allele frequencies measures how much the
    candidate pool DISAGREES there (KURO ``_position_entropy`` intent). A candidate's
    bonus is the entropy-weighted MINORITY-allele content: mean over sites of
    ``site_entropy[s] * (1 - freq[s, allele_of_candidate])``. Candidates carrying rare
    alleles at uncertain sites score higher, so the value VARIES per candidate and
    ``entropy_weight`` genuinely shifts the ranking (not a constant)."""
    if not positions:
        return np.zeros(0)
    arr = np.asarray(positions, dtype=int)  # (P, n_sites)
    n_sites = arr.shape[1]
    site_entropy = np.zeros(n_sites)
    freq = np.zeros((n_sites, n_alleles))
    for s in range(n_sites):
        counts = np.bincount(arr[:, s], minlength=n_alleles).astype(float)
        total = counts.sum()
        probs = counts / total if total > 0 else counts
        freq[s] = probs
        nz = probs[probs > 0]
        site_entropy[s] = float(-(nz * np.log2(nz)).sum()) if nz.size else 0.0
    # per-candidate: freq of each candidate's own allele at each site -> (P, n_sites)
    cand_freq = freq[np.arange(n_sites)[None, :], arr]
    return (site_entropy[None, :] * (1.0 - cand_freq)).mean(axis=1)


# ---------------------------------------------------------------------------
# Arm dispatch
# ---------------------------------------------------------------------------
def select_indices(
    arm: str,
    *,
    mean: Sequence[float],
    n: int,
    rng: np.random.Generator,
    std: Sequence[float] | None = None,
    sample: Sequence[float] | None = None,
    features: np.ndarray | None = None,
    anchor_features: np.ndarray | None = None,
    positions: Sequence[tuple[int, ...]] | None = None,
    anchor_positions: Sequence[tuple[int, ...]] | None = None,
    n_alleles: int = 2,
    evolvepro_round: int = 1,
    round_size: int | None = None,
    kappa: float = DEFAULT_UCB_KAPPA,
) -> list[int]:
    """Return indices (into the pool) selected by ``arm``.

    ``mean`` is the surrogate mean over the pool. ``std`` (UCB) and ``sample``
    (Thompson) are the RF per-tree std and one posterior draw. ``features`` are the
    surrogate input vectors for embdiv maximin. ``positions`` are per-candidate
    genotype/position signatures for sigma_kuro diversity + entropy.
    """
    m = np.asarray(mean, dtype=float)
    p = len(m)
    k = min(n, p)
    if k <= 0:
        return []

    if arm == "random":
        return [int(i) for i in rng.permutation(p)[:k]]

    if arm == "topn":
        return [int(i) for i in np.argsort(-m)[:k]]

    if arm == "ucb":
        if std is None:
            raise ValueError("ucb requires std (RF per-tree std)")
        s = np.asarray(std, dtype=float)
        return [int(i) for i in np.argsort(-(m + kappa * s))[:k]]

    if arm == "thompson":
        if sample is None:
            raise ValueError("thompson requires a posterior sample array")
        sm = np.asarray(sample, dtype=float)
        return [int(i) for i in np.argsort(-sm)[:k]]

    if arm == "embdiv":
        if features is None:
            raise ValueError("embdiv requires features")
        feats = np.asarray(features, dtype=float)
        anc = (
            np.asarray(anchor_features, dtype=float)
            if anchor_features is not None and len(anchor_features)
            else np.zeros((0, feats.shape[1]))
        )

        return _maximin_with_anchor(feats, anc, m, k)

    if arm == "sigma_kuro":
        if positions is None:
            raise ValueError("sigma_kuro requires positions")
        rsize = round_size if round_size is not None else k
        from kuma_core.kuro.evolvepro import sigma_adaptive_params

        k_explore, entropy_weight = sigma_adaptive_params(int(evolvepro_round), int(rsize))
        # exploration pool: larger early (high k_explore), shrinking with data.
        pool_size = min(p, max(k, int(round(k * (1.0 + 2.0 * k_explore)))))
        top_pool = list(np.argsort(-m)[:pool_size])
        pos = [tuple(positions[i]) for i in top_pool]
        ent = _position_entropy(pos, n_alleles)
        anc_pos = [tuple(x) for x in (anchor_positions or [])]

        def ham(i_local: int, j_local: int) -> float:
            a = pos[i_local]
            if j_local < len(anc_pos):
                b = anc_pos[j_local]
            else:
                b = pos[j_local - len(anc_pos)]
            return float(sum(1 for x, y in zip(a, b, strict=True) if x != y))

        tiebreak = np.array([m[i] for i in top_pool], dtype=float)
        local_anchor = list(range(len(anc_pos)))
        chosen_local = _greedy_maximin(
            list(range(len(top_pool))),
            ham,
            local_anchor,
            k,
            tiebreak,
            entropy=ent,
            entropy_weight=entropy_weight,
        )
        return [int(top_pool[c]) for c in chosen_local]

    raise ValueError(f"unknown acquisition arm: {arm}")


def _argmax_tiebreak(score: np.ndarray, tiebreak: np.ndarray, chosen_mask: np.ndarray) -> int:
    """Index of max ``score`` (ignoring chosen), ties broken by highest ``tiebreak``."""
    s = np.where(chosen_mask, -np.inf, score)
    mx = float(s.max())
    cand = np.flatnonzero(s >= mx - 1e-12)
    if cand.size == 1:
        return int(cand[0])
    return int(cand[int(np.argmax(tiebreak[cand]))])


def _maximin_with_anchor(
    feats: np.ndarray, anchor: np.ndarray, tiebreak: np.ndarray, n: int
) -> list[int]:
    """Vectorized greedy maximin (farthest-point) in Euclidean feature space.

    Maintains a running per-pool min-distance to the chosen+anchor set and updates it
    incrementally after each pick — O(n * pool * dim) instead of O(n * pool^2)."""
    feats = np.asarray(feats, dtype=float)
    p = len(feats)
    k = min(n, p)
    if k <= 0:
        return []
    tb = np.asarray(tiebreak, dtype=float)
    if anchor is not None and len(anchor):
        anc = np.asarray(anchor, dtype=float)
        d = np.linalg.norm(feats[:, None, :] - anc[None, :, :], axis=2)
        min_dist = d.min(axis=1)
    else:
        min_dist = np.full(p, np.inf)
    chosen: list[int] = []
    chosen_mask = np.zeros(p, dtype=bool)
    for _ in range(k):
        best = _argmax_tiebreak(min_dist, tb, chosen_mask)
        chosen.append(best)
        chosen_mask[best] = True
        dnew = np.linalg.norm(feats - feats[best], axis=1)
        min_dist = np.minimum(min_dist, dnew)
    return chosen