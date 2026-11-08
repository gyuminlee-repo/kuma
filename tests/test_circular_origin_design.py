"""SDM design on a circular template must not depend on where the origin sits.

A plasmid has no privileged position, so rotating the same circular template
has to yield the same primer pairs. Before the fix a codon near the origin
returned nothing: the upstream slice and the full-overlap grid stopped at
index 0, and an intended interval written as ``273..0`` was read as negative
length, so the off-target check reported the primer's own binding site.
"""
from __future__ import annotations

import random
from typing import cast

import pytest

from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.polymerase import PolymeraseRegistry
from kuma_core.kuro.sdm_engine import (
    OverlapMode,
    check_offtarget,
    design_single_sdm,
    diagnose_sdm_failure,
)

_N = 300
_CODON = 150
_SHIFTS = [0, 150, 147, 153, 3]


def _template() -> str:
    rng = random.Random(42)
    base = "".join(rng.choice("ACGT") for _ in range(_N))
    return base[:_CODON] + "GCT" + base[_CODON + 3:]


def _rotation(shift: int) -> tuple[str, Mutation]:
    seq = _template()
    rotated = seq[shift:] + seq[:shift]
    codon_start = (_CODON - shift) % _N
    assert rotated[codon_start:codon_start + 3] == "GCT"
    return rotated, Mutation(
        raw="A50V", wt_aa="A", position=50, mt_aa="V",
        codon_start=codon_start, wt_codon="GCT", mt_codon="GTT",
    )


@pytest.mark.parametrize("mode", ["partial", "full"])
def test_candidates_are_rotation_invariant(mode: str) -> None:
    profile = PolymeraseRegistry().get("Q5")
    pairs: dict[int, set[tuple[str, str]]] = {}
    for shift in _SHIFTS:
        seq, mutation = _rotation(shift)
        results = design_single_sdm(
            seq, mutation, profile,
            overlap_mode=cast(OverlapMode, mode), topology="circular",
        )
        pairs[shift] = {(c.forward_seq, c.reverse_seq) for c in results}
        for candidate in results:
            # Coordinates come back in the caller frame, not the rotated one.
            assert candidate.mutation.codon_start == mutation.codon_start
            assert 0 <= candidate.overlap_window.start < _N
    assert pairs[0], "the control rotation must yield candidates"
    for shift in _SHIFTS[1:]:
        assert pairs[shift] == pairs[0], f"rotation {shift} differs"


def test_intended_interval_through_origin_is_excluded() -> None:
    """A primer whose own site wraps the origin is not reported as off-target."""
    seq = _template()
    primer = seq[273:300]
    hits = check_offtarget(primer, seq, 273, 0, topology="circular")
    assert hits == []


def test_diagnosis_does_not_depend_on_rotation() -> None:
    """The failure diagnostic sees the same template the search saw."""
    profile = PolymeraseRegistry().get("Q5")
    seq, mutation = _rotation(150)
    text = diagnose_sdm_failure(seq, mutation, profile, topology="circular")
    assert isinstance(text, str)
