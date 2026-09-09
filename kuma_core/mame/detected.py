"""Run metric helpers over the designed-mutant set.

Additive overlay over the existing 8-class verdict system. This module does NOT
change ``classify_verdict``, the ``VerdictClass`` set, or ``pick_best_replicate``.

Two run-level metrics live here and they answer different questions:

- :func:`compute_success_rate` counts ``PASS`` only. This is the reported run
  success figure. The pick list exports ``PASS`` alone
  (``kuma_core.mame.export.janus_mapping.DEFAULT_INCLUDE_VERDICTS``), so the
  fraction of designed mutants an operator can actually carry forward is the
  ``PASS`` fraction and nothing wider.
- :func:`compute_recovery` counts ``PASS`` or ``AMBIGUOUS``. This is a
  supporting figure describing how many designed variants were reproduced at
  all, including the ones a replicate disagreement left ambiguous.

``DETECTED_CLASSES`` is the ``PASS+AMBIGUOUS`` set that :func:`compute_recovery`
and the pick-priority ordering read. It is NOT the reported run success figure:
anything presenting a headline percentage takes it from
:func:`compute_success_rate`. Callers that render both must label which verdict
set each one counts, because the two share a denominator and an unlabelled pair
invites quoting the higher number.

Semantics (locked by deep-interview spec ``deep-interview-mame-detected-recovery``):

- A well is **detected** iff its verdict is ``PASS`` or ``AMBIGUOUS``. Both
  guarantee every expected mutation for that well was matched (with correct MT),
  so the intended variant was reproduced. The other six classes are NOT detected.
  ``detected`` is independent of ``ReplicateResult.failed`` (which is also False
  for LOWDEPTH / fallback picks).
- A designed mutant is **recovered** iff at least one of its replicate plate
  verdicts is detected (OR across replicate native barcodes). It is **passed**
  iff at least one of them is ``PASS``, by the same OR.
- Both rates divide by ALL designed mutants. Missing or zero-read designed
  mutants (no ``ReplicateResult``) count in the denominator only. Non-designed
  groups (a ``WT`` control, ``UNKNOWN_*`` heuristic groups) are excluded from
  both numerator and denominator via designed-set membership. The shared
  denominator is computed once in :func:`_count_designed`, which both public
  functions call, so the two rates cannot drift apart.
- When the designed-mutant set is unavailable (e.g. an export/reload path that
  never cached it), both functions return ``None`` so callers render ``n/a``
  instead of a misleading ``0%``.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass

from kuma_core.mame.models import ReplicateResult, VerdictClass

# Verdict classes that count as a reproduced (detected) expected mutation.
# Read by compute_recovery and by pick priority. Not the reported success figure.
DETECTED_CLASSES: frozenset[VerdictClass] = frozenset(
    {VerdictClass.PASS, VerdictClass.AMBIGUOUS}
)


def is_detected(verdict: VerdictClass) -> bool:
    """True iff the well verdict reproduces its expected mutation (PASS/AMBIGUOUS)."""
    return verdict in DETECTED_CLASSES


def replicate_is_recovered(replicate: ReplicateResult) -> bool:
    """True iff any replicate plate verdict for this mutant is detected (OR across NBs)."""
    return any(is_detected(vr.verdict) for vr in replicate.plate_verdicts.values())


def replicate_is_passed(replicate: ReplicateResult) -> bool:
    """True iff any replicate plate verdict for this mutant is PASS (OR across NBs).

    Narrower than :func:`replicate_is_recovered` by exactly the AMBIGUOUS class.
    """
    return any(
        vr.verdict is VerdictClass.PASS for vr in replicate.plate_verdicts.values()
    )


@dataclass(frozen=True)
class RecoveryMetrics:
    """Run-level recovery over the designed-mutant set, counting PASS+AMBIGUOUS."""

    recovered_mutants: int
    total_mutants: int
    recovery_rate: float  # recovered / total; 0.0 when total == 0


@dataclass(frozen=True)
class SuccessMetrics:
    """Run-level success over the designed-mutant set, counting PASS only.

    A separate dataclass rather than a reuse of :class:`RecoveryMetrics`, and
    rather than one merged type with a generic ``numerator`` field, because the
    field name is the only place the counted verdict set is written down at a
    call site. ``health.py``, ``report/builder.py`` and ``export/excel_writer.py``
    read these by attribute name and copy them into wire fields; a shared
    ``numerator`` would let a success figure be stored under a recovery name
    without anything failing. The denominator is shared in code
    (:func:`_count_designed`) rather than in a shared type.
    """

    passed_mutants: int
    total_mutants: int
    success_rate: float  # passed / total; 0.0 when total == 0


def designed_mutant_ids(expected_mutations: Iterable) -> frozenset[str]:
    """Distinct designed ``mutant_id`` set from ``read_expected_mutations`` rows.

    A single ``mutant_id`` may span multiple expected rows (combinatorial labels);
    the set deduplicates so the denominator is per-mutant, not per-row.
    """
    return frozenset(m.mutant_id for m in expected_mutations)


def _count_designed(
    replicates: Iterable[ReplicateResult],
    designed_ids: Collection[str] | None,
    predicate: Callable[[ReplicateResult], bool],
) -> tuple[int, int] | None:
    """Shared numerator/denominator engine for every designed-set rate.

    Returns ``(hits, total)`` where ``total`` is the size of the designed set and
    ``hits`` counts distinct designed mutants with at least one replicate
    satisfying ``predicate``. Returns ``None`` when ``designed_ids`` is ``None``.

    Both public rate functions route through here so the denominator and the
    designed-set membership filter are one piece of code rather than two copies.
    """
    if designed_ids is None:
        return None
    designed = frozenset(designed_ids)
    hit_ids = {
        rr.mutant_id
        for rr in replicates
        if rr.mutant_id in designed and predicate(rr)
    }
    return len(hit_ids), len(designed)


def compute_recovery(
    replicates: Iterable[ReplicateResult],
    designed_ids: Collection[str] | None,
) -> RecoveryMetrics | None:
    """Compute run-level recovery (PASS+AMBIGUOUS) over the designed-mutant set.

    ``designed_ids`` is the distinct designed ``mutant_id`` set (see
    :func:`designed_mutant_ids`). Returns ``None`` when it is ``None`` (designed
    set unavailable, callers render ``n/a``). Supporting figure: the reported run
    success figure is :func:`compute_success_rate`.
    """
    counted = _count_designed(replicates, designed_ids, replicate_is_recovered)
    if counted is None:
        return None
    recovered, total = counted
    return RecoveryMetrics(
        recovered_mutants=recovered,
        total_mutants=total,
        recovery_rate=recovered / total if total else 0.0,
    )


def compute_success_rate(
    replicates: Iterable[ReplicateResult],
    designed_ids: Collection[str] | None,
) -> SuccessMetrics | None:
    """Compute run-level success (PASS only) over the designed-mutant set.

    Same denominator, same designed-set membership rule and same ``None``
    behaviour as :func:`compute_recovery`, enforced by both calling
    :func:`_count_designed`. The numerator is narrower by the AMBIGUOUS class,
    so this rate is never above the recovery rate on the same inputs.
    """
    counted = _count_designed(replicates, designed_ids, replicate_is_passed)
    if counted is None:
        return None
    passed, total = counted
    return SuccessMetrics(
        passed_mutants=passed,
        total_mutants=total,
        success_rate=passed / total if total else 0.0,
    )
