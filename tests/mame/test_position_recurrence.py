"""Which reference positions come back well after well, and nothing more.

The measurement behind this, two ispS runs on different flow cells five months
apart, 87 and 79 wells over a 1715 bp amplicon, reading the median weak-strand
share of the minor allele by how many wells reported the position:

    wells reporting      260212      260729
    1 (unique)            0.250       0.256
    2-3                   0.205       0.267
    4-9                   0.053       0.071
    10+                   0.016       0.000

Nine positions recurred in ten or more wells in BOTH runs. So the tally is worth
making visible, and it is still not a rule: these tests pin that the module
emits a table and no verdict, that the table states its own remainder, and that
an unknown strand share never enters a median as 0.0.
"""

from dataclasses import dataclass

import pytest

from kuma_core.mame.models import NoisyPosition
from kuma_core.mame.run_quality import (
    STRAND_ABSENT,
    STRAND_NO_DATA,
    STRAND_PRESENT,
    serialise_position_recurrence,
    summarise_position_recurrence,
)


@dataclass
class _Well:
    """The two attributes the tally reads, as ``BarcodeRecord`` presents them."""

    noisy_positions: tuple[NoisyPosition, ...]
    n_eligible_positions: int


def _position(
    position: int, plus: int, minus: int, *, minor_fraction: float = 0.04
) -> NoisyPosition:
    return NoisyPosition(
        position=position,
        minor_fraction=minor_fraction,
        depth=500,
        plus_count=plus,
        minus_count=minus,
    )


def _well(*positions: NoisyPosition, eligible: int | None = None) -> _Well:
    """A well whose pool is as large as its sample unless stated otherwise."""
    return _Well(
        noisy_positions=positions,
        n_eligible_positions=len(positions) if eligible is None else eligible,
    )


def test_a_shared_position_is_named_with_its_well_count_and_median_share() -> None:
    """The signal itself: one position, three wells, and the median of the three.

    Shares are 0.1, 0.2 and 0.4, so the median is 0.2 and the extremes bracket
    it. Position 42 appears in one well only and is therefore not a row.
    """
    wells = [
        _well(_position(1248, plus=90, minus=10)),
        _well(_position(1248, plus=80, minus=20)),
        _well(_position(1248, plus=60, minus=40), _position(42, plus=50, minus=50)),
    ]

    summary = summarise_position_recurrence(wells)

    assert [row.position for row in summary.positions] == [1248]
    row = summary.positions[0]
    assert row.wells == 3
    assert row.median_weak_strand_share == 0.2
    assert row.min_weak_strand_share == 0.1
    assert row.max_weak_strand_share == 0.4
    assert row.shares_known == 3
    assert row.shares_unknown == 0
    # Nothing on the block grades the row: no severity, no finding, no verdict.
    payload = serialise_position_recurrence(summary)
    assert "severity" not in payload
    assert "findings" not in payload
    assert payload["positions"][0]["wells"] == 3


def test_a_run_with_no_recurrence_reports_an_empty_table_and_its_remainder() -> None:
    """Three wells, three different positions, and the singletons are counted.

    An empty table with no count would be indistinguishable from a plate on
    which nothing was eligible at all.
    """
    wells = [
        _well(_position(101, plus=10, minus=10)),
        _well(_position(202, plus=10, minus=10)),
        _well(_position(303, plus=10, minus=10)),
    ]

    summary = summarise_position_recurrence(wells)

    assert summary.positions == []
    assert summary.positions_seen == 3
    assert summary.positions_single_well == 3
    assert summary.wells_contributing == 3

    payload = serialise_position_recurrence(summary)
    assert payload["positions"] == []
    assert payload["positions_single_well"] == 3


def test_a_plate_with_nothing_eligible_does_not_raise() -> None:
    summary = summarise_position_recurrence([_well(), _well()])

    assert summary.positions == []
    assert summary.wells_contributing == 0
    assert summary.positions_seen == 0
    assert summary.positions_single_well == 0
    assert serialise_position_recurrence(summary)["lower_bound"] is True


def test_truncated_wells_are_counted_and_the_block_says_it_is_a_lower_bound() -> None:
    """Two wells sampled from a larger pool, one that reported everything it had.

    On the two measured runs EVERY well was truncated (87 of 87, 79 of 79), so a
    recurrence count from these lists is a floor. ``wells_truncated`` is what
    lets a reader see that.
    """
    wells = [
        _well(_position(1248, plus=50, minus=50), eligible=31),
        _well(_position(1248, plus=50, minus=50), eligible=27),
        _well(_position(1248, plus=50, minus=50)),
    ]

    summary = summarise_position_recurrence(wells)

    assert summary.wells_contributing == 3
    assert summary.wells_truncated == 2

    payload = serialise_position_recurrence(summary)
    assert payload["wells_truncated"] == 2
    assert payload["wells_contributing"] == 3
    assert payload["lower_bound"] is True


def test_an_unknown_share_never_enters_a_median_as_zero() -> None:
    """The failure mode most likely to be introduced in silence.

    The third well has no reads on either strand at 1248, so its share is
    UNKNOWN rather than 0.0, which is the reading "one strand only". Entering it
    as 0.0 would drag the median from 0.4 to 0.2 and invent one-strand evidence
    nobody measured. The well is still counted as having reported the position.
    """
    unknown = _Well(
        noisy_positions=(_position(1248, plus=0, minus=0),),
        n_eligible_positions=1,
    )
    wells = [
        _well(_position(1248, plus=60, minus=40)),
        _well(_position(1248, plus=60, minus=40)),
        unknown,
    ]

    summary = summarise_position_recurrence(wells)
    row = summary.positions[0]

    assert row.wells == 3
    assert row.shares_known == 2
    assert row.shares_unknown == 1
    assert row.median_weak_strand_share == 0.4
    assert row.min_weak_strand_share == 0.4
    assert row.max_weak_strand_share == 0.4

    # And with every share unknown the three statistics are None, not 0.0.
    all_unknown = summarise_position_recurrence([unknown, unknown])
    blank = all_unknown.positions[0]
    assert blank.wells == 2
    assert blank.median_weak_strand_share is None
    assert blank.min_weak_strand_share is None
    assert blank.max_weak_strand_share is None
    assert serialise_position_recurrence(all_unknown)["positions"][0][
        "median_weak_strand_share"
    ] is None


def test_the_table_is_ordered_by_recurrence_and_never_cut_off() -> None:
    """Most-recurrent first, then by coordinate, and every recurring row present.

    An ordering is not a ranking: no row is dropped off the end, because a cap
    would hide exactly the positions this tally exists to surface.
    """
    wells = [
        _well(*[_position(p, plus=5, minus=5) for p in (10, 20, 30, 40)]),
        _well(*[_position(p, plus=5, minus=5) for p in (10, 20, 30, 40)]),
        _well(_position(10, plus=5, minus=5), _position(20, plus=5, minus=5)),
        _well(_position(10, plus=5, minus=5)),
    ]

    summary = summarise_position_recurrence(wells)

    assert [(row.position, row.wells) for row in summary.positions] == [
        (10, 4),
        (20, 3),
        (30, 2),
        (40, 2),
    ]


# ── Migrated from the former qc/cross_well_recurrence module ─────────────────
#
# That module was a second aggregator over the same input with no production
# caller. Its unique columns (the recurrence rate, the minor-fraction spread and
# the plate-level strand determination) moved onto this one, and these are the
# cases it carried that nothing here already covered. Each names the mutation it
# is meant to catch, so a future reader can check it still has teeth.


def test_recurrence_rate_denominator_is_contributing_wells() -> None:
    """Kills a denominator swapped for the number of wells passed in.

    A well with no eligible position carries no evidence either way. Folding it
    into the denominator would understate every rate on a plate that had some.
    """
    wells = [
        _well(_position(50, plus=10, minus=10, minor_fraction=0.05)),
        _well(_position(50, plus=10, minus=10, minor_fraction=0.05)),
        _well(),  # contributes nothing, must not enter the denominator
        _well(),
    ]

    summary = summarise_position_recurrence(wells)

    assert summary.wells_contributing == 2
    assert summary.positions[0].wells == 2
    assert summary.positions[0].recurrence_rate == 1.0
    assert serialise_position_recurrence(summary)["positions"][0][
        "recurrence_rate"
    ] == 1.0


def test_spread_is_reported_beside_the_median() -> None:
    """Kills median->mean, and kills dropping min/max.

    This is the shape that separates a plate-wide low-fraction site from one
    well in genuine mixture at the same position: measured at position 1654,
    eighteen wells at median 0.018 with one well at 0.476. A single scalar
    cannot state it.
    """
    # All three statistics differ, on purpose. A fixture whose median equals its
    # own minimum cannot catch min being computed as the median, which is the
    # cheapest way to lose the lower end.
    wells = [_well(_position(1654, plus=10, minus=10, minor_fraction=0.024))]
    wells += [
        _well(_position(1654, plus=10, minus=10, minor_fraction=0.0505))
        for _ in range(16)
    ]
    wells.append(_well(_position(1654, plus=10, minus=10, minor_fraction=0.476)))

    (row,) = summarise_position_recurrence(wells).positions

    assert row.wells == 18
    assert row.median_minor_fraction == pytest.approx(0.0505)
    assert row.min_minor_fraction == pytest.approx(0.024)
    assert row.max_minor_fraction == pytest.approx(0.476)
    # A mean would be pulled to ~0.0727 and hide both ends.
    assert row.median_minor_fraction < 0.06
    payload = serialise_position_recurrence(summarise_position_recurrence(wells))
    assert payload["positions"][0]["min_minor_fraction"] == pytest.approx(0.024)
    assert payload["positions"][0]["max_minor_fraction"] == pytest.approx(0.476)


def test_forward_normalised_plate_reports_no_strand_information() -> None:
    """Kills removal of the plate-level strand determination.

    Every share on such a plate evaluates to 0.0, which the record defines as
    "read off one strand only" and a reader would otherwise take for a
    basecaller artifact. The three measured plates are exactly this case: reads
    were normalised to the forward strand upstream, so no minus read survives.

    The shares keep their own reading rather than being blanked, because 0.0 is
    what was measured and the serialised key is read that way downstream.
    ``strand_information`` is what tells a reader those zeros carry no contrast.
    """
    wells = [_well(_position(1232, plus=10, minus=0)) for _ in range(3)]

    summary = summarise_position_recurrence(wells)

    assert summary.strand_information == STRAND_ABSENT
    (row,) = summary.positions
    assert row.median_weak_strand_share == 0.0
    assert row.shares_known == 3
    assert row.shares_unknown == 0
    assert (
        serialise_position_recurrence(summary)["strand_information"] == STRAND_ABSENT
    )


def test_two_strand_plate_reports_measured_shares() -> None:
    """The other half: a plate that did carry contrast says so."""
    wells = [_well(_position(1232, plus=6, minus=4)) for _ in range(3)]

    summary = summarise_position_recurrence(wells)

    assert summary.strand_information == STRAND_PRESENT
    (row,) = summary.positions
    assert row.median_weak_strand_share == pytest.approx(0.4)
    assert row.shares_known == 3
    assert row.shares_unknown == 0


def test_reverse_normalised_plate_also_reports_no_strand_information() -> None:
    """Kills the mutation that drops ``any_plus`` from the determination.

    The forward case is the one the measured plates show, so a check written
    only against it passes every test here while leaving the identical trap on
    the other side: reads normalised to the REVERSE strand leave ``plus_count``
    at zero everywhere, every share still evaluates to 0.0, and a minus-only
    test would report the plate as having measured strand. Neither direction
    carries contrast.
    """
    wells = [_well(_position(1232, plus=0, minus=10)) for _ in range(3)]

    summary = summarise_position_recurrence(wells)

    assert summary.strand_information == STRAND_ABSENT


def test_strand_absent_is_distinct_from_no_data() -> None:
    """An empty plate measured nothing; it did not measure "one strand"."""
    summary = summarise_position_recurrence([_well(), _well()])

    assert summary.strand_information == STRAND_NO_DATA
    assert summary.wells_contributing == 0
    assert summary.positions == []


def test_recurrence_separates_a_plate_wide_site_from_a_single_well_mixture() -> None:
    """The discrimination the migrated columns exist for, as the plates showed it.

    Position 1232 was reported by 90 of 93 contributing wells at a median
    fraction of 0.0505; position 16 was reported by two wells, one of them at
    0.456 and its neighbour at 0.029, and the same well read 0.017 on another
    plate. Both are rows. The columns, not a threshold, tell them apart.
    """
    wells = [
        _well(
            _position(1232, plus=10, minus=10, minor_fraction=0.05),
            _position(16, plus=10, minus=10, minor_fraction=0.029),
        )
    ]
    wells += [
        _well(_position(1232, plus=10, minus=10, minor_fraction=0.05))
        for _ in range(89)
    ]
    wells.append(
        _well(
            _position(1232, plus=10, minus=10, minor_fraction=0.05),
            _position(16, plus=10, minus=10, minor_fraction=0.456),
        )
    )

    rows = {
        row.position: row for row in summarise_position_recurrence(wells).positions
    }

    systemic, mixture = rows[1232], rows[16]
    assert systemic.recurrence_rate == pytest.approx(1.0)
    assert mixture.recurrence_rate < 0.05
    # The mixture row spans an order of magnitude; the recurrent one does not.
    assert mixture.max_minor_fraction / mixture.min_minor_fraction > 10
    assert systemic.max_minor_fraction == systemic.min_minor_fraction
