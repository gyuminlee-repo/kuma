"""Regression tests for the linear flank search window and the new defaults.

Two properties are pinned here.

1. A linear template whose flank is shorter than ``flank_max`` is designed on
   rather than refused. What a primer physically needs is ``flank_min`` plus one
   binding site, so the window is clamped to the template and only a clamped
   width below ``binding_min_len`` is fatal.
2. Under the shipped defaults both binding sites land entirely inside
   ``[gene_start - flank_max, gene_start - flank_min]`` and
   ``[gene_end + flank_min, gene_end + flank_max]``.
"""

import random

import pytest

from kuma_core.mame.ingest.barcode_package import design_flanking_primers
from kuma_core.mame.ingest.polymerase import get_profile

_PROFILE = get_profile("Q5")
_COMPLEMENT = str.maketrans("ACGT", "TGCA")


def _random_template(length: int, seed: int) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def _revcomp(seq: str) -> str:
    return seq.upper().translate(_COMPLEMENT)[::-1]


def test_flank_shorter_than_flank_max_is_clamped_not_refused() -> None:
    """The reported failure: 150 bp flanks around a 750 bp gene with a 400 bp
    window. Both windows overrun the template and both are clamped."""
    flank = 150
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260918)

    fwd, rev, _warns = design_flanking_primers(
        template,
        gene_start=flank,
        gene_end=flank + gene,
        profile=_PROFILE,
        flank_min=100,
        flank_max=400,
        require_gc_clamp=False,
    )

    assert 18 <= len(fwd) <= 35
    assert 18 <= len(rev) <= 35


def test_short_flank_works_under_the_shipped_defaults() -> None:
    """A 30 bp flank is shorter than the default flank_max of 60, so the
    default window is clamped too and design still succeeds."""
    flank = 30
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260919)

    fwd, rev, _warns = design_flanking_primers(
        template,
        gene_start=flank,
        gene_end=flank + gene,
        profile=_PROFILE,
        require_gc_clamp=False,
    )

    assert 18 <= len(fwd) <= 35
    assert 18 <= len(rev) <= 35


def test_clamped_window_narrower_than_binding_site_raises_with_numbers() -> None:
    """Clamping does not create room that is not there. The error states the
    width that remains and the width that is required."""
    flank = 10
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260920)

    with pytest.raises(ValueError, match=r"leaves 10 bp.*binding_min_len \(18\)"):
        design_flanking_primers(
            template,
            gene_start=flank,
            gene_end=flank + gene,
            profile=_PROFILE,
            require_gc_clamp=False,
        )

    with pytest.raises(ValueError, match=r"leaves 10 bp.*binding_min_len \(18\)"):
        design_flanking_primers(
            template,
            gene_start=200,
            gene_end=len(template) - flank,
            profile=_PROFILE,
            require_gc_clamp=False,
        )


def test_default_window_geometry_on_both_strands() -> None:
    """Both binding sites sit wholly inside the default search windows.

    The template is random so each site occurs exactly once and its index is
    the designed coordinate rather than a repeat elsewhere.
    """
    flank = 300
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260921)
    gene_start = flank
    gene_end = flank + gene
    flank_min, flank_max = 0, 60

    fwd, rev, _warns = design_flanking_primers(
        template,
        gene_start=gene_start,
        gene_end=gene_end,
        profile=_PROFILE,
    )

    fwd_site = fwd.upper()
    rev_site = _revcomp(rev)
    assert template.count(fwd_site) == 1
    assert template.count(rev_site) == 1

    fwd_pos = template.index(fwd_site)
    assert fwd_pos >= gene_start - flank_max
    assert fwd_pos + len(fwd_site) <= gene_start - flank_min

    rev_pos = template.index(rev_site)
    assert rev_pos >= gene_end + flank_min
    assert rev_pos + len(rev_site) <= gene_end + flank_max
