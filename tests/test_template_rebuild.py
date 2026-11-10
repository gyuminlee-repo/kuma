"""Template rebuild: recorded codons, refusals, and the design it feeds.

A round that adds one substitution to an earlier clone has to be designed
against that clone. The rebuild applies the codon the earlier design recorded
rather than re-choosing one, so the product matches the plasmid in the freezer.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from kuma_core.kuro import cli
from kuma_core.kuro.codon_table import CODON_TO_AA
from kuma_core.kuro.mutation import Mutation, rebuild_template_sequence
from kuma_core.kuro.sdm_engine import load_sequence

TARGET_START = 1790

_TSV_HEADER = (
    "# overlap_mode=partial\n"
    "Mutation\tForward_Primer\tReverse_Primer\tFwd_Length\tRev_Length\t"
    "Tm_Fwd\tTm_Rev\tTm_Overlap\tTolerance\tPenalty\tOff_Target\t"
    "GC_Fwd\tGC_Rev\tWT_Codon\tMT_Codon\tOverlap_Seq\tWarnings\tGroup\n"
)


def _tsv(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    """Write a design TSV carrying only the columns the rebuild reads."""
    lines = [_TSV_HEADER]
    for notation, wt_codon, mt_codon in rows:
        lines.append(
            f"{notation}\tACGTACGTACGTACGTAC\tACGTACGTACGTACGTAC\t18\t18\t"
            f"62.0\t62.0\t42.0\t±1.0\t0.0\tNO\t50.0\t50.0\t"
            f"{wt_codon}\t{mt_codon}\tACGTAC\t\t\n"
        )
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _mutation(notation: str, wt_codon: str, mt_codon: str) -> Mutation:
    """A Mutation as ``read_design_tsv`` restores one: no coordinate."""
    return Mutation(
        raw=notation,
        wt_aa=notation[0],
        position=int(notation[1:-1]),
        mt_aa=notation[-1],
        codon_start=0,
        wt_codon=wt_codon,
        mt_codon=mt_codon,
    )


@pytest.fixture(scope="module")
def wild_type(genbank_path: Path) -> str:
    _header, sequence, _genes = load_sequence(genbank_path)
    return sequence


def _codon(sequence: str, position: int) -> str:
    start = TARGET_START + (position - 1) * 3
    return sequence[start:start + 3]


# ── core rebuild ────────────────────────────────────────────────────────


def test_recorded_codon_is_applied_and_length_is_unchanged(wild_type):
    """The rebuilt template carries the earlier round's codon, not a new one.

    Length invariance is the premise of the whole feature: residue numbering
    has to keep meaning across rounds.
    """
    assert _codon(wild_type, 232) == "CAA"
    rebuilt = rebuild_template_sequence(
        wild_type, TARGET_START, [_mutation("Q232A", "CAA", "GCA")]
    )
    assert _codon(rebuilt, 232) == "GCA"
    assert len(rebuilt) == len(wild_type)
    # Everything outside the one codon is untouched.
    start = TARGET_START + 231 * 3
    assert rebuilt[:start] == wild_type[:start]
    assert rebuilt[start + 3:] == wild_type[start + 3:]


def test_a_rare_synonymous_choice_survives_instead_of_the_optimal_codon(wild_type):
    """GCA, GCC, GCG and GCT all give alanine; only the recorded one is right."""
    rebuilt = rebuild_template_sequence(
        wild_type, TARGET_START, [_mutation("Q232A", "CAA", "GCC")]
    )
    assert _codon(rebuilt, 232) == "GCC"


def test_every_applied_codon_translates_to_the_expected_residue(wild_type):
    rebuilt = rebuild_template_sequence(
        wild_type,
        TARGET_START,
        [_mutation("Q232A", "CAA", "GCA"), _mutation("Y233A", "TAC", "GCT")],
    )
    assert CODON_TO_AA[_codon(rebuilt, 232)] == "A"
    assert CODON_TO_AA[_codon(rebuilt, 233)] == "A"


def test_order_does_not_change_the_product(wild_type):
    forward = rebuild_template_sequence(
        wild_type,
        TARGET_START,
        [_mutation("Q232A", "CAA", "GCA"), _mutation("E335A", "GAG", "GCG")],
    )
    reverse = rebuild_template_sequence(
        wild_type,
        TARGET_START,
        [_mutation("E335A", "GAG", "GCG"), _mutation("Q232A", "CAA", "GCA")],
    )
    assert forward == reverse


def test_wild_type_codon_mismatch_names_the_position_and_both_codons(wild_type):
    """A template that does not carry the recorded codon is the wrong template."""
    with pytest.raises(ValueError) as exc:
        rebuild_template_sequence(
            wild_type, TARGET_START, [_mutation("Q232A", "CAG", "GCA")]
        )
    message = str(exc.value)
    assert "Q232A" in message and "232" in message
    assert "CAG" in message and "CAA" in message


def test_a_wrong_target_start_is_caught_by_the_codon_check(wild_type):
    with pytest.raises(ValueError, match="expected codon CAA"):
        rebuild_template_sequence(
            wild_type, TARGET_START + 3, [_mutation("Q232A", "CAA", "GCA")]
        )


def test_two_substitutions_at_one_position_are_refused(wild_type):
    with pytest.raises(ValueError, match="two substitutions"):
        rebuild_template_sequence(
            wild_type,
            TARGET_START,
            [_mutation("Q232A", "CAA", "GCA"), _mutation("Q232E", "CAA", "GAA")],
        )


def test_an_identical_substitution_listed_twice_is_also_refused(wild_type):
    """Applying it twice would be harmless; accepting it silently is not.

    Two rows for one residue mean the caller does not know what the clone
    carries, which is the same ambiguity as two different substitutions.
    """
    with pytest.raises(ValueError, match="two substitutions"):
        rebuild_template_sequence(
            wild_type,
            TARGET_START,
            [_mutation("Q232A", "CAA", "GCA"), _mutation("Q232A", "CAA", "GCA")],
        )


@pytest.mark.parametrize("codon", ["", "GC", "GCAA", "NNN", "gc-"])
def test_a_malformed_codon_is_refused_rather_than_changing_length(wild_type, codon):
    with pytest.raises(ValueError, match="not a DNA codon"):
        rebuild_template_sequence(
            wild_type, TARGET_START, [_mutation("Q232A", "CAA", codon)]
        )


def test_a_recorded_codon_that_encodes_another_residue_is_refused(wild_type):
    """GAA is glutamate; a row claiming it for Q232A disagrees with itself."""
    with pytest.raises(ValueError, match="encodes E, not A"):
        rebuild_template_sequence(
            wild_type, TARGET_START, [_mutation("Q232A", "CAA", "GAA")]
        )


def test_a_position_past_the_sequence_is_refused(wild_type):
    with pytest.raises(ValueError, match="exceeds sequence length"):
        rebuild_template_sequence(
            wild_type, TARGET_START, [_mutation("Q99999A", "CAA", "GCA")]
        )


def test_an_empty_request_does_not_quietly_return_the_wild_type(wild_type):
    with pytest.raises(ValueError, match="wild-type"):
        rebuild_template_sequence(wild_type, TARGET_START, [])


def test_a_lowercase_template_is_read_as_dna(wild_type):
    rebuilt = rebuild_template_sequence(
        wild_type.lower(), TARGET_START, [_mutation("Q232A", "CAA", "GCA")]
    )
    assert _codon(rebuilt, 232) == "GCA"


# ── reading rounds out of design results ────────────────────────────────


def test_rounds_accumulate_across_several_tsv_files(tmp_path):
    first = _tsv(tmp_path / "r1.tsv", [("Q232A", "CAA", "GCA")])
    second = _tsv(tmp_path / "r2.tsv", [("Y233A", "TAC", "GCT")])
    recorded, sources = cli.read_recorded_substitutions([first, second])
    assert list(recorded) == ["Q232A", "Y233A"]
    assert recorded["Y233A"].mt_codon == "GCT"
    assert sources["Q232A"] == str(first)


def test_the_same_row_in_two_rounds_is_one_recorded_choice(tmp_path):
    first = _tsv(tmp_path / "r1.tsv", [("Q232A", "CAA", "GCA")])
    second = _tsv(tmp_path / "r2.tsv", [("Q232A", "CAA", "GCA"), ("Y233A", "TAC", "GCT")])
    recorded, _sources = cli.read_recorded_substitutions([first, second])
    assert list(recorded) == ["Q232A", "Y233A"]


def test_one_notation_recorded_with_two_codons_is_refused(tmp_path):
    first = _tsv(tmp_path / "r1.tsv", [("Q232A", "CAA", "GCA")])
    second = _tsv(tmp_path / "r2.tsv", [("Q232A", "CAA", "GCC")])
    with pytest.raises(ValueError) as exc:
        cli.read_recorded_substitutions([first, second])
    message = str(exc.value)
    assert "GCA" in message and "GCC" in message
    assert str(second) in message


# ── CLI ─────────────────────────────────────────────────────────────────


def _template_args(tmp_path, genbank_path, *extra, output="template.fa"):
    primers = _tsv(
        tmp_path / "r1.tsv",
        [("Q232A", "CAA", "GCA"), ("Y233A", "TAC", "GCT"), ("E335A", "GAG", "GCG")],
    )
    return cli.build_parser().parse_args([
        "template",
        "--fasta", str(genbank_path),
        "--target-start", str(TARGET_START),
        "--primers", str(primers),
        "--output", str(tmp_path / output),
        *extra,
    ])


def _fasta_sequence(path: Path) -> tuple[str, str]:
    header = ""
    parts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            header = line[1:]
        elif line:
            parts.append(line)
    return header, "".join(parts)


def test_the_fasta_header_states_the_genotype_it_is_a_template_for(
    tmp_path, genbank_path, wild_type
):
    args = _template_args(tmp_path, genbank_path, "--genotype", "Q232A/E335A")
    cli.cmd_template(args)
    header, sequence = _fasta_sequence(Path(args.output))
    assert "genotype=Q232A/E335A" in header
    assert len(sequence) == len(wild_type)
    assert _codon(sequence, 232) == "GCA"
    assert _codon(sequence, 335) == "GCG"
    assert _codon(sequence, 233) == _codon(wild_type, 233)


def test_a_colon_separated_genotype_token_is_accepted(tmp_path, genbank_path):
    """Candidate lists write ``S304C:V547I``; a KURO mutation CSV accepts both."""
    args = _template_args(tmp_path, genbank_path, "--genotype", "E335A:Q232A")
    cli.cmd_template(args)
    header, _sequence = _fasta_sequence(Path(args.output))
    # Components are ordered by position regardless of how they were typed.
    assert "genotype=Q232A/E335A" in header


def test_repeating_the_option_accumulates_substitutions(tmp_path, genbank_path):
    args = _template_args(
        tmp_path, genbank_path, "--genotype", "Q232A", "--genotype", "Y233A"
    )
    cli.cmd_template(args)
    header, _sequence = _fasta_sequence(Path(args.output))
    assert "genotype=Q232A/Y233A" in header


def test_without_a_selection_every_recorded_substitution_is_applied(
    tmp_path, genbank_path
):
    args = _template_args(tmp_path, genbank_path)
    cli.cmd_template(args)
    header, sequence = _fasta_sequence(Path(args.output))
    assert "genotype=Q232A/Y233A/E335A" in header
    assert _codon(sequence, 233) == "GCT"


def test_a_notation_absent_from_the_results_is_named_and_refused(
    tmp_path, genbank_path
):
    args = _template_args(tmp_path, genbank_path, "--genotype", "K200A/Q232A")
    with pytest.raises(SystemExit) as exc:
        cli.cmd_template(args)
    assert "K200A" in str(exc.value)
    assert not Path(args.output).exists()


def test_a_genotype_carrying_no_substitution_is_refused(tmp_path, genbank_path):
    args = _template_args(tmp_path, genbank_path, "--genotype", "WT")
    with pytest.raises(SystemExit, match="no substitution"):
        cli.cmd_template(args)


def test_an_unsupported_output_suffix_is_refused(tmp_path, genbank_path):
    args = _template_args(tmp_path, genbank_path, output="template.txt")
    with pytest.raises(SystemExit, match="Unsupported output suffix"):
        cli.cmd_template(args)


def test_an_annotated_output_needs_an_annotated_input(tmp_path, fasta_path):
    primers = _tsv(tmp_path / "r1.tsv", [("Q232A", "CAA", "GCA")])
    args = cli.build_parser().parse_args([
        "template",
        "--fasta", str(fasta_path),
        "--target-start", str(TARGET_START),
        "--primers", str(primers),
        "--output", str(tmp_path / "template.gb"),
    ])
    with pytest.raises(SystemExit, match="annotated"):
        cli.cmd_template(args)


def test_a_raw_fasta_input_still_rebuilds_a_fasta_template(tmp_path, fasta_path):
    """``load_sequence`` rejects a raw FASTA; the rebuild does not need a CDS."""
    primers = _tsv(tmp_path / "r1.tsv", [("Q232A", "CAA", "GCA")])
    args = cli.build_parser().parse_args([
        "template",
        "--fasta", str(fasta_path),
        "--target-start", str(TARGET_START),
        "--primers", str(primers),
        "--output", str(tmp_path / "template.fa"),
    ])
    cli.cmd_template(args)
    _header, sequence = _fasta_sequence(Path(args.output))
    assert _codon(sequence, 232) == "GCA"


# ── what the feature exists for ─────────────────────────────────────────


def test_the_annotated_template_designs_the_next_round_against_the_clone(
    tmp_path, genbank_path, wild_type
):
    """The point of the tool: the next primer matches the clone, not the WT.

    Q232 and Y233 are adjacent, so a primer for Y233A reaches across codon 232.
    Designed against the wild type it carries CAA there; designed against the
    rebuilt Q232A template it carries the recorded GCA, which is what the
    plasmid in the freezer has.
    """
    from kuma_core.kuro.sdm_engine import design_sdm_primers

    primers = _tsv(tmp_path / "r1.tsv", [("Q232A", "CAA", "GCA")])
    template = tmp_path / "template_Q232A.gb"
    cli.cmd_template(cli.build_parser().parse_args([
        "template",
        "--fasta", str(genbank_path),
        "--target-start", str(TARGET_START),
        "--primers", str(primers),
        "--genotype", "Q232A",
        "--output", str(template),
    ]))

    mutations = tmp_path / "round2.csv"
    mutations.write_text("mutation\nY233A\n", encoding="utf-8")

    def design(fasta: Path):
        results, _candidates, failures = design_sdm_primers(
            fasta_path=fasta,
            target_start=TARGET_START,
            mutations_csv=mutations,
            organism="ecoli",
        )
        assert not failures, failures
        assert len(results) == 1
        return results[0]

    from_wild_type = design(genbank_path)
    from_template = design(template)

    rebuilt = rebuild_template_sequence(
        wild_type, TARGET_START, [_mutation("Q232A", "CAA", "GCA")]
    )
    expected_background = rebuild_template_sequence(
        rebuilt, TARGET_START, [_mutation("Y233A", "TAC", from_template.mutation.mt_codon)]
    )
    # The round-2 primer is a stretch of the clone being mutated, and is not a
    # stretch of the wild-type plasmid: codon 232 differs.
    assert from_template.forward_seq in expected_background
    assert from_template.forward_seq not in wild_type
    assert from_wild_type.forward_seq != from_template.forward_seq


def test_the_rebuilt_record_keeps_its_annotation_and_length(
    tmp_path, genbank_path, wild_type
):
    args = cli.build_parser().parse_args([
        "template",
        "--fasta", str(genbank_path),
        "--target-start", str(TARGET_START),
        "--primers", str(_tsv(tmp_path / "r1.tsv", [("Q232A", "CAA", "GCA")])),
        "--output", str(tmp_path / "template.gb"),
    ])
    cli.cmd_template(args)

    source_header, _source_seq, source_genes = load_sequence(genbank_path)
    header, sequence, genes = load_sequence(Path(args.output))
    assert len(sequence) == len(wild_type)
    assert _codon(sequence, 232) == "GCA"
    assert "genotype=Q232A" in header
    assert source_header.split("genotype=")[0].strip() in header
    assert [(g.cds_start, g.cds_end) for g in genes] == [
        (g.cds_start, g.cds_end) for g in source_genes
    ]


def test_the_rebuild_refuses_its_own_product(
    tmp_path, genbank_path, wild_type
):
    """Re-running on the product stops rather than double-applying.

    The template already carries GCA at 232, so the recorded wild-type codon is
    no longer there and the second pass stops. A silent second application
    would move no codon here, but a reversal or a replacement would.
    """
    rebuilt = rebuild_template_sequence(
        wild_type, TARGET_START, [_mutation("Q232A", "CAA", "GCA")]
    )
    with pytest.raises(ValueError, match="but the template carries GCA"):
        rebuild_template_sequence(
            rebuilt, TARGET_START, [_mutation("Q232A", "CAA", "GCA")]
        )


def test_a_mutation_carrying_a_stale_coordinate_is_recomputed(wild_type):
    """``read_design_tsv`` restores ``codon_start=0``; using it would overwrite
    the first codon of the plasmid."""
    stale = replace(_mutation("Q232A", "CAA", "GCA"), codon_start=0)
    rebuilt = rebuild_template_sequence(wild_type, TARGET_START, [stale])
    assert rebuilt[:3] == wild_type[:3]
    assert _codon(rebuilt, 232) == "GCA"
