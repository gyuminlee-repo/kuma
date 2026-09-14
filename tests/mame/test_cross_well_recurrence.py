"""Cross-well recurrence table.

Every test names the mutation it is meant to catch, so a future reader can
check that the test still has teeth rather than trusting that it passes.
"""

from __future__ import annotations

import pytest

from kuma_core.mame.models import NoisyPosition
from kuma_core.mame.qc import summarise_cross_well_recurrence
from kuma_core.mame.qc.cross_well_recurrence import (
    STRAND_ABSENT,
    STRAND_NO_DATA,
    STRAND_PRESENT,
)


class _Well:
    """Minimal stand-in for the two classes that satisfy the protocol."""

    def __init__(self, positions, eligible=None):
        self._positions = tuple(positions)
        self._eligible = len(self._positions) if eligible is None else eligible

    @property
    def noisy_positions(self):
        return self._positions

    @property
    def n_eligible_positions(self):
        return self._eligible


def _pos(position, fraction, *, plus=10, minus=0, depth=200):
    return NoisyPosition(
        position=position,
        minor_fraction=fraction,
        depth=depth,
        plus_count=plus,
        minus_count=minus,
    )


def test_single_well_position_is_not_a_row():
    """Kills the mutation ``_MIN_WELLS_TO_RECUR = 2`` -> ``1``.

    A position one well reported has not recurred. It must be counted in the
    remainder instead of silently vanishing.
    """
    wells = [_Well([_pos(100, 0.3)]), _Well([_pos(200, 0.3)])]

    result = summarise_cross_well_recurrence(wells)

    assert [row.position for row in result.positions] == []
    assert result.positions_seen == 2
    assert result.positions_single_well == 2


def test_recurrence_rate_denominator_is_contributing_wells():
    """Kills a denominator swapped for the number of wells passed in.

    A well with no eligible position carries no evidence either way. Folding it
    into the denominator would understate every rate on a plate that had some.
    """
    wells = [
        _Well([_pos(50, 0.05)]),
        _Well([_pos(50, 0.05)]),
        _Well([]),  # contributes nothing, must not enter the denominator
        _Well([]),
    ]

    result = summarise_cross_well_recurrence(wells)

    assert result.wells_contributing == 2
    assert result.positions[0].wells == 2
    assert result.positions[0].recurrence_rate == 1.0


def test_spread_is_reported_beside_the_median():
    """Kills median->mean, and kills dropping min/max.

    This is the shape that separates a plate-wide low-fraction site from one
    well in genuine mixture at the same position: measured at position 1654,
    eighteen wells at median 0.018 with one well at 0.476. A single scalar
    cannot state it.
    """
    wells = [_Well([_pos(1654, 0.018)]) for _ in range(17)]
    wells.append(_Well([_pos(1654, 0.476)]))

    (row,) = summarise_cross_well_recurrence(wells).positions

    assert row.wells == 18
    assert row.median_minor_fraction == pytest.approx(0.018)
    assert row.min_minor_fraction == pytest.approx(0.018)
    assert row.max_minor_fraction == pytest.approx(0.476)
    # A mean would be pulled to ~0.043 and hide both ends.
    assert row.median_minor_fraction < 0.02


def test_forward_normalised_plate_reports_no_strand_information():
    """Kills removal of the plate-level strand guard.

    Every share on such a plate evaluates to 0.0, which the record defines as
    "read off one strand only" and a reader would take for a basecaller
    artifact. The three measured plates are exactly this case: reads were
    normalised to the forward strand upstream, so no minus read survives.
    """
    wells = [_Well([_pos(1232, 0.05, plus=10, minus=0)]) for _ in range(3)]

    result = summarise_cross_well_recurrence(wells)

    assert result.strand_information == STRAND_ABSENT
    (row,) = result.positions
    assert row.median_weak_strand_share is None
    assert row.min_weak_strand_share is None
    assert row.max_weak_strand_share is None
    assert row.shares_known == 0
    assert row.shares_unknown == row.wells


def test_two_strand_plate_reports_measured_shares():
    """The other half of the guard: a real measurement must not be suppressed."""
    wells = [_Well([_pos(1232, 0.05, plus=6, minus=4)]) for _ in range(3)]

    result = summarise_cross_well_recurrence(wells)

    assert result.strand_information == STRAND_PRESENT
    (row,) = result.positions
    assert row.median_weak_strand_share == pytest.approx(0.4)
    assert row.shares_known == 3
    assert row.shares_unknown == 0


def test_strand_absent_is_distinct_from_no_data():
    """An empty plate measured nothing; it did not measure "one strand"."""
    result = summarise_cross_well_recurrence([_Well([]), _Well([])])

    assert result.strand_information == STRAND_NO_DATA
    assert result.wells_contributing == 0
    assert result.positions == []


def test_truncated_wells_are_counted():
    """Kills dropping the ``len(positions) < n_eligible_positions`` comparison.

    Every count in the table is a lower bound whenever a well reported fewer
    positions than it had eligible. On all three measured plates every single
    contributing well was truncated, so a table that did not say so would read
    as a census.
    """
    wells = [
        _Well([_pos(10, 0.05), _pos(20, 0.04)], eligible=40),
        _Well([_pos(10, 0.05), _pos(20, 0.04)], eligible=2),
    ]

    result = summarise_cross_well_recurrence(wells)

    assert result.wells_contributing == 2
    assert result.wells_truncated == 1


def test_rows_are_ordered_most_recurrent_first_then_by_position():
    """Determinism: ties must not depend on dict insertion order."""
    wells = [
        _Well([_pos(300, 0.05), _pos(100, 0.05), _pos(200, 0.05)]),
        _Well([_pos(300, 0.05), _pos(100, 0.05), _pos(200, 0.05)]),
        _Well([_pos(300, 0.05)]),
    ]

    rows = summarise_cross_well_recurrence(wells).positions

    assert [(r.position, r.wells) for r in rows] == [(300, 3), (100, 2), (200, 2)]


def test_recurrence_separates_a_plate_wide_site_from_a_single_well_mixture():
    """The discrimination this module exists for, in the shape the plates showed.

    Position 1232 was reported by 90 of 93 contributing wells at a median
    fraction of 0.0505; position 16 was reported by two wells, one of them at
    0.456 and its neighbour at 0.029, and the same well read 0.017 on another
    plate. Both are rows. The columns, not a threshold, tell them apart.
    """
    wells = [_Well([_pos(1232, 0.05), _pos(16, 0.029)])]
    wells += [_Well([_pos(1232, 0.05)]) for _ in range(89)]
    wells.append(_Well([_pos(1232, 0.05), _pos(16, 0.456)]))

    rows = {row.position: row for row in summarise_cross_well_recurrence(wells).positions}

    systemic, mixture = rows[1232], rows[16]
    assert systemic.recurrence_rate == pytest.approx(1.0)
    assert mixture.recurrence_rate < 0.05
    # The mixture row spans an order of magnitude; the recurrent one does not.
    assert mixture.max_minor_fraction / mixture.min_minor_fraction > 10
    assert systemic.max_minor_fraction == systemic.min_minor_fraction
