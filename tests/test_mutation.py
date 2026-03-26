"""Tests for mutation parsing and codon substitution."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuro.codon_table import CODON_TO_AA
from kuro.mutation import (
    Mutation,
    mutate_sequence,
    parse_mutation_notation,
    parse_mutations,
)
from tests.conftest import TARGET_START


# Codon table tests moved to test_codon_table.py


class TestMutationParsing:
    def test_parse_notation(self):
        wt, pos, mt = parse_mutation_notation("Q232A")
        assert wt == "Q"
        assert pos == 232
        assert mt == "A"

    def test_parse_notation_single_digit(self):
        wt, pos, mt = parse_mutation_notation("A1G")
        assert wt == "A"
        assert pos == 1
        assert mt == "G"

    def test_invalid_notation(self):
        with pytest.raises(ValueError, match="Invalid mutation notation"):
            parse_mutation_notation("invalid")

    def test_parse_mutations_csv(self, template_sequence, mutations_csv):
        mutations = parse_mutations(mutations_csv, template_sequence, TARGET_START)
        assert len(mutations) == 12

        # Check first mutation: Q232A
        m = mutations[0]
        assert m.raw == "Q232A"
        assert m.wt_aa == "Q"
        assert m.position == 232
        assert m.mt_aa == "A"
        assert m.mt_codon == "GCG"  # Best E. coli codon for Ala
        # Verify WT codon encodes Q (Gln)
        assert CODON_TO_AA[m.wt_codon] == "Q"

    def test_all_12_mutations_parse(self, template_sequence, mutations_csv):
        mutations = parse_mutations(mutations_csv, template_sequence, TARGET_START)
        expected_names = [
            "Q232A", "Y233A", "E335A", "E167A", "K200A", "F203A",
            "D227A", "G237A", "P240A", "Y155A", "H100A", "C175A",
        ]
        actual_names = [m.raw for m in mutations]
        assert actual_names == expected_names

    def test_wt_codon_verification(self, template_sequence, mutations_csv):
        """Every parsed mutation's WT codon must encode the expected WT amino acid."""
        mutations = parse_mutations(mutations_csv, template_sequence, TARGET_START)
        for m in mutations:
            assert CODON_TO_AA[m.wt_codon] == m.wt_aa, (
                f"{m.raw}: codon {m.wt_codon} encodes {CODON_TO_AA[m.wt_codon]}, "
                f"expected {m.wt_aa}"
            )


class TestMutateSequence:
    def test_mutate_sequence(self, template_sequence, mutations_csv):
        mutations = parse_mutations(mutations_csv, template_sequence, TARGET_START)
        m = mutations[0]  # Q232A

        mutated = mutate_sequence(template_sequence, m)
        assert len(mutated) == len(template_sequence)

        # The codon at codon_start should now be mt_codon
        cs = m.codon_start
        assert mutated[cs:cs + 3] == m.mt_codon

        # Rest of sequence should be unchanged
        assert mutated[:cs] == template_sequence[:cs]
        assert mutated[cs + 3:] == template_sequence[cs + 3:]
