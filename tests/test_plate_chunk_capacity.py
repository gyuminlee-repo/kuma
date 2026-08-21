"""Plate chunking has to agree with plate assignment.

``_assign_well_with_range`` divides by ``_capacity_for_range``, which a
``mapping_range`` over the 384 rows makes 48 or 24. ``_chunk_by_plate`` counted
to 96 regardless and stripped the ``P2-`` prefix on the way, so the second
plate's wells joined the first plate's chunk and became indistinguishable from
it: the order sheet named two different primers for one physical position.

The repository's own note on this pair says a fixture that stays under the
boundary proves nothing, because the two implementations agree there. That is
exactly why this went unseen, and why every case here crosses its own capacity.
"""

from __future__ import annotations

from collections import Counter

import pytest

from kuma_core.kuro.plate_mapper import (
    PlateMapping,
    _assign_well_with_range,
    _capacity_for_range,
    _chunk_by_plate,
)


def _mappings(count: int, mapping_range: tuple[str, str] | None) -> list[PlateMapping]:
    """*count* mappings, each on the well the assignment gives it."""
    return [
        PlateMapping(
            well=_assign_well_with_range(i, "row", mapping_range),
            primer_name=f"p{i}",
            sequence="ACGT",
            primer_type="forward",
            mutation=f"M{i + 1}A",
            tm=60.0,
            tm_overlap=60.0,
            wt_codon="AAA",
            mt_codon="GCA",
        )
        for i in range(count)
    ]


#: (label, mapping_range, expected capacity). A range over 384 rows halves the
#: rows into fwd/rev pairs, so A-H is 48 and A-D is 24.
_RANGES = [
    ("no range", None, 96),
    ("rows A-H", ("A", "H"), 48),
    ("rows A-D", ("A", "D"), 24),
]


@pytest.mark.parametrize("label,mapping_range,capacity", _RANGES)
def test_capacity_is_what_the_test_assumes(
    label: str, mapping_range: tuple[str, str] | None, capacity: int
) -> None:
    """Pin the capacities the cases below are built on.

    Without this a change to _capacity_for_range would quietly move every
    boundary these tests aim at, and they would keep passing while testing
    nothing in particular.
    """
    assert _capacity_for_range(mapping_range) == capacity


@pytest.mark.parametrize("label,mapping_range,capacity", _RANGES)
def test_no_well_is_used_twice_on_one_plate(
    label: str, mapping_range: tuple[str, str] | None, capacity: int
) -> None:
    """One plate, one primer per well.

    Reverted, this fails for both ranged cases: at capacity 48 over 60
    mappings a single chunk came back holding 12 duplicated wells. The no-range
    case passes either way, which is why nothing caught this.
    """
    chunks = _chunk_by_plate(_mappings(capacity + capacity // 4, mapping_range))

    for index, chunk in enumerate(chunks):
        counts = Counter(m.well for m in chunk)
        duplicated = sorted(w for w, n in counts.items() if n > 1)
        assert not duplicated, (
            f"{label}: plate {index} names {len(duplicated)} well(s) twice: "
            f"{duplicated[:5]}"
        )


@pytest.mark.parametrize("label,mapping_range,capacity", _RANGES)
def test_a_plate_holds_no_more_than_its_capacity(
    label: str, mapping_range: tuple[str, str] | None, capacity: int
) -> None:
    """The chunk boundary is the capacity the assignment used, not 96."""
    chunks = _chunk_by_plate(_mappings(capacity * 2 + 1, mapping_range))

    for index, chunk in enumerate(chunks):
        assert len(chunk) <= capacity, (
            f"{label}: plate {index} holds {len(chunk)} mappings, "
            f"more than the {capacity} wells it has"
        )


@pytest.mark.parametrize("label,mapping_range,capacity", _RANGES)
def test_every_mapping_lands_on_exactly_one_plate(
    label: str, mapping_range: tuple[str, str] | None, capacity: int
) -> None:
    """The control. Chunking must not drop or duplicate a primer.

    Without it a chunker that returned nothing would pass both tests above.
    """
    count = capacity * 2 + 1
    chunks = _chunk_by_plate(_mappings(count, mapping_range))

    names = [m.primer_name for chunk in chunks for m in chunk]
    assert len(names) == count
    assert len(set(names)) == count


@pytest.mark.parametrize("label,mapping_range,capacity", _RANGES)
def test_the_plate_prefix_is_stripped_from_the_well(
    label: str, mapping_range: tuple[str, str] | None, capacity: int
) -> None:
    """A well on plate 2 is written as its own coordinate, not "P2-A1".

    The prefix says which plate; inside that plate the address is the plain
    well, which is what the order sheet and the robot read.
    """
    chunks = _chunk_by_plate(_mappings(capacity + 1, mapping_range))

    assert len(chunks) == 2
    assert all("-" not in m.well for chunk in chunks for m in chunk)
    assert chunks[1][0].well == chunks[0][0].well == "A1"


def test_a_single_short_plate_still_returns_one_chunk() -> None:
    """The ordinary case, well under any capacity."""
    chunks = _chunk_by_plate(_mappings(5, None))

    assert len(chunks) == 1
    assert len(chunks[0]) == 5


def test_no_mappings_returns_one_empty_plate() -> None:
    """The shape callers already rely on: they index [0] unconditionally."""
    assert _chunk_by_plate([]) == [[]]
