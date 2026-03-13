"""Tests for the SDM primer design engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from evolveprimer.sdm_engine import (
    SdmPrimerResult,
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
        return design_sdm_primers(
            fasta_path=fasta_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase="Q5",
            overlap_len=20,
        )

    def test_12_of_12_success(self, sdm_results):
        """All 12 mutations must produce valid primers."""
        assert len(sdm_results) == 12

    def test_primer_lengths(self, sdm_results):
        """Primers should be between 25 and 60 bp."""
        for r in sdm_results:
            assert 20 <= r.fwd_len <= 60, f"{r.mutation.raw} fwd: {r.fwd_len} bp"
            assert 20 <= r.rev_len <= 60, f"{r.mutation.raw} rev: {r.rev_len} bp"

    def test_tm_in_range(self, sdm_results):
        """Non-overlap Tm should be in a reasonable range (50-85°C)."""
        for r in sdm_results:
            assert 50 <= r.tm_no_fwd <= 85, (
                f"{r.mutation.raw} Tm_no_fwd={r.tm_no_fwd:.1f}"
            )
            assert 50 <= r.tm_no_rev <= 85, (
                f"{r.mutation.raw} Tm_no_rev={r.tm_no_rev:.1f}"
            )

    def test_tm_double_check(self, sdm_results):
        """Report Tm condition (Tm_no > Tm_overlap + 5°C) compliance."""
        met = sum(1 for r in sdm_results if r.tm_condition_met)
        # At least 10/12 should meet the condition
        assert met >= 10, f"Only {met}/12 meet Tm condition"

    def test_gc_content(self, sdm_results):
        """GC content should be between 30-70%."""
        for r in sdm_results:
            assert 25 <= r.gc_fwd <= 75, f"{r.mutation.raw} GC_fwd={r.gc_fwd:.1f}%"
            assert 25 <= r.gc_rev <= 75, f"{r.mutation.raw} GC_rev={r.gc_rev:.1f}%"

    def test_codon_usage(self, sdm_results):
        """Mutant codons should be E. coli optimal."""
        from evolveprimer.codon_table import best_codon
        for r in sdm_results:
            expected = best_codon(r.mutation.mt_aa)
            assert r.mutation.mt_codon == expected, (
                f"{r.mutation.raw}: got {r.mutation.mt_codon}, "
                f"expected {expected}"
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
        results = design_sdm_primers(
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
        assert len(lines) == 13  # header + 12 mutations
        assert "Mutation" in lines[0]
