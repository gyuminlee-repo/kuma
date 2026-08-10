"""Draft well-layout generator for MAME confirmation runs.

Given the list of designed expected mutations (KURO ``expected_mutations`` sheet
order), produce a draft 96-well plate layout that places one mutant per well in
column-major order (matching ``seq_to_well``), with exactly one WT control well
at the ordinal the source stated, or after the last mutant when it stated none.

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

from kuma_core.mame.export.well_mapper import seq_to_well, well_to_seq
from kuma_core.mame.models import ExpectedMutation
from kuma_core.mame.plate_geometry import PLATE_CAPACITY as _PLATE_CAPACITY


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
        """True when the draft covers every mutant and carries a WT control."""
        return not self.dropped_mutant_ids


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
) -> DraftLayout:
    """Build a column-major draft layout over ``N + 1`` occupants.

    The plate occupants are the ``N`` mutations plus exactly one WT control, in
    that order unless the source said otherwise. Occupant ``j`` takes well ``j``
    (1-based, column-major via ``seq_to_well``).

    ``wt_ordinal`` is the 1-based occupant position of the WT control, as read
    off the source by ``io/variant_list.read_variant_source``. ``None`` appends
    it after the last mutant. A source that named its own WT row at position
    *k* puts WT in well *k* and moves the mutants from *k* on one well down;
    dropping that row instead (which is what happened before) moved every well
    after it one place up and said nothing about it.

    The caller decides the mutant order. Pass :func:`canonical_plate_order`
    output to get the plate the bench actually fills; the list as given keeps
    KURO sheet order.

    Capacity is decided on total occupancy (``N + 1``) BEFORE anything is
    placed, because ``N`` alone is the wrong question: 96 mutants plus a control
    is 97 wells, and placing first and clamping afterwards asked ``seq_to_well``
    for well 97. Over capacity, ``layout`` comes back empty and the mutants that
    do not fit are named in ``dropped_mutant_ids``. Nothing partial is returned:
    a truncated draft reads as a correct full plate to anyone looking at the
    rows, so every well past the cut would be mis-scored in silence.
    """
    n = len(expected_mutations)
    if n > MUTANT_CAPACITY:
        return DraftLayout(
            layout={},
            dropped_mutant_ids=[
                m.mutant_id for m in expected_mutations[MUTANT_CAPACITY:]
            ],
        )

    wt_seq = n + 1 if wt_ordinal is None else max(1, min(wt_ordinal, n + 1))
    layout: dict[str, str] = {}
    remaining = iter(expected_mutations)
    for seq in range(1, n + 2):
        if seq == wt_seq:
            layout[seq_to_well(seq)] = "WT"
        else:
            layout[seq_to_well(seq)] = next(remaining).mutant_id
    return DraftLayout(layout=layout)


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
    "DraftLayout",
    "apply_well_selection",
    "build_draft_layout",
    "canonical_plate_order",
    "normalise_selected_wells",
]
