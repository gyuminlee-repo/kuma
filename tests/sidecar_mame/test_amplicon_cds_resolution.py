"""CDS coordinates after the reference has been cut down to the amplicon.

The raw-run path replaces the reference with the extracted amplicon, which moves
every coordinate. The caller may state the CDS in whole-reference coordinates, in
amplicon coordinates, or not usefully at all, and the resolution carries its own
ORF answer for the last case.

The missing-span case is the reason this file exists: the guard used to sit on
the first branch only, so a resolution that reported extraction without a span
would have read ``span.end`` on the second and killed a finished demux with an
AttributeError.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.ingest.amplicon_reference import (
    AmpliconReferenceResolution,
    AmpliconSpan,
)
from sidecar_mame.handlers.analyze import resolve_amplicon_cds


def _resolution(
    span: AmpliconSpan | None,
    cds: tuple[int, int] = (0, 300),
    coding_bounds_found: bool = True,
):
    return AmpliconReferenceResolution(
        reference_fasta=Path("amplicon.fa"),
        extracted=span is not None,
        span=span,
        original_length=5000,
        cds_start=cds[0],
        cds_end=cds[1],
        note="",
        coding_bounds_found=coding_bounds_found,
    )


def test_whole_reference_coordinates_are_shifted_onto_the_amplicon() -> None:
    resolution = _resolution(AmpliconSpan(start=1000, end=2000))

    assert resolve_amplicon_cds(resolution, 1100, 1400) == (100, 400)


def test_coordinates_already_inside_the_amplicon_are_left_alone() -> None:
    resolution = _resolution(AmpliconSpan(start=1000, end=2000))

    # 0..900 fits the 1000 bp amplicon and cannot be whole-reference bounds.
    assert resolve_amplicon_cds(resolution, 0, 900) == (0, 900)


def test_bounds_that_fit_neither_fall_back_to_the_resolved_orf() -> None:
    resolution = _resolution(AmpliconSpan(start=1000, end=2000), cds=(12, 912))

    assert resolve_amplicon_cds(resolution, 0, 4000) == (12, 912)


def test_a_missing_span_falls_back_instead_of_raising() -> None:
    """The producer never pairs extraction with a missing span, and reading one
    anyway is how a contract change becomes a crash mid-run."""
    resolution = _resolution(None, cds=(12, 912))

    assert resolve_amplicon_cds(resolution, 1100, 1400) == (12, 912)


def test_no_orf_and_no_usable_annotation_is_refused_rather_than_framed_at_zero() -> (
    None
):
    """The fallback used to hand back ``(0, 0)``, which is not a CDS.

    Downstream that became ``cds_start=0`` with the CDS end defaulted to the
    whole amplicon, so the plate was translated in frame 0 from the primer
    tail. Every amino-acid number then belonged to a different frame than the
    design: wells carrying an expected mutation came back WRONG_AA, and wells
    with an empty expected list (WT controls) came back clean PASS against a
    frame nobody chose.
    """
    resolution = _resolution(
        AmpliconSpan(start=1000, end=2000), cds=(0, 0), coding_bounds_found=False
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_amplicon_cds(resolution, 0, 0)

    message = str(excinfo.value)
    assert "no forward reading frame" in message
    assert "cds_start" in message


def test_a_caller_supplied_cds_still_rescues_an_amplicon_without_an_orf() -> None:
    """The refusal is the narrowest one available: only when nothing else fits.

    Whole-reference bounds inside the span (case 2) and amplicon-coordinate
    bounds (case 3) are answers in their own right, so an operator who states
    the CDS is never blocked by the ORF search having come up empty.
    """
    resolution = _resolution(
        AmpliconSpan(start=1000, end=2000), cds=(0, 0), coding_bounds_found=False
    )

    assert resolve_amplicon_cds(resolution, 1100, 1400) == (100, 400)
    assert resolve_amplicon_cds(resolution, 0, 900) == (0, 900)
