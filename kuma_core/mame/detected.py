"""재현검출(detected) / 재현율(recovery) metric helpers.

Additive overlay over the existing 8-class verdict system. This module does NOT
change ``classify_verdict``, the ``VerdictClass`` set, or ``pick_best_replicate``.

Semantics (locked by deep-interview spec ``deep-interview-mame-detected-recovery``):

- A well is **detected** iff its verdict is ``PASS`` or ``AMBIGUOUS`` — both
  guarantee every expected mutation for that well was matched (with correct MT),
  so the intended variant was reproduced. The other six classes are NOT detected.
  ``detected`` is independent of ``ReplicateResult.failed`` (which is also False
  for LOWDEPTH / fallback picks).
- A designed mutant is **recovered** iff at least one of its replicate plate
  verdicts is detected (OR across replicate native barcodes).
- **recovery_rate** = recovered designed mutants / ALL designed mutants. Missing
  or zero-read designed mutants (no ``ReplicateResult``) count in the denominator
  only. Non-designed groups (a ``WT`` control, ``UNKNOWN_*`` heuristic groups) are
  excluded from both numerator and denominator via designed-set membership.
- When the designed-mutant set is unavailable (e.g. an export/reload path that
  never cached it), :func:`compute_recovery` returns ``None`` so callers render
  ``n/a`` instead of a misleading ``0%``.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass

from kuma_core.mame.models import ReplicateResult, VerdictClass

# Verdict classes that count as a reproduced (detected) expected mutation.
DETECTED_CLASSES: frozenset[VerdictClass] = frozenset(
    {VerdictClass.PASS, VerdictClass.AMBIGUOUS}
)


def is_detected(verdict: VerdictClass) -> bool:
    """True iff the well verdict reproduces its expected mutation (PASS/AMBIGUOUS)."""
    return verdict in DETECTED_CLASSES


def replicate_is_recovered(replicate: ReplicateResult) -> bool:
    """True iff any replicate plate verdict for this mutant is detected (OR across NBs)."""
    return any(is_detected(vr.verdict) for vr in replicate.plate_verdicts.values())


@dataclass(frozen=True)
class RecoveryMetrics:
    """Run-level recovery (재현율) over the designed-mutant set."""

    recovered_mutants: int
    total_mutants: int
    recovery_rate: float  # recovered / total; 0.0 when total == 0


def designed_mutant_ids(expected_mutations: Iterable) -> frozenset[str]:
    """Distinct designed ``mutant_id`` set from ``read_expected_mutations`` rows.

    A single ``mutant_id`` may span multiple expected rows (combinatorial labels);
    the set deduplicates so the recovery denominator is per-mutant, not per-row.
    """
    return frozenset(m.mutant_id for m in expected_mutations)


def compute_recovery(
    replicates: Iterable[ReplicateResult],
    designed_ids: Collection[str] | None,
) -> RecoveryMetrics | None:
    """Compute run-level recovery over the designed-mutant set.

    ``designed_ids`` is the distinct designed ``mutant_id`` set (see
    :func:`designed_mutant_ids`). Returns ``None`` when it is ``None`` (designed
    set unavailable → callers render ``n/a``). The denominator is the full
    designed set; the numerator counts designed mutants with at least one detected
    replicate.
    """
    if designed_ids is None:
        return None
    designed = frozenset(designed_ids)
    total = len(designed)
    recovered_ids = {
        rr.mutant_id
        for rr in replicates
        if rr.mutant_id in designed and replicate_is_recovered(rr)
    }
    recovered = len(recovered_ids)
    rate = recovered / total if total else 0.0
    return RecoveryMetrics(
        recovered_mutants=recovered,
        total_mutants=total,
        recovery_rate=rate,
    )
