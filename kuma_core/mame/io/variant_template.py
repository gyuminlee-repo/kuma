"""The blank variant list MAME hands out, with every well already written in.

The expected-variant input has been an ordered list and nothing else: row 1 is
the first well, row 2 the second, and the plate order lives only in the head of
whoever typed it. Nothing in the file says which well a row means, so a list
written one row short, or sorted in a spreadsheet, places every later mutant in
the wrong well and no layer downstream can tell. That is how 96 wells shifted at
once on 2026-08-04.

This module is the outbound half of the fix: the app issues a workbook whose
``well`` column is already filled in plate order, the operator types variants
beside the wells, and the same file comes back. The reader can then place a row
by the well it names rather than by where it happens to sit.

The wells are not computed here. :mod:`kuma_core.mame.plate_geometry` owns plate
address arithmetic, and a second copy of ``(col - 1) * 8 + row`` in this file
would be one more place for the two to drift apart, which is the disease this
work exists to cure. :func:`seq_to_well` is called for 1..96 and its answers are
written down as they come.

Two things about the sheet are deliberate:

``variant`` as the column header
    :mod:`kuma_core.mame.io.variant_list` recognises a variant column by name,
    and ``"variant"`` is the first candidate it tries, so a returned template is
    read without the operator naming a column.

anything but ``expected_mutations`` as the sheet name
    That name is the signal for a KURO export, and a workbook carrying it is
    routed to the strict ten-column reader. A template is not a KURO export, so
    it must not answer to that name.

The control is written into the template rather than left to the operator
because a run without one cannot be normalised, and the bench convention is that
it goes in the last well. Both the well and whether to write it at all are
arguments: the default is a convention, not a fact about a campaign.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from kuma_core.mame.plate_geometry import PLATE_CAPACITY, seq_to_well, well_to_seq

#: Sheet the template is written to. Deliberately not ``expected_mutations``:
#: see the module docstring.
TEMPLATE_SHEET = "variant_template"

#: Column headers, in order. ``variant`` is what ``variant_list`` looks for
#: first, and ``well`` is the address the reader places the row by.
TEMPLATE_HEADERS = ("well", "variant")

#: What goes in the control well. In ``kuma_core.mame.models.WT_LABELS``, which
#: is what makes the reader treat this row as the wild-type control.
CONTROL_LABEL = "WT"


def default_control_well() -> str:
    """The well the control lands in when the caller names none.

    The last well of the plate, which is the bench convention. Derived from the
    geometry rather than written out, so a plate of another shape would move it
    rather than silently disagree.
    """
    return seq_to_well(PLATE_CAPACITY)


def write_variant_template(
    output_path: Path | str,
    *,
    control_well: str | None = None,
    include_control: bool = True,
) -> Path:
    """Write a blank variant list with all 96 wells pre-filled to *output_path*.

    Args:
        output_path: Where the xlsx goes. Parent directories must exist.
        control_well: Which well carries the wild-type control. ``None`` uses
            :func:`default_control_well`. Ignored when *include_control* is
            false.
        include_control: Write the control row at all. False leaves every
            variant cell empty, for a campaign that places its own control.

    Returns:
        The path written, as a :class:`~pathlib.Path`.

    Raises:
        ValueError: When *control_well* names no well on the plate. Raised by
            :func:`kuma_core.mame.plate_geometry.well_to_seq`, so the template
            and the reader refuse the same labels.
    """
    control_seq: int | None = None
    if include_control:
        well = control_well if control_well is not None else default_control_well()
        # Not a local check: well_to_seq is the same function the reader uses to
        # place a row, so a label it refuses here is a label that would not have
        # been placeable anyway.
        control_seq = well_to_seq(well)

    workbook = Workbook()
    # A new Workbook always has one sheet, but ``active`` is typed as optional
    # because a workbook read off disk can have none. Creating one covers that
    # without an assert, which -O would strip.
    sheet = workbook.active if workbook.active is not None else workbook.create_sheet()
    sheet.title = TEMPLATE_SHEET
    sheet.append(list(TEMPLATE_HEADERS))
    for seq in range(1, PLATE_CAPACITY + 1):
        variant = CONTROL_LABEL if seq == control_seq else None
        sheet.append([seq_to_well(seq), variant])

    path = Path(output_path)
    workbook.save(path)
    workbook.close()
    return path


__all__ = [
    "TEMPLATE_SHEET",
    "TEMPLATE_HEADERS",
    "CONTROL_LABEL",
    "default_control_well",
    "write_variant_template",
]
