"""A multi-substitution row keeps its identity, and one bad row stays one.

A5: the codon enumeration in ``design_single_sdm`` and in
``diagnose_sdm_failure`` rebuilt a Mutation per candidate codon without
``group_id``, so a component of an ``A2V/A3G`` row came out of design with no
record of the row that asked for it and the Group cell of the export was blank.

A6: when the batch parse hit one malformed row, the per-row fallback used the
single-notation parser and rejected every valid ``A2V/A3G`` row alongside it. A
file carrying neither a ``mutation`` nor a ``variant`` column read zero rows and
failed zero rows, which an operator sees as a run that produced nothing and
complained about nothing.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from kuma_core.kuro import sdm_engine
from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.polymerase import PolymeraseRegistry
from kuma_core.kuro.sdm_engine import (
    design_sdm_primers,
    design_single_sdm,
    diagnose_sdm_failure,
    export_results_tsv,
)

TARGET = 60
_STOPS = {"TAA", "TAG", "TGA"}


def _template() -> str:
    """A plasmid-shaped template whose residues 2 and 3 are both alanine."""
    rng = random.Random(42)
    flank = "".join(rng.choice("ACGT") for _ in range(TARGET))
    body: list[str] = []
    while len(body) < 60:
        codon = "".join(rng.choice("ACGT") for _ in range(3))
        if codon not in _STOPS:
            body.append(codon)
    cds = "ATGGCTGCT" + "".join(body) + "TAA"
    return flank + cds + "".join(rng.choice("ACGT") for _ in range(TARGET))


def _cds_end() -> int:
    return TARGET + 9 + 60 * 3 + 3


def _mutation(raw: str = "A2V", group_id: str | None = "A2V/A3G") -> Mutation:
    return Mutation(
        raw=raw, wt_aa="A", position=2, mt_aa="V",
        codon_start=TARGET + 3, wt_codon="GCT", mt_codon="GTT",
        group_id=group_id,
    )


def _write_inputs(tmp_path: Path, header: str, rows: list[str]) -> tuple[Path, Path]:
    from Bio import SeqIO
    from Bio.Seq import Seq
    from Bio.SeqFeature import FeatureLocation, SeqFeature
    from Bio.SeqRecord import SeqRecord

    record = SeqRecord(Seq(_template()), id="t", name="t")
    record.annotations["molecule_type"] = "DNA"
    record.features.append(SeqFeature(
        FeatureLocation(TARGET, _cds_end(), strand=1), type="CDS",
        qualifiers={"gene": ["t"]},
    ))
    template = tmp_path / "t.gb"
    with template.open("w", encoding="utf-8") as stream:
        SeqIO.write([record], stream, "genbank")
    csv_path = tmp_path / "m.csv"
    csv_path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
    return template, csv_path


def test_design_single_sdm_keeps_the_source_row() -> None:
    results = design_single_sdm(
        _template(), _mutation(), PolymeraseRegistry().get("Q5"),
        overlap_mode="partial",
    )
    assert results, "fixture must produce candidates"
    assert {r.mutation.group_id for r in results} == {"A2V/A3G"}


def test_diagnose_passes_the_source_row_to_its_probes(monkeypatch) -> None:
    """The diagnostic builds its own codon variants; they must carry the group.

    Asserting on the returned message cannot see this: the message is a string
    about primer lengths either way, which is why the first draft of this test
    passed against the broken code. What matters is the Mutation the inner
    probes receive, so the one call every variant goes through is spied on.
    """
    seen: list[Mutation] = []
    real = sdm_engine.mutate_sequence

    def spy(seq: str, mutation: Mutation) -> str:
        seen.append(mutation)
        return real(seq, mutation)

    monkeypatch.setattr(sdm_engine, "mutate_sequence", spy)
    diagnose_sdm_failure(
        _template(), _mutation(), PolymeraseRegistry().get("Q5"),
        overlap_mode="partial",
    )
    assert seen, "the diagnostic never reached a codon variant"
    assert {m.group_id for m in seen} == {"A2V/A3G"}


def test_batch_design_gives_every_component_the_row(tmp_path) -> None:
    template, csv_path = _write_inputs(tmp_path, "mutation", ["A2V/A3G"])
    results, _candidates, failed = design_sdm_primers(template, TARGET, csv_path)
    assert failed == {}
    assert {r.mutation.raw: r.mutation.group_id for r in results} == {
        "A2V": "A2V/A3G", "A3G": "A2V/A3G",
    }


def test_the_group_reaches_the_design_tsv(tmp_path) -> None:
    from kuma_core.kuro.cli import read_design_tsv

    template, csv_path = _write_inputs(tmp_path, "mutation", ["A2V/A3G"])
    results, _candidates, _failed = design_sdm_primers(template, TARGET, csv_path)
    tsv = tmp_path / "primers.tsv"
    export_results_tsv(results, tsv)
    _mode, restored = read_design_tsv(tsv)
    assert {r.mutation.raw: r.mutation.group_id for r in restored} == {
        "A2V": "A2V/A3G", "A3G": "A2V/A3G",
    }


def test_a_tsv_without_the_group_column_still_loads(tmp_path) -> None:
    from kuma_core.kuro.cli import read_design_tsv

    tsv = tmp_path / "legacy.tsv"
    tsv.write_text(
        "# overlap_mode=partial\n"
        "Mutation\tForward_Primer\tReverse_Primer\tTm_Fwd\tTm_Rev\tTm_Overlap\n"
        "A2V\tACGT\tTGCA\t62.0\t58.0\t42.0\n",
        encoding="utf-8",
    )
    _mode, restored = read_design_tsv(tsv)
    assert [r.mutation.group_id for r in restored] == [None]


def test_one_malformed_row_does_not_reject_the_valid_rows(tmp_path) -> None:
    template, csv_path = _write_inputs(
        tmp_path, "mutation", ["A2V/A3G", "NOT_A_MUTATION"],
    )
    results, _candidates, failed = design_sdm_primers(template, TARGET, csv_path)
    assert {r.mutation.raw: r.mutation.group_id for r in results} == {
        "A2V": "A2V/A3G", "A3G": "A2V/A3G",
    }
    assert set(failed) == {"NOT_A_MUTATION"}


def test_a_row_fails_whole_or_not_at_all(tmp_path) -> None:
    """``A2V/A3G`` where the second component is impossible designs neither.

    Position 999 is past the CDS, so the row cannot be built. Leaving A2V
    behind would turn a request for a double mutant into a request for a single
    one, which is a different experiment.
    """
    template, csv_path = _write_inputs(tmp_path, "mutation", ["A2V/A999V"])
    results, _candidates, failed = design_sdm_primers(template, TARGET, csv_path)
    assert results == []
    assert set(failed) == {"A2V/A999V"}


def test_the_variant_column_is_read_when_there_is_no_mutation_column(tmp_path) -> None:
    template, csv_path = _write_inputs(tmp_path, "variant", ["A2V/A3G"])
    results, _candidates, failed = design_sdm_primers(template, TARGET, csv_path)
    assert {r.mutation.raw for r in results} == {"A2V", "A3G"}
    assert failed == {}


def test_a_file_with_no_mutation_column_is_an_error(tmp_path) -> None:
    template, csv_path = _write_inputs(tmp_path, "name", ["A2V"])
    with pytest.raises(ValueError, match="mutation"):
        design_sdm_primers(template, TARGET, csv_path)


def test_an_empty_file_is_an_error_not_an_empty_success(tmp_path) -> None:
    template, csv_path = _write_inputs(tmp_path, "", [])
    with pytest.raises(ValueError, match="mutation"):
        design_sdm_primers(template, TARGET, csv_path)


def test_a_row_with_an_empty_cell_is_skipped(tmp_path) -> None:
    template, csv_path = _write_inputs(tmp_path, "mutation,note", ["A2V,ok", ",blank"])
    results, _candidates, failed = design_sdm_primers(template, TARGET, csv_path)
    assert [r.mutation.raw for r in results] == ["A2V"]
    assert failed == {}


def test_one_notation_claimed_by_two_rows_is_refused(tmp_path) -> None:
    template, csv_path = _write_inputs(tmp_path, "mutation", ["A2V", "A2V/A3G"])
    with pytest.raises(ValueError, match="two different rows"):
        design_sdm_primers(template, TARGET, csv_path)


def test_repeating_a_substitution_inside_one_row_is_not_a_conflict(tmp_path) -> None:
    template, csv_path = _write_inputs(tmp_path, "mutation", ["A2V/A2V"])
    results, _candidates, failed = design_sdm_primers(template, TARGET, csv_path)
    assert failed == {}
    assert {r.mutation.group_id for r in results} == {"A2V/A2V"}


def test_the_same_row_twice_is_not_a_conflict(tmp_path) -> None:
    template, csv_path = _write_inputs(tmp_path, "mutation", ["A2V", "A2V"])
    results, _candidates, failed = design_sdm_primers(template, TARGET, csv_path)
    assert failed == {}
    assert {r.mutation.group_id for r in results} == {None}
