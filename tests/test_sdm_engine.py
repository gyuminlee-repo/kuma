"""Tests for the SDM primer design engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuro.sdm_engine import (
    SdmPrimerResult,
    _synthesis_score,
    design_sdm_primers,
    export_results_tsv,
    load_fasta,
)
from tests.conftest import FIXTURES_DIR, TARGET_START


class TestLoadFasta:
    def test_load_fasta(self, fasta_path):
        header, seq = load_fasta(fasta_path)
        assert "pSHCE-dmpR" in header
        assert len(seq) == 4532
        assert seq[:3] == "AAA"  # First 3 bases

    def test_atg_at_target_start(self, fasta_path):
        _, seq = load_fasta(fasta_path)
        assert seq[TARGET_START:TARGET_START + 3] == "ATG"


class TestDesignSdmPrimers:
    """Integration test: design primers for all 12 mutations."""

    @pytest.fixture(scope="class")
    def sdm_results(self, fasta_path, mutations_csv) -> list[SdmPrimerResult]:
        results, _, _f = design_sdm_primers(
            fasta_path=fasta_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase="Q5",
            overlap_len=20,
        )
        return results

    def test_majority_success(self, sdm_results):
        """Most mutations must produce valid primers (>=10/12)."""
        assert len(sdm_results) >= 10

    def test_primer_lengths(self, sdm_results):
        """Primers should be between 18 and 60 bp."""
        for r in sdm_results:
            assert 18 <= r.fwd_len <= 60, f"{r.mutation.raw} fwd: {r.fwd_len} bp"
            assert 18 <= r.rev_len <= 60, f"{r.mutation.raw} rev: {r.rev_len} bp"

    def test_tm_in_range(self, sdm_results):
        """Non-overlap Tm should be in a reasonable range (50-85°C)."""
        for r in sdm_results:
            assert 50 <= r.tm_fwd <= 85, (
                f"{r.mutation.raw} Tm_no_fwd={r.tm_fwd:.1f}"
            )
            assert 50 <= r.tm_rev <= 85, (
                f"{r.mutation.raw} Tm_no_rev={r.tm_rev:.1f}"
            )

    def test_tm_within_tolerance(self, sdm_results):
        """All results should have Tm within their tolerance_used range."""
        for r in sdm_results:
            assert r.tm_condition_met, (
                f"{r.mutation.raw}: tm_condition not met "
                f"(fwd={r.tm_fwd:.1f}, rev={r.tm_rev:.1f}, "
                f"overlap={r.tm_overlap:.1f}, tol=±{r.tolerance_used})"
            )

    def test_gc_content(self, sdm_results):
        """GC content should be between 15-90% (relaxed for GC-rich SDM contexts)."""
        for r in sdm_results:
            assert 15 <= r.gc_fwd <= 90, f"{r.mutation.raw} GC_fwd={r.gc_fwd:.1f}%"
            assert 15 <= r.gc_rev <= 90, f"{r.mutation.raw} GC_rev={r.gc_rev:.1f}%"

    def test_codon_usage(self, sdm_results):
        """Mutant codons should encode the correct amino acid."""
        from kuro.codon_table import codon_to_aa
        for r in sdm_results:
            actual_aa = codon_to_aa(r.mutation.mt_codon)
            assert actual_aa == r.mutation.mt_aa, (
                f"{r.mutation.raw}: codon {r.mutation.mt_codon} encodes "
                f"{actual_aa}, expected {r.mutation.mt_aa}"
            )

    def test_forward_contains_mutation(self, sdm_results):
        """Forward primer must contain the mutant codon."""
        for r in sdm_results:
            assert r.mutation.mt_codon in r.forward_seq, (
                f"{r.mutation.raw}: mutant codon {r.mutation.mt_codon} "
                f"not found in forward primer"
            )


class TestExportTsv:
    def test_export(self, fasta_path, mutations_csv, tmp_path):
        results, _, _f = design_sdm_primers(
            fasta_path=fasta_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase="Q5",
            overlap_len=20,
        )
        tsv_path = tmp_path / "test_primers.tsv"
        export_results_tsv(results, tsv_path)

        assert tsv_path.exists()
        lines = tsv_path.read_text().strip().split("\n")
        assert len(lines) >= 11  # header + successful mutations (>=10)
        assert "Mutation" in lines[0]


class TestSynthesisScore:
    def test_clean_sequence(self):
        assert _synthesis_score("ATGCATGCATGCATGC") == 100.0

    def test_empty_sequence(self):
        assert _synthesis_score("") == 100.0

    def test_homopolymer_run_4(self):
        score = _synthesis_score("ATGCAAAATGCATGC")
        assert score == 95.0  # -5 * (4-3) = -5

    def test_homopolymer_run_6(self):
        score = _synthesis_score("ATGCAAAAAATGCAT")
        assert score == 70.0  # -5*(6-3)=-15, plus extreme GC -15

    def test_gc_rich_run_6(self):
        seq = "ATGCGGCCCCTGCATG"
        score = _synthesis_score(seq)
        assert score < 100.0

    def test_dinucleotide_repeat(self):
        score = _synthesis_score("ATATATATCATGCATG")
        assert score == 77.0  # -8 dinucleotide + -15 extreme GC

    def test_multiple_dinucleotide_patterns(self):
        score = _synthesis_score("ATATATATGCGCGCGC")
        assert score < 92.0  # AT repeat + GC repeat

    def test_extreme_gc_low(self):
        score = _synthesis_score("AAATTTTAAATTTAAA")
        assert score == 80.0  # -15 GC<30% + -5 homopolymer(TTTT)

    def test_compound_penalty(self):
        # 16x A: homopolymer -5*(16-3)=-65, extreme GC -15 = -80, floor 0
        score = _synthesis_score("AAAAAAAAAAAAAAAA")
        assert score == 20.0  # 100 - 65(homopolymer) - 15(GC<30%)

    def test_score_is_rounded(self):
        score = _synthesis_score("ATGC")
        assert isinstance(score, float)


class TestCancelCheck:
    def test_immediate_cancel(self, fasta_path, mutations_csv):
        results, _, _ = design_sdm_primers(
            fasta_path=fasta_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            cancel_check=lambda: True,
        )
        assert len(results) == 0

    def test_no_cancel(self, fasta_path, mutations_csv):
        results, _, _ = design_sdm_primers(
            fasta_path=fasta_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            cancel_check=lambda: False,
        )
        assert len(results) >= 10

    def test_partial_cancel(self, fasta_path, mutations_csv):
        counter = {"n": 0}
        def cancel_after_3():
            counter["n"] += 1
            return counter["n"] > 3
        results, _, _ = design_sdm_primers(
            fasta_path=fasta_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            cancel_check=cancel_after_3,
        )
        assert 0 < len(results) <= 3
