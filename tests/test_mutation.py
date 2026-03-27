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
    split_multi_notation,
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


class TestSplitMultiNotation:
    def test_split_multi_notation_single(self):
        """Single mutation: returns list with one element."""
        result = split_multi_notation("Q232A")
        assert result == ["Q232A"]

    def test_split_multi_notation_double(self):
        """Slash-separated double mutation: returns two elements."""
        result = split_multi_notation("A40P/E61Y")
        assert result == ["A40P", "E61Y"]

    def test_split_multi_notation_triple(self):
        """Slash-separated triple mutation: returns three elements."""
        result = split_multi_notation("A40P/E61Y/K100R")
        assert result == ["A40P", "E61Y", "K100R"]

    def test_split_multi_notation_multichain(self):
        """Chain with WT: WT token is silently dropped, mutations returned."""
        result = split_multi_notation("A40P/E61Y:WT")
        assert result == ["A40P", "E61Y"]

    def test_split_multi_notation_multichain_both(self):
        """Colon separating two chains each with one mutation: both returned."""
        result = split_multi_notation("A40P:E61Y")
        assert result == ["A40P", "E61Y"]


class TestParseMutationsMulti:
    """Tests for parse_mutations() with multi-mutation CSV input."""

    def test_parse_mutations_multi_csv(self, template_sequence, tmp_path):
        """Multi-mutation rows are decomposed into individual Mutation objects."""
        # Q232A and Y233A are both valid positions in the DmpR fixture sequence.
        csv_file = tmp_path / "multi_test.csv"
        csv_file.write_text("mutation\nQ232A/Y233A\n")

        mutations = parse_mutations(csv_file, template_sequence, TARGET_START)

        assert len(mutations) == 2
        assert mutations[0].raw == "Q232A"
        assert mutations[1].raw == "Y233A"
        # Both belong to the same group
        assert mutations[0].group_id == "Q232A/Y233A"
        assert mutations[1].group_id == "Q232A/Y233A"

    def test_parse_mutations_mixed_csv(self, template_sequence, tmp_path):
        """Single and multi-mutation rows produce the correct total Mutation count."""
        # Single row (1 mutation) + double row (2 mutations) = 3 total
        csv_file = tmp_path / "mixed_test.csv"
        csv_file.write_text("mutation\nH100A\nQ232A/Y233A\n")

        mutations = parse_mutations(csv_file, template_sequence, TARGET_START)

        assert len(mutations) == 3
        # Single-mutation row has no group_id
        assert mutations[0].raw == "H100A"
        assert mutations[0].group_id is None
        # Multi-mutation rows carry group_id
        assert mutations[1].raw == "Q232A"
        assert mutations[1].group_id == "Q232A/Y233A"
        assert mutations[2].raw == "Y233A"
        assert mutations[2].group_id == "Q232A/Y233A"


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
