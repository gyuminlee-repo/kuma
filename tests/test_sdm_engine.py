"""Tests for the SDM primer design engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuro.sdm_engine import (
    OffTargetHit,
    SdmPrimerResult,
    _synthesis_score,
    check_offtarget,
    check_offtarget_sliding,
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
            overlap_len=18,
        )
        return results

    def test_majority_success(self, sdm_results):
        """Most mutations must produce valid primers (>=10/12)."""
        assert len(sdm_results) >= 10

    def test_primer_lengths(self, sdm_results):
        """Primers must match KURO spec: fwd 17-39 bp, rev 19-27 bp."""
        for r in sdm_results:
            assert 17 <= r.fwd_len <= 39, f"{r.mutation.raw} fwd: {r.fwd_len} bp"
            assert 19 <= r.rev_len <= 27, f"{r.mutation.raw} rev: {r.rev_len} bp"

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
            overlap_len=18,
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


class TestCheckOfftargetSliding:
    """Sliding-window off-target (PrimerBench / SnapGene-style)."""

    def test_empty_on_short_primer(self):
        # Primer shorter than min_length returns no hits.
        hits = check_offtarget_sliding(
            primer_seq="ACGTACGT",
            template="ACGTACGTACGTACGT",
            intended_start=0,
            intended_end=8,
            min_length=15,
        )
        assert hits == []

    def test_detects_internal_match(self):
        # 15-bp internal window ("CGTACGTACGTACGT") matches elsewhere on the
        # template — 3' anchor would miss, sliding must catch.
        internal = "CGTACGTACGTACGT"  # 15 bp
        primer = "AA" + internal + "TT"  # 19 bp, internal window matches
        # Template: intended site + distant copy of the internal window
        template = primer + "N" * 50 + internal + "N" * 20
        hits = check_offtarget_sliding(
            primer_seq=primer,
            template=template,
            intended_start=0,
            intended_end=len(primer),
            min_length=15,
        )
        internal_hits = [h for h in hits if h.truncation_type == "internal"]
        assert len(internal_hits) >= 1
        assert any(h.match_length == 15 for h in internal_hits)

    def test_full_length_match(self):
        primer = "ACGTACGTACGTACGTAC"  # 18 bp
        template = "N" * 40 + primer + "N" * 40 + primer + "N" * 40
        hits = check_offtarget_sliding(
            primer_seq=primer,
            template=template,
            intended_start=40,
            intended_end=40 + len(primer),
            min_length=15,
        )
        full = [h for h in hits if h.truncation_type == "full"]
        assert len(full) >= 1

    def test_self_hit_excluded(self):
        primer = "ACGTACGTACGTACGTAC"  # 18 bp, appears once
        template = "N" * 40 + primer + "N" * 40
        hits = check_offtarget_sliding(
            primer_seq=primer,
            template=template,
            intended_start=40,
            intended_end=40 + len(primer),
            min_length=15,
        )
        assert hits == []

    def test_antisense_detection(self):
        from kuro.overlap import reverse_complement
        primer = "ACGTACGTACGTACGTAC"  # 18 bp
        # Place the reverse complement elsewhere on the sense strand so it
        # surfaces as an antisense hit from the primer's point of view.
        rc = reverse_complement(primer)
        template = "N" * 40 + primer + "N" * 40 + rc + "N" * 40
        hits = check_offtarget_sliding(
            primer_seq=primer,
            template=template,
            intended_start=40,
            intended_end=40 + len(primer),
            min_length=15,
        )
        antisense = [h for h in hits if h.strand == "antisense"]
        assert len(antisense) >= 1
