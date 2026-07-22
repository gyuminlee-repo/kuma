"""Ingest / mode router tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.ingest import IngestMode, load_barcode_directory, route_ingest
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file


def test_load_barcode_directory_parses_all_fixtures(mock_fasta_dir: Path) -> None:
    records = load_barcode_directory(mock_fasta_dir)
    # 3 native x 4 custom = 12.
    assert len(records) == 12
    custom_labels = {(r.native_barcode, r.custom_barcode) for r in records}
    for nb in ("NB01", "NB02", "NB03"):
        for custom in ("1_1", "1_2", "1_3", "1_4"):
            assert (nb, custom) in custom_labels


def test_mode_router_barcode(mock_fasta_dir: Path) -> None:
    records = route_ingest(mock_fasta_dir, IngestMode.BARCODE)
    assert len(records) == 12


def test_mode_router_amplicon(tmp_path: Path) -> None:
    """Amplicon mode: one `*-consensus.fasta` per native barcode directory."""

    nb = tmp_path / "BATCH1"
    nb.mkdir()
    body = "ATGGTG" + "N" * 90 + "TGA"
    (nb / "sample-consensus.fasta").write_text(f">sample\n{body}\n", encoding="utf-8")

    records = route_ingest(tmp_path, IngestMode.AMPLICON)
    assert len(records) == 1
    assert records[0].consensus_seq.startswith("ATGGTG")


# ---------------------------------------------------------------------------
# fasta_parser fail-fast: multi-header raw-read FASTA must raise ValueError
# ---------------------------------------------------------------------------

def test_parse_fasta_file_single_header_ok(tmp_path: Path) -> None:
    """Single-record consensus FASTA parses without error."""
    fasta = tmp_path / "1_1.fasta"
    fasta.write_text(">1_1\nATGCATGCATGC\n", encoding="utf-8")
    record = parse_fasta_file(fasta, native_barcode="NB01")
    assert record.consensus_seq == "ATGCATGC" + "ATGC"
    assert record.read_count == 1


def test_parse_fasta_file_depth_header_populates_read_count(tmp_path: Path) -> None:
    """Consensus FASTA depth=N metadata should become BarcodeRecord.read_count."""
    fasta = tmp_path / "1_1.fasta"
    fasta.write_text(
        ">1_1 depth=37 mixed_positions=2 max_minor_allele_fraction=0.490\n"
        "ATGCATGCATGC\n",
        encoding="utf-8",
    )
    record = parse_fasta_file(fasta, native_barcode="NB01")
    assert record.custom_barcode == "1_1"
    assert record.consensus_seq == "ATGCATGCATGC"
    assert record.read_count == 37
    assert record.n_mixed_positions == 2
    assert record.max_minor_allele_fraction == 0.49
    assert record.n_low_depth_positions == 0
    assert record.consensus_n_fraction == 0.0


def test_parse_fasta_file_quality_header_populates_low_depth_metrics(
    tmp_path: Path,
) -> None:
    """MAME consensus metadata should carry per-base low-depth/N evidence."""
    fasta = tmp_path / "1_1.fasta"
    fasta.write_text(
        ">1_1 depth=37 input_reads=40 aligned_reads=38 mapq_failed=1 "
        "span_failed=1 low_depth_positions=3 consensus_n_fraction=0.250 "
        "low_quality_bases=7\n"
        "ATGNNNGCATGC\n",
        encoding="utf-8",
    )
    record = parse_fasta_file(fasta, native_barcode="NB01")
    assert record.read_count == 37
    assert record.n_input_reads == 40
    assert record.n_aligned_reads == 38
    assert record.n_mapq_failed == 1
    assert record.n_span_failed == 1
    assert record.n_low_depth_positions == 3
    # No basis marker, so the stored 0.250 carries the old whole-reference
    # denominator and is recovered against the covered positions instead:
    # all 3 Ns are the low-depth ones, leaving 0 of 9 covered positions no-call.
    assert record.consensus_n_fraction == 0.0
    assert record.consensus_n_fraction_evaluable is True
    assert record.n_low_quality_bases == 7


def test_parse_fasta_file_without_metadata_is_not_evaluable(tmp_path: Path) -> None:
    """A bare header carries no basis for a covered-scoped N fraction."""
    fasta = tmp_path / "1_1.fasta"
    fasta.write_text(">1_1\nATGN\n", encoding="utf-8")
    record = parse_fasta_file(fasta, native_barcode="NB01")
    assert record.n_low_depth_positions == 0
    assert record.consensus_n_fraction_evaluable is False


def test_load_barcode_directory_ignores_fastq_consensus_files(tmp_path: Path) -> None:
    """MAME consumes its own consensus FASTA tree, not third-party FASTQ output."""
    nb = tmp_path / "sort_barcode06"
    nb.mkdir()
    (nb / "consensus.fastq").write_text(
        "@1_7 depth=42\nATGCATGC\n+\nIIIIIIII\n",
        encoding="utf-8",
    )

    records = load_barcode_directory(tmp_path)
    assert records == []


def test_parse_fasta_file_multi_header_raises(tmp_path: Path) -> None:
    """Multi-record FASTA (raw-read bundle) must raise ValueError with
    informative message — anti-fallback discipline."""
    fasta = tmp_path / "raw_reads.fasta"
    fasta.write_text(
        ">read1\nATGCATGC\n>read2\nTGCATGCA\n>read3\nGCATGCAT\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="3 sequence records"):
        parse_fasta_file(fasta, native_barcode="NB01")


def test_parse_fasta_file_multi_header_error_message_informative(tmp_path: Path) -> None:
    """Error message must mention 'consensus' to guide the user."""
    fasta = tmp_path / "raw_reads.fasta"
    fasta.write_text(">r1\nATGC\n>r2\nTGCA\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        parse_fasta_file(fasta, native_barcode="NB01")
    msg = str(exc_info.value)
    assert "2 sequence records" in msg
    assert "consensus" in msg.lower()


def test_parse_fasta_file_no_header_raises(tmp_path: Path) -> None:
    """FASTA with no header line raises ValueError."""
    fasta = tmp_path / "no_header.fasta"
    fasta.write_text("ATGCATGC\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no header line"):
        parse_fasta_file(fasta, native_barcode="NB01")
