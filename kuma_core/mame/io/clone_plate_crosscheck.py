"""Does the clone plate the run fills sit where the primer plate says it does?

Two plates exist on the bench and only one of them is drafted by MAME. KURO
orders the primers into a source plate and writes those wells down on
``Fwd List``/``Fwd Plate``, assigning each one by design-sheet index
(``kuro.plate_mapper._assign_well``). The run then drafts the clone plate with
``layout.build_clone_plate_layout``, which since v0.16.85 orders the occupants by
residue position ascending because that is the order the bench pipettes in. The
two orders coincide only on an export already written in position order, so for
most workbooks well ``A2`` holds one mutant on the primer plate and another on
the clone plate.

``io.plate_order_check`` does not see this. It compares the primer plate against
``expected_mutations`` read in sheet order, which is the export's internal
consistency and not the plate the run scores; its own docstring says so. This
module is the missing comparison: the primer plate against
``build_clone_plate_layout``.

**It reports and it must never block.** A disagreement here is the normal state
of a design-ordered export, not a fault in one, and ten of the twelve workbooks
on hand are design-ordered. Blocking would refuse almost every real analyse run.
It is also not a disagreement either side can settle: which plate the two
numbers describe is a fact about the tubes in the rack, and nothing in the file
records whether the operator pipetted in sheet order or in position order.
Repairing it means changing which well KURO orders each primer into, which is a
decision about a physical ordering sheet. So the answer is a value the caller
can show and nothing else, which is why this does not reuse
``PlateOrderReport``: that type is wired to a validation error and a refusal, and
putting a reportable finding through it would weaken the refusal.

The wild-type control is left out, for the same reason
:mod:`kuma_core.mame.io.plate_order_check` leaves it out: a plate sheet lists
primers, the control has none, and its absence is not a disagreement.

The declared well selection is NOT an input here. A selection narrows a run and
never rearranges it (``layout.apply_well_selection``), so a well where the two
plates disagree disagrees whether or not that well is scored, and feeding the
selection in would hide the finding for exactly the wells the operator chose to
leave out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kuma_core.mame.io.plate_order_check import EXPECTED_SHEET, read_primer_plate
from kuma_core.mame.io.variant_list import read_variant_source
from kuma_core.mame.layout import (
    DEFAULT_WT_PLACEMENT,
    WT_SAMPLE,
    WtPlacement,
    build_clone_plate_layout,
)
from kuma_core.mame.plate_geometry import well_to_seq

#: Why a comparison did or did not happen. The strings travel to the frontend
#: unchanged, so each one is a reason an operator can be shown rather than a
#: flag that has to be interpreted.
#:
#: - ``"match"``: compared, every well agrees.
#: - ``"mismatch"``: compared, at least one well does not.
#: - ``"not_a_workbook"``: the path is missing or is not an xlsx.
#: - ``"no_expected_sheet"``: no ``expected_mutations`` sheet, so not a KURO export.
#: - ``"no_plate_sheet"``: no readable ``Fwd List``/``Fwd Plate``, so there is no
#:   primer plate to compare against.
#: - ``"unreadable"``: the workbook or its variant list could not be read. Every
#:   such refusal is already reported by the path that loads the file for the
#:   run, so it is a reason to stay quiet here rather than a second failure.
#: - ``"combination"``: the expected sheet carries a combination genotype. One
#:   clone then uses one primer pair per substitution, so a primer-plate well and
#:   a clone-plate well are no longer the same address and there is nothing to
#:   compare. ``io.plate_order_check._expected_layout`` refuses the same shape
#:   for the same reason.
#: - ``"stated_wells"``: the variant source states a ``Well`` column, so both
#:   sides take their addresses from the file.
#:   ``build_clone_plate_layout`` passes a stated placement through untouched
#:   (``layout.py``, ``if wells is None``), which makes this comparison identical
#:   to :func:`~kuma_core.mame.io.plate_order_check.check_plate_order` - a check
#:   that already runs and already blocks. Reporting a second result would claim
#:   an independent comparison that did not happen, so this says what it is
#:   instead.
#: - ``"over_capacity"``: the occupants do not fit on one plate, so the draft
#:   placed nothing and there is no clone plate to compare. The run refuses this
#:   workbook on its own.
CloneCrosscheckStatus = str


@dataclass(frozen=True)
class ClonePlateCrosscheckReport:
    """Where the primer plate and the run's clone plate put different clones."""

    #: One of the values documented on :data:`CloneCrosscheckStatus`.
    status: CloneCrosscheckStatus
    #: Which sheet supplied the primer plate, or ``None`` when none did.
    plate_sheet: str | None = None
    #: How many wells either side named, control well excluded. Zero unless a
    #: comparison ran.
    wells_compared: int = 0
    #: How many of those wells disagree. The full count, not the capped list.
    mismatch_count: int = 0
    #: ``(well, on_primer_plate, on_clone_plate)`` for the first few disagreeing
    #: wells in plate order. A side that places nothing in a well contributes an
    #: empty string.
    examples: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def compared(self) -> bool:
        """True when a comparison actually ran."""
        return self.status in {"match", "mismatch"}

    @property
    def reportable(self) -> bool:
        """True when there is a finding to show an operator."""
        return self.status == "mismatch"


def crosscheck_clone_plate(
    path: Path,
    *,
    sheet: str | None = None,
    variant_column: str | None = None,
    wt_placement: WtPlacement = DEFAULT_WT_PLACEMENT,
    max_examples: int = 5,
) -> ClonePlateCrosscheckReport:
    """Compare the primer plate in *path* against the clone plate a run would fill.

    ``sheet``, ``variant_column`` and ``wt_placement`` are the run's own
    arguments, forwarded so the clone plate compared here is the clone plate the
    run drafts. Reading the file some other way would make the answer a statement
    about a plate nobody builds, which is the fault this module was added to
    close rather than to repeat.

    This never raises and it never refuses anything. Every outcome, including a
    file it cannot read, comes back as a :class:`ClonePlateCrosscheckReport`
    whose ``status`` says which outcome it was.
    """
    path = Path(path)
    if path.suffix.lower() not in {".xlsx", ".xlsm"} or not path.exists():
        return ClonePlateCrosscheckReport(status="not_a_workbook")

    import openpyxl

    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - the openpyxl surface is broad
        return ClonePlateCrosscheckReport(status="unreadable")
    try:
        if EXPECTED_SHEET not in workbook.sheetnames:
            return ClonePlateCrosscheckReport(status="no_expected_sheet")
        plate, _duplicates, plate_sheet = read_primer_plate(workbook)
    except Exception:  # noqa: BLE001 - the openpyxl surface is broad
        return ClonePlateCrosscheckReport(status="unreadable")
    finally:
        workbook.close()

    if not plate:
        return ClonePlateCrosscheckReport(status="no_plate_sheet")

    try:
        read = read_variant_source(path, sheet=sheet, variant_column=variant_column)
    except Exception:  # noqa: BLE001 - every refusal is reported by the loading path
        return ClonePlateCrosscheckReport(status="unreadable", plate_sheet=plate_sheet)

    ids = [mutation.mutant_id for mutation in read.expected]
    if len(set(ids)) != len(ids):
        return ClonePlateCrosscheckReport(status="combination", plate_sheet=plate_sheet)
    if read.wells is not None:
        return ClonePlateCrosscheckReport(
            status="stated_wells", plate_sheet=plate_sheet
        )

    clone = build_clone_plate_layout(
        read.expected,
        wt_ordinal=read.wt_ordinal,
        wells=read.wells,
        wt_well=read.wt_well,
        wt_placement=wt_placement,
    )
    if not clone.layout:
        return ClonePlateCrosscheckReport(
            status="over_capacity", plate_sheet=plate_sheet
        )

    occupied = {
        well: sample for well, sample in clone.layout.items() if sample != WT_SAMPLE
    }
    control_wells = {
        well for well, sample in clone.layout.items() if sample == WT_SAMPLE
    }

    examples: list[tuple[str, str, str]] = []
    mismatch_count = 0
    compared = 0
    for well in sorted(set(plate) | set(occupied), key=well_to_seq):
        if well in control_wells:
            continue
        compared += 1
        on_plate = plate.get(well, "")
        on_clone = occupied.get(well, "")
        if on_plate == on_clone:
            continue
        mismatch_count += 1
        if len(examples) < max_examples:
            examples.append((well, on_plate, on_clone))

    return ClonePlateCrosscheckReport(
        status="mismatch" if mismatch_count else "match",
        plate_sheet=plate_sheet,
        wells_compared=compared,
        mismatch_count=mismatch_count,
        examples=examples,
    )


__all__ = [
    "CloneCrosscheckStatus",
    "ClonePlateCrosscheckReport",
    "crosscheck_clone_plate",
]
