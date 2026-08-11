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

from kuma_core.mame.models import NoisyPosition
from kuma_core.mame.run_quality import (
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
