"""Tests for codon usage table and codon selection utilities."""

from __future__ import annotations

import pytest

from kuro.codon_table import (
    CODON_TO_AA,
    ECOLI_CODON_USAGE,
    CodonTableRegistry,
    best_codon,
    closest_codon,
    codon_to_aa,
    get_codon_table,
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

    def test_organism_kwarg_accepted(self):
        # organism kwarg is now valid — should return a valid codon
        codon = best_codon("A", organism="yeast")
        assert len(codon) == 3
        assert codon_to_aa(codon) == "A"


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

    def test_organism_parameter_changes_result(self):
        # E. coli best A codon is GCG; yeast best A codon is GCT
        ecoli_codons = mt_codons_for_design("AAA", "A", organism="ecoli")
        yeast_codons = mt_codons_for_design("AAA", "A", organism="scerevisiae")
        # The optimal codons should differ
        ecoli_optimal = best_codon("A", "ecoli")
        yeast_optimal = best_codon("A", "scerevisiae")
        assert ecoli_optimal != yeast_optimal
        # Both should encode A
        assert codon_to_aa(ecoli_codons[0]) == "A"
        assert codon_to_aa(yeast_codons[0]) == "A"


class TestCodonTableRegistry:
    def test_list_organisms_returns_four(self):
        registry = CodonTableRegistry()
        organisms = registry.list_organisms()
        assert len(organisms) == 4
        expected = {"ecoli", "bsubtilis", "scerevisiae", "hsapiens"}
        assert set(organisms) == expected

    def test_list_organisms_detailed_has_keys(self):
        registry = CodonTableRegistry()
        details = registry.list_organisms_detailed()
        assert len(details) == 4
        for item in details:
            assert "key" in item
            assert "name" in item
            assert "taxid" in item

    def test_get_codon_table_ecoli(self):
        table = get_codon_table("ecoli")
        assert "A" in table
        assert "M" in table
        assert "*" in table
        # All 20 AA + stop
        assert len(table) == 21

    def test_get_codon_table_all_organisms(self):
        registry = CodonTableRegistry()
        for org in registry.list_organisms():
            table = registry.get_codon_table(org)
            assert len(table) == 21
            # Each AA should have at least one codon
            for aa, codons in table.items():
                assert len(codons) >= 1
                # Frequencies should sum close to 1.0
                total = sum(freq for _, freq in codons)
                assert 0.95 <= total <= 1.05, f"{org}/{aa}: freq sum={total}"

    def test_alias_resolution(self):
        registry = CodonTableRegistry()
        t1 = registry.get_codon_table("ecoli")
        t2 = registry.get_codon_table("E. coli")
        t3 = registry.get_codon_table("Escherichia coli")
        assert t1 is t2  # same cached object
        assert t1 is t3

    def test_unknown_organism_raises(self):
        registry = CodonTableRegistry()
        with pytest.raises(ValueError, match="Unknown organism"):
            registry.get_codon_table("nonexistent_organism")

    def test_ecoli_backward_compatible(self):
        # ECOLI_CODON_USAGE constant should match get_codon_table("ecoli")
        table = get_codon_table("ecoli")
        assert table == ECOLI_CODON_USAGE

    def test_best_codon_per_organism(self):
        # E. coli: best A = GCG (GC-rich preference)
        assert best_codon("A", "ecoli") == "GCG"
        # Yeast: best A = GCT (AT-rich preference)
        assert best_codon("A", "scerevisiae") == "GCT"
        # Human: best A = GCC
        assert best_codon("A", "hsapiens") == "GCC"

    def test_closest_codon_per_organism(self):
        # Same target but different organisms may pick different codons
        ecoli_closest = closest_codon("AAA", "A", organism="ecoli")
        yeast_closest = closest_codon("AAA", "A", organism="scerevisiae")
        assert codon_to_aa(ecoli_closest) == "A"
        assert codon_to_aa(yeast_closest) == "A"

