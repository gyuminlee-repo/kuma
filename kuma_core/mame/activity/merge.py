"""Replicate merging with authoritative-priority strategy.

v0.3 Phase B-1.
Spec: notes/architecture/2026-05-06-v0.3-phase-ab-interfaces.md §3-1
"""

from __future__ import annotations

import logging

from .models import MergeReplicatesStats, Variant

logger = logging.getLogger(__name__)


def merge_replicates_priority(
    authoritative: dict[Variant, list[float]],
    fallback: dict[Variant, list[float]],
    *,
    mismatch_threshold: float = 0.1,
) -> tuple[dict[Variant, float], MergeReplicatesStats]:
    """Merge replicate measurements preferring authoritative source.

    Rules:
    - If a Variant is in *authoritative*: use mean(authoritative[v]).
    - If a Variant is only in *fallback*: use mean(fallback[v]).
    - If in both: use authoritative mean; flag in mismatched when
      |mean_auth - mean_fall| > mismatch_threshold.
    - Replicate count is variable (list length 1..n); no magic numbers.

    Args:
        authoritative: Re-measurement data. dict[Variant, list[float]].
        fallback:       Primary / earlier measurement data.
        mismatch_threshold: Absolute difference threshold for mismatch flag.

    Returns:
        (merged, stats) where merged maps Variant → single float mean.

    Raises:
        ValueError: Any value list (auth or fallback) that is empty.
    """
    # Validate all lists up-front (anti-fallback: fail fast with context).
    for variant, values in authoritative.items():
        if not values:
            raise ValueError(
                f"authoritative[{variant!r}] is an empty list; "
                "at least one replicate value is required"
            )
    for variant, values in fallback.items():
        if not values:
            raise ValueError(
                f"fallback[{variant!r}] is an empty list; "
                "at least one replicate value is required"
            )

    merged: dict[Variant, float] = {}
    mismatched: list[Variant] = []

    # All Variants present in either dict.
    all_variants: set[Variant] = set(authoritative) | set(fallback)

    for variant in all_variants:
        if variant in authoritative:
            mean_auth = _mean(authoritative[variant])
            merged[variant] = mean_auth
            if variant in fallback:
                mean_fall = _mean(fallback[variant])
                diff = abs(mean_auth - mean_fall)
                if diff > mismatch_threshold:
                    mismatched.append(variant)
                    logger.warning(
                        "Replicate mismatch for %r: auth_mean=%.6f, "
                        "fall_mean=%.6f, diff=%.6f > threshold=%.6f",
                        variant,
                        mean_auth,
                        mean_fall,
                        diff,
                        mismatch_threshold,
                    )
        else:
            # fallback only
            merged[variant] = _mean(fallback[variant])

    stats = MergeReplicatesStats(
        authoritative_count=len(authoritative),
        fallback_count=len(fallback),
        merged_count=len(merged),
        mismatched=mismatched,
    )
    return merged, stats


def _mean(values: list[float]) -> float:
    """Arithmetic mean. Caller guarantees non-empty list."""
    return sum(values) / len(values)
