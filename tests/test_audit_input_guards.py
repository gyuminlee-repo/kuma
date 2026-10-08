"""Input-contract regressions: never change the requested genotype silently."""
from pathlib import Path

import pytest

from kuma_core.kuro.mutation import parse_mutation_notation, parse_mutations, split_multi_notation
from kuma_core.mame.export.janus_mapping import JanusSettings


@pytest.mark.parametrize("notation", ["A0G", "M00A", "Q000Y"])
def test_mutation_positions_are_one_based(notation: str) -> None:
    with pytest.raises(ValueError, match="mutation notation|1-based"):
        parse_mutation_notation(notation)


def test_zero_position_cannot_mutate_a_matching_upstream_codon(tmp_path: Path) -> None:
    mutations = tmp_path / "mutations.csv"
    mutations.write_text("mutation\nA0G\n", encoding="utf-8")
    # Position zero previously resolved to the upstream GCT when CDS starts at 3.
    with pytest.raises(ValueError, match="mutation notation|1-based"):
        parse_mutations(mutations, "GCTATGGCT", 3, "ecoli")


def test_position_one_still_resolves_at_the_cds_start(tmp_path: Path) -> None:
    mutations = tmp_path / "mutations.csv"
    mutations.write_text("mutation\nM1A\n", encoding="utf-8")
    result = parse_mutations(mutations, "GCTATGGCT", 3, "ecoli")
    assert result[0].position == 1
    assert result[0].codon_start == 3
    assert result[0].wt_codon == "ATG"


@pytest.mark.parametrize("notation", ["A2V/BAD", "BAD", "A2V:E3", "A0G/WT"])
def test_invalid_component_rejects_the_whole_mutation_row(notation: str) -> None:
    with pytest.raises(ValueError):
        split_multi_notation(notation)


def test_bad_component_cannot_become_a_single_mutant(tmp_path: Path) -> None:
    mutations = tmp_path / "mutations.csv"
    mutations.write_text("mutation\nA2V/BAD\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parse_mutations(mutations, "ATGGCTGAA", 0, "ecoli")


def test_valid_compound_and_explicit_wt_are_preserved() -> None:
    assert split_multi_notation("A2V/E3Y:WT") == ["A2V", "E3Y"]
    assert split_multi_notation("WT") == []


@pytest.mark.parametrize("volume", [float("inf"), float("-inf"), float("nan"), 0.0, -1.0])
def test_instrument_volume_must_be_finite_and_positive(volume: float) -> None:
    with pytest.raises(ValueError, match="volume"):
        JanusSettings(volume=volume)


@pytest.mark.parametrize("volume", [0.1, 70.0, 100.0])
def test_valid_instrument_volume_is_not_replaced(volume: float) -> None:
    assert JanusSettings(volume=volume).volume == volume
