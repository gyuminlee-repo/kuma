"""Tests for the SDM primer design engine."""

from __future__ import annotations

from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

from kuma_core.kuro.sdm_engine import (
    OffTargetHit,
    SdmPrimerResult,
    _design_full_overlap,
    _synthesis_score,
    check_offtarget,
    check_offtarget_sliding,
    design_sdm_primers,
    design_single_sdm,
    export_results_tsv,
    load_fasta,
    load_sequence,
)
from kuma_core.kuro.mutation import Mutation
from tests.conftest import FIXTURES_DIR, TARGET_START


class TestLoadFastaRaw:
    """`load_fasta()` remains a raw FASTA reader (used by sidecar RPC).

    The CDS-only enforcement is in `load_sequence()`, not `load_fasta()`.
    """

    def test_load_fasta(self, fasta_path):
        header, seq = load_fasta(fasta_path)
        assert "pSHCE-dmpR" in header
        assert len(seq) == 4532
        assert seq[:3] == "AAA"  # First 3 bases

    def test_atg_at_target_start(self, fasta_path):
        _, seq = load_fasta(fasta_path)
        assert seq[TARGET_START:TARGET_START + 3] == "ATG"


class TestLoadSequenceFastaRejection:
    """`load_sequence()` must reject FASTA inputs (CDS annotation required)."""

    def test_fa_extension_rejected(self, fasta_path):
        with pytest.raises(ValueError, match="CDS annotation required"):
            load_sequence(fasta_path)

    def test_fasta_extension_rejected(self, tmp_path):
        p = tmp_path / "sample.fasta"
        p.write_text(">hdr\nATGAAA\n")
        with pytest.raises(ValueError, match="CDS annotation required"):
            load_sequence(p)

    def test_fna_extension_rejected(self, tmp_path):
        p = tmp_path / "sample.fna"
        p.write_text(">hdr\nATGAAA\n")
        with pytest.raises(ValueError, match="CDS annotation required"):
            load_sequence(p)


class TestGenbankCdsExtraction:
    """End-to-end GenBank CDS extraction (covers complement strand,
    multi-record files, and missing /translation qualifier).
    """

    @staticmethod
    def _write_genbank(path: Path, records) -> None:
        SeqIO.write(records, str(path), "genbank")

    def test_complement_strand_translation(self, tmp_path):
        """A CDS on the complement strand must be extracted as reverse complement
        and translated correctly when /translation is absent.
        """
        # Build a 60 bp sequence; place a CDS on complement strand at 10..40 (Python slice).
        # On complement, the CDS reads as the reverse complement of seq[10:40].
        # Use a clean ORF on the reverse strand: start with ATG, stop at TAA.
        # Forward seq[10:40] = reverse_complement of "ATG AAA CCC GGG TTT TAA" (30 nt)
        cds_rev = "ATGAAACCCGGGTTTTAA"  # 18 nt, ends with TAA stop
        cds_fwd_segment = str(Seq(cds_rev).reverse_complement())
        full_seq = "N" * 10 + cds_fwd_segment + "N" * (60 - 10 - len(cds_fwd_segment))
        assert len(full_seq) == 60

        feat = SeqFeature(
            FeatureLocation(10, 10 + len(cds_fwd_segment), strand=-1),
            type="CDS",
            qualifiers={"gene": ["testGene"], "product": ["test product"]},
        )
        rec = SeqRecord(Seq(full_seq), id="TEST1", name="TEST1",
                        description="complement strand test",
                        annotations={"molecule_type": "DNA", "organism": "Test organism"})
        rec.features.append(feat)

        gb_path = tmp_path / "complement.gb"
        self._write_genbank(gb_path, [rec])

        header, sequence, genes = load_sequence(gb_path)
        assert len(genes) == 1
        gene = genes[0]
        assert gene.gene == "testGene"
        # Translation from extract() should drop stop codon → "MKPGF"
        expected_aa = str(Seq(cds_rev).translate(to_stop=True))
        assert gene.translation == expected_aa
        assert gene.translation == "MKPGF"

    def test_multi_record_genbank(self, tmp_path):
        """Multi-record GenBank: all CDS across records must be collected."""
        from Bio.Seq import Seq
        from Bio.SeqFeature import SeqFeature, FeatureLocation
        from Bio.SeqRecord import SeqRecord

        def make_record(rid: str, gene_name: str) -> SeqRecord:
            seq = "ATG" + "AAA" * 9 + "TAA" + "GGG" * 5
            feat = SeqFeature(
                FeatureLocation(0, 30, strand=1),
                type="CDS",
                qualifiers={"gene": [gene_name], "translation": ["MKKKKKKKKK"]},
            )
            rec = SeqRecord(Seq(seq), id=rid, name=rid, description=rid,
                            annotations={"molecule_type": "DNA"})
            rec.features.append(feat)
            return rec

        recs = [make_record("REC1", "geneA"), make_record("REC2", "geneB")]
        gb_path = tmp_path / "multi.gb"
        self._write_genbank(gb_path, recs)

        _header, _sequence, genes = load_sequence(gb_path)
        assert len(genes) == 2
        names = {g.gene for g in genes}
        assert names == {"geneA", "geneB"}

    def test_missing_translation_sense_strand(self, tmp_path):
        """CDS without /translation: translate from sense strand, stop at first stop codon."""
        from Bio.Seq import Seq
        from Bio.SeqFeature import SeqFeature, FeatureLocation
        from Bio.SeqRecord import SeqRecord

        # ATG AAA CCC GGG TTT TAA = MKPGF + stop
        cds_seq = "ATGAAACCCGGGTTTTAA"
        full_seq = "C" * 5 + cds_seq + "C" * 5
        feat = SeqFeature(
            FeatureLocation(5, 5 + len(cds_seq), strand=1),
            type="CDS",
            qualifiers={"gene": ["noTransGene"]},  # NO /translation qualifier
        )
        rec = SeqRecord(Seq(full_seq), id="NOTR", name="NOTR",
                        description="missing translation test",
                        annotations={"molecule_type": "DNA"})
        rec.features.append(feat)

        gb_path = tmp_path / "no_translation.gb"
        self._write_genbank(gb_path, [rec])

        _header, _sequence, genes = load_sequence(gb_path)
        assert len(genes) == 1
        assert genes[0].translation == "MKPGF"


class TestDesignSdmPrimers:
    """Integration test: design primers for all 12 mutations."""

    @pytest.fixture(scope="class")
    def sdm_results(self, genbank_path, mutations_csv) -> list[SdmPrimerResult]:
        results, _, _f = design_sdm_primers(
            fasta_path=genbank_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase="Q5",
            overlap_len=18,
        )
        return results

    def test_paper_target_baseline_yield(self, sdm_results):
        """First-pass yield is a minority of this fixture, and that is correct.

        Pinning the design targets to the paper values 62/58/42 with
        min_3prime_dist 4 on the fixed Benchling Tm scale gives a first-pass
        yield of 5/12 on this 12-mutation fixture. The other 7 are legitimate
        failures under the paper constraints (physically impossible placement,
        3' distance, or rev length 19 bp floor and rev Tm 58 unsatisfiable at
        the same time), not a regression. In real use the rescue cascade
        recovers further mutations on top of this baseline.

        Enzyme identity moved to Ta only, so every profile designs alike and
        5/12 equals the Benchling reference.
        """
        assert len(sdm_results) >= 5

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
        from kuma_core.kuro.codon_table import codon_to_aa
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
    def test_export(self, genbank_path, mutations_csv, tmp_path):
        results, _, _f = design_sdm_primers(
            fasta_path=genbank_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase="Q5",
            overlap_len=18,
        )
        tsv_path = tmp_path / "test_primers.tsv"
        export_results_tsv(results, tsv_path)

        assert tsv_path.exists()
        lines = tsv_path.read_text().strip().split("\n")
        # Design now follows the paper targets (62/58/42) + min_3prime_dist 4 on the
        # fixed Benchling Tm scale, so the yield changed: 5 successes ->
        # metadata(1)+header(1)+5 = 7 lines.
        assert len(lines) >= 7  # metadata + header + successful mutations (>=5)
        assert lines[0].startswith("# overlap_mode=")
        assert "Mutation" in lines[1]
        assert "Tm_Overlap" in lines[1]  # partial mode keeps original column name

    def test_export_full_overlap_renames_third_tm_column(self, genbank_path, mutations_csv, tmp_path):
        results, _, _f = design_sdm_primers(
            fasta_path=genbank_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase="Q5",
            overlap_len=18,
            overlap_mode="full",
        )
        tsv_path = tmp_path / "test_primers_full.tsv"
        export_results_tsv(results, tsv_path, overlap_mode="full")

        assert tsv_path.exists()
        lines = tsv_path.read_text().strip().split("\n")
        assert lines[0] == "# overlap_mode=full"
        assert "Tm_Primer" in lines[1]
        assert "Tm_Overlap" not in lines[1]


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
    def test_immediate_cancel(self, genbank_path, mutations_csv):
        results, _, _ = design_sdm_primers(
            fasta_path=genbank_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            cancel_check=lambda: True,
        )
        assert len(results) == 0

    def test_no_cancel(self, genbank_path, mutations_csv):
        results, _, _ = design_sdm_primers(
            fasta_path=genbank_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            cancel_check=lambda: False,
        )
        # Design now follows the paper targets (62/58/42) + min_3prime_dist 4 on the
        # fixed Benchling Tm scale, so the yield changed: 5/12.
        assert len(results) >= 5

    def test_partial_cancel(self, genbank_path, mutations_csv):
        counter = {"n": 0}
        def cancel_after_3():
            counter["n"] += 1
            return counter["n"] > 3
        results, _, _ = design_sdm_primers(
            fasta_path=genbank_path,
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
        from kuma_core.kuro.overlap import reverse_complement
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


class TestDesignFullOverlap:
    """Unit tests for _design_full_overlap and full-overlap branch of design_single_sdm."""

    # Synthetic template: 100 bp with a clearly addressable codon at position 30
    SEQ = "ATGATGATGATGATGATGATGATGATGATG" + "GCAGCAGCA" + "CGTCGTCGTCGTCGTCGTCGTCGTCGTCGT"
    # codon_start=30, WT codon = "GCA" (Ala), mutant codon = "GCG" (also Ala, silent)
    CODON_START = 30
    MUTANT_CODON = "GCG"

    def test_normal_case_tm60(self):
        """Returns a valid (fwd, rev, tm_fwd, tm_rev, left_ext) tuple within ±2°C of 60."""
        result = _design_full_overlap(
            seq=self.SEQ,
            codon_start=self.CODON_START,
            mutant_codon=self.MUTANT_CODON,
            target_tm=60.0,
            tolerance=4.0,
            fwd_len_min=17,
            fwd_len_max=39,
            rev_len_min=17,
            rev_len_max=39,
        )
        assert result is not None, "Expected a valid primer pair for Tm=60, tol=4"
        fwd, rev, tm_fwd, tm_rev, left_ext = result
        assert len(fwd) >= 17
        assert len(fwd) <= 39
        assert len(fwd) == len(rev), "Full overlap: fwd and rev must be same length (rev = rc(fwd))"
        assert tm_fwd == tm_rev, "Full overlap: fwd Tm and rev Tm are always equal (rc symmetry)"
        assert self.MUTANT_CODON in fwd, "Mutant codon must appear in forward primer"
        from kuma_core.kuro.overlap import reverse_complement
        assert rev == reverse_complement(fwd), "Reverse primer must be rc of forward primer"

    def test_tm_match_failure(self):
        """Returns None when tolerance is too tight and no valid primer exists."""
        result = _design_full_overlap(
            seq=self.SEQ,
            codon_start=self.CODON_START,
            mutant_codon=self.MUTANT_CODON,
            target_tm=99.0,   # unreachable Tm
            tolerance=0.1,
            fwd_len_min=17,
            fwd_len_max=39,
        )
        assert result is None, "Should return None when target Tm is unreachable"

    def test_length_constraint_boundary(self):
        """Length limits are respected: primer length stays in [L_min, L_max]."""
        result = _design_full_overlap(
            seq=self.SEQ,
            codon_start=self.CODON_START,
            mutant_codon=self.MUTANT_CODON,
            target_tm=55.0,
            tolerance=8.0,   # wide tolerance to maximise coverage
            fwd_len_min=20,
            fwd_len_max=25,
            rev_len_min=20,
            rev_len_max=25,
        )
        assert result is not None, (
            "_design_full_overlap returned None with target_tm=55 tol=8 and [20,25] bounds; "
            "sequence may be too short or bounds exclude all valid lengths"
        )
        fwd, rev, _tm_fwd, _tm_rev, _left_ext = result
        assert 20 <= len(fwd) <= 25, f"fwd length {len(fwd)} out of [20, 25]"
        assert 20 <= len(rev) <= 25, f"rev length {len(rev)} out of [20, 25]"

    def test_design_single_sdm_full_mode(self, template_sequence):
        """design_single_sdm with overlap_mode='full' returns valid SdmPrimerResult list."""
        from kuma_core.kuro.polymerase import PolymeraseRegistry
        registry = PolymeraseRegistry()
        profile = registry.get("Q5")
        mut = Mutation(
            raw="A597V",
            wt_aa="A",
            position=597,
            mt_aa="V",
            codon_start=TARGET_START + (597 - 1) * 3,
            wt_codon="GCG",
            mt_codon="GTG",
        )
        results = design_single_sdm(
            template_sequence, mut, profile,
            overlap_mode="full",
            tol_max=5.0,
        )
        # Must produce at least one result (wide tolerance)
        assert len(results) >= 1, "design_single_sdm full mode produced no results"
        r = results[0]
        from kuma_core.kuro.overlap import reverse_complement
        assert r.reverse_seq == reverse_complement(r.forward_seq), (
            "Full overlap: reverse_seq must be rc(forward_seq)"
        )
        assert r.tm_fwd == r.tm_rev, "Full overlap: fwd/rev Tm must be equal"

    @pytest.fixture(scope="class")
    def partial_results(self, genbank_path, mutations_csv) -> list[SdmPrimerResult]:
        """Run partial mode as regression baseline."""
        results, _, _ = design_sdm_primers(
            fasta_path=genbank_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase="Q5",
            overlap_len=18,
        )
        return results

    def test_partial_regression(self, partial_results):
        """Partial overlap still succeeds on the fixture dataset (regression guard)."""
        # Design now follows the paper targets (62/58/42) + min_3prime_dist 4 on the
        # fixed Benchling Tm scale, so the yield changed: 5/12.
        assert len(partial_results) >= 5, "Partial mode must still succeed on fixture dataset"
        for r in partial_results:
            assert r.fwd_len >= 17, f"{r.mutation.raw} fwd_len {r.fwd_len} < 17"
            assert r.rev_len >= 19, f"{r.mutation.raw} rev_len {r.rev_len} < 19 (partial spec)"


class TestSdmTmTargetsAreMethodLevel:
    """SDM Tm targets are method constants, identical for every polymerase.

    Landwehr et al. 2025 (Nat Commun 16, 865) SI Fig. S4 fixes Fwd 62 / Rev 58 /
    Overlap 42 C for the overlap-extension geometry, independent of the enzyme.
    These tests fail if the targets are ever re-derived from each profile own
    opt_tm (which produced Q5/KOD 68/64/48 and Taq 64/60/44).
    """

    @pytest.fixture()
    def mutation(self) -> Mutation:
        return Mutation(
            raw="A597V",
            wt_aa="A",
            position=597,
            mt_aa="V",
            codon_start=TARGET_START + (597 - 1) * 3,
            wt_codon="GCG",
            mt_codon="GTG",
        )

    @pytest.mark.parametrize("name", ["Q5", "KOD", "Taq", "DreamTaq", "Phusion"])
    def test_designed_tm_tracks_method_targets_not_opt_tm(
        self, template_sequence, mutation: Mutation, name: str
    ):
        from kuma_core.kuro.polymerase import PolymeraseRegistry

        profile = PolymeraseRegistry().get(name)
        tol = 4.0
        results = design_single_sdm(
            template_sequence, mutation, profile, overlap_mode="partial", tol_max=tol
        )
        assert results, f"{name}: design produced no results"
        r = results[0]
        # opt_tm-derived targets (e.g. Q5 68) would land >tol away from 62.
        assert abs(r.tm_fwd - 62.0) <= tol, f"{name}: tm_fwd {r.tm_fwd} not tracking 62"
        assert abs(r.tm_rev - 58.0) <= tol, f"{name}: tm_rev {r.tm_rev} not tracking 58"
        assert abs(r.tm_overlap - 42.0) <= tol, (
            f"{name}: tm_overlap {r.tm_overlap} not tracking 42"
        )

    def test_custom_profile_without_targets_falls_back_to_method_constants(
        self, template_sequence, mutation: Mutation
    ):
        """A user custom profile carrying only opt_tm must not derive targets from it."""
        from dataclasses import replace

        from kuma_core.kuro.polymerase import PolymeraseRegistry

        # opt_tm 68 with no explicit targets: the old code derived 68/64/48.
        custom = replace(
            PolymeraseRegistry().get("KOD"),
            name="CustomPoly",
            opt_tm=68.0,
            opt_tm_fwd=None,
            opt_tm_rev=None,
            opt_tm_overlap=None,
        )
        results = design_single_sdm(
            template_sequence, mutation, custom, overlap_mode="partial", tol_max=4.0
        )
        assert results, "custom profile: design produced no results"
        r = results[0]
        assert abs(r.tm_fwd - 62.0) <= 4.0, f"custom: tm_fwd {r.tm_fwd} derived from opt_tm"
        assert abs(r.tm_rev - 58.0) <= 4.0, f"custom: tm_rev {r.tm_rev} derived from opt_tm"


class TestDesignIsEnzymeIndependent:
    """Contract: the polymerase choice must not change the designed primers.

    Design runs on one fixed Tm scale (the paper Benchling SantaLucia 1998 scale)
    with method-level targets, so every profile sharing a length spec yields
    byte-identical primers. Enzyme identity surfaces only in the annealing
    temperature. This fails if a per-profile buffer, or the NEB calibration table,
    ever re-enters the design path (via _calc_sdm_tm or _check_secondary_structure,
    whose penalty feeds candidate ranking).
    """

    # Q5 SDM is excluded deliberately: it is a full-overlap kit profile with its own
    # length spec (fwd/rev 25-45, overlap_len None, default mode "full"), so it
    # designs differently for reasons of geometry, not Tm scale.
    SHARED_LEN_SPEC = ["KOD", "Taq", "Phusion", "Q5", "DreamTaq", "TAKARA_GXL"]

    def _design(self, genbank_path, mutations_csv, name: str):
        results, _cand, _fail = design_sdm_primers(
            fasta_path=genbank_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase=name,
            overlap_len=18,
        )
        return [(r.mutation.raw, r.forward_seq, r.reverse_seq) for r in results]

    def test_all_profiles_design_byte_identical_primers(self, genbank_path, mutations_csv):
        designs = {n: self._design(genbank_path, mutations_csv, n) for n in self.SHARED_LEN_SPEC}
        ref_name = self.SHARED_LEN_SPEC[0]
        reference = designs[ref_name]
        assert reference, f"{ref_name} reference design is empty"
        for name, got in designs.items():
            assert got == reference, (
                f"{name} designed different primers than {ref_name}: design must be "
                f"enzyme-independent (got {len(got)} vs {len(reference)} results)"
            )

    def test_annealing_temperature_still_varies_by_profile(self, genbank_path, mutations_csv):
        """The flip side: Ta is where enzyme identity is allowed to show up."""
        from kuma_core.kuro import neb_tm
        from kuma_core.kuro.annealing import compute_annealing
        from kuma_core.kuro.polymerase import PolymeraseRegistry

        offsets = neb_tm.load_offsets()
        registry = PolymeraseRegistry()
        results, _cand, _fail = design_sdm_primers(
            fasta_path=genbank_path,
            target_start=TARGET_START,
            mutations_csv=mutations_csv,
            polymerase="KOD",
            overlap_len=18,
        )
        assert results, "no design to compute Ta from"
        r = results[0]
        tas = {
            n: compute_annealing(r.forward_seq, r.reverse_seq, registry.get(n), offsets)[
                "recommended_ta"
            ]
            for n in self.SHARED_LEN_SPEC
        }
        assert len({v for v in tas.values() if v is not None}) > 1, (
            f"Ta must differ by polymerase, got {tas}"
        )
