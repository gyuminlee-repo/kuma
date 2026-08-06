"""Post-hoc well<->expected mapping sanity check.

Every other guard in this codebase inspects the *inputs* to a run (the
barcode workbook, the expected workbook, the primer plate sheets) before the
pipeline starts. None of them can catch a mapping that is internally
consistent but wrong end-to-end: a well_layout that was built from the wrong
(stale) expected-mutations file, or a plate that was re-numbered after the
layout was drawn. The pipeline classifies every well correctly against
whichever expected set it was told, and the result table renders like any
other run.

The one place that failure mode leaves a trace is the result itself: a well
observes a real amino-acid change, but that change belongs to a *different*
well's expected mutation, not its own. A single such well is unremarkable
(WRONG_AA happens). Many of them, systematically, is not, see the incident
this module was written for (2026-08, 288-well run, PASS 2 / WRONG_AA 239):

    wells with an observed AA change:            244
      matched their OWN well's expected:            0   (0.0%)
      matched a DIFFERENT well's expected:        241  (98.8%)
    2000x label-permutation null: mean 2.49/244 (1.0%), max 16 (6.6%)

That is not a chemistry failure; it is a labeling failure the pipeline has no
way to see from the inside, because nothing here reads well coordinates -
only expected/observed label sets scoped per well. This module makes the
signature explicit and checkable without depending on any real dataset.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Below this many comparable wells, a permuted subset of expected labels can
#: overlap by chance often enough that "high cross-match" stops being
#: informative (a 96-well campaign already clears this by more than 4x).  A
#: run this small is refused a verdict rather than risk a false alarm: a
#: missed real mislabeling is recoverable (the operator still has raw data),
#: a false "suspect" on a small, correct run is not something anyone can act
#: on without re-running the whole plate.
_MIN_WELLS_CONSIDERED = 24

#: A correctly labeled run should self-match on essentially every well that
#: shows a change at all (the 2026-08 incident: 0.0%). 5% leaves room for a
#: handful of genuine WRONG_AA/contamination wells without diluting the
#: signal the incident produced.
_SELF_RATE_MAX = 0.05

#: The incident's cross-match rate was 98.8%; the random-permutation null for
#: the same well count averaged 1.0% (max 6.6% across 2000 trials). 50% sits
#: an order of magnitude above the null ceiling, so it only fires on a
#: mapping that is wrong in a structured (not random) way.
_CROSS_RATE_MIN = 0.5


@dataclass(frozen=True, slots=True)
class WellObservation:
    """One well's expected/observed label sets, reduced to what this check needs.

    ``well_id`` only has to be a stable per-well key; it is never parsed or
    compared as a plate coordinate here, only used to tell a well apart from
    every other one in the same run. ``expected`` is that well's OWN expected
    AA-change labels (e.g. ``("V5F",)``, empty for a WT control well).
    ``observed`` is what translate/compare actually saw there (typically
    ``VerdictRecord.translated.observed_aa_changes``).
    """

    well_id: str
    expected: tuple[str, ...]
    observed: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MappingIntegrityReport:
    """Result of :func:`check_mapping_integrity`.

    Rates are precomputed here (not left for the caller to divide) so a
    caller cannot report a rate against the wrong denominator, and so a
    ``wells_considered == 0`` run cannot raise a ZeroDivisionError on its way
    to the frontend.
    """

    wells_considered: int
    self_match: int
    cross_match: int
    self_rate: float
    cross_rate: float
    suspect: bool


def check_mapping_integrity(
    observations: list[WellObservation],
    *,
    min_wells: int = _MIN_WELLS_CONSIDERED,
    self_rate_max: float = _SELF_RATE_MAX,
    cross_rate_min: float = _CROSS_RATE_MIN,
) -> MappingIntegrityReport:
    """Compare each well's observed changes against its own vs. others' expected sets.

    Only wells with at least one observed AA change are "considered", a well
    with no change carries no evidence either way, and folding it in would
    dilute both rates against wells that never had a chance to disagree.

    A considered well counts as ``self_match`` when any of its observed
    changes appears in its OWN expected set, and as ``cross_match`` when none
    do but at least one observed change appears in some OTHER well's expected
    set. The two counts are mutually exclusive by construction: a well that
    already explains its own observation is not evidence of a swap, even if
    the same label happens to also be a different well's expected mutation
    (duplicate designs land on more than one well routinely, see the module
    docstring). This is what keeps a high ``self_rate`` run safe from
    ``suspect`` even when duplicate expected labels push raw overlap counts
    up; the exclusivity, not the threshold, is what guards it.

    ``suspect`` requires all three: enough wells to trust the rate
    (``wells_considered >= min_wells``), a self-match rate at or below what a
    correctly labeled run should ever produce, and a cross-match rate an
    order of magnitude above what random label overlap alone explains (see
    the threshold constants' docstrings for the incident numbers behind
    them).
    """
    considered = [o for o in observations if o.observed]
    wells_considered = len(considered)

    self_match = 0
    cross_match = 0
    for o in considered:
        own = set(o.expected)
        seen = set(o.observed)
        if seen & own:
            self_match += 1
            continue
        if any(seen & set(other.expected) for other in considered if other is not o):
            cross_match += 1

    self_rate = self_match / wells_considered if wells_considered else 0.0
    cross_rate = cross_match / wells_considered if wells_considered else 0.0
    suspect = (
        wells_considered >= min_wells
        and self_rate <= self_rate_max
        and cross_rate >= cross_rate_min
    )
    return MappingIntegrityReport(
        wells_considered=wells_considered,
        self_match=self_match,
        cross_match=cross_match,
        self_rate=self_rate,
        cross_rate=cross_rate,
        suspect=suspect,
    )


def observations_from_verdicts(verdicts: list) -> list[WellObservation]:
    """Build :class:`WellObservation` rows from a finished run's ``VerdictRecord`` list.

    ``VerdictRecord.expected_mutations`` is already the per-well SCOPED
    expected set the verdict was classified against (the full designed-set
    fallback when no well_layout was supplied), so no separate
    well->expected map has to be threaded in here. A verdict whose
    custom_barcode does not resolve to a plate coordinate (non-R_F format,
    e.g. a non-combinatorial ingest mode) is skipped: this check is about
    well identity, and a record with no derivable well identity cannot be
    told apart from any other for the cross-match comparison.
    """
    from kuma_core.mame.export import seq_to_well
    from kuma_core.mame.export.excel_writer import _custom_barcode_to_seq

    observations: list[WellObservation] = []
    for vr in verdicts:
        seq = _custom_barcode_to_seq(vr.translated.barcode.custom_barcode)
        if seq is None:
            continue
        observations.append(
            WellObservation(
                well_id=seq_to_well(seq),
                expected=tuple(vr.expected_mutations),
                observed=tuple(vr.translated.observed_aa_changes),
            )
        )
    return observations


__all__ = [
    "MappingIntegrityReport",
    "WellObservation",
    "check_mapping_integrity",
    "observations_from_verdicts",
]
