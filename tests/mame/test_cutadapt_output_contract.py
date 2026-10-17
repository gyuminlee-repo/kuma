"""The CLI's file-format contract, without demultiplexing any biological input."""
from pathlib import Path

import pytest

from kuma_core.mame.ingest.demux import _collect_cutadapt_outputs


@pytest.mark.parametrize("name", ["well.fasta", "_unassigned.fasta"])
def test_fastq_disguised_as_fasta_is_not_reported_as_zero_reads(tmp_path: Path, name: str):
    (tmp_path / name).write_text("@record\nTEXT\n+\nIIII\n")
    with pytest.raises(RuntimeError, match="FASTA"):
        _collect_cutadapt_outputs(tmp_path, {"well": "unused"})


def test_valid_and_empty_fasta_counts_are_unchanged(tmp_path: Path):
    (tmp_path / "well.fasta").write_text(">record one\nTEXT\n>record two\nTEXT\n")
    (tmp_path / "_unassigned.fasta").write_text("")
    assert _collect_cutadapt_outputs(tmp_path, {"well": "unused"}) == ({"well": 2}, 2, 0)
