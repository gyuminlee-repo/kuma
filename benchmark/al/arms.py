"""Selection-policy arms for the AL simulation (plan: 4 arms).

An arm decides, given the current candidate pool and a per-variant ranking score,
which `n` variants to select this round. Round-1 uses a cold-start score (no
oracle); rounds >= 2 use the EVOLVEpro surrogate's y_pred on revealed labels.

Arms (paired across a shared seed):
- ``topn``           Arm1: Top-N by score every round (the control).
- ``domain_r1only``  Arm2 (pivotal): domain-quota at round-1, Top-N afterwards.
- ``domain_every``   Arm3: domain-quota every round.
- ``random_r1``      Arm4: random round-1, Top-N afterwards (cold-start lower bound).

Domain-quota selection delegates to ``kuma_core.kuro.evolvepro.domain_aware_select``
(real InterPro/Pfam domains, not pseudo-segments).
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from al.firewall import topn_by_score

# domain_aware_select(rows, domains, top_n, strategy) -> (selected_rows, stats)
# pareto_diversity_select(rows, top_n, entropy_weight=, ca_coords=, ...) -> (selected, replaced)
try:  # import is cheap; kept guarded so unit tests can run without the kuro pkg path
    from kuma_core.kuro.evolvepro import domain_aware_select, pareto_diversity_select
except Exception:  # pragma: no cover
    domain_aware_select = None  # type: ignore[assignment]
    pareto_diversity_select = None  # type: ignore[assignment]

# Arms. The PI-intended diversity is `pareto_*` (structure/uncertainty dispersion to
# escape local minima), distinct from the InterPro sequence-position `domain_*` quota.
ARMS = ("topn", "domain_r1only", "domain_every", "pareto_r1only", "pareto_every", "random_r1")

# entropy_weight for the Pareto arm: MODIFY-style uncertainty-guided exploration
# ("helps escape local optima in the fitness landscape" per pareto_diversity_select).
PARETO_ENTROPY_WEIGHT = 0.3


def _domain_select(
    candidates: Sequence[str], score: Mapping[str, float], n: int, domains
) -> list[str]:
    if domain_aware_select is None:
        raise RuntimeError("kuma_core.kuro.evolvepro.domain_aware_select unavailable")
    # domain_aware_select assumes rows are pre-sorted by score DESC (it picks
    # candidates[:quota] within each domain — see kuro/evolvepro.py:930). Pass
    # score-sorted rows with a deterministic tie-break so the quota picks the
    # top-by-score variants per domain, not arbitrary file order.
    rows = sorted(
        ((v, float(score[v])) for v in candidates), key=lambda r: (-r[1], r[0])
    )
    selected, _stats = domain_aware_select(rows, domains, n, strategy="equal")
    return [v for v, _ in selected]


def _random_select(candidates: Sequence[str], n: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    pool = list(candidates)
    rng.shuffle(pool)
    return pool[:n]


def _pareto_select(candidates: Sequence[str], score: Mapping[str, float], n: int) -> list[str]:
    """PI-intended diversity: MODIFY-style Pareto fitness-diversity (greedy maximin)
    with entropy-guided exploration to escape local minima. Rows pre-sorted DESC."""
    if pareto_diversity_select is None:
        raise RuntimeError("kuma_core.kuro.evolvepro.pareto_diversity_select unavailable")
    rows = sorted(
        ((v, float(score[v])) for v in candidates), key=lambda r: (-r[1], r[0])
    )
    selected, _replaced = pareto_diversity_select(
        rows, n, entropy_weight=PARETO_ENTROPY_WEIGHT
    )
    return [v for v, _ in selected]


def select(
    arm: str,
    *,
    round_idx: int,
    candidates: Sequence[str],
    score: Mapping[str, float],
    n: int,
    domains=None,
    seed: int = 0,
) -> list[str]:
    """Pick `n` variants from `candidates` per the arm's policy for this round.

    `round_idx` is 0-based; round 0 is the cold-start round. `score` is the
    cold-start score at round 0 and the surrogate y_pred at rounds >= 1.
    """
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; known {ARMS}")
    is_r1 = round_idx == 0
    n = min(n, len(candidates))

    if arm == "topn":
        return topn_by_score(candidates, score, n)
    if arm == "random_r1":
        return _random_select(candidates, n, seed) if is_r1 else topn_by_score(candidates, score, n)
    if arm == "domain_r1only":
        if domains is None:
            raise ValueError("domain_r1only requires domains")
        return _domain_select(candidates, score, n, domains) if is_r1 else topn_by_score(candidates, score, n)
    if arm == "domain_every":
        if domains is None:
            raise ValueError("domain_every requires domains")
        return _domain_select(candidates, score, n, domains)
    if arm == "pareto_r1only":
        return _pareto_select(candidates, score, n) if is_r1 else topn_by_score(candidates, score, n)
    if arm == "pareto_every":
        return _pareto_select(candidates, score, n)
    raise AssertionError("unreachable")
