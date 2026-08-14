"""The reference readers refuse a multi-record FASTA on every path.

``kuma_core.mame.ingest.amplicon_reference`` grew this guard first, but the
consensus-directory run never reaches that resolver: it goes straight from the
handler into ``run_analyze``, whose reader used to glue every record together.
These tests pin the refusal at that second reader and pin the two messages to
each other, because an operator who moves between the two inputs must not be
told two different things about the same file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.ingest.amplicon_reference import AmpliconReferenceError, _read_fasta
from kuma_core.mame.pipeline import _read_reference_fasta
from kuma_core.mame.reference_fasta import multi_record_reason


def _write_two_records(tmp_path: Path) -> Path:
    reference = tmp_path / "two_records.fa"
    reference.write_text(
        ">backbone description here\nGGGGGGGGGG\n>target_gene\nATGGCTTAA\n",
        encoding="utf-8",
    )
    return reference


def test_pipeline_reader_refuses_a_two_record_reference(tmp_path: Path) -> None:
    """The old reader returned ``GGGGGGGGGGATGGCTTAA``, a molecule nothing has.

    The length that concatenation produces is asserted against explicitly so the
    test states what used to come back rather than merely checking that an error
    now exists.
    """
    reference = _write_two_records(tmp_path)

    with pytest.raises(ValueError) as excinfo:
        _read_reference_fasta(reference)

    message = str(excinfo.value)
    assert "2 sequence records" in message
    # Both names, because the operator has to pick one and cannot without them.
    assert "backbone" in message
    assert "target_gene" in message
    # The description after the id is not part of the name.
    assert "description" not in message
    assert str(reference) in message
    # What the pre-fix reader would have handed to every verdict in the run.
    assert len("GGGGGGGGGG" + "ATGGCTTAA") == 19


def test_both_layers_state_the_same_thing_about_the_same_file(
    tmp_path: Path,
) -> None:
    """Amplicon resolver and pipeline glue must not word the refusal apart."""
    reference = _write_two_records(tmp_path)

    with pytest.raises(AmpliconReferenceError) as ingest_exc:
        _read_fasta(reference)
    with pytest.raises(ValueError) as pipeline_exc:
        _read_reference_fasta(reference)

    assert str(ingest_exc.value) == str(pipeline_exc.value)


def test_pipeline_reader_still_accepts_the_two_valid_shapes(tmp_path: Path) -> None:
    """One record is the ordinary case, and a bare sequence file was always ok."""
    single = tmp_path / "one.fa"
    single.write_text(">only\nacgtACGT\n", encoding="utf-8")
    headerless = tmp_path / "bare.txt"
    headerless.write_text("acgt\nACGT\n", encoding="utf-8")

    assert _read_reference_fasta(single) == "ACGTACGT"
    assert _read_reference_fasta(headerless) == "ACGTACGT"


def test_long_record_lists_are_cut_short_with_a_count(tmp_path: Path) -> None:
    """A file with dozens of records must not bury the instruction under names."""
    reason = multi_record_reason([f">rec{i}" for i in range(11)])

    assert reason is not None
    assert "11 sequence records" in reason
    assert "rec7" in reason
    assert "rec8" not in reason
    assert "(+3 more)" in reason


def test_an_empty_header_is_still_counted_and_named() -> None:
    """Names listed and count stated have to agree, blank headers included."""
    reason = multi_record_reason([">", ">named"])

    assert reason is not None
    assert "2 sequence records" in reason
    assert "(unnamed)" in reason
