"""Echo 384 source-plate halves, as a 96-head Zephyr can actually stamp them.

A 96-head sits on a 9 mm pitch and a 384-well plate is on 4.5 mm, so one stamp
reaches every other column. Rows are already doubled the same way: a 96-well
address ``<row><col>`` lands on 384 row ``2r`` for the forward primer and
``2r + 1`` for the reverse, so forward primers sit on rows A, C, E, G, I, K, M,
O and reverse primers on B, D, F, H, J, L, N, P. Columns follow
``col_384 = (col - 1) * 2 + 1 + col_offset`` with ``col_offset`` 0 or 1.

One round is therefore a column parity:

* ``A1`` is the odd columns 1, 3 ... 23,
* ``A2`` is the even columns 2, 4 ... 24.

Each is 12 columns over all 16 rows, 192 wells, 96 forward plus 96 reverse. The
two of them fill one plate, which is the "2 round primer set / 1 Echo source
plate" concept the campaign runs on.

Why two options and not four. Commit ``c285d5d6`` (#211, v0.14.0) offered A1,
A2, B1 and B2 and paired them with a ``paired_quadrant`` helper that sent
reverse primers to the partner (A1 to B1, A2 to B2). That made the row axis a
duplicate: A1 and B1 named the same round with forward and reverse swapped, as
did A2 and B2. The real degree of freedom is the column parity alone, and the
helper existed only to undo the duplication it introduced. Two options are the
whole choice, and forward and reverse need no separate placement value.

Counter-evidence exists and is recorded here on purpose. Sheet ``Echo mapping
file`` of the real worklist
``$WORKSPACE_ROOT/020.admin/projects/040.mapping_files_echo/``
``Project2-1. primer dispensing (Echo525).xlsx`` (parsed 2026-09-13: 190
transfers over 161 source wells) occupies columns 1-12 with no gap and touches
nothing in columns 13-24. Read literally that file states a round fills a
contiguous block of twelve columns: destination ``A2`` draws from source
``A2``, while the parity rule above puts that same transfer at source ``A3``.

On 2026-09-20 the operator confirmed that the interleaved layout is the correct
one, because the instrument itself cannot reach anything else in one stamp.
That statement governs this module and overrides the reading of the workbook.

**Why that workbook holds contiguous columns is (미확인).** It may record a
different dispensing method or a different instrument. Nothing available here
establishes which, and a guess must not be written down as though it were
established.

This geometry has flipped twice already. ``c285d5d6`` (#211, v0.14.0) put the
interleaved layout in, ``a9ad1472`` (#414, v0.16.61) replaced it with two
contiguous halves named ``A1`` and ``A13`` on the strength of the workbook, and
this module restores the interleaved layout as a two-way choice. A third flip
needs more than another reading of that workbook. It needs the operator to
state what the instrument does, because the workbook and the instrument have
already been seen to disagree.

Three vocabularies have used these names and they do not agree:

    stored   v0.14.0 - v0.16.60     v0.16.61 - v0.16.67   this release on
    ------   --------------------   -------------------   -----------------
    A1       odd columns, fwd rows  columns 1-12          odd columns
    B1       odd columns, rev rows  (never written)       (never written)
    A2       even columns, fwd      (legacy marker only)  even columns
    B2       even columns, rev      (never written)       (never written)
    A13      (never written)        columns 13-24         (never written)

The interleaved era and this one mean the same thing by ``A1`` and by ``A2``,
so those values pass through untouched. ``B1`` and ``B2`` name the same rounds
with the axes swapped, so they fold onto ``A1`` and ``A2`` and no coordinate
moves. Only the half era disagrees, and only ``A13`` says so on its own. A
stored ``A1`` from the half era is spelled exactly like a current one and is
separated by the saved app version, which this module never sees: it is handed
values rather than files, so that test lives in ``src/lib/echoQuadrant.ts``.

Which halves are already spent on a part-used plate is not tracked here. The
operator states it, because the plate is a physical object this program never
sees and a stale guess is worse than a question.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

_ROWS_96 = "ABCDEFGH"
_ROWS_384 = "ABCDEFGHIJKLMNOP"

#: The two column parities a round can take, in the order the UI offers them.
QUADRANTS: tuple[str, ...] = ("A1", "A2")

#: quadrant -> 384 column offset. 0 gives columns 1, 3 .. 23 and 1 gives
#: columns 2, 4 .. 24.
_COL_OFFSETS: dict[str, int] = {"A1": 0, "A2": 1}

#: Interleaved-era names for the rounds this module already has, written when
#: the picker also offered a row axis. ``B1`` was the odd columns seen from
#: their reverse rows and ``B2`` the even ones, so each folds onto its partner
#: and not one source well moves.
FOLDED_QUADRANTS: dict[str, str] = {"B1": "A1", "B2": "A2"}

#: Values only a project saved under the half layout (0.16.61 to the release
#: before this one) can carry. ``A1`` and ``A2`` are not among them: both are
#: current names too, and ``A2`` was merely a legacy marker there. Seeing
#: ``A13`` dates the whole stored placement.
LEGACY_QUADRANTS: frozenset[str] = frozenset({"A13"})


class PersistedPlacement(NamedTuple):
    """What a stored Echo placement means under the column-parity layout.

    Attributes:
        quadrant: Round this placement takes, or ``None`` when nothing usable
            was stored and the operator has to pick again.
        used_quadrants: Rounds that are spent, in ``QUADRANTS`` order.
        legacy_seen: Every value of a placement written under the half layout,
            in the order it was read (the ``quadrant`` first) and including an
            ``A1`` or ``A2`` that sits beside a half name, since those are half
            names too. Empty for anything this module can read without
            refusing, which includes a folded ``B1``. Callers report it rather
            than re-deriving the rule.
    """

    quadrant: str | None
    used_quadrants: list[str]
    legacy_seen: tuple[str, ...]


def fold_persisted_placement(
    quadrant: str | None,
    used_quadrants: Sequence[str] | None = None,
) -> PersistedPlacement:
    """Read a stored Echo placement. This function is the rule.

    Both fields are read together, because one half name dates the whole
    placement: ``quadrant="A13"`` with ``used_quadrants=["A1"]`` is a half-era
    project, and that ``A1`` is columns 1-12 rather than the odd columns.

    A half-era placement yields ``(None, ["A1", "A2"], <names>)``. Both parts
    of that need saying:

    * ``quadrant`` drops to "nothing selected". A block of twelve consecutive
      columns holds six odd columns and six even ones, so it corresponds to no
      parity and folding it onto one would move every source well without
      saying so. The operator picks again.
    * both rounds become spent. That same block sits on 48 of the 192 wells of
      each round, so neither is clean and refusing is the direction this module
      prefers.

    An interleaved-era ``B1`` or ``B2`` folds onto ``A1`` or ``A2`` instead of
    being refused. Those names denoted the very rounds this module has, seen
    from their reverse rows, so the fold moves no coordinate and needs nothing
    from the operator. It is therefore not reported in ``legacy_seen``.

    Anything else this version wrote passes through unchanged, with unknown
    strings dropped and rounds de-duplicated into ``QUADRANTS`` order. An empty
    placement stays empty: a project that never chose a round has nothing to
    date, and calling both rounds spent for it would invent a plate state the
    operator never stated.

    Anything that reads a saved project, in this process or in the UI, mirrors
    this function instead of testing the stored strings itself.
    """
    target_raw = None if quadrant is None else quadrant.strip().upper()
    spent_raw = [value.strip().upper() for value in (used_quadrants or [])]
    names = ([] if target_raw is None else [target_raw]) + spent_raw

    if any(name in LEGACY_QUADRANTS for name in names):
        # 한 값이라도 half 이름이면 그 placement 전체가 half 시절의 것이다. 같이
        # 저장된 "A1" 도 홀수 열이 아니라 1~12 열 블록을 뜻하므로 함께 보고한다.
        return PersistedPlacement(None, list(QUADRANTS), tuple(names))

    target = FOLDED_QUADRANTS.get(target_raw, target_raw) if target_raw else None
    spent = {
        FOLDED_QUADRANTS.get(name, name)
        for name in spent_raw
        if FOLDED_QUADRANTS.get(name, name) in QUADRANTS
    }
    return PersistedPlacement(
        target if target in QUADRANTS else None,
        [q for q in QUADRANTS if q in spent],
        (),
    )


def validate_quadrant(quadrant: str) -> str:
    """Return the canonical round name, or raise for anything else.

    A half name is refused here rather than folded. It corresponds to no column
    parity (see the module docstring) and folding it onto one would move every
    source well without saying so. An interleaved-era ``B1`` or ``B2`` is
    accepted and folded, because it names a round this module has. Loading a
    saved project does not come through here, it comes through
    :func:`fold_persisted_placement`.
    """
    name = quadrant.strip().upper()
    name = FOLDED_QUADRANTS.get(name, name)
    if name in LEGACY_QUADRANTS:
        raise ValueError(
            f"Quadrant {quadrant!r} is a source-plate half from v0.16.61 and "
            f"matches no column parity, because a block of twelve consecutive "
            f"columns covers part of both rounds. Select one of "
            f"{', '.join(QUADRANTS)} for this round."
        )
    if name not in _COL_OFFSETS:
        raise ValueError(
            f"Unknown quadrant {quadrant!r}. Expected one of {', '.join(QUADRANTS)}."
        )
    return name


def to_384_well(well_96: str, quadrant: str, *, reverse: bool = False) -> str:
    """Map a 96-well address into *quadrant* of a 384-well plate.

    The forward primer for 96 well ``A1`` is 384 ``A1`` in round A1 and ``A2``
    in round A2. Its reverse primer is one row below, ``B1`` and ``B2``. 96
    ``A2`` is 384 ``A3`` in round A1, one column skipped, and the far corner
    ``H12`` is ``O23``/``P23`` in round A1 and ``O24``/``P24`` in round A2.
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
    return f"{row_384}{(col - 1) * 2 + 1 + col_offset}"


def quadrant_wells(quadrant: str, *, reverse: bool | None = None) -> list[str]:
    """Every 384 well *quadrant* covers, in column-major 96-well order.

    ``reverse=False`` gives the 96 forward wells, ``reverse=True`` the 96
    reverse wells, and the default gives all 192 wells of the round.
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
    """Resolve the round to dispense into and refuse one that is already spent.

    Returns the canonical round name.

    Forward and reverse are not a separate choice: the reverse primer is always
    one row below its forward primer in the same column, so there is one thing
    to check. A part-used plate is the normal case when new plates are short:
    the operator says which rounds are gone and this refuses to dispense on top
    of them. Overwriting a filled round destroys the primers already in it, so
    this is an error rather than a warning.
    """
    target = validate_quadrant(quadrant)
    placement = fold_persisted_placement(None, used_quadrants)
    spent = set(placement.used_quadrants)

    if target in spent:
        free = [q for q in QUADRANTS if q not in spent]
        # 어디서 온 소진인지 문구로 갈라 둔다. 작업자가 입력한 round 면 자기가 한
        # 선택이고, half 이름에서 온 것이면 그 라운드가 양쪽에 걸쳐 있었다는
        # 뜻이라 다시 고를 수 있는 round 가 아예 없다. 같은 문장이면 작업자는 왜
        # 둘 다 막혔는지 알 수 없다.
        origin = (
            f"folded from the stored value(s) {', '.join(placement.legacy_seen)}, "
            f"source-plate halves from v0.16.61 that each cover part of both "
            f"rounds"
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
    "FOLDED_QUADRANTS",
    "LEGACY_QUADRANTS",
    "QUADRANTS",
    "PersistedPlacement",
    "check_quadrants_available",
    "fold_persisted_placement",
    "quadrant_wells",
    "to_384_well",
    "validate_quadrant",
]
