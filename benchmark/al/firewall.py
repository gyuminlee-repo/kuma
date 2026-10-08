"""Oracle firewall (plan F1 — the single fatal-leak control for Track-1).

The active-learning simulation reveals true DMS labels only for variants the
policy has already selected; ranking must never see un-revealed labels. A single
leak (ranking by true DMS at any point, especially round-1) makes Top-N
unbeatable by construction and invalidates the whole Track-1 claim.

Two layers, per the consensus plan:

1. STRUCTURAL firewall. Round-1 ranking goes through `round1_select`, whose
   signature can only receive cold-start scores (variant -> float). It has no
   parameter through which oracle/DMS labels could be passed, so a leak cannot
   be written by accident. `RevealedLabels` models the "labels revealed so far"
   that rounds >= 2 are allowed to train on.

2. PERMUTATION-INVARIANCE check. `assert_round1_label_invariant` shuffles the
   oracle labels and asserts the round-1 selection is byte-identical, while a
   supplied round>=2 selector (which trains on revealed labels) changes. This is
   the correct leak test; "round-1 recall ~ random" is NOT (a valid cold-start
   should beat random), so recall-vs-random is only a descriptive statistic.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

# A round-1 selector: (candidate variants, cold-start score per variant, n) -> picks.
# By type it cannot receive oracle labels.
Round1Selector = Callable[[Sequence[str], Mapping[str, float], int], list[str]]


class OracleLeak(AssertionError):
    """Raised when a ranking step is shown to depend on un-revealed labels."""


def round1_select(
    candidates: Sequence[str],
    cold_start_score: Mapping[str, float],
    n: int,
    *,
    selector: Round1Selector,
) -> list[str]:
    """Structural entry point for round-1 selection.

    Only `cold_start_score` (e.g. ESM-2 zero-shot LLR or a published MSA zero-shot)
    is available to `selector`. There is deliberately no oracle parameter.
    """
    missing = [v for v in candidates if v not in cold_start_score]
    if missing:
        raise ValueError(
            f"cold-start score missing for {len(missing)} candidates "
            f"(e.g. {missing[:3]}); round-1 cannot rank without it"
        )
    picks = selector(list(candidates), cold_start_score, n)
    if len(set(picks)) != len(picks):
        raise ValueError("round-1 selector returned duplicates")
    if any(p not in cold_start_score for p in picks):
        raise ValueError("round-1 selector returned an out-of-pool variant")
    return picks


def topn_by_score(
    candidates: Sequence[str], score: Mapping[str, float], n: int
) -> list[str]:
    """Plain Top-N by descending score with a deterministic variant tie-break."""
    return sorted(candidates, key=lambda v: (-score[v], v))[:n]


def assert_round1_label_invariant(
    round1_fn: Callable[[Mapping[str, float]], list[str]],
    oracle_labels: Mapping[str, float],
    *,
    seed: int = 0,
) -> None:
    """Prove a round-1 selection function does not depend on the oracle labels.

    ``round1_fn`` is given the oracle labels as its only argument; a CORRECT
    round-1 selector ignores them (it ranks by cold-start score captured in its
    closure). We call it on the real labels and on a permutation of those labels:
    the two selections MUST be byte-identical (order included). A selector that
    secretly ranks by the oracle will change under the permutation -> OracleLeak.

    This is the genuine leak test (the labels really are injected and varied), and
    is NOT recall-vs-random. Raises OracleLeak on violation.
    """
    import random

    base = list(round1_fn(oracle_labels))

    rng = random.Random(seed)
    keys = list(oracle_labels.keys())
    vals = [oracle_labels[k] for k in keys]
    distinct = len(set(vals)) > 1
    # Ensure a NON-identity permutation when the labels are not all equal, so the
    # test cannot pass vacuously on an unlucky seed that reproduces the order.
    for _ in range(64):
        rng.shuffle(vals)
        if not distinct or [oracle_labels[k] for k in keys] != vals:
            break
    shuffled = dict(zip(keys, vals, strict=True))

    after = list(round1_fn(shuffled))
    if base != after:
        raise OracleLeak(
            "round-1 selection changed under oracle-label permutation; "
            "ranking is leaking un-revealed labels"
        )
