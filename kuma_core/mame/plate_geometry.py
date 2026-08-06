"""The plate every placement rule in MAME is written against, in one place.

A 96-well plate is 8 rows by 12 columns, and the combinatorial custom barcode
names a well as ``{R}_{F}``: the reverse index is the row (1..8) and the forward
index is the column (1..12). Every mapping in the codebase is built on that,
directly or through ``seq = (F - 1) * 8 + R``:

  - ``kuma_core/mame/export/well_mapper.py`` ``seq_to_well`` / ``well_to_seq``
  - ``kuma_core/mame/export/nb_label.py`` ``well_sort_key``
  - ``kuma_core/mame/export/excel_writer.py`` ``_custom_barcode_to_seq``
  - ``kuma_core/mame/export/janus_mapping.py`` (its own copy of the same sum)
  - ``python-core/sidecar_mame/handlers/export.py`` (a third copy)
  - ``kuma_core/mame/layout.py`` ``build_draft_layout``

The numbers used to be written out at each of those sites, which made the
assumption invisible: nothing anywhere checked that the barcode file being read
actually describes 8 reverse and 12 forward seeds. A file with a different shape
was not refused. It ran, and ``_custom_barcode_to_seq`` returned ``None`` for
every well outside the 8x12 box, whose well id then went into the workbook as an
empty string. An operator reading that sheet sees wells with no coordinate and
has no way to tell it from a read failure.

So the geometry is stated once here, and :func:`check_barcode_layout` is what a
caller runs before a multi-minute demux to find out whether the file it is about
to read fits (2026-08-06).

:class:`PlateAddressing` is the second half of that: the copies did not only
repeat the numbers, they repeated two *choices* that had no name anywhere. Which
barcode axis is the plate row, and whether the plate fills down a column or
across a row. Both were spelled as arithmetic (``(F - 1) * 8 + R``) in four
places, so a reader could not tell a deliberate convention from a transcription,
and a test written against a diagonal token such as ``3_3`` agrees with either
reading of the first choice while a test that only checks well labels agrees
with either reading of the second. Naming them makes both testable:
``token_to_seq("2_5")`` is 34 under the convention MAME uses and 13 under the
swapped axis, and it is 34 against 17 for the two fill orders, while
``seq_to_well`` returns ``B5`` for both fill orders and so proves nothing on its
own.

:data:`DEFAULT_ADDRESSING` is the convention, and it is the only one MAME has:
row is the reverse index, origin A1, filling down each column. These are values
in the code so the assumption can be stated and asserted, NOT settings. Nothing
reads them from a file or a dialog, and they must not be surfaced as a control:
the plate convention is a property of how the bench prepares the barcodes, not
of a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Rows on the plate, and therefore the highest reverse-barcode index.
PLATE_ROWS = 8
#: Columns on the plate, and therefore the highest forward-barcode index.
PLATE_COLS = 12
#: Wells on the plate. The ceiling on any layout MAME can describe.
PLATE_CAPACITY = PLATE_ROWS * PLATE_COLS

#: The reverse barcode index is the plate row (the convention MAME uses).
ROW_AXIS_REVERSE = "reverse"
#: The forward barcode index is the plate row (the swapped reading).
ROW_AXIS_FORWARD = "forward"
_ROW_AXES = (ROW_AXIS_REVERSE, ROW_AXIS_FORWARD)

#: Fill down each column before moving right: A1, B1, ... H1, A2 (MAME uses this).
TRAVERSAL_COLUMN = "column"
#: Fill across each row before moving down: A1, A2, ... A12, B1.
TRAVERSAL_ROW = "row"
_TRAVERSALS = (TRAVERSAL_COLUMN, TRAVERSAL_ROW)


@dataclass(frozen=True)
class PlateAddressing:
    """How a ``{R}_{F}`` barcode token becomes a well on this plate.

    Two decisions, each previously implicit in arithmetic repeated at four call
    sites:

    ``row_axis``
        Which half of the token is the row. ``"reverse"`` reads ``{R}_{F}`` as
        (row, column); ``"forward"`` reads it as (column, row).
    ``traversal``
        Which direction the sequence index runs. ``"column"`` walks down a
        column before moving right; ``"row"`` walks across a row before moving
        down.

    The origin is A1 in both cases: row 1 is ``A`` and column 1 is ``1``.

    ``rows`` and ``cols`` are the plate itself and are not a campaign parameter.
    A campaign larger than one plate is split across plates, which MAME
    separates by native barcode, so a wider grid is not what a bigger campaign
    needs.
    """

    row_axis: str = ROW_AXIS_REVERSE
    traversal: str = TRAVERSAL_COLUMN
    rows: int = PLATE_ROWS
    cols: int = PLATE_COLS

    def __post_init__(self) -> None:
        if self.row_axis not in _ROW_AXES:
            raise ValueError(
                f"row_axis must be one of {_ROW_AXES}; got {self.row_axis!r}"
            )
        if self.traversal not in _TRAVERSALS:
            raise ValueError(
                f"traversal must be one of {_TRAVERSALS}; got {self.traversal!r}"
            )

    @property
    def capacity(self) -> int:
        """Wells on the plate, and the ceiling on any sequence index."""
        return self.rows * self.cols

    @property
    def reverse_axis_size(self) -> int:
        """How many reverse seeds a full barcode set carries under this reading."""
        return self.rows if self.row_axis == ROW_AXIS_REVERSE else self.cols

    @property
    def forward_axis_size(self) -> int:
        """How many forward seeds a full barcode set carries under this reading."""
        return self.cols if self.row_axis == ROW_AXIS_REVERSE else self.rows

    def token_to_rc(self, token: str) -> tuple[int, int] | None:
        """``{R}_{F}`` -> ``(row, col)``, or ``None`` when it names no well.

        ``None`` covers every shape the plate cannot place: a token that is not
        two integers, and a pair that lands off the grid.
        """
        parts = token.split("_")
        if len(parts) != 2:
            return None
        try:
            r = int(parts[0])
            f = int(parts[1])
        except ValueError:
            return None
        row, col = (r, f) if self.row_axis == ROW_AXIS_REVERSE else (f, r)
        if not (1 <= row <= self.rows and 1 <= col <= self.cols):
            return None
        return row, col

    def rc_to_token(self, row: int, col: int) -> str:
        """``(row, col)`` -> the ``{R}_{F}`` token a producer writes for it."""
        r, f = (row, col) if self.row_axis == ROW_AXIS_REVERSE else (col, row)
        return f"{r}_{f}"

    def rc_to_seq(self, row: int, col: int) -> int:
        """``(row, col)`` -> 1-based sequence index under this traversal."""
        if self.traversal == TRAVERSAL_COLUMN:
            return (col - 1) * self.rows + row
        return (row - 1) * self.cols + col

    def seq_to_rc(self, seq: int) -> tuple[int, int]:
        """1-based sequence index -> ``(row, col)``. Raises off the plate."""
        if not 1 <= seq <= self.capacity:
            raise ValueError(f"seq must be in [1, {self.capacity}]; got {seq}")
        if self.traversal == TRAVERSAL_COLUMN:
            return (seq - 1) % self.rows + 1, (seq - 1) // self.rows + 1
        return (seq - 1) // self.cols + 1, (seq - 1) % self.cols + 1

    def token_to_seq(self, token: str) -> int | None:
        """``{R}_{F}`` -> 1-based sequence index, or ``None`` when unplaceable."""
        rc = self.token_to_rc(token)
        if rc is None:
            return None
        return self.rc_to_seq(*rc)

    def seq_to_well(self, seq: int) -> str:
        """1-based sequence index -> well label, e.g. ``34`` -> ``"B5"``.

        Not a discriminator on its own: both traversals name the same well for
        the same token, they only disagree about the index in between.
        """
        row, col = self.seq_to_rc(seq)
        return f"{chr(ord('A') + row - 1)}{col}"

    def well_to_seq(self, well: str) -> int:
        """Well label -> 1-based sequence index. Raises on anything off the plate."""
        well = well.strip().upper()
        if len(well) < 2:
            raise ValueError(f"invalid well label: {well!r}")
        row_char = well[0]
        col_str = well[1:]
        if not ("A" <= row_char <= chr(ord("A") + self.rows - 1)):
            raise ValueError(f"invalid row in well: {well!r}")
        if not col_str.isdigit():
            raise ValueError(f"invalid column in well: {well!r}")
        col_num = int(col_str)
        if not 1 <= col_num <= self.cols:
            raise ValueError(f"column out of range in well: {well!r}")
        return self.rc_to_seq(ord(row_char) - ord("A") + 1, col_num)

    def sort_key(self, token: str) -> tuple[int, int]:
        """Sort key monotonic in :meth:`token_to_seq`, for a ``{R}_{F}`` token.

        Deliberately more forgiving than :meth:`token_to_seq`: this orders rows
        for display, and a token it cannot read sorts first rather than removing
        the row from the sheet. Missing or non-numeric parts count as 0, and
        parts are compared as numbers so ``1_2`` precedes ``1_10``.
        """
        parts = token.split("_")
        r = int(parts[0]) if len(parts) > 1 and parts[0].isdigit() else 0
        f = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        row, col = (r, f) if self.row_axis == ROW_AXIS_REVERSE else (f, r)
        return (col, row) if self.traversal == TRAVERSAL_COLUMN else (row, col)


#: The convention MAME uses, and the only one it has. Row is the reverse index,
#: origin A1, filling down each column. Not a setting: see the module docstring.
DEFAULT_ADDRESSING = PlateAddressing()


def token_to_seq(token: str) -> int | None:
    """:meth:`PlateAddressing.token_to_seq` under :data:`DEFAULT_ADDRESSING`."""
    return DEFAULT_ADDRESSING.token_to_seq(token)


def seq_to_well(seq: int) -> str:
    """:meth:`PlateAddressing.seq_to_well` under :data:`DEFAULT_ADDRESSING`."""
    return DEFAULT_ADDRESSING.seq_to_well(seq)


def well_to_seq(well: str) -> int:
    """:meth:`PlateAddressing.well_to_seq` under :data:`DEFAULT_ADDRESSING`."""
    return DEFAULT_ADDRESSING.well_to_seq(well)


def sort_key(token: str) -> tuple[int, int]:
    """:meth:`PlateAddressing.sort_key` under :data:`DEFAULT_ADDRESSING`."""
    return DEFAULT_ADDRESSING.sort_key(token)


def norm_well(well: str) -> str:
    """Zero-pad a well label: ``"A2"`` -> ``"A02"``, ``"A02"`` -> ``"A02"``.

    Independent of the addressing: a label is padded the same way whichever
    axis produced it. Lives here so the one function that decides what a well is
    called is beside the one that decides where it is.
    """
    well = str(well).strip().upper()
    if len(well) >= 2 and well[1:].isdigit():
        return f"{well[0]}{int(well[1:]):02d}"
    return well


@dataclass(frozen=True)
class BarcodeLayoutReport:
    """Whether a barcode set fits the plate, and what does not fit if it fails."""

    #: Reverse-barcode indices read from the file, ascending.
    r_indices: tuple[int, ...] = ()
    #: Forward-barcode indices read from the file, ascending.
    f_indices: tuple[int, ...] = ()
    #: Indices past the plate: ``("R", 9)`` for a ninth row, ``("F", 13)`` for a
    #: thirteenth column. These are the wells that would lose their coordinate.
    out_of_range: tuple[tuple[str, int], ...] = ()
    #: Indices missing from an otherwise contiguous run, e.g. an F set of
    #: 1,2,4 reports 3. A gap is not fatal, but it means fewer wells than the
    #: count suggests, so it is reported rather than left for the operator to
    #: notice in the workbook.
    gaps: tuple[tuple[str, int], ...] = field(default=())

    @property
    def fits(self) -> bool:
        """True when every index lands on the plate."""
        return not self.out_of_range

    @property
    def describable_wells(self) -> int:
        """Wells this set can actually name, i.e. the in-range combinations."""
        r_ok = sum(1 for i in self.r_indices if 1 <= i <= PLATE_ROWS)
        f_ok = sum(1 for i in self.f_indices if 1 <= i <= PLATE_COLS)
        return r_ok * f_ok


def check_barcode_layout(
    r_indices: list[int] | tuple[int, ...],
    f_indices: list[int] | tuple[int, ...],
) -> BarcodeLayoutReport:
    """Does this barcode set describe wells on an 8x12 plate?

    ``r_indices`` and ``f_indices`` are the numeric suffixes read off the
    barcode rows (``<prefix>_r_<n>`` / ``<prefix>_f_<n>``). Order does not
    matter; duplicates are collapsed.

    A set that does not fit is not repaired here. Which axis the operator meant
    to be the row is not a guess this layer can make, and the file is the only
    place that can say it.
    """
    r_sorted = tuple(sorted(set(int(i) for i in r_indices)))
    f_sorted = tuple(sorted(set(int(i) for i in f_indices)))

    out: list[tuple[str, int]] = []
    out.extend(("R", i) for i in r_sorted if i < 1 or i > PLATE_ROWS)
    out.extend(("F", i) for i in f_sorted if i < 1 or i > PLATE_COLS)

    gaps: list[tuple[str, int]] = []
    for axis, seen in (("R", r_sorted), ("F", f_sorted)):
        if not seen:
            continue
        for i in range(1, max(seen) + 1):
            if i not in seen:
                gaps.append((axis, i))

    return BarcodeLayoutReport(
        r_indices=r_sorted,
        f_indices=f_sorted,
        out_of_range=tuple(out),
        gaps=tuple(gaps),
    )


__all__ = [
    "PLATE_ROWS",
    "PLATE_COLS",
    "PLATE_CAPACITY",
    "ROW_AXIS_REVERSE",
    "ROW_AXIS_FORWARD",
    "TRAVERSAL_COLUMN",
    "TRAVERSAL_ROW",
    "PlateAddressing",
    "DEFAULT_ADDRESSING",
    "token_to_seq",
    "seq_to_well",
    "well_to_seq",
    "sort_key",
    "norm_well",
    "BarcodeLayoutReport",
    "check_barcode_layout",
]
