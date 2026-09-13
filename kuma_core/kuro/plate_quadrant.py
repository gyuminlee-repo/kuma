"""Echo 384 source-plate halves, as the lab actually builds them.

A 384 source plate holds two rounds of a primer set. One round occupies the
left half (columns 1-12) and the next occupies the right half (columns 13-24).
Within a half the geometry is the legacy row-doubled one: a 96-well address
``<row><col>`` lands on 384 row ``2r`` for the forward primer and ``2r + 1``
for the reverse primer, with the column carried over unchanged apart from the
half offset. Forward primers therefore sit on rows A, C, E, G, I, K, M, O and
reverse primers on B, D, F, H, J, L, N, P.

The reference is the real worklist the lab ran, sheet ``Echo mapping file`` of
``$WORKSPACE_ROOT/020.admin/projects/040.mapping_files_echo/``
``Project2-1. primer dispensing (Echo525).xlsx`` (parsed 2026-09-13: 190
transfers over 161 source wells, 95 forward and 66 reverse). Its occupancy is:

    col    1  2  3  4  5  6  7  8  9 10 11 12 13 .. 24
     A     F  F  F  F  F  F  F  F  F  F  F  F  .     .
     B     R  R  R  R  R  R  R  R  R  .  .  .  .     .
     C     F  F  F  F  F  F  F  F  F  F  F  F  .     .
     D     R  R  R  R  R  R  R  R  R  .  .  .  .     .
     ...   the same alternation down to row P

The first two transfers are ``V5F_F -> A1`` and ``V10L_F -> C1``, so
consecutive mutants step two rows down the same column. Columns run 1-12 with
no gap, and nothing in the file touches columns 13-24, which is the second
round's half.

Why this file used to say otherwise: commit ``c285d5d6`` (#211, v0.14.0,
2026-07-31) introduced an interleaved layout that skipped every other column as
well as every other row, on the strength of a grid read off a video. That screen
was never confirmed to be the source-plate build UI, and the worklist above
contradicts it directly (dest ``A2`` draws from source ``A2``, while the
interleaved rule puts it at ``A3``). Read the workbook before changing this
geometry again.

Selection is therefore between two halves and not four quadrants. A quadrant
cannot work here: it offers only four forward rows, which is not enough for 96
mutants. The halves are named after the well each starts at, ``A1`` and ``A13``.

The persisted key is still called ``quadrant`` so projects saved before this
change keep loading. Their stored values ``A1``/``B1`` fold onto ``A1`` and
``A2``/``B2`` onto ``A13``, which is the conservative direction: a folded
``used_quadrants`` marks more of the plate as spent than it may be, and this
module already prefers a refusal over dispensing on top of existing primers.

Which halves are already spent on a part-used plate is not tracked here. The
operator states it, because the plate is a physical object this program never
sees and a stale guess is worse than a question.
"""

from __future__ import annotations

_ROWS_96 = "ABCDEFGH"
_ROWS_384 = "ABCDEFGHIJKLMNOP"

#: The two wells a round can start from, in the order the UI offers them.
QUADRANTS: tuple[str, ...] = ("A1", "A13")

#: half -> 384 column offset.
_COL_OFFSETS: dict[str, int] = {"A1": 0, "A13": 12}

#: Values a project saved before the half layout can carry, and the half each
#: one folds onto. The old A1/B1 pair was the left columns and A2/B2 the right.
_LEGACY_FOLD: dict[str, str] = {
    "A1": "A1",
    "B1": "A1",
    "A2": "A13",
    "B2": "A13",
    "A13": "A13",
}


def validate_quadrant(quadrant: str) -> str:
    """Return the canonical half name, or raise for anything else.

    Legacy values from saved projects are folded rather than rejected, so an old
    project loads instead of dying on its stored placement.
    """
    name = quadrant.strip().upper()
    folded = _LEGACY_FOLD.get(name)
    if folded is None:
        raise ValueError(
            f"Unknown quadrant {quadrant!r}. Expected one of {', '.join(QUADRANTS)}."
        )
    return folded


def to_384_well(well_96: str, quadrant: str, *, reverse: bool = False) -> str:
    """Map a 96-well address into *quadrant* of a 384-well plate.

    The forward primer for 96 well ``A1`` is 384 ``A1`` in half A1 and ``A13``
    in half A13. Its reverse primer is one row below, ``B1`` and ``B13``. The
    far corner ``H12`` is ``O12``/``P12`` in half A1 and ``O24``/``P24`` in
    half A13.
    """
    name = validate_quadrant(quadrant)
    col_offset = _COL_OFFSETS[name]

    row_letter = well_96[0].upper()
    if row_letter not in _ROWS_96:
        raise ValueError(f"96-well row must be A-H, got {well_96!r}")
    try:
        col = int(well_96[1:])
    except ValueError as exc:
        raise ValueError(f"96-well column must be numeric, got {well_96!r}") from exc
    if not 1 <= col <= 12:
        raise ValueError(f"96-well column must be 1-12, got {well_96!r}")

    row_384 = _ROWS_384[_ROWS_96.index(row_letter) * 2 + (1 if reverse else 0)]
    return f"{row_384}{col + col_offset}"


def quadrant_wells(quadrant: str, *, reverse: bool | None = None) -> list[str]:
    """Every 384 well *quadrant* covers, in column-major 96-well order.

    ``reverse=False`` gives the 96 forward wells, ``reverse=True`` the 96
    reverse wells, and the default gives all 192 wells of the half.
    """
    name = validate_quadrant(quadrant)
    strands = (False, True) if reverse is None else (reverse,)
    return [
        to_384_well(f"{row}{col}", name, reverse=strand)
        for strand in strands
        for col in range(1, 13)
        for row in _ROWS_96
    ]


def check_quadrants_available(
    quadrant: str,
    used_quadrants: list[str] | None = None,
) -> str:
    """Resolve the half to dispense into and refuse one that is already spent.

    Returns the canonical half name.

    Forward and reverse are not a separate choice: the reverse primer is always
    one row below its forward primer in the same half, so there is one thing to
    check. A part-used plate is the normal case when new plates are short: the
    operator says which halves are gone and this refuses to dispense on top of
    them. Overwriting a filled half destroys the primers already in it, so this
    is an error rather than a warning.
    """
    target = validate_quadrant(quadrant)
    spent = {validate_quadrant(q) for q in (used_quadrants or [])}

    if target in spent:
        free = [q for q in QUADRANTS if q not in spent]
        raise ValueError(
            f"Quadrant {target} already used on this plate. "
            + (
                f"Still free: {', '.join(free)}."
                if free
                else "No quadrant is free; this plate is full."
            )
        )
    return target


__all__ = [
    "QUADRANTS",
    "check_quadrants_available",
    "quadrant_wells",
    "to_384_well",
    "validate_quadrant",
]
