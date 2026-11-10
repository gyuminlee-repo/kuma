"""The clone plate is filled by residue position, and two paths have to say so.

The bench fills the clone plate in residue-position order. Two code paths model
that plate from the same workbook and used to derive the order differently:
``activity.numeric_id_decode.expected_variant_order`` sorted
(``canonical_plate_order``) while every caller of ``layout.build_draft_layout``
passed the sheet as written. On a workbook already in position order the two
agree and nothing shows. On any other workbook they name different wells for
the same clone, and nothing downstream compares them, so a numeric-ID decode
was read against a plate the verdicts never used.

``layout.build_clone_plate_layout`` is the one place the clone-plate order is
decided now, and this module is the mechanical check that the two paths cannot
drift apart again. It also pins the two rules that make the sorting safe: a file
that states its own wells is never reordered, and the control ordinal counts the
ordered list rather than the sheet rows.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from kuma_core.mame.activity.numeric_id_decode import expected_variant_order
from kuma_core.mame.io.variant_list import read_variant_source
from kuma_core.mame.layout import (
    WT_SAMPLE,
    WtPlacement,
    build_clone_plate_layout,
    build_draft_layout,
)

_HEADER = [
    "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
    "group_id", "primer_set_ref", "notation_type", "status",
]

#: Positions descending, which is the shape the agreement used to break on.
#: A combination clone is in the middle so the tie between its two positions is
#: pinned too: it is one clone and sorts at its lowest position.
_DESCENDING_SHEET = [
    ["M001", 233, "Y", "A", "TAT", "GCT", "", "Y233A", "substitution", "DESIGNED"],
    ["M002", 150, "L", "V", "CTG", "GTG", "M002", "L150V", "combo", "DESIGNED"],
    ["M002", 61, "E", "Y", "GAA", "TAT", "M002", "E61Y", "combo", "DESIGNED"],
    ["M003", 4, "K", "R", "AAA", "CGT", "", "K4R", "substitution", "DESIGNED"],
    ["WT", 0, "-", "-", "-", "-", "", "-", "wt", "DESIGNED"],
]


def _write(path: Path, rows: list[list[object]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append(_HEADER)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _write_stated_wells(path: Path, rows: list[list[object]]) -> Path:
    """A plain variant list carrying its own ``Well`` column."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "variants"
    ws.append(["Well", "Variant"])
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _padded(well: str) -> str:
    """``A1`` the layout spells, ``A01`` the activity path compares on."""
    return f"{well[0]}{int(well[1:]):02d}"


def test_the_plate_and_the_decode_order_name_the_same_well_for_every_clone(
    tmp_path,
) -> None:
    """The cross-path invariant. Before this it held only by luck of the sheet.

    Reverted to ``build_draft_layout``, the layout reads A1=M001, B1=M002,
    C1=M003 off the sheet while the decode order reads A01=M003, B01=M002,
    C01=M001 off the positions, so two of the three clones are decoded as each
    other.
    """
    path = _write(tmp_path / "descending.xlsx", _DESCENDING_SHEET)
    read = read_variant_source(path)

    draft = build_clone_plate_layout(
        read.expected,
        wt_ordinal=read.wt_ordinal,
        wells=read.wells,
        wt_well=read.wt_well,
    )
    order, warnings = expected_variant_order(path)

    plate = {
        _padded(well): occupant
        for well, occupant in draft.layout.items()
        if occupant != WT_SAMPLE
    }
    decoded = {well: mutant for _short, mutant, well in order}

    assert plate == decoded
    # The value both now agree on, stated rather than merely compared, so a
    # change that breaks both the same way still fails here.
    assert plate == {"A01": "M003", "B01": "M002", "C01": "M001"}
    # The only warnings on this path are about M00n carrying no EVOLVEpro
    # short form, which is a fact about the id rather than about the plate. The
    # slot is kept either way, so the comparison above still covers every clone.
    assert [w for w in warnings if "EVOLVEpro short form" not in w] == []


def test_the_sorted_plate_puts_the_control_in_the_well_it_shipped_in(
    tmp_path,
) -> None:
    """Sorting moves mutants, not the control, under the default placement."""
    path = _write(tmp_path / "descending.xlsx", _DESCENDING_SHEET)
    read = read_variant_source(path)

    draft = build_clone_plate_layout(
        read.expected, wt_ordinal=read.wt_ordinal
    )

    assert draft.layout["H12"] == WT_SAMPLE
    assert draft.dropped_mutant_ids == []


def test_a_file_that_states_its_wells_is_not_reordered(tmp_path) -> None:
    """``wells`` pairs with the rows positionally, so sorting would re-seat it.

    The same sheet in the same descending order, with the addresses written
    down: the clone plate function has to hand it over untouched, which is what
    makes a stated-well workbook mean what it says.
    """
    path = _write_stated_wells(
        tmp_path / "wells.xlsx",
        [["C3", "Y233A"], ["A1", "L150V"], ["H12", "K4R"]],
    )
    read = read_variant_source(path)
    assert read.wells is not None

    clone_plate = build_clone_plate_layout(
        read.expected,
        wt_ordinal=read.wt_ordinal,
        wells=read.wells,
        wt_well=read.wt_well,
    )
    primitive = build_draft_layout(
        read.expected,
        wt_ordinal=read.wt_ordinal,
        wells=read.wells,
        wt_well=read.wt_well,
    )

    assert clone_plate.layout == {"A1": "L150V", "C3": "Y233A", "H12": "K4R"}
    assert clone_plate.layout == primitive.layout


def test_the_control_ordinal_counts_the_ordered_list(tmp_path) -> None:
    """``wt_ordinal`` is an occupant ordinal of the PLATE, not a sheet row.

    Only ``AFTER_LAST_VARIANT`` consults it, so that is the placement this
    pins. The sheet lists its control second of three occupants; after ordering,
    the occupant it follows is the lowest position (``M003``), not the row above
    it in the file (``M001``). Reading the ordinal against the sheet instead
    would be a third order in the same run, agreeing with neither path.
    """
    path = _write(
        tmp_path / "wt_in_the_middle.xlsx",
        [
            ["M001", 233, "Y", "A", "TAT", "GCT", "", "Y233A", "substitution", "DESIGNED"],
            ["WT", 0, "-", "-", "-", "-", "", "-", "wt", "DESIGNED"],
            ["M002", 150, "L", "V", "CTG", "GTG", "", "L150V", "substitution", "DESIGNED"],
            ["M003", 4, "K", "R", "AAA", "CGT", "", "K4R", "substitution", "DESIGNED"],
        ],
    )
    read = read_variant_source(path)
    assert read.wt_ordinal == 2

    draft = build_clone_plate_layout(
        read.expected,
        wt_ordinal=read.wt_ordinal,
        wt_placement=WtPlacement.AFTER_LAST_VARIANT,
    )

    assert draft.layout == {"A1": "M003", "B1": WT_SAMPLE, "C1": "M002", "D1": "M001"}


def test_the_primitive_still_places_the_list_as_handed_over(tmp_path) -> None:
    """``build_draft_layout`` did not learn to sort.

    ``io.plate_order_check`` depends on it not sorting: it compares the clone
    plate against the KURO primer-plate sheet, whose wells are assigned by
    design-sheet index, and a disagreement there blocks the run.
    """
    path = _write(tmp_path / "descending.xlsx", _DESCENDING_SHEET)
    read = read_variant_source(path)

    draft = build_draft_layout(read.expected, wt_ordinal=read.wt_ordinal)

    assert [draft.layout[well] for well in ("A1", "B1", "C1")] == [
        "M001", "M002", "M003",
    ]
