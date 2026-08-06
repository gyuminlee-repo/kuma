"""Synthetic tests for kuma_core.mame.qc.mapping_integrity.

Nothing here touches real run data; every scenario builds its own
WellObservation list so the suspect/not-suspect boundary is exercised
directly without depending on VerdictRecord plumbing.
"""

from __future__ import annotations

from kuma_core.mame.qc.mapping_integrity import (
    WellObservation,
    check_mapping_integrity,
)

_N_WELLS = 40  # comfortably above the default min_wells=24 threshold


def _correct_layout(n: int = _N_WELLS) -> list[WellObservation]:
    """Every well observes exactly its own expected substitution."""
    return [
        WellObservation(
            well_id=f"W{i:02d}",
            expected=(f"V{i}F",),
            observed=(f"V{i}F",),
        )
        for i in range(n)
    ]


def test_permuted_layout_is_suspect() -> None:
    """A well_layout rotated by one well is exactly the incident's shape."""
    n = _N_WELLS
    expected_by_well = [f"V{i}F" for i in range(n)]
    # well i observes the substitution that is actually well (i+1)'s expected --
    # never its own, always a neighbor's. Mirrors the 0% self / ~99% cross split
    # from the 2026-08 incident.
    observations = [
        WellObservation(
            well_id=f"W{i:02d}",
            expected=(expected_by_well[i],),
            observed=(expected_by_well[(i + 1) % n],),
        )
        for i in range(n)
    ]
    report = check_mapping_integrity(observations)
    assert report.wells_considered == n
    assert report.self_match == 0
    assert report.cross_match == n
    assert report.suspect is True


def test_correct_layout_is_not_suspect() -> None:
    report = check_mapping_integrity(_correct_layout())
    assert report.wells_considered == _N_WELLS
    assert report.self_match == _N_WELLS
    assert report.cross_match == 0
    assert report.suspect is False


def test_duplicate_designs_raise_cross_overlap_but_self_match_protects() -> None:
    """Real designs can repeat a substitution across wells (replicate mutants).

    That alone must not trip ``suspect``: as long as most wells still explain
    their own observation (self_match dominates), a modest amount of raw
    label overlap from duplicated designs is not evidence of a swap.
    """
    n = _N_WELLS
    observations = []
    for i in range(n):
        # Every 5th well shares its expected label with its neighbour --
        # a duplicate design placed on two wells -- but each well still
        # observes and matches its OWN expected label.
        label = f"V{i // 5}F"
        observations.append(
            WellObservation(well_id=f"W{i:02d}", expected=(label,), observed=(label,))
        )
    # Sprinkle in two genuinely mislabeled wells whose observation happens to
    # match a different well's (duplicated) expected label -- the only way
    # cross_match can be nonzero here without also being self-matched.
    observations[0] = WellObservation(
        well_id="W00", expected=("V0F",), observed=("V1F",)
    )
    observations[7] = WellObservation(
        well_id="W07", expected=("V1F",), observed=("V2F",)
    )

    report = check_mapping_integrity(observations)
    assert report.wells_considered == n
    assert report.self_rate > 0.9
    assert report.cross_match >= 1
    assert report.suspect is False


def test_below_min_wells_never_suspect_even_if_fully_permuted() -> None:
    """A small run cannot be graded: a permutation of a few wells overlaps by
    chance too often to mean anything (see the module docstring threshold
    rationale), so it must never raise a false alarm."""
    n = 10
    labels = [f"V{i}F" for i in range(n)]
    observations = [
        WellObservation(
            well_id=f"W{i:02d}", expected=(labels[i],), observed=(labels[(i + 1) % n],)
        )
        for i in range(n)
    ]
    report = check_mapping_integrity(observations)
    assert report.wells_considered == n
    assert report.self_match == 0
    assert report.cross_match == n
    assert report.suspect is False


def test_no_observed_changes_is_not_suspect_and_has_zero_rates() -> None:
    observations = [
        WellObservation(well_id=f"W{i:02d}", expected=(f"V{i}F",), observed=())
        for i in range(_N_WELLS)
    ]
    report = check_mapping_integrity(observations)
    assert report.wells_considered == 0
    assert report.self_match == 0
    assert report.cross_match == 0
    assert report.self_rate == 0.0
    assert report.cross_rate == 0.0
    assert report.suspect is False


def test_empty_observation_list() -> None:
    report = check_mapping_integrity([])
    assert report.wells_considered == 0
    assert report.suspect is False


def test_self_match_takes_priority_over_cross_when_both_would_hit() -> None:
    """A well matching its own expected must not also count as cross_match,
    even when the same observed label is also (coincidentally) another
    well's expected label."""
    observations = [
        WellObservation(well_id="A", expected=("V1F",), observed=("V1F",)),
        WellObservation(well_id="B", expected=("V1F",), observed=("V1F",)),
    ]
    report = check_mapping_integrity(observations)
    assert report.self_match == 2
    assert report.cross_match == 0
