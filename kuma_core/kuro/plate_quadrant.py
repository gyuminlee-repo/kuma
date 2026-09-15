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
change keep loading, but a stored old value cannot be folded onto one half.
The old mapper computed ``col_384 = (col - 1) * 2 + 1 + col_offset`` with
``col_offset`` 0 for ``A1``/``B1`` and 1 for ``A2``/``B2`` (read back with
``git show 4d38efe2~1:kuma_core/kuro/plate_quadrant.py``), so ``A1``/``B1``
occupied the odd columns 1, 3 .. 23 and ``A2``/``B2`` the even columns
2, 4 .. 24. **All four spanned the full plate width.** Measured: of the 192
wells one old forward/reverse pair occupied, 96 fall in the new left half and
96 in the new right half. An old value therefore marks part of both halves as
spent while pointing at no half of its own, which is what
:func:`fold_persisted_placement` encodes:

* in ``used_quadrants`` an old value expands to ``["A1", "A13"]``, because
  neither half can take a fresh 192-well round without landing on primers that
  are already there. Refusing is the direction this module prefers;
* in ``quadrant`` an old value is dropped to "nothing selected", because
  folding it onto a half would move every source well silently (old ``A2`` was
  384 ``A3`` and is 384 ``A2`` now; old ``H12`` was ``O23`` and is ``O12``).
  The operator picks a half again.

``A1`` is ambiguous on its own: it names a half now and named an odd-column
interleaved set before. It is read as the new half, because the opposite
reading would mark every project this version saves as full. A stored
placement counts as old only when ``A2``, ``B1`` or ``B2`` appears in its
``quadrant`` or in its ``used_quadrants``, and then every value in it is read
the old way. (사실) The pre-change picker toggled the four used-quadrant
checkboxes independently (``git show
4d38efe2~1:src/components/widgets/PlateQuadrantPicker.tsx``), so an old project
really can carry ``["A1"]`` with no partner value, and that case cannot be told
apart from a current one.

Which halves are already spent on a part-used plate is not tracked here. The
operator states it, because the plate is a physical object this program never
sees and a stale guess is worse than a question.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

_ROWS_96 = "ABCDEFGH"
_ROWS_384 = "ABCDEFGHIJKLMNOP"

#: The two wells a round can start from, in the order the UI offers them.
QUADRANTS: tuple[str, ...] = ("A1", "A13")

#: half -> 384 column offset.
_COL_OFFSETS: dict[str, int] = {"A1": 0, "A13": 12}

#: Values only a project saved before the half layout can carry. ``A1`` is not
#: one of them: it is a current half name too, and the module docstring says
#: why the current reading wins. Seeing any of these dates the whole stored
#: placement.
LEGACY_QUADRANTS: frozenset[str] = frozenset({"A2", "B1", "B2"})


class PersistedPlacement(NamedTuple):
    """What a stored Echo placement means under the half layout.

    Attributes:
        quadrant: Half this round takes, or ``None`` when nothing usable was
            stored and the operator has to pick again.
        used_quadrants: Halves that are spent, in ``QUADRANTS`` order.
        legacy_seen: Every value of a placement that predates the half layout,
            in the order it was read (the ``quadrant`` first) and including an
            ``A1`` that sits beside an old value, since that ``A1`` is an old
            name too. Empty for a placement this version wrote. Callers report
            it rather than re-deriving the rule.
    """

    quadrant: str | None
    used_quadrants: list[str]
    legacy_seen: tuple[str, ...]


def fold_persisted_placement(
    quadrant: str | None,
    used_quadrants: Sequence[str] | None = None,
) -> PersistedPlacement:
    """Read a stored Echo placement. This function is the rule.

    Both fields are read together, because one old value dates the whole
    placement: ``quadrant="B2"`` with ``used_quadrants=["A1"]`` is an old
    project, and that ``A1`` is an odd-column interleaved set rather than the
    left half.

    An old placement yields ``(None, ["A1", "A13"], <old values>)``: every old
    value spanned the full plate width, so both halves hold primers and no half
    is a legitimate selection. A current placement passes through unchanged,
    with unknown strings dropped and halves de-duplicated into ``QUADRANTS``
    order.

    Anything that reads a saved project, in this process or in the UI, mirrors
    this function instead of testing the stored strings itself.
    """
    target_raw = None if quadrant is None else quadrant.strip().upper()
    spent_raw = [value.strip().upper() for value in (used_quadrants or [])]
    names = ([] if target_raw is None else [target_raw]) + spent_raw

    if any(name in LEGACY_QUADRANTS for name in names):
        # 한 값이라도 옛 이름이면 그 placement 전체가 옛 것이다. 같이 저장된
        # "A1" 도 좌측 절반이 아니라 홀수 열 집합을 뜻하므로 함께 보고한다.
        return PersistedPlacement(None, list(QUADRANTS), tuple(names))

    spent = {name for name in spent_raw if name in QUADRANTS}
    return PersistedPlacement(
        target_raw if target_raw in QUADRANTS else None,
        [half for half in QUADRANTS if half in spent],
        (),
    )


def validate_quadrant(quadrant: str) -> str:
    """Return the canonical half name, or raise for anything else.

    A value that predates the half layout is refused here rather than folded.
    It names no half (see the module docstring) and folding it onto one would
    move every source well without saying so. Loading a saved project does not
    come through here, it comes through :func:`fold_persisted_placement`, which
    is why refusing is safe for an old project.
    """
    name = quadrant.strip().upper()
    if name in LEGACY_QUADRANTS:
        raise ValueError(
            f"Quadrant {quadrant!r} predates the source-plate half layout and "
            f"names no half of it, because it spanned the full plate width. "
            f"Select one of {', '.join(QUADRANTS)} for this round."
        )
    if name not in QUADRANTS:
        raise ValueError(
            f"Unknown quadrant {quadrant!r}. Expected one of {', '.join(QUADRANTS)}."
        )
    return name


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
    placement = fold_persisted_placement(None, used_quadrants)
    spent = set(placement.used_quadrants)

    if target in spent:
        free = [q for q in QUADRANTS if q not in spent]
        # 어디서 온 소진인지 문구로 갈라 둔다. 작업자가 입력한 절반이면 자기가 한
        # 선택이고, 옛 값에서 온 것이면 그 라운드가 양쪽 절반에 걸쳐 있었다는
        # 뜻이라 다시 고를 수 있는 절반이 아예 없다. 같은 문장이면 작업자는 왜
        # 둘 다 막혔는지 알 수 없다.
        origin = (
            f"folded from the stored value(s) {', '.join(placement.legacy_seen)}, "
            f"which predate the half layout and spanned the full plate width"
            if placement.legacy_seen
            else "stated for this plate"
        )
        raise ValueError(
            f"Quadrant {target} already used on this plate ({origin}). "
            + (
                f"Still free: {', '.join(free)}."
                if free
                else "No quadrant is free; this plate is full."
            )
        )
    return target


__all__ = [
    "LEGACY_QUADRANTS",
    "QUADRANTS",
    "PersistedPlacement",
    "check_quadrants_available",
    "fold_persisted_placement",
    "quadrant_wells",
    "to_384_well",
    "validate_quadrant",
]
