"""Draft well-layout generator for MAME confirmation runs.

Given the list of designed expected mutations, produce a draft 96-well plate
layout.

Where an occupant goes has two possible sources, and the difference between them
is the whole point of this module. A source carrying a ``Well`` column states the
address of every occupant, and this generator places them there and computes
nothing. A source without one states only an order, so the generator assigns well
*j* to occupant *j* in column-major order (matching ``seq_to_well``) and decides
the control well from :class:`WtPlacement`.

The draft layout maps ``well_id -> sample_name`` and is consumed by the pipeline
as a ``well_layout`` override (highest-priority well->sample source). "WT" wells
carry an empty expected-mutation scope (a clean consensus PASSes; any observed
variant fails).

96 is the hard ceiling, not a tunable: the combinatorial custom barcode is
``{R}_{F}`` with ``R`` in 1..8 and ``F`` in 1..12 (12 fwd + 8 rev seeds), so a
97th well has no distinguishing sequence in the reads. One analyze run scores
one plate; native barcodes are replicates of that plate. A campaign larger than
96 mutants is therefore split across plates and run one plate at a time, not
folded into the native-barcode axis: that axis says which repeat of a well a
read came from, so a second plate's A1 would be scored as a repeat of the first
plate's A1. Anything this generator has to drop is reported rather than clamped
away in silence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

from kuma_core.mame.export.well_mapper import seq_to_well, well_to_seq
from kuma_core.mame.models import ExpectedMutation
from kuma_core.mame.plate_geometry import PLATE_CAPACITY as _PLATE_CAPACITY

#: The occupant name the control well carries. One spelling, because every
#: consumer of a layout tests for it by string.
WT_SAMPLE = "WT"


class WtPlacement(str, Enum):
    """Where the control well goes when the source does not name a well for it.

    Only the row-order path consults this. A source carrying a ``Well`` column
    states the control well itself, and nothing here overrides a stated fact.

    ``LAST_WELL``
        The control takes the last well of the plate (``H12``, sequence 96) and
        the mutants fill from ``A1`` in row order. Wells between the last mutant
        and ``H12`` stay empty.
    ``AFTER_LAST_VARIANT``
        The control takes the well right after the last mutant, or the ordinal
        the source stated when it carried a wild-type row of its own. This is
        what MAME did before 2026-08-18.
    ``NONE``
        No control well. The plate is mutants only.
    """

    LAST_WELL = "last_well"
    AFTER_LAST_VARIANT = "after_last_variant"
    NONE = "none"


#: The placement a caller gets without asking. Changed from
#: ``AFTER_LAST_VARIANT`` to ``LAST_WELL`` on 2026-08-18 by user decision.
#:
#: The old default only agreed with the bench on a full plate. A row ordinal is
#: not a well address: a 40-mutant list with its wild-type row on line 41 put
#: the control in ``A6``, while the bench convention pipettes it into ``H12``.
#: MAME then scored ``A6`` as the control and did not score ``H12`` at all, and
#: nothing in the result said so. Anchoring the control to the last well makes
#: the default agree with the convention, at the cost of moving the control of
#: an existing 40-mutant run from ``A6`` to ``H12``. That move is the intended
#: change, not a side effect: a caller that wants the old placement asks for
#: ``AFTER_LAST_VARIANT`` by name.
DEFAULT_WT_PLACEMENT = WtPlacement.LAST_WELL


def resolve_wt_placement(raw: str | None) -> WtPlacement:
    """The control-well policy a raw request value names, or the default.

    The one place ``wt_placement`` is validated: every RPC that accepts it
    (``mame.build_well_layout``, ``analyze``, ``mame.export_barcode_worklist``)
    reads the same param under the same name and must refuse the same unknown
    value with the same words, or a caller that got refused by one and then
    tried another would see the request silently succeed. ``raw`` is exactly
    what a params dict or a Pydantic field holds -- pulling the key out of a
    dict is the caller's job, not this function's, so it is not passed one.

    ``None`` takes :data:`DEFAULT_WT_PLACEMENT` rather than raising: an absent
    parameter is "the caller did not ask", which every surface here treats as
    the pre-2026-08-18 default, not as a malformed request.
    """
    if raw is None:
        return DEFAULT_WT_PLACEMENT
    try:
        return WtPlacement(raw)
    except ValueError:
        allowed = [p.value for p in WtPlacement]
        raise ValueError(f"wt_placement must be one of {allowed}; got {raw!r}") from None


@dataclass(frozen=True)
class DraftLayout:
    """A draft placement, or the refusal that stopped one from being built."""

    #: Insertion-ordered ``{well_id: sample_name}`` in column-major order, with the
    #: WT control at its own ordinal. Well labels are not zero-padded; the pipeline
    #: normalises them. Empty when the set does not fit: a partial plate reads like
    #: a whole one, so nothing is placed rather than some of it.
    layout: dict[str, str]
    #: ``mutant_id`` values that do not fit alongside the WT control, in sheet
    #: order. Non-empty means nothing was placed and the draft cannot be used.
    dropped_mutant_ids: list[str] = field(default_factory=list)
    #: Wells the caller declared that no occupant took, in plate order. Only
    #: :func:`apply_well_selection` fills it; a draft that placed itself
    #: declared nothing, so the list is empty there.
    unused_wells: list[str] = field(default_factory=list)
    #: ``{well_id: sample_name}`` for draft occupants whose well the caller did
    #: not declare, in plate order. Placement is anchored to the plate, so
    #: leaving a well out drops what the draft put there rather than sliding
    #: the rest up. Only :func:`apply_well_selection` fills it.
    excluded_occupants: dict[str, str] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        """True when every mutant found a well.

        Says nothing about the control: a layout without one is a legitimate
        result now (a source that named no control well, or ``WtPlacement.NONE``),
        and :attr:`wt_well` is what answers that question.
        """
        return not self.dropped_mutant_ids

    @property
    def wt_well(self) -> str | None:
        """The control well, or ``None`` when this plate carries no control.

        Derived from the placement rather than stored beside it, so the two
        cannot disagree. That also makes it survive
        :func:`apply_well_selection`: narrowing a draft to a selection that
        leaves the control well out returns ``None`` here, which is the truth
        about the plate that ran.
        """
        for well, sample in self.layout.items():
            if sample == WT_SAMPLE:
                return well
        return None

    @property
    def has_wt_well(self) -> bool:
        """True when a control well is on this plate.

        Worth a name of its own because the answer used to be structurally
        always-true: the generator appended a control whether the file
        mentioned one or not, so nothing downstream had a reason to ask.
        """
        return self.wt_well is not None


def canonical_plate_order(
    expected_mutations: list[ExpectedMutation],
) -> list[ExpectedMutation]:
    """Order the designed mutants the way the bench fills the plate.

    Residue position ascending. Python sorts stably, so several substitutions at
    one position keep the KURO sheet order, which is the order the design was
    written in and therefore the only tie-break with a source of truth behind it.

    Measured against the 2026-03 campaign plate (95 mutants): position agrees for
    all 95 wells, and the sheet tie-break agrees at eight of the twelve positions
    carrying several substitutions. The four that differ (87, 267, 426, 552) are
    each a permutation inside one position, which is the shape a hand transcription
    slip takes rather than a different rule. Position 426 is the one already known
    to be mislabelled in the hand-written layout, so this ordering is the reason to
    stop hand-writing it, not a fit to it.
    """
    return sorted(expected_mutations, key=lambda m: m.position)


#: Wells one plate has left for mutants once the WT control takes its own.
MUTANT_CAPACITY = _PLATE_CAPACITY - 1


def build_draft_layout(
    expected_mutations: list[ExpectedMutation],
    wt_ordinal: int | None = None,
    *,
    wells: list[str] | None = None,
    wt_well: str | None = None,
    wt_placement: WtPlacement = DEFAULT_WT_PLACEMENT,
) -> DraftLayout:
    """Build a column-major draft layout, from stated wells or from row order.

    There are two sources a placement can come from, and they are not equal.

    **Stated wells.** ``wells`` is the well each mutation in
    ``expected_mutations`` was given by the file, and ``wt_well`` is the well
    the file gave the control (``None`` when it named none). This branch does no
    arithmetic at all: a well address is a fact the file states, and nothing
    here is entitled to move it. The plate holds 96 of them, not 95, because a
    control is only present when the file says so, and ``wt_placement`` is
    ignored for the same reason.

    **Row order.** ``wells`` is ``None``, so the file said nothing about wells
    and the reader passed the row ordinals it read instead. Occupant *j* takes
    well *j* (1-based, column-major via ``seq_to_well``), and ``wt_placement``
    decides where the control goes; see :class:`WtPlacement`. ``wt_ordinal`` is
    the 1-based occupant position of a wild-type row the source carried, and it
    is consulted only by ``AFTER_LAST_VARIANT``, the placement that treats a row
    ordinal as a well.

    The caller decides the mutant order. Pass :func:`canonical_plate_order`
    output to get the plate the bench actually fills; the list as given keeps
    KURO sheet order.

    Capacity on the row-order branch is decided on total occupancy (``N + 1``)
    BEFORE anything is placed, because ``N`` alone is the wrong question: 96
    mutants plus a control is 97 wells, and placing first and clamping
    afterwards asked ``seq_to_well`` for well 97. That ceiling holds for all
    three placements, ``NONE`` included: which mutants are on the plate must not
    depend on where the control sits, or the same list would fit or not fit
    depending on a setting. Over capacity, ``layout`` comes back empty and the
    mutants that do not fit are named in ``dropped_mutant_ids``. Nothing partial
    is returned: a truncated draft reads as a correct full plate to anyone
    looking at the rows, so every well past the cut would be mis-scored in
    silence.

    Raises:
        ValueError: when ``wells`` is given and does not have one entry per
            mutation. The two travel together out of the reader, so a length
            mismatch is a caller that re-ordered or filtered one of them, which
            would silently re-seat the plate.
    """
    if wells is not None:
        return _place_on_stated_wells(expected_mutations, wells, wt_well)

    n = len(expected_mutations)
    if n > MUTANT_CAPACITY:
        return DraftLayout(
            layout={},
            dropped_mutant_ids=[
                m.mutant_id for m in expected_mutations[MUTANT_CAPACITY:]
            ],
        )

    if wt_placement is WtPlacement.NONE:
        wt_seq: int | None = None
    elif wt_placement is WtPlacement.LAST_WELL:
        wt_seq = _PLATE_CAPACITY
    else:
        wt_seq = n + 1 if wt_ordinal is None else max(1, min(wt_ordinal, n + 1))

    # The first N wells the control does not take. This one expression covers
    # all three placements: LAST_WELL leaves 1..N free because N is at most 95,
    # AFTER_LAST_VARIANT opens a gap at its ordinal and pushes the rest down,
    # and NONE excludes nothing.
    mutant_seqs = [s for s in range(1, _PLATE_CAPACITY + 1) if s != wt_seq][:n]
    placed = dict(zip(mutant_seqs, (m.mutant_id for m in expected_mutations)))
    if wt_seq is not None:
        placed[wt_seq] = WT_SAMPLE
    return DraftLayout(
        layout={seq_to_well(seq): placed[seq] for seq in sorted(placed)}
    )


def _place_on_stated_wells(
    expected_mutations: list[ExpectedMutation],
    wells: list[str],
    wt_well: str | None,
) -> DraftLayout:
    """Place occupants on the wells the file named, in plate order.

    Nothing is inferred here and nothing can overflow: the reader has already
    refused a duplicate well and a well off the plate, so every entry names a
    distinct one of the 96 and there is no ordinal to run past the end. The only
    thing this adds is the ordering, because ``DraftLayout.layout`` promises
    column-major insertion order and a file lists its rows in whatever order the
    operator typed them.
    """
    if len(wells) != len(expected_mutations):
        raise ValueError(
            f"stated wells ({len(wells)}) and mutations "
            f"({len(expected_mutations)}) do not correspond. They come out of "
            "the reader as one list of pairs, so a mismatch means one of them "
            "was re-ordered or filtered on its own, which re-seats the plate."
        )
    placed = {
        well: mutation.mutant_id
        for well, mutation in zip(wells, expected_mutations)
    }
    if wt_well is not None:
        placed[wt_well] = WT_SAMPLE
    return DraftLayout(
        layout={well: placed[well] for well in sorted(placed, key=well_to_seq)}
    )


def normalise_selected_wells(selected_wells: Iterable[str]) -> list[str]:
    """Column-major, de-duplicated, plate-bounded well labels.

    The selection arrives as whatever the caller assembled, and the assignment
    rule ("occupant *i* goes to the *i*th selected well") only means something
    once the wells are in the plate order the bench fills. Sorting here rather
    than trusting the incoming order is what makes the frontend grid and the run
    agree without either of them having to preserve click order.

    Labels outside the plate are dropped. A caller that cares whether that
    happened compares the length it sent with the length it got back.
    """
    seen: dict[int, str] = {}
    for label in selected_wells:
        try:
            seq = well_to_seq(str(label).strip())
        except (ValueError, IndexError):
            continue
        if 1 <= seq <= _PLATE_CAPACITY and seq not in seen:
            seen[seq] = seq_to_well(seq)
    return [seen[seq] for seq in sorted(seen)]


def apply_well_selection(
    draft: DraftLayout,
    selected_wells: Iterable[str],
) -> DraftLayout:
    """Narrow a draft to the wells the operator declared, in place.

    A campaign smaller than the plate leaves wells empty, and which wells those
    are is a fact about the bench that no file states. Declaring them is the
    only way the run can know that a read arriving from one of them is a signal
    rather than a sample: an undeclared well is scored as whatever the draft
    happened to place there.

    The placement is the draft's own and the selection does not move it. Each
    occupant keeps the well ``build_draft_layout`` gave it, and declaring a
    subset says which of those wells this campaign actually filled: what sits in
    an undeclared well is not on the plate at all, so it comes back in
    ``excluded_occupants`` and is scored by nothing. Selecting the leading
    ``N + 1`` wells therefore reproduces the draft unchanged, which is what the
    default selection is, and selecting the whole plate does too.

    Re-seating was the older rule (occupant *i* took the *i*th declared well)
    and it is wrong on the bench: deselecting one well slid every later variant
    up one, so a plate the operator was looking at rearranged itself under a
    click that was meant to describe it. Anchoring to the draft is what makes
    the grid a picture of the plate rather than a queue.

    Neither direction is a refusal. Fewer declared wells than occupants is the
    ordinary case now (a partly filled plate), and the occupants left out are
    named. More wells than occupants is a declaration the run cannot use up,
    which is not on its own a mistake: an operator selecting the two columns
    they filled, or the whole plate out of habit, has said nothing false about
    the bench. So the surplus is named in ``unused_wells`` and the run proceeds.
    Silence was the wrong answer for the same reason it is everywhere else
    here: 96 wells selected against 31 occupants dropped 65 declarations with
    nothing on the result to say it happened.
    """
    wells = normalise_selected_wells(selected_wells)
    declared = set(wells)
    kept = {
        well: sample for well, sample in draft.layout.items() if well in declared
    }
    excluded = {
        well: sample for well, sample in draft.layout.items() if well not in declared
    }
    return DraftLayout(
        layout=kept,
        dropped_mutant_ids=list(draft.dropped_mutant_ids),
        unused_wells=[well for well in wells if well not in draft.layout],
        excluded_occupants=excluded,
    )


__all__ = [
    "MUTANT_CAPACITY",
    "DEFAULT_WT_PLACEMENT",
    "WT_SAMPLE",
    "DraftLayout",
    "WtPlacement",
    "apply_well_selection",
    "build_draft_layout",
    "canonical_plate_order",
    "normalise_selected_wells",
    "resolve_wt_placement",
]
