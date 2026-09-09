"""Regression tests for FASTQ base-quality wiring in the raw_run demux path.

Before this fix, ``combinatorial_demux._iter_fastq`` read and discarded the
FASTQ quality line, so every ``Alignment`` built downstream carried
``read_qual=None`` and ``consensus.call_consensus_with_metrics``'s
``min_base_quality`` filter (``ingest/consensus.py``) never excluded a single
base regardless of its Phred score. These tests pin three things:

1. ``_iter_fastq`` yields the quality string alongside (id, sequence).
2. ``_WellReadBuffer`` carries that quality through append/spill/load.
3. The quality actually changes a consensus CALL: a fixture with a
   majority-wrong, low-quality base at one position and a minority-correct,
   high-quality base at the same position must consensus to the correct base
   when quality is wired (the fix), and to the wrong, majority base when it
   is dropped (the pre-fix bug), reproduced here via the same
   ``align_reads_grouped`` entry point the real pipeline uses.
"""

from __future__ import annotations

import gzip
import re
from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import align_reads_grouped
from kuma_core.mame.ingest.combinatorial_demux import (
    _iter_fastq,
    _WellReadBuffer,
    run_combinatorial_demux,
)
from kuma_core.mame.ingest.consensus import call_consensus_with_metrics
from tests.fixtures.mame import _make_fixture as fx
from tests.mame.minimap2_support import requires_minimap2

FIXTURE_DIR = fx.FIXTURE_DIR

# 238 bp, non-repetitive, same fixture sequence used in test_align.py, long
# enough for minimap2 to seed reliably at map-ont defaults.
_REF_SEQ = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACC"
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAG"
)

_MISMATCH_POS = 40  # arbitrary interior position, well clear of either end
_HIGH_Q = "I" * len(_REF_SEQ)  # Phred 40 everywhere
_LOW_QCHAR = "#"  # Phred 2 (ord('#') - 33 == 2), well under min_base_quality=10


def _write_fasta(path: Path, name: str, seq: str) -> None:
    path.write_text(f">{name}\n{seq}\n", encoding="utf-8")


def _wrong_base(ref_base: str) -> str:
    return "A" if ref_base != "A" else "C"


def _build_majority_wrong_reads() -> list[tuple[str, str, str]]:
    """7 reads with a low-quality wrong base at _MISMATCH_POS, 3 reads with a
    high-quality correct (reference) base at the same position. Every other
    position matches the reference at high quality on all 10 reads.
    """
    ref_base = _REF_SEQ[_MISMATCH_POS]
    wrong_base = _wrong_base(ref_base)
    reads: list[tuple[str, str, str]] = []
    for i in range(7):
        seq = _REF_SEQ[:_MISMATCH_POS] + wrong_base + _REF_SEQ[_MISMATCH_POS + 1 :]
        qual = _HIGH_Q[:_MISMATCH_POS] + _LOW_QCHAR + _HIGH_Q[_MISMATCH_POS + 1 :]
        reads.append((f"wrong{i}", seq, qual))
    for i in range(3):
        reads.append((f"right{i}", _REF_SEQ, _HIGH_Q))
    return reads


# ---------------------------------------------------------------------------
# 1. _iter_fastq yields quality
# ---------------------------------------------------------------------------


def test_iter_fastq_yields_quality(tmp_path: Path) -> None:
    fq = tmp_path / "reads.fastq"
    fq.write_text("@r1 extra\nACGT\n+\nIIII\n@r2\nGGCC\n+\n!!!!\n", encoding="utf-8")

    records = list(_iter_fastq([fq]))

    assert records == [("r1", "ACGT", "IIII"), ("r2", "GGCC", "!!!!")]


def test_iter_fastq_yields_quality_gz(tmp_path: Path) -> None:
    fq = tmp_path / "reads.fastq.gz"
    with gzip.open(fq, "wt") as fh:
        fh.write("@r1\nACGT\n+\nIIII\n")

    records = list(_iter_fastq([fq]))

    assert records == [("r1", "ACGT", "IIII")]


# ---------------------------------------------------------------------------
# 2. _WellReadBuffer carries quality through append/spill/load
# ---------------------------------------------------------------------------


def test_well_read_buffer_roundtrips_quality_in_memory() -> None:
    buf = _WellReadBuffer(budget_bytes=0)  # 0 disables the spill threshold
    well = (1, 1)
    buf.append(well, "r1", "ACGT", "IIII")
    buf.append(well, "r2", "GGCC", "!!!!")

    assert buf.load(well) == [("r1", "ACGT", "IIII"), ("r2", "GGCC", "!!!!")]
    assert not buf.spilled


def test_well_read_buffer_roundtrips_quality_after_spill() -> None:
    # A budget of 1 byte forces a flush to disk on the very first append.
    buf = _WellReadBuffer(budget_bytes=1)
    well = (2, 3)
    buf.append(well, "r1", "ACGT", "IIII")
    buf.append(well, "r2", "GGCC", "!!!!")

    assert buf.spilled
    assert buf.load(well) == [("r1", "ACGT", "IIII"), ("r2", "GGCC", "!!!!")]
    buf.close()


# ---------------------------------------------------------------------------
# 3. The wiring changes a real consensus call
# ---------------------------------------------------------------------------


@requires_minimap2
def test_quality_wiring_flips_consensus_call(tmp_path: Path) -> None:
    """End-to-end over the real pipeline entry point (``align_reads_grouped``),
    fed with (id, seq, qual) 3-tuples exactly as ``_WellReadBuffer.load``
    returns them.

    The majority (7/10) reads carry a low-quality wrong base at
    ``_MISMATCH_POS``; the minority (3/10) carry a high-quality correct base.
    Wired quality must exclude the low-quality majority votes and consensus
    the correct base; without it (the pre-fix bug), the naive majority vote
    wins and consensus the wrong base.
    """
    ref_fasta = tmp_path / "ref.fasta"
    _write_fasta(ref_fasta, "ref", _REF_SEQ)
    reads = _build_majority_wrong_reads()

    # --- fixed pre-conditions: the vote is genuinely split as designed ------
    ref_base = _REF_SEQ[_MISMATCH_POS]
    wrong_base = _wrong_base(ref_base)
    assert wrong_base != ref_base

    # --- with quality wired (the fix): 3-tuples carry qual through ---------
    grouped = align_reads_grouped(
        groups=[("well", reads)],
        reference_fasta=ref_fasta,
        min_mapq=0,
        require_full_span=False,
        threads=1,
    )
    alignments = grouped["well"]
    assert len(alignments) == 10, "all 10 reads must align for this fixture to test anything"
    assert all(a.read_qual is not None for a in alignments), (
        "wiring regression: Alignment.read_qual is None even though 3-tuple "
        "reads were supplied"
    )

    call_with_quality = call_consensus_with_metrics(
        alignments, _REF_SEQ, min_depth=1, min_base_quality=10
    )
    assert call_with_quality.n_low_quality_bases == 7, (
        "the 7 low-quality wrong-base votes must be counted and excluded"
    )
    assert call_with_quality.consensus_seq[_MISMATCH_POS] == ref_base, (
        "with quality wired, the high-quality minority should win the position "
        f"but got {call_with_quality.consensus_seq[_MISMATCH_POS]!r}"
    )

    # --- with quality dropped (the pre-fix bug): reads as 2-tuples ----------
    reads_no_qual = [(rid, seq) for rid, seq, _qual in reads]
    grouped_no_qual = align_reads_grouped(
        groups=[("well", reads_no_qual)],
        reference_fasta=ref_fasta,
        min_mapq=0,
        require_full_span=False,
        threads=1,
    )
    alignments_no_qual = grouped_no_qual["well"]
    assert all(a.read_qual is None for a in alignments_no_qual)

    call_without_quality = call_consensus_with_metrics(
        alignments_no_qual, _REF_SEQ, min_depth=1, min_base_quality=10
    )
    assert call_without_quality.n_low_quality_bases == 0, (
        "with no quality string, the filter has nothing to exclude"
    )
    assert call_without_quality.consensus_seq[_MISMATCH_POS] == wrong_base, (
        "without quality, the naive majority (7 wrong vs 3 right) should win "
        f"but got {call_without_quality.consensus_seq[_MISMATCH_POS]!r}"
    )

    # The two calls must disagree at this position; that disagreement IS the
    # wiring: same reads, same aligner, same consensus function, only the
    # presence of the quality string differs.
    assert (
        call_with_quality.consensus_seq[_MISMATCH_POS]
        != call_without_quality.consensus_seq[_MISMATCH_POS]
    )

# ---------------------------------------------------------------------------
# 4. End-to-end over run_combinatorial_demux itself (not just the aligner)
# ---------------------------------------------------------------------------

_LOW_QUALITY_RE = re.compile(r"low_quality_bases=(\d+)")


def _low_quality_bases_for_well(consensus_dir: Path, well_name: str) -> int:
    header = (consensus_dir / f"{well_name}.fasta").read_text(encoding="utf-8")
    m = _LOW_QUALITY_RE.search(header)
    assert m is not None, f"no low_quality_bases field in {well_name}.fasta header: {header!r}"
    return int(m.group(1))


def _lowered_quality_copy(src: Path, dst: Path) -> None:
    """Copy a FASTQ(.gz) file with every quality char replaced by _LOW_QCHAR.

    Sequences and read ids are untouched; only the fourth line of each record
    changes, so any read-set / alignment difference between the two runs is
    attributable to quality alone.
    """
    with gzip.open(src, "rt") as fh:
        lines = fh.readlines()
    for i in range(3, len(lines), 4):
        qual_len = len(lines[i].rstrip("\n"))
        lines[i] = _LOW_QCHAR * qual_len + "\n"
    with gzip.open(dst, "wt") as fh:
        fh.writelines(lines)


@requires_minimap2
def test_run_combinatorial_demux_wires_quality_end_to_end(tmp_path: Path) -> None:
    """Same fixture reads run through the full ``run_combinatorial_demux``
    pipeline twice, once at the fixture's real quality (Phred 40, 'I') and
    once with every base forced to Phred 2 ('#'). Only the ``min_base_quality``
    filter can tell the two runs apart, since read ids, sequences and barcodes
    are identical.

    This is the regression the fix targets: before it, ``_iter_fastq`` and
    ``_WellReadBuffer`` dropped the quality line before it ever reached
    ``align_reads_grouped``, so ``low_quality_bases`` in the consensus FASTA
    header was 0 regardless of input quality. This test would have failed
    against that code (both runs reporting 0).
    """
    well_name = "1_1"  # 5 reads in the fixture, the highest-depth well

    normal_out = tmp_path / "normal"
    run_combinatorial_demux(
        raw_fastq_paths=[FIXTURE_DIR / "synth_R1.fastq.gz"],
        reference_fasta=FIXTURE_DIR / "reference.fasta",
        barcodes_xlsx=FIXTURE_DIR / "sample_map.xlsx",
        output_dir=normal_out,
        mapq_threshold=0,
        coverage_fraction=0.5,
        min_depth=3,
    )
    normal_low_q = _low_quality_bases_for_well(normal_out / "consensus", well_name)

    low_q_fastq = tmp_path / "synth_R1_lowq.fastq.gz"
    _lowered_quality_copy(FIXTURE_DIR / "synth_R1.fastq.gz", low_q_fastq)
    lowq_out = tmp_path / "lowq"
    run_combinatorial_demux(
        raw_fastq_paths=[low_q_fastq],
        reference_fasta=FIXTURE_DIR / "reference.fasta",
        barcodes_xlsx=FIXTURE_DIR / "sample_map.xlsx",
        output_dir=lowq_out,
        mapq_threshold=0,
        coverage_fraction=0.5,
        min_depth=3,
    )
    lowq_low_q = _low_quality_bases_for_well(lowq_out / "consensus", well_name)

    assert normal_low_q == 0, (
        f"fixture reads are Phred 40 throughout; expected 0 excluded bases, got {normal_low_q}"
    )
    assert lowq_low_q > 0, (
        "wiring regression: forcing every base to Phred 2 must exclude at "
        f"least one base from the well {well_name} pileup, got {lowq_low_q}"
    )
