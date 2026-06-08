"""Draft well-layout generator for MAME confirmation runs.

Given the list of designed expected mutations (KURO ``expected_mutations`` sheet
order), produce a draft 96-well plate layout that places one mutant per well in
column-major order (matching ``seq_to_well``), followed by a single WT control
well immediately after the last mutant.

The draft layout maps ``well_id -> sample_name`` and is consumed by the pipeline
as a ``well_layout`` override (highest-priority well->sample source). "WT" wells
carry an empty expected-mutation scope (a clean consensus PASSes; any observed
variant fails).
"""

from __future__ import annotations

from kuma_core.mame.export.well_mapper import seq_to_well
from kuma_core.mame.models import ExpectedMutation

_PLATE_CAPACITY = 96


def build_draft_layout(expected_mutations: list[ExpectedMutation]) -> dict[str, str]:
    """Build a column-major draft layout: well i -> mutant_id, well N+1 -> "WT".

    well ``i`` (1-based, column-major via ``seq_to_well``) is assigned
    ``expected_mutations[i-1].mutant_id`` for ``i = 1..N`` where ``N`` is the
    number of expected mutations. A single WT control occupies well ``N+1``.

    Clamping:
    - ``N + 1 > 96`` (i.e. ``N >= 96``): the WT well is omitted.
    - ``N > 96``: mutants beyond the 96th are omitted (plate capacity).

    Returns a ``dict[well_id, sample_name]`` keyed by ``seq_to_well`` labels
    (not zero-padded; the pipeline normalises on lookup).
    """
    layout: dict[str, str] = {}
    n_mutants = min(len(expected_mutations), _PLATE_CAPACITY)
    for i in range(1, n_mutants + 1):
        layout[seq_to_well(i)] = expected_mutations[i - 1].mutant_id
    wt_seq = len(expected_mutations) + 1
    if wt_seq <= _PLATE_CAPACITY:
        layout[seq_to_well(wt_seq)] = "WT"
    return layout


__all__ = ["build_draft_layout"]
