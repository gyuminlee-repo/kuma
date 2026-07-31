"""Echo 384 source-plate quadrants, as a 96-head Zephyr can actually fill them.

A 96-head sits on a 9 mm pitch and a 384-well plate is on 4.5 mm, so one stamp
reaches every other row *and* every other column: 8 x 12 = 96 wells. Which 96
depends on where the head starts, and there are exactly four starting wells:
A1, A2, B1 and B2. Those four interleaved sets tile the plate.

The previous mapping doubled rows only (96 row *r* -> 384 row 2r) and left the
column alone, so a filled plate occupied rows A-P across columns 1-12. That
layout is reachable by hand or by a single-channel head, but not by one 96-head
stamp, which is how these source plates are actually made.

Pairing is not a separate choice. A round needs a forward set and a reverse set,
and the existing convention already puts them on adjacent rows (2r and 2r+1). A
quadrant keeps that: picking A1 for forward puts reverse in B1, picking A2 puts
it in B2. So one 384 plate carries two rounds, which is the
"2 round primer set / 1 Echo source plate" concept the campaign runs on.

Which quadrants are already spent on a part-used plate is not tracked here. The
operator states it, because the plate is a physical object this program never
sees and a stale guess is worse than a question.
"""

from __future__ import annotations

_ROWS_96 = "ABCDEFGH"
_ROWS_384 = "ABCDEFGHIJKLMNOP"

#: The four wells a 96-head can start from, in the order the UI offers them.
QUADRANTS: tuple[str, ...] = ("A1", "A2", "B1", "B2")

#: quadrant -> (row offset, column offset), both 0 or 1.
_OFFSETS: dict[str, tuple[int, int]] = {
    "A1": (0, 0),
    "A2": (0, 1),
    "B1": (1, 0),
    "B2": (1, 1),
}


def validate_quadrant(quadrant: str) -> str:
    """Return the canonical quadrant name, or raise for anything else."""
    name = quadrant.strip().upper()
    if name not in _OFFSETS:
        raise ValueError(
            f"Unknown quadrant {quadrant!r}. Expected one of {', '.join(QUADRANTS)}."
        )
    return name


def paired_quadrant(quadrant: str) -> str:
    """Return the reverse-primer quadrant that goes with *quadrant*.

    Forward and reverse stay on adjacent rows of the same columns, which is the
    convention the row-doubled layout already used. A1 pairs with B1 and A2 with
    B2, so the two pairs are the two rounds one plate can hold.
    """
    name = validate_quadrant(quadrant)
    row, col = _OFFSETS[name]
    for candidate, (r, c) in _OFFSETS.items():
        if c == col and r != row:
            return candidate
    raise AssertionError(f"no partner for {name}")  # unreachable by construction


def to_384_well(well_96: str, quadrant: str) -> str:
    """Map a 96-well address into *quadrant* of a 384-well plate.

    ``A1`` in quadrant A1 is 384 ``A1``; in quadrant A2 it is ``A2``; in B1 it is
    ``B1``; in B2 it is ``B2``. ``H12`` in quadrant A1 is ``O23``, the far corner
    of that interleaved set.
    """
    name = validate_quadrant(quadrant)
    row_offset, col_offset = _OFFSETS[name]

    row_letter = well_96[0].upper()
    if row_letter not in _ROWS_96:
        raise ValueError(f"96-well row must be A-H, got {well_96!r}")
    try:
        col = int(well_96[1:])
    except ValueError as exc:
        raise ValueError(f"96-well column must be numeric, got {well_96!r}") from exc
    if not 1 <= col <= 12:
        raise ValueError(f"96-well column must be 1-12, got {well_96!r}")

    row_384 = _ROWS_384[_ROWS_96.index(row_letter) * 2 + row_offset]
    col_384 = (col - 1) * 2 + 1 + col_offset
    return f"{row_384}{col_384}"


def quadrant_wells(quadrant: str) -> list[str]:
    """Every 384 well *quadrant* covers, in column-major 96-well order."""
    name = validate_quadrant(quadrant)
    return [
        to_384_well(f"{row}{col}", name)
        for col in range(1, 13)
        for row in _ROWS_96
    ]


def check_quadrants_available(
    fwd_quadrant: str,
    used_quadrants: list[str] | None = None,
) -> tuple[str, str]:
    """Resolve the forward/reverse pair and refuse one that is already spent.

    Returns ``(forward, reverse)``.

    A part-used plate is the normal case when new plates are short: the operator
    says which quadrants are gone and this refuses to dispense on top of them.
    Overwriting a filled quadrant destroys the primers already in it, so this is
    an error rather than a warning.
    """
    forward = validate_quadrant(fwd_quadrant)
    reverse = paired_quadrant(forward)
    spent = {validate_quadrant(q) for q in (used_quadrants or [])}

    clash = [q for q in (forward, reverse) if q in spent]
    if clash:
        # 쓸 수 있는 forward 는 자기도 짝도 비어 있어야 한다. 짝이 막힌 quadrant 를
        # "free" 로 알려주면 사용자가 그걸 골랐다가 같은 거부를 다시 받는다.
        free = [
            q
            for q in QUADRANTS
            if q not in spent and paired_quadrant(q) not in spent
        ]
        raise ValueError(
            f"Quadrant {' and '.join(clash)} already used on this plate. "
            f"Forward {forward} needs reverse {reverse}. "
            + (
                f"Still free: {', '.join(free)}."
                if free
                else "No quadrant is free; this plate is full."
            )
        )
    return forward, reverse


__all__ = [
    "QUADRANTS",
    "check_quadrants_available",
    "paired_quadrant",
    "quadrant_wells",
    "to_384_well",
    "validate_quadrant",
]
