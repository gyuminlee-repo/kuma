"""The coverage report survives every layer between the raw run and the screen.

``tests/mame/test_coverage_uniformity.py`` pins what the two helpers compute.
This file pins that the numbers they compute actually ARRIVE: the raw MinKNOW run
folder is the primary MAME input and it takes the ``combinatorial_demux`` path, so
a metric that only exists on ``compute_well_consensuses`` is a metric no operator
can see.

Nothing here constructs a verdict. All five fields are REPORT ONLY, and a future
change that makes one a gate input owns that argument rather than inheriting it
from this file.

The raw-run path is exercised at ``_compute_well_consensus``, which takes
PRE-COMPUTED alignments, rather than end to end: everything above it shells out to
the bundled minimap2 binary, which a plain checkout does not have. The layers
above are then covered by their own contracts, header round trip and analyze
serialization, so the whole chain is pinned without the binary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.ingest import combinatorial_demux as cd_mod
from kuma_core.mame.ingest.align import Alignment, _CIGAR_M
from kuma_core.mame.ingest.consensus_metadata import (
    ConsensusMetadata,
    format_consensus_fasta_record,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file

_REF = "ACGT" * 40  # 160 bp, long enough for a hole to matter


def _aln(read_seq: str, r_st: int, ref_len: int, read_id: str) -> Alignment:
    """Minimal full-match alignment of *read_seq* starting at *r_st*."""
    return Alignment(
        read_id=read_id,
        read_seq=read_seq,
        mapq=60,
        cigar=[[len(read_seq), _CIGAR_M]],
        r_st=r_st,
        r_en=r_st + len(read_seq),
        q_st=0,
        q_en=len(read_seq),
        strand=1,
        reference_length=ref_len,
    )


def _full_reads(n: int, seq: str) -> list[Alignment]:
    return [_aln(seq, 0, len(_REF), f"full{i}") for i in range(n)]


# ---------------------------------------------------------------------------
# The raw-run path measures, it does not merely carry a field
# ---------------------------------------------------------------------------


def test_raw_run_path_measures_an_evenly_covered_well() -> None:
    """Values, not just keys: a flat well reports a flat CV and full breadth."""
    alignments = _full_reads(20, _REF)
    reads = [(a.read_id, a.read_seq) for a in alignments]

    result = cd_mod._compute_well_consensus(
        "1_1", reads, alignments, _REF, len(_REF), min_depth=1
    )

    assert result.depth_cv == pytest.approx(0.0)
    assert result.depth_p10 == pytest.approx(20.0)
    assert result.depth_min_covered == 20
    assert result.breadth_at_mix_min_depth == pytest.approx(1.0)
    # Every read is the reference, so the consensus is too.
    assert result.consensus_identity == pytest.approx(1.0)


def test_raw_run_path_separates_a_hole_from_an_even_well_at_equal_depth() -> None:
    """The case ``mean_depth`` cannot express, measured through the real CIGAR walk.

    The holed well is covered at 20x over the first 80 bp and 20x over the last
    40 bp, leaving 40 bp uncovered. Breadth drops to 0.75 and the CV stays 0.0,
    which is exactly why both are reported: the CV ranges over COVERED positions
    and cannot see a clean gap.
    """
    left = [_aln(_REF[:80], 0, len(_REF), f"l{i}") for i in range(20)]
    right = [_aln(_REF[120:], 120, len(_REF), f"r{i}") for i in range(20)]
    alignments = left + right
    reads = [(a.read_id, a.read_seq) for a in alignments]

    result = cd_mod._compute_well_consensus(
        "1_2", reads, alignments, _REF, len(_REF), min_depth=1
    )

    assert result.breadth_at_mix_min_depth == pytest.approx(0.75)
    assert result.depth_cv == pytest.approx(0.0)
    assert result.depth_min_covered == 20
    # The 40 uncovered positions are N, so they are not in the identity
    # denominator; what WAS called still matches the reference.
    assert result.consensus_identity == pytest.approx(1.0)


def test_raw_run_path_reports_identity_below_one_for_a_mismatching_well() -> None:
    """A consensus that disagrees with the reference says so."""
    variant = "T" + _REF[1:]
    alignments = _full_reads(20, variant)
    reads = [(a.read_id, a.read_seq) for a in alignments]

    result = cd_mod._compute_well_consensus(
        "2_1", reads, alignments, _REF, len(_REF), min_depth=1
    )

    assert result.consensus_identity is not None
    assert result.consensus_identity < 1.0
    assert result.consensus_identity == pytest.approx(1 - 1 / len(_REF))


@pytest.mark.parametrize(
    ("reads", "alignments"),
    [([], []), ([("r0", "A" * 30)], [])],
    ids=["no reads", "no alignments"],
)
def test_a_well_with_no_consensus_measures_breadth_and_nothing_else(
    reads: list[tuple[str, str]], alignments: list[Alignment]
) -> None:
    """0.0 breadth is a measurement; the other four are not.

    This well genuinely covers none of the reference, which is a real 0.0. It has
    no covered position to spread and no called base to compare, so those four
    stay ``None``. Guarding all five on one condition would erase the 0.0.
    """
    result = cd_mod._compute_well_consensus(
        "3_1", reads, alignments, _REF, len(_REF), min_depth=1
    )

    assert result.breadth_at_mix_min_depth == 0.0
    assert result.depth_cv is None
    assert result.depth_p10 is None
    assert result.depth_min_covered is None
    assert result.consensus_identity is None


def test_well_consensus_fields_are_reachable_by_name_and_by_position() -> None:
    """``WellConsensus`` is a ``NamedTuple``, so both access styles hold.

    The five coverage fields are last, and this pins that: a field inserted in
    the middle would move them and silently shift a positional reader.
    """
    result = cd_mod._compute_well_consensus(
        "1_1", [], [], _REF, len(_REF), min_depth=1
    )

    assert len(result) == 30
    assert result[-5:] == (
        result.depth_cv,
        result.depth_p10,
        result.depth_min_covered,
        result.breadth_at_mix_min_depth,
        result.consensus_identity,
    )
    assert result[0] == result.consensus_seq


# ---------------------------------------------------------------------------
# FASTA header round trip, which is how the raw-run path reaches analysis
# ---------------------------------------------------------------------------


def test_header_round_trip_preserves_the_measured_values(tmp_path: Path) -> None:
    """The written header is read back as the same numbers.

    This is the actual carrier: the raw-run path writes one consensus FASTA per
    well and the analysis re-ingests those files.
    """
    path = tmp_path / "1_1.fasta"
    path.write_text(
        format_consensus_fasta_record(
            "1_1",
            "ACGT",
            ConsensusMetadata(
                depth=100,
                input_reads=110,
                aligned_reads=100,
                mapq_failed=0,
                span_failed=0,
                mixed_positions=0,
                max_minor_allele_fraction=0.0,
                low_depth_positions=0,
                consensus_n_fraction=0.0,
                low_quality_bases=0,
                depth_cv=0.211111,
                depth_p10=42.5,
                depth_min_covered=17,
                breadth_at_mix_min_depth=0.802,
                consensus_identity=0.999667,
            ),
        ),
        encoding="utf-8",
    )

    record = parse_fasta_file(path, "NB01")

    assert record.depth_cv == pytest.approx(0.211111)
    assert record.depth_p10 == pytest.approx(42.5)
    assert record.depth_min_covered == 17
    assert record.breadth_at_mix_min_depth == pytest.approx(0.802)
    # Six decimals survive. At three, one mismatch in a 3 kb amplicon would round
    # to a perfect 1.000 and the header would claim something false.
    assert record.consensus_identity == pytest.approx(0.999667)


def test_header_round_trip_keeps_a_measured_zero_breadth(tmp_path: Path) -> None:
    """A zero-read well writes breadth and omits the other four."""
    path = tmp_path / "2_1.fasta"
    path.write_text(
        format_consensus_fasta_record(
            "2_1",
            "NNNN",
            ConsensusMetadata(
                depth=0,
                input_reads=0,
                aligned_reads=0,
                mapq_failed=0,
                span_failed=0,
                mixed_positions=0,
                max_minor_allele_fraction=0.0,
                low_depth_positions=4,
                consensus_n_fraction=1.0,
                low_quality_bases=0,
                breadth_at_mix_min_depth=0.0,
            ),
        ),
        encoding="utf-8",
    )
    header = path.read_text(encoding="utf-8").splitlines()[0]

    assert "breadth_at_mix_min_depth=0.000000" in header
    assert "depth_cv=" not in header
    assert "consensus_identity=" not in header

    record = parse_fasta_file(path, "NB01")

    assert record.breadth_at_mix_min_depth == 0.0
    assert record.depth_cv is None
    assert record.consensus_identity is None


def test_a_legacy_consensus_file_reads_back_as_unknown(tmp_path: Path) -> None:
    """No keys means unknown, never a flat zero-identity well.

    An ``or 0.0`` in the parser would turn every file written before these keys
    existed into a measurement nobody made.
    """
    path = tmp_path / "3_1.fasta"
    path.write_text(">3_1 depth=42\nACGT\n", encoding="utf-8")

    record = parse_fasta_file(path, "NB01")

    assert record.depth_cv is None
    assert record.depth_p10 is None
    assert record.depth_min_covered is None
    assert record.breadth_at_mix_min_depth is None
    assert record.consensus_identity is None
