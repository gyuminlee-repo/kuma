"""Draft well-layout generator for MAME confirmation runs.

Given the list of designed expected mutations (KURO ``expected_mutations`` sheet
order), produce a draft 96-well plate layout that places one mutant per well in
column-major order (matching ``seq_to_well``), followed by a single WT control
well immediately after the last mutant.

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

from dataclasses import dataclass, field

from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.models import ExpectedMutation
from kuma_core.mame.plate_geometry import PLATE_CAPACITY as _PLATE_CAPACITY


@dataclass(frozen=True)
class DraftLayout:
    """A draft placement plus whatever the 96-well ceiling forced out of it."""

    #: Insertion-ordered ``{well_id: sample_name}`` in column-major order, WT last
    #: when it fits. Well labels are not zero-padded; the pipeline normalises them.
    layout: dict[str, str]
    #: ``mutant_id`` values past the 96th well, in sheet order. Non-empty means the
    #: draft does not describe the full mutation set and cannot be used as-is.
    dropped_mutant_ids: list[str] = field(default_factory=list)
    #: True when the plate is exactly full and the WT control well had to be
    #: omitted. Consequential on its own: without a declared WT well the control
    #: is attributed as ``UNKNOWN_*`` and the clean-control check is lost.
    wt_omitted: bool = False

    @property
    def is_complete(self) -> bool:
        """True when the draft covers every mutant and carries a WT control."""
        return not self.dropped_mutant_ids and not self.wt_omitted


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


def build_draft_layout(
    expected_mutations: list[ExpectedMutation],
    include_wt: bool = True,
) -> DraftLayout:
    """Build a column-major draft layout: well i -> mutant_id, well N+1 -> "WT".

    well ``i`` (1-based, column-major via ``seq_to_well``) is assigned
    ``expected_mutations[i-1].mutant_id`` for ``i = 1..N`` where ``N`` is the
    number of expected mutations. A single WT control occupies well ``N+1``.

    ``include_wt=False`` skips that control well. Pass it when the source list
    already carried a wild-type row (see ``io/variant_list.py``), which the
    generic reader strips out and reports rather than parsing as a mutation.

    The caller decides the order. Pass :func:`canonical_plate_order` output to get
    the plate the bench actually fills; the list as given keeps KURO sheet order.

    Clamping (reported via the returned :class:`DraftLayout`, never silent):
    - ``N + 1 > 96`` (i.e. ``N >= 96``): the WT well is omitted -> ``wt_omitted``.
    - ``N > 96``: mutants beyond the 96th are omitted -> ``dropped_mutant_ids``.

    Callers must decide what a clamped draft means for them. A truncated draft
    looks like a correct full plate to anyone reading only the rows, so treating
    ``dropped_mutant_ids`` as cosmetic mis-scores every well past the cut.
    """
    layout: dict[str, str] = {}
    n_mutants = min(len(expected_mutations), _PLATE_CAPACITY)
    for i in range(1, n_mutants + 1):
        layout[seq_to_well(i)] = expected_mutations[i - 1].mutant_id
    if not include_wt:
        # The source listed its own WT row, so appending one here would put two
        # controls on the plate and mis-attribute the second.
        return DraftLayout(
            layout=layout,
            dropped_mutant_ids=[m.mutant_id for m in expected_mutations[_PLATE_CAPACITY:]],
            wt_omitted=False,
        )
    wt_seq = len(expected_mutations) + 1
    wt_omitted = wt_seq > _PLATE_CAPACITY
    if not wt_omitted:
        layout[seq_to_well(wt_seq)] = "WT"
    return DraftLayout(
        layout=layout,
        dropped_mutant_ids=[m.mutant_id for m in expected_mutations[_PLATE_CAPACITY:]],
        wt_omitted=wt_omitted,
    )


__all__ = ["DraftLayout", "build_draft_layout", "canonical_plate_order"]
