"""Which custom barcodes a campaign uses, well by well.

The combinatorial barcode is ``{R}_{F}``, decided by where a sample sits: the
plate row picks the reverse seed and the column picks the forward one. Nothing
stated that pairing anywhere an operator could read it before pipetting. The
package written at barcode setup lists the twenty primers (twelve forward, eight
reverse) with no plate in it, the sample-map template that once carried a
per-well sheet is gone, and ``custom_barcode`` appears only on the workbook a
finished run writes, which is a record of what was sequenced rather than a plan
for what to sequence.

That was tolerable while every campaign filled the leading wells: the pairing
was "read the plate in column-major order" and an operator could do it in their
head. A declared selection breaks that. Wells A1, B1 and B3 use R1/R2 and F1/F3
and skip A3 entirely, and reading that off a grid is exactly the kind of
transcription this codebase keeps finding mistakes in.

So the pairing is computed from the same addressing the run scores with
(``plate_geometry.DEFAULT_ADDRESSING``), never from a second copy of the rule.
The primer NAMES are read from the barcode workbook when one is given, because
a name is what an operator picks a tube by; sequences stay in that workbook
rather than being copied here, so there is one place to correct if a seed
changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kuma_core.mame.plate_geometry import (
    DEFAULT_ADDRESSING,
    seq_to_well,
    well_to_seq,
)


@dataclass(frozen=True)
class WorklistRow:
    """One occupied well and the barcode pair it is read with."""

    #: Well label, not zero-padded, as the rest of the layout writes it.
    well: str
    #: What sits in the well: a ``mutant_id``, or ``"WT"`` for the control.
    sample: str
    #: The ``{R}_{F}`` token the demux matcher files this well under.
    custom_barcode: str
    #: 1-based reverse (row) seed index, and its name when a workbook gave one.
    reverse_index: int
    reverse_name: str | None
    #: 1-based forward (column) seed index, and its name when a workbook gave one.
    forward_index: int
    forward_name: str | None


@dataclass(frozen=True)
class BarcodeWorklist:
    """The barcode pairs one campaign uses, and the seeds it needs to prepare."""

    #: One row per occupied well, in plate order.
    rows: list[WorklistRow] = field(default_factory=list)
    #: Distinct reverse seed indices in use, ascending. The subset of the eight
    #: an operator actually has to lay out for this campaign.
    reverse_indices: list[int] = field(default_factory=list)
    #: Distinct forward seed indices in use, ascending.
    forward_indices: list[int] = field(default_factory=list)
    #: Seed indices a row needs that the workbook does not carry, as
    #: ``"F5"``/``"R3"`` labels. Reported rather than raised: a worklist that
    #: names the wells is still worth having, and a missing seed is a fact about
    #: the workbook the operator has to see rather than a reason to hand back
    #: nothing.
    missing_seeds: list[str] = field(default_factory=list)


def _name_at(axis: list[tuple[str, str]], index: int) -> str | None:
    """The seed name at a 1-based index, or ``None`` past the end of the axis.

    ``load_barcode_prefixes`` sorts by index and keeps position, so position
    *i* is seed *i + 1* for a workbook numbered without gaps. A gapped workbook
    is a defect ``check_barcode_layout`` refuses before a run starts, and this
    reads the same list rather than a second interpretation of it.
    """
    if 1 <= index <= len(axis):
        return axis[index - 1][0]
    return None


def build_barcode_worklist(
    layout: dict[str, str],
    reverse_seeds: list[tuple[str, str]] | None = None,
    forward_seeds: list[tuple[str, str]] | None = None,
) -> BarcodeWorklist:
    """Pair every occupied well with the barcode the run reads it under.

    ``layout`` is the placed ``{well: sample}`` map, so a declared selection has
    already been applied and the wells this campaign left empty are simply not
    in it. Passing the draft unchanged gives the whole plate, which is what a
    run that declares nothing uses.

    The seed lists are what ``load_barcode_prefixes`` returns, reverse first.
    Both are optional: without them the pairing is still complete (it comes from
    the plate, not the workbook) and the name columns come back ``None``.
    """
    reverse = reverse_seeds or []
    forward = forward_seeds or []

    rows: list[WorklistRow] = []
    reverse_used: set[int] = set()
    forward_used: set[int] = set()
    missing: set[str] = set()

    for well, sample in sorted(layout.items(), key=lambda kv: well_to_seq(kv[0])):
        row, col = DEFAULT_ADDRESSING.seq_to_rc(well_to_seq(well))
        token = DEFAULT_ADDRESSING.rc_to_token(row, col)
        # Read back off the token rather than deciding which of (row, col) is
        # the reverse axis a second time. That decision belongs to the
        # addressing, and a copy of it here would be a copy that can drift.
        r_index, f_index = (int(part) for part in token.split("_"))
        r_name = _name_at(reverse, r_index)
        f_name = _name_at(forward, f_index)
        if reverse and r_name is None:
            missing.add(f"R{r_index}")
        if forward and f_name is None:
            missing.add(f"F{f_index}")
        reverse_used.add(r_index)
        forward_used.add(f_index)
        rows.append(
            WorklistRow(
                well=seq_to_well(well_to_seq(well)),
                sample=sample,
                custom_barcode=token,
                reverse_index=r_index,
                reverse_name=r_name,
                forward_index=f_index,
                forward_name=f_name,
            )
        )

    return BarcodeWorklist(
        rows=rows,
        reverse_indices=sorted(reverse_used),
        forward_indices=sorted(forward_used),
        missing_seeds=sorted(missing),
    )


#: Column order of the csv. Stated once so the writer and its test cannot
#: disagree about it, and so a reader can see the sheet without running one.
WORKLIST_HEADER = (
    "well",
    "sample",
    "custom_barcode",
    "reverse_index",
    "reverse_primer",
    "forward_index",
    "forward_primer",
)


def write_barcode_worklist_csv(worklist: BarcodeWorklist, output: Path) -> Path:
    """Write ``worklist`` as a csv and return the path it landed on.

    csv rather than xlsx because this is a list an operator reads at the bench
    or pastes into a liquid handler sheet, and every other bench list this app
    writes (the pick list, the robot sheet) is a csv for the same reason.
    """
    import csv

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(WORKLIST_HEADER)
        for row in worklist.rows:
            writer.writerow(
                [
                    row.well,
                    row.sample,
                    row.custom_barcode,
                    row.reverse_index,
                    row.reverse_name or "",
                    row.forward_index,
                    row.forward_name or "",
                ]
            )
    return output


__all__ = [
    "BarcodeWorklist",
    "WORKLIST_HEADER",
    "WorklistRow",
    "build_barcode_worklist",
    "write_barcode_worklist_csv",
]
