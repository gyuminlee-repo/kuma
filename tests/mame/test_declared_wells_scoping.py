"""A declared selection has to stop the undeclared wells from being judged.

Reported from a run whose plate carried ten filled wells: the operator declared
those ten, and the result came back with all ninety-six scored, sixty-nine of
them WRONG_AA. Declaring fewer wells did not narrow the run, it made the rest
fail, because a well outside the layout falls back to the FULL expected-label
list and cannot match it.

The reads exist for those wells whatever the declaration says (barcode leakage
puts a handful of reads on combinations nobody pipetted), so the question is
not whether records arrive. It is whether a record from a well the campaign
declared empty becomes a verdict. It must not: an empty well has nothing to
sequence, and a verdict on it is a judgement of a sample that was never there.
"""

from pathlib import Path

import pytest

from kuma_core.mame.models import BarcodeRecord


def _record(custom_barcode: str, seq: str) -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode="NB01",
        custom_barcode=custom_barcode,
        consensus_seq=seq,
        file_size_kb=10.0,
        source_path=Path(f"/tmp/{custom_barcode}.fasta"),
        read_count=100,
    )


def test_a_well_outside_the_declared_layout_gets_no_verdict(tmp_path: Path) -> None:
    """The defect, stated as the contract it broke.

    Two wells declared, four wells carrying reads. A1 and B1 are the campaign;
    C1 and D1 are wells the operator said were empty. Before this, all four
    were scored and the two undeclared ones came back WRONG_AA against the
    whole expected list.
    """
    pytest.importorskip("openpyxl")
    from kuma_core.mame.models import ExpectedMutation
    from kuma_core.mame.pipeline import run_analyze

    # A 12 nt CDS: MKV F, with single-codon changes per well.
    reference = tmp_path / "ref.fasta"
    reference.write_text(">ref\nATGAAAGTTTTT\n", encoding="utf-8")
    expected = [
        ExpectedMutation(
            mutant_id="K2R", position=2, wt_aa="K", mt_aa="R",
            wt_codon="AAA", mt_codon="CGT", group_id="", primer_set_ref="K2R",
            notation_type="substitution", status="DESIGNED",
        ),
        ExpectedMutation(
            mutant_id="V3L", position=3, wt_aa="V", mt_aa="L",
            wt_codon="GTT", mt_codon="CTT", group_id="", primer_set_ref="V3L",
            notation_type="substitution", status="DESIGNED",
        ),
    ]
    records = [
        _record("1_1", "ATGCGTGTTTTT"),  # A1, K2R as declared
        _record("2_1", "ATGAAACTTTTT"),  # B1, V3L as declared
        _record("3_1", "ATGAAAGTTTTT"),  # C1, undeclared, reads leaked in
        _record("4_1", "ATGCGTGTTTTT"),  # D1, undeclared, reads leaked in
    ]

    verdicts, _replicates = run_analyze(
        input_dir=tmp_path,
        reference_path=reference,
        expected_path=tmp_path / "unused.xlsx",
        output_path=tmp_path / "out.xlsx",
        cds_start=0,
        cds_end=12,
        well_layout={"A1": "K2R", "B1": "V3L"},
        records=records,
        expected_mutations=expected,
        scored_wells={"A1", "B1"},
    )

    scored = {v.translated.barcode.custom_barcode for v in verdicts}
    assert scored == {"1_1", "2_1"}


def test_without_a_declaration_every_well_with_reads_is_still_scored(
    tmp_path: Path,
) -> None:
    """The default has to be untouched, or every run without a selection changes.

    ``scored_wells=None`` is what a run that declared nothing sends, and there
    an unlisted well is a well nobody said anything about rather than one
    declared empty. Those keep their old fallback verdict.
    """
    pytest.importorskip("openpyxl")
    from kuma_core.mame.models import ExpectedMutation
    from kuma_core.mame.pipeline import run_analyze

    reference = tmp_path / "ref.fasta"
    reference.write_text(">ref\nATGAAAGTTTTT\n", encoding="utf-8")
    expected = [
        ExpectedMutation(
            mutant_id="K2R", position=2, wt_aa="K", mt_aa="R",
            wt_codon="AAA", mt_codon="CGT", group_id="", primer_set_ref="K2R",
            notation_type="substitution", status="DESIGNED",
        ),
    ]
    records = [
        _record("1_1", "ATGCGTGTTTTT"),
        _record("3_1", "ATGAAAGTTTTT"),
    ]

    verdicts, _replicates = run_analyze(
        input_dir=tmp_path,
        reference_path=reference,
        expected_path=tmp_path / "unused.xlsx",
        output_path=tmp_path / "out.xlsx",
        cds_start=0,
        cds_end=12,
        well_layout={"A1": "K2R"},
        records=records,
        expected_mutations=expected,
    )

    scored = {v.translated.barcode.custom_barcode for v in verdicts}
    assert scored == {"1_1", "3_1"}
