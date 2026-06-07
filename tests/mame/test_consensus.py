"""Unit tests for kuma_core.mame.ingest.consensus.

Tests cover:
- Simple majority vote (ref base wins when 3 vs 1).
- Deletion majority → 'N' (gap-free output).
- No-coverage positions → 'N'.
- min_depth = 2: positions with only 1 read → 'N'.
- Reverse-complement reads: bases are RC'd before voting.
- CIGAR deletion operator (op=2) contributes '-' vote.
- CIGAR insertion operator (op=1) does not shift reference positions.
- CIGAR soft-clip (op=4) does not shift reference positions.
- per_position_depth returns correct counts.
"""

from __future__ import annotations

from kuma_core.mame.ingest.align import (
    Alignment,
    _CIGAR_D,
    _CIGAR_I,
    _CIGAR_M,
    _CIGAR_S,
)
from kuma_core.mame.ingest.consensus import (
    call_consensus,
    call_consensus_with_metrics,
    per_position_depth,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMP = str.maketrans("ACGTacgt", "TGCAtgca")


def _rc(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _make_aln(
    read_seq: str,
    ref_len: int,
    cigar: list[list[int]] | None = None,
    strand: int = 1,
    r_st: int = 0,
    q_st: int = 0,
) -> Alignment:
    """Build a minimal Alignment for testing."""
    if cigar is None:
        cigar = [[len(read_seq), _CIGAR_M]]
    r_en = r_st
    q_en = q_st
    for length, op in cigar:
        from kuma_core.mame.ingest.align import _REF_CONSUMING, _QUERY_CONSUMING
        if op in _REF_CONSUMING:
            r_en += length
        if op in _QUERY_CONSUMING:
            q_en += length
    return Alignment(
        read_id="test",
        read_seq=read_seq,
        mapq=60,
        cigar=cigar,
        r_st=r_st,
        r_en=r_en,
        q_st=q_st,
        q_en=q_en,
        strand=strand,
        reference_length=ref_len,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCallConsensus:

    def test_perfect_match(self) -> None:
        ref = "ATGCATGC"
        aln = _make_aln(ref, len(ref))
        result = call_consensus([aln], ref)
        assert result == ref

    def test_majority_vote_ref_wins(self) -> None:
        """3 reads with ref base (G at pos 2), 1 read with T → consensus G at pos 2."""
        ref = "ATGCATGC"  # pos 2 = 'G'
        # 3 reads identical to ref (G at pos 2).
        reads_ref = [_make_aln(ref, len(ref)) for _ in range(3)]
        # 1 read with T at pos 2.
        mutant = ref[:2] + "T" + ref[3:]
        reads_mut = [_make_aln(mutant, len(ref))]
        result = call_consensus(reads_ref + reads_mut, ref)
        assert result[2] == "G"  # majority is 'G' (3 vs 1)

    def test_majority_vote_mutation_wins(self) -> None:
        """4 reads with C at pos 0 vs 1 read with A → consensus C."""
        ref = "ATGCATGC"
        mut_seq = "C" + ref[1:]
        reads_c = [_make_aln(mut_seq, len(ref)) for _ in range(4)]
        reads_a = [_make_aln(ref, len(ref))]
        result = call_consensus(reads_c + reads_a, ref)
        assert result[0] == "C"

    def test_no_reads_returns_all_n(self) -> None:
        ref = "ATGCATGC"
        result = call_consensus([], ref)
        assert result == "N" * len(ref)

    def test_min_depth_uncovered_positions_n(self) -> None:
        """With min_depth=2, a position covered by only 1 read → 'N'."""
        ref = "ATGCATGC"
        aln = _make_aln(ref, len(ref))
        result = call_consensus([aln], ref, min_depth=2)
        # All positions have depth 1 < min_depth=2 → all 'N'.
        assert result == "N" * len(ref)

    def test_low_depth_metrics_report_per_base_n_signal(self) -> None:
        """Per-position depth gating is surfaced alongside the consensus."""
        ref = "ATGCATGC"
        aln = _make_aln(ref, len(ref))

        result = call_consensus_with_metrics([aln], ref, min_depth=2)

        assert result.consensus_seq == "N" * len(ref)
        assert result.n_low_depth_positions == len(ref)
        assert result.consensus_n_fraction == 1.0

    def test_deletion_majority_yields_n(self) -> None:
        """Majority deletion at a position → 'N' (gap-free output)."""
        ref = "ATGCATGC"
        ref_len = len(ref)
        # 3 reads with deletion at pos 3-4; 1 read without.
        # Simulate by: 3 reads with CIGAR [3M, 2D, 3M] and 1 full-match read.
        del_reads = [
            _make_aln(
                read_seq="ATGATGC",  # 7 bp: ATG + TGC (missing GC at pos 3-4)
                ref_len=ref_len,
                cigar=[[3, _CIGAR_M], [2, _CIGAR_D], [3, _CIGAR_M]],
            )
            for _ in range(3)
        ]
        full_read = _make_aln(ref, ref_len)
        result = call_consensus(del_reads + [full_read], ref)
        # Positions 3 and 4: 3 deletion votes vs 1 base vote → deletion majority → 'N'.
        assert result[3] == "N"
        assert result[4] == "N"

    def test_reverse_complement_read_voted_correctly(self) -> None:
        """A reverse-strand read must be RC'd before voting."""
        ref = "ATGCATGC"
        ref_len = len(ref)
        # Forward read matches ref perfectly.
        fwd_read = _make_aln(ref, ref_len, strand=1)
        # Reverse-complement read: sequence is RC of ref, but strand=-1.
        rc_seq = _rc(ref)
        rev_read = _make_aln(rc_seq, ref_len, strand=-1)
        result = call_consensus([fwd_read, rev_read], ref)
        # Both reads vote the same bases (RC then RC back = original).
        assert result == ref

    def test_insertion_does_not_shift_reference_positions(self) -> None:
        """Insertion in read (CIGAR op=I) does not advance ref_pos."""
        ref = "ATGCATGC"
        ref_len = len(ref)
        # Read: "ATG" + "NNN" (insertion) + "CATGC" = 11 bp
        # CIGAR: 3M 3I 5M
        aln = _make_aln(
            read_seq="ATGNNNCATGC",
            ref_len=ref_len,
            cigar=[[3, _CIGAR_M], [3, _CIGAR_I], [5, _CIGAR_M]],
        )
        result = call_consensus([aln], ref)
        # Positions 0-2 from "ATG", positions 3-7 from "CATGC".
        assert result[0] == "A"
        assert result[1] == "T"
        assert result[2] == "G"
        assert result[3] == "C"

    def test_soft_clip_does_not_affect_reference_positions(self) -> None:
        """Soft-clipped bases (CIGAR op=4) consume query but not reference."""
        ref = "ATGCATGC"
        ref_len = len(ref)
        # Read: 2 soft-clipped bases + full match.
        # CIGAR: 2S 8M
        aln = Alignment(
            read_id="test",
            read_seq="NNATGCATGC",  # 2 soft-clip + 8 match
            mapq=60,
            cigar=[[2, _CIGAR_S], [8, _CIGAR_M]],
            r_st=0,
            r_en=ref_len,
            q_st=0,
            q_en=10,
            strand=1,
            reference_length=ref_len,
        )
        result = call_consensus([aln], ref)
        # After skipping 2 soft-clip bases, the aligned part is ref-identical.
        assert result == ref

    def test_output_length_equals_reference_length(self) -> None:
        ref = "ATGCATGCATGCATGC"
        aln = _make_aln(ref, len(ref))
        result = call_consensus([aln], ref)
        assert len(result) == len(ref)

    def test_all_bases_uppercase(self) -> None:
        ref = "ATGCATGC"
        aln = _make_aln(ref, len(ref))
        result = call_consensus([aln], ref)
        assert result == result.upper()
        assert all(b in "ACGTN" for b in result)

    def test_snp_detection_known_mutation(self) -> None:
        """Majority SNP at known position is correctly called."""
        ref = "ATGCATGCATGC"
        ref_len = len(ref)
        # 5 reads with 'T' at pos 4 (original: 'A'), 1 with original 'A'.
        mut = ref[:4] + "T" + ref[5:]
        reads_mut = [_make_aln(mut, ref_len) for _ in range(5)]
        reads_ref = [_make_aln(ref, ref_len)]
        result = call_consensus(reads_mut + reads_ref, ref)
        assert result[4] == "T"
        # Surrounding positions should match ref.
        assert result[3] == "C"
        assert result[5] == "T"

    def test_mixed_minor_allele_metrics_detect_51_49_signal(self) -> None:
        """A clean majority base still records substantial within-well mixture."""
        ref = "ATGCATGC"
        mut = ref[:2] + "T" + ref[3:]
        reads_major = [_make_aln(ref, len(ref)) for _ in range(51)]
        reads_minor = [_make_aln(mut, len(ref)) for _ in range(49)]

        result = call_consensus_with_metrics(
            reads_major + reads_minor,
            ref,
            mix_min_depth=10,
            mix_minor_fraction_threshold=0.20,
        )

        assert result.consensus_seq[2] == "G"
        assert result.n_mixed_positions == 1
        assert result.max_minor_allele_fraction == 0.49
        assert result.n_low_depth_positions == 0
        assert result.consensus_n_fraction == 0.0

    def test_fastq_low_quality_base_votes_are_excluded(self) -> None:
        """FASTQ qualities prevent low-confidence bases from winning consensus."""
        ref = "ATGCATGC"
        mut = ref[:2] + "T" + ref[3:]
        high_ref = _make_aln(ref, len(ref))
        high_ref.read_qual = "I" * len(ref)  # Q40
        low_mut_reads = [_make_aln(mut, len(ref)) for _ in range(3)]
        for aln in low_mut_reads:
            aln.read_qual = "!" * len(ref)  # Q0, excluded

        result = call_consensus_with_metrics(
            [high_ref, *low_mut_reads],
            ref,
            min_base_quality=10,
        )

        assert result.consensus_seq[2] == "G"
        assert result.n_low_quality_bases == 3 * len(ref)


class TestPerPositionDepth:

    def test_single_full_read(self) -> None:
        ref = "ATGCATGC"
        ref_len = len(ref)
        aln = _make_aln(ref, ref_len)
        depths = per_position_depth([aln], ref_len)
        assert len(depths) == ref_len
        assert all(d == 1 for d in depths)

    def test_two_reads_double_depth(self) -> None:
        ref = "ATGCATGC"
        ref_len = len(ref)
        alns = [_make_aln(ref, ref_len), _make_aln(ref, ref_len)]
        depths = per_position_depth(alns, ref_len)
        assert all(d == 2 for d in depths)

    def test_partial_read_depth(self) -> None:
        ref = "ATGCATGC"
        ref_len = len(ref)
        # A read that only covers positions 2-5 (4 bp, CIGAR=4M, r_st=2).
        partial_seq = ref[2:6]
        aln = Alignment(
            read_id="partial",
            read_seq=partial_seq,
            mapq=60,
            cigar=[[4, _CIGAR_M]],
            r_st=2,
            r_en=6,
            q_st=0,
            q_en=4,
            strand=1,
            reference_length=ref_len,
        )
        depths = per_position_depth([aln], ref_len)
        assert depths[0] == 0
        assert depths[1] == 0
        assert depths[2] == 1
        assert depths[5] == 1
        assert depths[6] == 0
        assert depths[7] == 0

    def test_empty_alignments_zero_depth(self) -> None:
        depths = per_position_depth([], 10)
        assert depths == [0] * 10
