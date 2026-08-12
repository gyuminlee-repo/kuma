# ruff: noqa: S101
"""Regression guards for two MAME correctness defects.

Defect 1 -- consensus query cursor on the minus strand
------------------------------------------------------
``Alignment.q_st``/``q_en`` are stored in the original (as-input) read
orientation, but the consensus pileup walks the CIGAR over the *reverse
complement* of ``read_seq`` when ``strand == -1``.  In that orientation the
alignment starts at ``len(read_seq) - q_en``, not at ``q_st``.  The two agree
only when the leading and trailing clips are equal.  Reads reach consensus as
``read_seq[q_st - trim : q_en + trim]`` slices, which is symmetric except when
the slice is clamped at a read boundary, so a read whose alignment ends within
``trim_flank_bp`` of its end used to have its entire pileup contribution shifted
by the clip difference.  On the reference workload 26 of 7779 minus-strand
consensus alignments were shifted, and they voted at chance-level identity.

Defect 2 -- ``is_first_hit`` consumed by failed hits
----------------------------------------------------
``is_first_hit`` was cleared even when a hit resolved to no well, so a read
whose first hit was ambiguous and whose second hit succeeded was booked to
``chimera_splits`` instead of ``assigned_reads``.  The serial and the chunked
parallel matcher carried the same logic and had to be fixed together.
"""

from __future__ import annotations

import gzip
import random
from collections import defaultdict
from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import Alignment, _CIGAR_M
from kuma_core.mame.ingest.combinatorial_demux import (
    _match_reads_chunk,
    _reverse_complement,
    run_combinatorial_demux,
)
from kuma_core.mame.ingest.consensus import _accumulate, call_consensus

# ---------------------------------------------------------------------------
# Defect 1: minus-strand query cursor
# ---------------------------------------------------------------------------

_RNG = random.Random(20260801)
_REF = "".join(_RNG.choice("ACGT") for _ in range(200))
_ALN_ST, _ALN_EN = 20, 180


def _minus_strand_alignment(lead_clip: int, trail_clip: int) -> Alignment:
    """Build a minus-strand alignment with the requested clip asymmetry.

    ``lead_clip``/``trail_clip`` are in the aligned (reverse-complement)
    orientation, i.e. the orientation the CIGAR and the SAM record use.  The
    stored ``read_seq`` is the original-orientation read, and ``q_st``/``q_en``
    are flipped into that orientation exactly as
    :func:`kuma_core.mame.ingest.align._coords_from_cigar` does.
    """
    rng = random.Random(lead_clip * 1000 + trail_clip)
    lead = "".join(rng.choice("ACGT") for _ in range(lead_clip))
    trail = "".join(rng.choice("ACGT") for _ in range(trail_clip))
    aligned = _REF[_ALN_ST:_ALN_EN]
    q_seq = lead + aligned + trail          # aligned orientation (SAM SEQ)
    read_seq = _reverse_complement(q_seq)   # as-input orientation
    total = len(q_seq)
    q_st_sam = lead_clip
    q_en_sam = lead_clip + len(aligned)
    return Alignment(
        read_id=f"minus_{lead_clip}_{trail_clip}",
        read_seq=read_seq,
        mapq=60,
        cigar=[[len(aligned), _CIGAR_M]],
        r_st=_ALN_ST,
        r_en=_ALN_EN,
        q_st=total - q_en_sam,
        q_en=total - q_st_sam,
        strand=-1,
        reference_length=len(_REF),
    )


class TestMinusStrandQueryCursor:
    def test_asymmetric_clip_still_reconstructs_the_reference(self) -> None:
        """A clamped slice (short trailing flank) must not shift the pileup.

        Pre-fix the cursor started at ``q_st`` = 5 + 160 - 25 = 20 instead of
        the correct 5, shifting every vote 15 bases and reconstructing garbage.
        """
        aln = _minus_strand_alignment(lead_clip=5, trail_clip=25)
        consensus = call_consensus([aln], _REF, min_depth=1)

        assert len(consensus) == len(_REF)
        assert consensus[_ALN_ST:_ALN_EN] == _REF[_ALN_ST:_ALN_EN]
        assert set(consensus[:_ALN_ST]) == {"N"}
        assert set(consensus[_ALN_EN:]) == {"N"}

    def test_symmetric_clip_control_is_unchanged(self) -> None:
        """The common (unclamped, symmetric) case behaves identically."""
        aln = _minus_strand_alignment(lead_clip=30, trail_clip=30)
        consensus = call_consensus([aln], _REF, min_depth=1)
        assert consensus[_ALN_ST:_ALN_EN] == _REF[_ALN_ST:_ALN_EN]

    def test_plus_strand_control_is_unchanged(self) -> None:
        """Plus-strand alignments keep using ``q_st`` verbatim."""
        aligned = _REF[_ALN_ST:_ALN_EN]
        read_seq = "ACGTACGTAC" + aligned + "TTTT"
        aln = Alignment(
            read_id="plus",
            read_seq=read_seq,
            mapq=60,
            cigar=[[len(aligned), _CIGAR_M]],
            r_st=_ALN_ST,
            r_en=_ALN_EN,
            q_st=10,
            q_en=10 + len(aligned),
            strand=1,
            reference_length=len(_REF),
        )
        consensus = call_consensus([aln], _REF, min_depth=1)
        assert consensus[_ALN_ST:_ALN_EN] == _REF[_ALN_ST:_ALN_EN]

    def test_scalar_accumulate_agrees_with_the_vectorized_path(self) -> None:
        """``_accumulate`` carries the same convention as ``_accumulate_all``."""
        aln = _minus_strand_alignment(lead_clip=5, trail_clip=25)
        per_pos: list[dict[str, int]] = [defaultdict(int) for _ in range(len(_REF))]
        ins_events = [0] * len(_REF)
        _accumulate(aln, per_pos, ins_events, min_base_quality=10)

        for pos in range(_ALN_ST, _ALN_EN):
            assert per_pos[pos] == {_REF[pos]: 1}, f"wrong vote at reference {pos}"


# ---------------------------------------------------------------------------
# Defect 2: is_first_hit accounting
# ---------------------------------------------------------------------------


class _FakeHit:
    """Minimal stand-in for the ``Alignment`` fields the matcher reads."""

    def __init__(self, q_st: int, q_en: int) -> None:
        self.q_st = q_st
        self.q_en = q_en
        self.strand = 1


def _chunk_stats(monkeypatch: pytest.MonkeyPatch, outcomes: list[object]) -> tuple:
    """Drive ``_match_reads_chunk`` over one read with scripted hit outcomes."""
    from kuma_core.mame.ingest import combinatorial_demux as cd

    remaining = list(outcomes)

    def fake_demux(**_kwargs: object) -> object:
        return remaining.pop(0)

    monkeypatch.setattr(cd, "_demux_read_anchored", fake_demux)

    hits = [_FakeHit(50 + 10 * i, 100 + 10 * i) for i in range(len(outcomes))]
    chunk = [(0, "read0", "A" * 400, hits)]
    (result,) = cd._match_reads_chunk(
        chunk, r_barcodes=[("r1", "ACGTACGTAC")], f_barcodes=[("f1", "TTTTGGGGCC")],
        window_bp=30, edit_dist_ratio=0.25, trim_flank_bp=30,
    )
    # ``drop_deltas`` (the per-reason split of ``ambiguous``) is unpacked and
    # discarded: the stub replaces _demux_read_anchored, so it never fills the
    # reason sink and the split is empty by construction here. What this helper
    # tests is the first-hit accounting, and the partition identity has its own
    # tests in tests/mame/test_demux_drop_reasons.py against the real matcher.
    _idx, appends, assigned, chimera, ambiguous, _drops = result
    return appends, assigned, chimera, ambiguous


class TestFirstHitAccounting:
    def test_ambiguous_first_hit_does_not_consume_the_assignment_slot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """First hit ambiguous, second hit good -> assigned, not a chimera split."""
        appends, assigned, chimera, ambiguous = _chunk_stats(
            monkeypatch, [None, (2, 3)]
        )
        assert len(appends) == 1
        assert (assigned, chimera, ambiguous) == (1, 0, 1)

    def test_genuine_second_well_is_still_a_chimera_split(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two successful hits in different wells keep the old accounting."""
        appends, assigned, chimera, ambiguous = _chunk_stats(
            monkeypatch, [(1, 1), (2, 3)]
        )
        assert len(appends) == 2
        assert (assigned, chimera, ambiguous) == (1, 1, 0)

    def test_duplicate_well_is_neither_assigned_nor_split(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A repeat hit on an already-assigned well is dropped silently."""
        appends, assigned, chimera, ambiguous = _chunk_stats(
            monkeypatch, [(1, 1), (1, 1)]
        )
        assert len(appends) == 1
        assert (assigned, chimera, ambiguous) == (1, 0, 0)

    def test_ambiguous_between_two_wells_is_not_double_charged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An ambiguous hit in the middle leaves the split accounting alone."""
        appends, assigned, chimera, ambiguous = _chunk_stats(
            monkeypatch, [(1, 1), None, (2, 3)]
        )
        assert len(appends) == 2
        assert (assigned, chimera, ambiguous) == (1, 1, 1)


# ---------------------------------------------------------------------------
# Defect 2: the serial and the parallel matcher must agree
# ---------------------------------------------------------------------------

_TEST_REF = (
    "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"
    "TTAGCCTGAGCATTACGGATCCGTTAACGGTACCTAGCATCAGGATCCAAGTTCAGCTAG"
)
_F_BARCODES = ["AATCCCACTAC", "TGAACTGAGCG", "TATCTGACCTT", "ATATGAGACG"]
_R_BARCODES = ["CCCTATGACA", "TAATGGCAAG", "AACAAGGCGT", "GTATGTAGAA"]
_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"


def _build_read(r_idx: int, f_idx: int) -> str:
    return (
        _F_BARCODES[f_idx - 1]
        + _F_TAIL
        + _TEST_REF
        + _reverse_complement(_R_TAIL)
        + _reverse_complement(_R_BARCODES[r_idx - 1])
    ).upper()


@pytest.fixture()
def _workload(tmp_path: Path) -> tuple[Path, Path, Path]:
    openpyxl = pytest.importorskip("openpyxl")

    ref = tmp_path / "reference.fasta"
    ref.write_text(f">test_ref\n{_TEST_REF}\n")

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    for i, bc in enumerate(_F_BARCODES, start=1):
        ws.append([f"isps_f_{i}", bc.lower() + _F_TAIL])
    for i, bc in enumerate(_R_BARCODES, start=1):
        ws.append([f"isps_r_{i}", bc.lower() + _R_TAIL])
    xlsx = tmp_path / "barcodes.xlsx"
    wb.save(xlsx)

    # Chimeric reads (two amplicons back to back) exercise the multi-hit path
    # where is_first_hit lives; plain reads cover the single-hit case.
    reads: list[tuple[str, str]] = []
    for i in range(6):
        reads.append((f"plain_{i}", _build_read(1, 1)))
    for i in range(6):
        reads.append((f"chimera_{i}", _build_read(1, 1) + _build_read(2, 3)))

    fastq = tmp_path / "reads.fastq.gz"
    with gzip.open(fastq, "wt") as fh:
        for read_id, seq in reads:
            fh.write(f"@{read_id}\n{seq}\n+\n{'I' * len(seq)}\n")
    return fastq, ref, xlsx


def _run(workload: tuple[Path, Path, Path], out_dir: Path) -> object:
    fastq, ref, xlsx = workload
    return run_combinatorial_demux(
        raw_fastq_paths=[fastq],
        reference_fasta=ref,
        barcodes_xlsx=xlsx,
        output_dir=out_dir,
        mapq_threshold=0,
        coverage_fraction=0.5,
        trim_flank_bp=30,
        min_depth=1,
        chimera_split=True,
    )


def test_serial_and_parallel_matchers_report_the_same_stats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _workload: tuple[Path, Path, Path],
) -> None:
    """The two copies of the hit-accounting loop must not drift apart.

    ``KUMA_MAME_PERREAD_THRESHOLD`` selects between the inline serial loop and
    the chunked ``_match_reads_chunk`` pool; both carry the same
    ``is_first_hit`` logic, so a one-sided fix shows up here.
    """
    monkeypatch.setenv("KUMA_MAME_PERREAD_THRESHOLD", str(10**9))
    serial = _run(_workload, tmp_path / "serial")

    monkeypatch.setenv("KUMA_MAME_PERREAD_THRESHOLD", "1")
    monkeypatch.setenv("KUMA_MAME_PERREAD_WORKERS", "2")
    parallel = _run(_workload, tmp_path / "parallel")

    assert serial.stats == parallel.stats
    assert {k: len(v) for k, v in serial.per_well_reads.items()} == {
        k: len(v) for k, v in parallel.per_well_reads.items()
    }


def test_multi_hit_reads_are_booked_as_assigned_not_split(
    tmp_path: Path, _workload: tuple[Path, Path, Path]
) -> None:
    """Every read that lands in at least one well counts once as assigned.

    ``assigned_reads`` is a per-read counter and ``chimera_splits`` counts the
    *extra* well assignments, so their sum can never exceed the number of
    (read, well) pairs actually written.
    """
    result = _run(_workload, tmp_path / "out")
    assert result.stats.chimera_splits > 0, (
        "fixture stopped producing multi-hit reads; the accounting under test "
        "is no longer exercised"
    )
    n_pairs = sum(len(v) for v in result.per_well_reads.values())
    assert result.stats.assigned_reads + result.stats.chimera_splits == n_pairs
    assert result.stats.assigned_reads <= result.stats.total_reads
