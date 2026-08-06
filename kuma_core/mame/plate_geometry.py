"""The plate every placement rule in MAME is written against, in one place.

A 96-well plate is 8 rows by 12 columns, and the combinatorial custom barcode
names a well as ``{R}_{F}``: the reverse index is the row (1..8) and the forward
index is the column (1..12). Every mapping in the codebase is built on that,
directly or through ``seq = (F - 1) * 8 + R``:

  - ``kuma_core/mame/export/well_mapper.py`` ``seq_to_well`` / ``well_to_seq``
  - ``kuma_core/mame/export/nb_label.py`` ``well_sort_key``
  - ``kuma_core/mame/export/excel_writer.py`` ``_custom_barcode_to_seq``
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
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Rows on the plate, and therefore the highest reverse-barcode index.
PLATE_ROWS = 8
#: Columns on the plate, and therefore the highest forward-barcode index.
PLATE_COLS = 12
#: Wells on the plate. The ceiling on any layout MAME can describe.
PLATE_CAPACITY = PLATE_ROWS * PLATE_COLS


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
    "BarcodeLayoutReport",
    "check_barcode_layout",
]
