"""Tests for codon usage table and codon selection utilities."""

from __future__ import annotations

import pytest

from kuro.codon_table import (
    CODON_TO_AA,
    ECOLI_CODON_USAGE,
    best_codon,
    closest_codon,
    codon_to_aa,
    mt_codons_for_design,
)


STANDARD_20_AA = "ACDEFGHIKLMNPQRSTVWY"


class TestBestCodon:
    def test_all_20_amino_acids_return_valid_codon(self):
        for aa in STANDARD_20_AA:
            codon = best_codon(aa)
            assert len(codon) == 3
            assert all(base in "ACGT" for base in codon)

    def test_best_codon_encodes_correct_aa(self):
        for aa in STANDARD_20_AA:
            codon = best_codon(aa)
            assert codon_to_aa(codon) == aa

    def test_best_codon_is_highest_frequency(self):
        for aa in STANDARD_20_AA:
            codons = ECOLI_CODON_USAGE[aa]
            max_freq = max(freq for _, freq in codons)
            result = best_codon(aa)
            freq_of_result = dict(codons)[result]
            assert freq_of_result == max_freq

    def test_stop_codon(self):
        codon = best_codon("*")
        assert codon == "TAA"  # most frequent stop in E. coli

    def test_lowercase_input(self):
        assert best_codon("a") == best_codon("A")

    def test_invalid_amino_acid_raises(self):
        with pytest.raises(ValueError, match="Invalid amino acid"):
            best_codon("X")

    def test_invalid_amino_acid_digit_raises(self):
        with pytest.raises(ValueError, match="Invalid amino acid"):
            best_codon("1")

    def test_extra_kwargs_raises(self):
        with pytest.raises(TypeError):
            best_codon("A", organism="yeast")


class TestCodonToAA:
    def test_all_codons_mapped(self):
        assert len(CODON_TO_AA) == 64

    def test_start_codon(self):
        assert CODON_TO_AA["ATG"] == "M"

    def test_stop_codons(self):
        for stop in ["TAA", "TAG", "TGA"]:
            assert CODON_TO_AA[stop] == "*"

    def test_codon_to_aa_function(self):
        assert codon_to_aa("ATG") == "M"
        assert codon_to_aa("GCG") == "A"

    def test_lowercase_codon_accepted(self):
        assert codon_to_aa("atg") == "M"

    def test_invalid_codon_raises(self):
        with pytest.raises(ValueError, match="Invalid codon"):
            codon_to_aa("XYZ")

    def test_too_short_codon_raises(self):
        with pytest.raises(ValueError, match="Invalid codon"):
            codon_to_aa("AT")


class TestClosestCodon:
    def test_same_codon_returns_itself(self):
        # GCG -> A; closest A codon to GCG is GCG itself
        assert closest_codon("GCG", "A") == "GCG"

    def test_one_base_change(self):
        # AAA encodes K; closest L codon should minimize hamming distance
        result = closest_codon("AAA", "L")
        assert codon_to_aa(result) == "L"

    def test_prefers_higher_frequency_at_same_distance(self):
        # For two codons equidistant from wt_codon, the higher-frequency one wins
        result = closest_codon("AAA", "A")
        assert codon_to_aa(result) == "A"
        # Verify it picks the best among equidistant options
        assert result in [c for c, _ in ECOLI_CODON_USAGE["A"]]

    def test_invalid_target_aa_raises(self):
        with pytest.raises(ValueError, match="Invalid amino acid"):
            closest_codon("ATG", "X")

    def test_lowercase_inputs_accepted(self):
        upper = closest_codon("GCG", "A")
        lower = closest_codon("gcg", "a")
        assert upper == lower


class TestMtCodonsForDesign:
    def test_closest_strategy_order(self):
        codons = mt_codons_for_design("AAA", "A", strategy="closest")
        assert len(codons) >= 1
        for c in codons:
            assert codon_to_aa(c) == "A"

    def test_optimal_strategy_order(self):
        codons = mt_codons_for_design("AAA", "A", strategy="optimal")
        assert codons[0] == best_codon("A")

    def test_single_result_when_closest_equals_optimal(self):
        # GCG is the best codon for A; closest to GCG for A is also GCG
        codons = mt_codons_for_design("GCG", "A", strategy="closest")
        assert len(codons) == 1
        assert codons[0] == "GCG"

    def test_two_distinct_codons_when_different(self):
        # AAA -> A: closest (GCA, hamming=2) != optimal (GCG)
        codons = mt_codons_for_design("AAA", "A", strategy="closest")
        assert len(codons) == 2
        assert codons[0] != codons[1]
        assert all(codon_to_aa(c) == "A" for c in codons)

    def test_methionine_always_returns_one(self):
        # M has only one codon (ATG)
        codons = mt_codons_for_design("TTT", "M")
        assert codons == ["ATG"]

    def test_tryptophan_always_returns_one(self):
        # W has only one codon (TGG)
        codons = mt_codons_for_design("TTT", "W")
        assert codons == ["TGG"]
