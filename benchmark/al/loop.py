"""Active-learning campaign loop (plan Phase 1 core).

One campaign = one (assay, arm, cold-start signal, N-condition, seed) cell:

    round 0  : select n by COLD-START score (no oracle) -> reveal true labels
    round r>=1: fit EVOLVEpro surrogate on labels revealed so far -> predict the
                un-revealed pool -> select n by the arm's policy on y_pred ->
                reveal true labels
    repeat for K rounds.

The surrogate is the REAL EVOLVEpro ``top_layer`` (regression_type='randomforest',
experimental=True). It is injected so unit tests can substitute a stub, but the
benchmark always uses the real one. True labels (the DMS oracle) are read ONLY to
reveal the selected batch and to compute metrics — never to rank candidates
(enforced structurally: round-0 ranking sees only the cold-start score, and the
surrogate is trained only on already-revealed labels).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from al import arms


@dataclass
class RoundRecord:
    round_idx: int
    selected: list[str]
    selected_fitness: list[float]
    cumulative_best: float
    n_revealed: int


@dataclass
class CampaignResult:
    arm: str
    seed: int
    rounds: list[RoundRecord] = field(default_factory=list)
    revealed_order: list[str] = field(default_factory=list)

    @property
    def cumulative_best_trajectory(self) -> list[float]:
        return [r.cumulative_best for r in self.rounds]


def _evolvepro_surrogate(
    embeddings_df: pd.DataFrame, labels_pd: pd.DataFrame, n_revealed_rounds: int
) -> dict[str, float]:
    """Fit real EVOLVEpro top_layer on revealed rounds; return {pool_variant: y_pred}."""
    from evolvepro.src.model import top_layer  # lazy: only when surrogate is needed

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
        raise RuntimeError("top_layer returned None (embeddings/labels misaligned)")
    _this_round, df_test, _df_all = out
    return dict(zip(df_test["variant"].astype(str), df_test["y_pred"].astype(float), strict=True))


def run_campaign(
    arm: str,
    candidates: Sequence[str],
    embeddings_df: pd.DataFrame,
    oracle: Mapping[str, float],
    cold_start_score: Mapping[str, float],
    n: int,
    k_rounds: int,
    *,
    domains=None,
    seed: int = 0,
    surrogate_fn: Callable[[pd.DataFrame, pd.DataFrame, int], dict[str, float]] | None = None,
) -> CampaignResult:
    """Run one AL campaign. ``embeddings_df`` is indexed by variant (all candidates)."""
    candidates = [str(v) for v in candidates]
    missing_emb = [v for v in candidates if v not in embeddings_df.index]
    if missing_emb:
        raise ValueError(f"{len(missing_emb)} candidates missing embeddings (e.g. {missing_emb[:3]})")
    missing_lab = [v for v in candidates if v not in oracle]
    if missing_lab:
        raise ValueError(f"{len(missing_lab)} candidates missing oracle labels (e.g. {missing_lab[:3]})")

    surrogate_fn = surrogate_fn or _evolvepro_surrogate
    # Fix embedding/label row order once (top_layer requires identical order).
    emb = embeddings_df.loc[candidates]

    # iteration: round index a variant was revealed in; NaN = un-revealed pool.
    iteration: dict[str, float] = {v: float("nan") for v in candidates}
    result = CampaignResult(arm=arm, seed=seed)
    revealed: set[str] = set()
    best = float("-inf")

    for r in range(k_rounds):
        pool = [v for v in candidates if v not in revealed]
        if not pool:
            break
        if r == 0:
            score = cold_start_score
        else:
            labels_pd = _build_labels(candidates, oracle, iteration)
            score = surrogate_fn(emb, labels_pd, r)
            # surrogate scores only the pool; guard completeness
            missing = [v for v in pool if v not in score]
            if missing:
                raise RuntimeError(f"surrogate did not score {len(missing)} pool variants")
        picks = arms.select(
            arm, round_idx=r, candidates=pool, score=score, n=n, domains=domains, seed=seed + r
        )
        fits = [float(oracle[v]) for v in picks]
        for v in picks:
            iteration[v] = float(r)
            revealed.add(v)
        result.revealed_order.extend(picks)
        if fits:
            best = max(best, max(fits))
        result.rounds.append(
            RoundRecord(
                round_idx=r,
                selected=list(picks),
                selected_fitness=fits,
                cumulative_best=best,
                n_revealed=len(revealed),
            )
        )
    return result


def _build_labels(
    candidates: Sequence[str], oracle: Mapping[str, float], iteration: Mapping[str, float]
) -> pd.DataFrame:
    """labels_pd for top_layer: rows in `candidates` order; revealed rows carry activity."""
    revealed_acts = [oracle[v] for v in candidates if not np.isnan(iteration[v])]
    if revealed_acts:
        med = float(np.median(revealed_acts))
        lo, hi = float(np.min(revealed_acts)), float(np.max(revealed_acts))
        span = (hi - lo) or 1.0
    else:
        med, lo, span = 0.0, 0.0, 1.0
    rows = []
    for v in candidates:
        it = iteration[v]
        revealed = not np.isnan(it)
        act = float(oracle[v]) if revealed else float("nan")
        rows.append(
            {
                "variant": v,
                "activity": act,
                "iteration": it,
                "activity_scaled": ((act - lo) / span) if revealed else float("nan"),
                "activity_binary": (1 if (revealed and act > med) else (0 if revealed else float("nan"))),
            }
        )
    return pd.DataFrame(rows)
