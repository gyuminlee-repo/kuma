"""Handler-level integration tests for demux_and_filter + A4/A5 consensus pipeline.

Tests ``handle_demux_and_filter`` end-to-end with ``reference_fasta`` provided.
Verifies:
- Output directory contains single-record consensus FASTA per well.
- ``load_barcode_directory`` accepts the output without ValueError.
- ``per_well_counts`` reflects raw read counts (not a constant 1).
- ``consensus_stats`` is populated with non-trivial values.
- ``consensus_pipeline`` is True.

Also tests the legacy path (no ``reference_fasta``) to confirm it still works
and ``consensus_pipeline`` is False.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from unittest.mock import patch

import pytest

from kuma_core.mame.ingest.fasta_parser import load_barcode_directory
from sidecar_mame.handlers.demux import handle_demux_and_filter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_REFERENCE = (
    "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    "AACGGCATGAACCTGAACAAGCTGAAAGCGTTCAACCAGTTCGCGAACATGAAAGCGTTC"
    "AACAAGTACTTCAACAAGATCTTCAACAAGTTCGCGAACATGAACAAGTTCAACTGA"
)

# Two custom barcodes used across all handler tests.
_BARCODES = {
    "1_1": "AATCCCACT",
    "1_2": "TTGGAACCC",
}


def _make_fastq(path: Path, reads: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for read_id, seq, qual in reads:
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")


def _write_reference(dest: Path, seq: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(f">ref\n{seq}\n", encoding="utf-8")


@pytest.fixture()
def ref_fasta(tmp_path: Path) -> Path:
    """Write the synthetic reference FASTA and return its path."""
    ref = tmp_path / "ref" / "reference.fasta"
    _write_reference(ref, _REFERENCE)
    return ref


@pytest.fixture()
def fastq_dir_with_ref_reads(tmp_path: Path) -> Path:
    """Create a synthetic FASTQ directory whose reads span the full reference.

    Reads are constructed as: <barcode><reference_body> so that:
    - Demux assigns them to the correct well.
    - mappy aligns them to the reference (full-span, high MAPQ).

    3 reads per barcode → majority-vote consensus equals the reference.
    """
    bdir = tmp_path / "fastq_pass" / "barcode06"
    bdir.mkdir(parents=True)

    reads: list[tuple[str, str, str]] = []
    for name, bc in _BARCODES.items():
        for j in range(3):
            read_id = f"read_{name}_{j}"
            # Prefix = barcode; body = reference sequence (exact match → aligns perfectly).
            seq = bc + _REFERENCE
            qual = "I" * len(seq)
            reads.append((read_id, seq, qual))

    # One unassigned read with a random prefix.
    reads.append(("unassigned_1", "CCCCCCCCCA" + "N" * len(_REFERENCE), "I" * (10 + len(_REFERENCE))))
    _make_fastq(bdir / "reads.fastq", reads)
    return bdir


# ---------------------------------------------------------------------------
# Handler integration tests
# ---------------------------------------------------------------------------


def test_handle_demux_with_consensus_pipeline_success(
    fastq_dir_with_ref_reads: Path,
    ref_fasta: Path,
    tmp_path: Path,
) -> None:
    """End-to-end: demux + consensus pipeline produces single-record FASTA per well."""
    output_dir = tmp_path / "out"

    result = handle_demux_and_filter(
        {
            "fastq_dir": str(fastq_dir_with_ref_reads),
            "custom_barcodes": _BARCODES,
            "output_dir": str(output_dir),
            "reference_fasta": str(ref_fasta),
            "use_cutadapt": False,
            "auto_detect_length": False,
        }
    )

    assert result["consensus_pipeline"] is True
    assert result["consensus_stats"] is not None


def test_handle_demux_consensus_output_single_header_per_well(
    fastq_dir_with_ref_reads: Path,
    ref_fasta: Path,
    tmp_path: Path,
) -> None:
    """Each per-well FASTA must have exactly 1 header after consensus calling."""
    output_dir = tmp_path / "out"

    handle_demux_and_filter(
        {
            "fastq_dir": str(fastq_dir_with_ref_reads),
            "custom_barcodes": _BARCODES,
            "output_dir": str(output_dir),
            "reference_fasta": str(ref_fasta),
            "use_cutadapt": False,
            "auto_detect_length": False,
        }
    )

    # output_dir contains one NB subdir (fastq_dir_with_ref_reads.name = barcode06).
    fasta_files = list(output_dir.rglob("*.fasta"))
    assert fasta_files, "No FASTA files found in output_dir"
    for fasta_path in fasta_files:
        if fasta_path.name.startswith("_"):
            continue  # skip _unassigned.fasta
        header_count = sum(
            1 for ln in fasta_path.read_text(encoding="utf-8").splitlines()
            if ln.startswith(">")
        )
        assert header_count == 1, (
            f"{fasta_path} has {header_count} headers (expected 1 consensus record)"
        )


def test_handle_demux_consensus_output_load_barcode_directory(
    fastq_dir_with_ref_reads: Path,
    ref_fasta: Path,
    tmp_path: Path,
) -> None:
    """load_barcode_directory must accept the consensus pipeline output without error."""
    output_dir = tmp_path / "out"

    handle_demux_and_filter(
        {
            "fastq_dir": str(fastq_dir_with_ref_reads),
            "custom_barcodes": _BARCODES,
            "output_dir": str(output_dir),
            "reference_fasta": str(ref_fasta),
            "use_cutadapt": False,
            "auto_detect_length": False,
        }
    )

    # Must not raise ValueError (fail-fast multi-header guard).
    records = load_barcode_directory(output_dir)
    assert len(records) == len(_BARCODES), (
        f"Expected {len(_BARCODES)} BarcodeRecords, got {len(records)}"
    )
    assert {record.read_count for record in records} == {3}
    assert {record.n_input_reads for record in records} == {3}
    assert {record.n_aligned_reads for record in records} == {3}
    assert {record.n_mapq_failed for record in records} == {0}
    assert {record.n_span_failed for record in records} == {0}
    assert {record.n_low_depth_positions for record in records} == {0}
    assert {record.consensus_n_fraction for record in records} == {0.0}
    assert {record.n_low_quality_bases for record in records} == {0}


def test_handle_demux_per_well_counts_reflect_raw_reads(
    fastq_dir_with_ref_reads: Path,
    ref_fasta: Path,
    tmp_path: Path,
) -> None:
    """per_well_counts must report raw read counts (not constant 1) after consensus."""
    output_dir = tmp_path / "out"

    result = handle_demux_and_filter(
        {
            "fastq_dir": str(fastq_dir_with_ref_reads),
            "custom_barcodes": _BARCODES,
            "output_dir": str(output_dir),
            "reference_fasta": str(ref_fasta),
            "use_cutadapt": False,
            "auto_detect_length": False,
        }
    )

    per_well = result["per_well_counts"]
    for well in _BARCODES:
        count = per_well.get(well, 0)
        # Each well received 3 reads in the fixture; n_input_reads should be 3.
        assert count == 3, (
            f"per_well_counts['{well}'] = {count}, expected 3 (raw read count)"
        )


def test_handle_demux_consensus_stats_populated(
    fastq_dir_with_ref_reads: Path,
    ref_fasta: Path,
    tmp_path: Path,
) -> None:
    """consensus_stats must contain non-trivial WellConsensusStats for each well."""
    output_dir = tmp_path / "out"

    result = handle_demux_and_filter(
        {
            "fastq_dir": str(fastq_dir_with_ref_reads),
            "custom_barcodes": _BARCODES,
            "output_dir": str(output_dir),
            "reference_fasta": str(ref_fasta),
            "use_cutadapt": False,
            "auto_detect_length": False,
        }
    )

    stats = result["consensus_stats"]
    assert stats, "consensus_stats should be a non-empty dict"
    for well_key, stat in stats.items():
        assert stat["n_input_reads"] > 0, f"{well_key}: n_input_reads == 0"
        assert stat["consensus_seq_length"] == len(_REFERENCE), (
            f"{well_key}: consensus length {stat['consensus_seq_length']} != ref length"
        )
        assert stat["mean_depth"] > 0.0, f"{well_key}: mean_depth == 0"
        assert stat["n_mapq_failed"] == 0
        assert stat["n_span_failed"] == 0
        assert stat["n_low_depth_positions"] == 0
        assert stat["consensus_n_fraction"] == 0.0
        assert stat["n_low_quality_bases"] == 0


def test_handle_demux_legacy_no_consensus(
    fastq_dir_with_ref_reads: Path,
    tmp_path: Path,
) -> None:
    """Legacy mode (no reference_fasta): consensus_pipeline must be False."""
    output_dir = tmp_path / "out"

    result = handle_demux_and_filter(
        {
            "fastq_dir": str(fastq_dir_with_ref_reads),
            "custom_barcodes": _BARCODES,
            "output_dir": str(output_dir),
            "use_cutadapt": False,
            "auto_detect_length": False,
        }
    )

    assert result["consensus_pipeline"] is False
    assert result["consensus_stats"] is None


def test_handle_demux_save_intermediate_reads(
    fastq_dir_with_ref_reads: Path,
    ref_fasta: Path,
    tmp_path: Path,
) -> None:
    """When save_intermediate_reads=True, raw-read FASTA files must be kept."""
    output_dir = tmp_path / "out"

    handle_demux_and_filter(
        {
            "fastq_dir": str(fastq_dir_with_ref_reads),
            "custom_barcodes": _BARCODES,
            "output_dir": str(output_dir),
            "reference_fasta": str(ref_fasta),
            "save_intermediate_reads": True,
            "use_cutadapt": False,
            "auto_detect_length": False,
        }
    )

    raw_fastas = list(output_dir.rglob("*.raw_reads.fasta"))
    assert raw_fastas, "Expected at least one .raw_reads.fasta file (save_intermediate_reads=True)"
