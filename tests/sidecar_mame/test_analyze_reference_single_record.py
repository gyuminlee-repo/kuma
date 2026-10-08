"""The sidecar reference reader refuses a multi-record FASTA.

This reader feeds the CDS-end default, the run-quality reference scale and the
read-length ratios, and the ``validate_inputs`` probe reaches it before an
analyze is ever started. It used to concatenate every record, so a backbone
glued to a target set all of those against a molecule that does not exist.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sidecar_mame.handlers.analyze import (
    _read_fasta_sequence,
    _read_reference_length,
    _read_reference_sequence,
)


def _write_two_records(tmp_path: Path) -> Path:
    reference = tmp_path / "two_records.fa"
    reference.write_text(
        ">backbone description here\nGGGGGGGGGG\n>target_gene\nATGGCTTAA\n",
        encoding="utf-8",
    )
    return reference


def test_reader_refuses_a_two_record_reference(tmp_path: Path) -> None:
    """The pre-fix reader returned the 19 bases of the two records joined."""
    reference = _write_two_records(tmp_path)

    with pytest.raises(ValueError) as excinfo:  # noqa: PT011
        _read_fasta_sequence(reference)

    message = str(excinfo.value)
    assert "2 sequence records" in message  # noqa: S101
    assert "backbone" in message  # noqa: S101
    assert "target_gene" in message  # noqa: S101
    assert str(reference) in message  # noqa: S101
    # The length the old reader would have reported for this file.
    assert len("GGGGGGGGGG" + "ATGGCTTAA") == 19  # noqa: S101


def test_the_length_and_sequence_entry_points_refuse_it_too(tmp_path: Path) -> None:
    """Both public wrappers reach the same reader, and neither may slip past."""
    reference = _write_two_records(tmp_path)

    with pytest.raises(ValueError):  # noqa: PT011
        _read_reference_sequence(reference)
    with pytest.raises(ValueError):  # noqa: PT011
        _read_reference_length(reference)


def test_single_record_and_headerless_references_still_load(tmp_path: Path) -> None:
    """The two shapes that were always valid stay valid."""
    single = tmp_path / "one.fa"
    single.write_text(">only\nacgtACGT\n", encoding="utf-8")
    headerless = tmp_path / "bare.fasta"
    headerless.write_text("acgt\nACGT\n", encoding="utf-8")

    assert _read_reference_sequence(single) == "ACGTACGT"  # noqa: S101
    assert _read_reference_length(headerless) == 8  # noqa: S101
