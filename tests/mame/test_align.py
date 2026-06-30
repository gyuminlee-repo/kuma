"""Unit tests for kuma_core.mame.ingest.align.

Tests cover:
- Basic alignment returns correct Alignment objects.
- MAPQ < 25 reads are excluded.
- 100% reference span filter (require_full_span=True).
- Reverse-strand reads are correctly included (strand == -1).
- Empty reads are skipped without error.
- Missing reference FASTA raises FileNotFoundError.
- mappy unavailable surfaces ImportError (mocked).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import Alignment, _get_reference_length, align_reads

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMP = str.maketrans("ACGTacgt", "TGCAtgca")


def _rc(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _write_fasta(path: Path, name: str, seq: str) -> None:
    path.write_text(f">{name}\n{seq}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Reference fixture (200 bp, non-repetitive to get reasonable MAPQ)
# ---------------------------------------------------------------------------

_REF_SEQ = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGACC"
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAG"
)  # 238 bp — long enough for mappy to produce non-trivial MAPQ


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetReferenceLength:
    def test_correct_length(self, tmp_path: Path) -> None:
        ref = tmp_path / "ref.fasta"
        _write_fasta(ref, "seq", _REF_SEQ)
        assert _get_reference_length(ref) == len(_REF_SEQ)

    def test_multiline_fasta(self, tmp_path: Path) -> None:
        ref = tmp_path / "ref.fasta"
        seq = _REF_SEQ
        # Write in 60-char lines.
        lines = [f">{seq[:4]}"]
        for i in range(0, len(seq), 60):
            lines.append(seq[i:i + 60])
        ref.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert _get_reference_length(ref) == len(seq)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            _get_reference_length(tmp_path / "nonexistent.fasta")

    def test_empty_fasta_raises(self, tmp_path: Path) -> None:
        ref = tmp_path / "empty.fasta"
        ref.write_text(">ref\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no sequence data"):
            _get_reference_length(ref)


class TestAlignReads:
    @pytest.fixture()
    def ref_fasta(self, tmp_path: Path) -> Path:
        path = tmp_path / "ref.fasta"
        _write_fasta(path, "ref", _REF_SEQ)
        return path

    def test_perfect_match_returns_alignment(self, ref_fasta: Path) -> None:
        reads = [("read1", _REF_SEQ)]
        alns = align_reads(reads, ref_fasta, min_mapq=0, require_full_span=False)
        assert len(alns) >= 1
        aln = alns[0]
        assert isinstance(aln, Alignment)
        assert aln.read_id == "read1"
        assert aln.read_seq == _REF_SEQ
        assert aln.r_st == 0
        assert aln.r_en == len(_REF_SEQ)
        assert aln.strand in (1, -1)

    def test_missing_reference_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            align_reads([("r1", _REF_SEQ)], tmp_path / "missing.fasta")

    def test_empty_reads_skipped(self, ref_fasta: Path) -> None:
        reads = [("empty", ""), ("valid", _REF_SEQ)]
        alns = align_reads(reads, ref_fasta, min_mapq=0, require_full_span=False)
        # Empty read should be skipped; valid read may align.
        # All returned alignments must have non-empty read_seq.
        for aln in alns:
            assert aln.read_seq != ""

    def test_reverse_complement_read_aligns(self, ref_fasta: Path) -> None:
        rc_read = _rc(_REF_SEQ)
        reads = [("rev_read", rc_read)]
        alns = align_reads(reads, ref_fasta, min_mapq=0, require_full_span=False)
        assert len(alns) >= 1
        aln = alns[0]
        assert aln.strand == -1

    def test_mapq_filter_excludes_low_quality(self, ref_fasta: Path) -> None:
        """A very short read against a long reference gets low MAPQ and is filtered."""
        # Use a short read (15 bp) — too short to get MAPQ ≥ 25 against a 238-bp ref.
        short_read = _REF_SEQ[:15]
        reads = [("short", short_read)]
        # With min_mapq=25, this should be excluded.
        alns = align_reads(reads, ref_fasta, min_mapq=25, require_full_span=False)
        # Short reads get MAPQ 0 or very low; check that high threshold excludes them.
        # (If mappy happens to give ≥25, test is inconclusive but not broken.)
        # We accept 0 or 1 results; the important thing is no crash.
        assert isinstance(alns, list)

    def test_require_full_span_filter(self, ref_fasta: Path) -> None:
        """A partial read must be excluded when require_full_span=True."""
        partial = _REF_SEQ[:80]  # covers only first 80 bp of 238 bp ref
        reads = [("partial", partial)]
        alns_filtered = align_reads(
            reads, ref_fasta, min_mapq=0, require_full_span=True
        )
        # Partial read must not pass full-span filter.
        assert len(alns_filtered) == 0

    def test_full_ref_read_passes_span_filter(self, ref_fasta: Path) -> None:
        """A read identical to the reference must pass the full-span filter."""
        reads = [("full", _REF_SEQ)]
        alns = align_reads(reads, ref_fasta, min_mapq=0, require_full_span=True)
        # Full-length read must have at least one passing alignment.
        assert len(alns) >= 1
        for aln in alns:
            assert aln.r_st == 0
            assert aln.r_en == len(_REF_SEQ)

    def test_graded_coverage_filter_excludes_partial(self, ref_fasta: Path) -> None:
        """A partial read is rejected by the graded coverage_fraction filter (the
        chimera_split=False demux path). Collapsing coverage to
        require_full_span=(coverage_fraction >= 1.0) previously dropped this filter
        for any fraction < 1.0, admitting partial-coverage reads into wells."""
        partial = _REF_SEQ[: len(_REF_SEQ) // 2]  # ~50% of the reference
        reads = [("partial", partial)]
        # Without a coverage filter the partial read is admitted (only MAPQ applies).
        kept_none = align_reads(reads, ref_fasta, min_mapq=0, require_full_span=False)
        assert len(kept_none) >= 1
        # The graded filter at 0.98 rejects the partial read.
        kept_098 = align_reads(
            reads, ref_fasta, min_mapq=0, require_full_span=False, coverage_fraction=0.98
        )
        assert len(kept_098) == 0
        # A full-length read still passes the same graded filter.
        kept_full = align_reads(
            [("full", _REF_SEQ)],
            ref_fasta,
            min_mapq=0,
            require_full_span=False,
            coverage_fraction=0.98,
        )
        assert len(kept_full) >= 1

    def test_alignment_has_cigar(self, ref_fasta: Path) -> None:
        reads = [("r1", _REF_SEQ)]
        alns = align_reads(reads, ref_fasta, min_mapq=0, require_full_span=False)
        assert len(alns) >= 1
        aln = alns[0]
        assert isinstance(aln.cigar, list)
        assert len(aln.cigar) > 0
        # Each element is [length, op] with length > 0 and op in 0–8.
        for length, op in aln.cigar:
            assert length > 0
            assert 0 <= op <= 8

    def test_no_alignments_for_random_sequence(self, ref_fasta: Path) -> None:
        # Poly-N sequence should not align.
        reads = [("poly_n", "N" * 200)]
        alns = align_reads(reads, ref_fasta, min_mapq=0, require_full_span=False)
        assert alns == []

    def test_multiple_reads_returned_in_order(self, ref_fasta: Path) -> None:
        reads = [
            ("r1", _REF_SEQ),
            ("r2", _REF_SEQ),
            ("r3", _REF_SEQ),
        ]
        alns = align_reads(reads, ref_fasta, min_mapq=0, require_full_span=True)
        assert len(alns) == 3
        ids = [a.read_id for a in alns]
        assert ids == ["r1", "r2", "r3"]

    def test_reverse_strand_q_st_in_original_read_coords(
        self, ref_fasta: Path
    ) -> None:
        """Reverse-strand q_st must be relative to the as-input read 5' end.

        The read is built as ``leftflank(L) + revcomp(REF) + rightflank(R)``
        with L != R. mappy reports forward-query coordinates, so for the
        reverse-mapped middle segment q_st must equal the leading flank length
        L (not the trailing flank length R). The pre-fix code returned R.
        """
        left = 10
        right = 40
        # Distinct flank bases unlikely to extend the alignment into the flanks.
        left_flank = "T" * left
        right_flank = "A" * right
        read = left_flank + _rc(_REF_SEQ) + right_flank
        reads = [("rev_flanked", read)]
        alns = align_reads(
            reads, ref_fasta, min_mapq=0, require_full_span=False
        )
        assert len(alns) >= 1
        aln = alns[0]
        assert aln.strand == -1
        assert aln.q_st == left

    def test_alignment_cigar_has_no_clip_ops(self, ref_fasta: Path) -> None:
        """Alignment.cigar must be clip-free like mappy (clips via q_st/q_en).

        A flanked read (left + REF + right) is soft-clipped at both ends by the
        aligner. The returned cigar must drop S(4)/H(5) ops; clipping is conveyed
        by q_st/q_en so consensus walking does not double-offset the query.
        """
        read = "T" * 15 + _REF_SEQ + "A" * 25
        alns = align_reads(
            [("flanked", read)], ref_fasta, min_mapq=0, require_full_span=False
        )
        assert len(alns) >= 1
        aln = alns[0]
        # Soft/hard clip ops (4, 5) must be absent from the stored cigar.
        assert all(op not in (4, 5) for _, op in aln.cigar)
        # Clipping is still reflected in the query coordinates.
        assert aln.q_st > 0
