"""Regression tests for the CDS overhang search window and the shipped defaults.

Four properties are pinned here.

1. A linear template whose flank is shorter than ``overhang_max`` is designed
   on rather than refused. What a primer physically needs is one binding site,
   so the reach is clamped to the template and only a clamped reach below
   ``max(overhang_min, binding_min_len)`` is fatal.
2. The gap between primer and gene is a fixed ``>= 0`` invariant rather than a
   parameter. No parameter combination may place a binding site inside
   ``[gene_start, gene_end)``.
3. Under the shipped defaults the overhang of both binding sites, measured in
   template coordinates, lies within ``[overhang_min, overhang_max]``.
4. An ``overhang_min`` below ``binding_min_len`` names a sub-range no primer
   can occupy. It warns rather than raises, because larger overhangs in the
   same range stay reachable.
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


def _sites(
    template: str, fwd: str, rev: str
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Resolve both binding sites to half-open template coordinates.

    Each site must occur exactly once, otherwise the index found is not the
    coordinate the design produced and every assertion built on it is void.
    """
    fwd_site = fwd.upper()
    rev_site = _revcomp(rev)
    assert template.count(fwd_site) == 1
    assert template.count(rev_site) == 1
    fwd_pos = template.index(fwd_site)
    rev_pos = template.index(rev_site)
    return (fwd_pos, fwd_pos + len(fwd_site)), (rev_pos, rev_pos + len(rev_site))


def test_flank_shorter_than_overhang_max_is_clamped_not_refused() -> None:
    """The reported failure: 150 bp flanks around a 750 bp gene with a 400 bp
    reach. Both windows overrun the template and both are clamped."""
    flank = 150
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260918)

    fwd, rev, _warns = design_flanking_primers(
        template,
        gene_start=flank,
        gene_end=flank + gene,
        profile=_PROFILE,
        overhang_min=100,
        overhang_max=400,
        require_gc_clamp=False,
    )

    assert 18 <= len(fwd) <= 35
    assert 18 <= len(rev) <= 35


def test_short_flank_works_under_the_shipped_defaults() -> None:
    """A 30 bp flank is shorter than the default overhang_max of 60, so the
    default reach is clamped too and design still succeeds."""
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


def test_clamped_reach_below_binding_site_raises_with_numbers() -> None:
    """Clamping does not create room that is not there. The error states the
    reach that remains and the reach that is required."""
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


def test_default_overhang_geometry_on_both_strands() -> None:
    """Both overhangs sit inside the default range, measured in coordinates."""
    flank = 300
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260921)
    gene_start = flank
    gene_end = flank + gene
    overhang_min, overhang_max = 20, 60

    fwd, rev, _warns = design_flanking_primers(
        template,
        gene_start=gene_start,
        gene_end=gene_end,
        profile=_PROFILE,
    )

    (fwd_start, fwd_end), (rev_start, rev_end) = _sites(template, fwd, rev)

    fwd_overhang = gene_start - fwd_start
    rev_overhang = rev_end - gene_end
    assert overhang_min <= fwd_overhang <= overhang_max
    assert overhang_min <= rev_overhang <= overhang_max
    # The gap invariant, restated at the defaults.
    assert fwd_end <= gene_start
    assert rev_start >= gene_end


@pytest.mark.parametrize("topology", ["linear", "circular"])
@pytest.mark.parametrize(
    "overhang_min,overhang_max", [(0, 60), (20, 60), (18, 18), (40, 120), (60, 300)]
)
@pytest.mark.parametrize("tm_range", [(-1000.0, 1000.0), (1000.0, 1001.0)])
def test_primer_never_enters_the_gene(
    topology: str,
    overhang_min: int,
    overhang_max: int,
    tm_range: tuple[float, float],
) -> None:
    """No parameter combination may place a binding site inside the CDS.

    A base a primer covers is read from the primer rather than from the
    template, so an overlap would hide the mutations this assay scores.
    """
    flank = 400
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260922)
    gene_start = flank
    gene_end = flank + gene

    fwd, rev, _warns = design_flanking_primers(
        template,
        gene_start=gene_start,
        gene_end=gene_end,
        profile=_PROFILE,
        overhang_min=overhang_min,
        overhang_max=overhang_max,
        tm_min=tm_range[0],
        tm_max=tm_range[1],
        require_gc_clamp=False,
        topology=topology,
    )

    (fwd_start, fwd_end), (rev_start, rev_end) = _sites(template, fwd, rev)

    assert fwd_end <= gene_start, f"forward site {fwd_start}-{fwd_end} enters the gene"
    assert rev_start >= gene_end, f"reverse site {rev_start}-{rev_end} enters the gene"
    assert overhang_min <= gene_start - fwd_start <= overhang_max
    assert overhang_min <= rev_end - gene_end <= overhang_max


def test_overhang_min_below_binding_min_len_warns_rather_than_raises() -> None:
    """overhang = gap + binding_length and gap >= 0, so an overhang under
    binding_min_len holds no binding site. Larger overhangs in the same range
    still work, so the setting is inert rather than fatal."""
    flank = 300
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260923)

    fwd, rev, warns = design_flanking_primers(
        template,
        gene_start=flank,
        gene_end=flank + gene,
        profile=_PROFILE,
        overhang_min=5,
        overhang_max=60,
        binding_min_len=18,
        require_gc_clamp=False,
    )

    assert any("overhang_min (5) is below binding_min_len (18)" in w for w in warns)
    (fwd_start, fwd_end), (rev_start, rev_end) = _sites(template, fwd, rev)
    # The effective minimum is binding_min_len, not the stated overhang_min.
    assert flank - fwd_start >= 18
    assert rev_end - (flank + gene) >= 18
    assert fwd_end <= flank
    assert rev_start >= flank + gene


def test_overhang_max_below_binding_min_len_is_refused() -> None:
    """The whole range being unreachable is a different matter: nothing can be
    designed, so it raises instead of warning."""
    template = _random_template(1000, seed=20260924)

    with pytest.raises(ValueError, match=r"binding_min_len \(18\)"):
        design_flanking_primers(
            template,
            gene_start=300,
            gene_end=700,
            profile=_PROFILE,
            overhang_min=5,
            overhang_max=10,
            require_gc_clamp=False,
        )


@pytest.mark.parametrize("topology", ["linear", "circular"])
@pytest.mark.parametrize("overhang_min,overhang_max", [(20, 60), (5, 60), (40, 120)])
def test_search_direction_is_pinned_per_strand(
    topology: str, overhang_min: int, overhang_max: int
) -> None:
    """The two strands search in opposite directions and that is deliberate.

    With the Tm window opened wide and the GC clamp off, every candidate is
    acceptable, so the first one tried is the one returned and the resulting
    coordinates are exact rather than approximate. Forward runs from the
    largest reachable overhang inwards, so it lands on the cap. Reverse runs
    from the smallest usable overhang outwards, so it lands on the floor.
    Flipping either loop breaks this test, which is the point: the forward
    ordering is what leaves terminal slack at the default of 60.
    """
    flank = 400
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260925)
    gene_start = flank
    gene_end = flank + gene

    fwd, rev, _warns = design_flanking_primers(
        template,
        gene_start=gene_start,
        gene_end=gene_end,
        profile=_PROFILE,
        overhang_min=overhang_min,
        overhang_max=overhang_max,
        tm_min=-1000.0,
        tm_max=1000.0,
        require_gc_clamp=False,
        topology=topology,
    )

    (fwd_start, _fwd_end), (_rev_start, rev_end) = _sites(template, fwd, rev)

    assert gene_start - fwd_start == overhang_max
    assert rev_end - gene_end == max(overhang_min, 18)
    assert len(fwd) == len(rev) == 18


def test_forward_direction_lands_on_the_clamped_cap() -> None:
    """The same pin under a linear clamp: the cap is the template, not
    overhang_max, and the forward primer still lands on it."""
    flank = 30
    gene = 750
    template = _random_template(flank + gene + flank, seed=20260926)

    fwd, rev, _warns = design_flanking_primers(
        template,
        gene_start=flank,
        gene_end=flank + gene,
        profile=_PROFILE,
        tm_min=-1000.0,
        tm_max=1000.0,
        require_gc_clamp=False,
    )

    (fwd_start, _fwd_end), (_rev_start, rev_end) = _sites(template, fwd, rev)
    assert flank - fwd_start == 30
    assert rev_end - (flank + gene) == 20
