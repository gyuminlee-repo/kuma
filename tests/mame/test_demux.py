"""Tests for A1 custom barcode demultiplexer (kuma_core.mame.ingest.demux)."""

from __future__ import annotations

import gzip
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kuma_core.mame.ingest.demux import (
    DemuxResult,
    _hamming_prefix,
    _validate_custom_barcodes,
    _validate_error_tolerance,
    demux_native_barcode,
    parse_custom_barcodes,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BARCODES: dict[str, str] = {
    "1_1": "AATCCCACT",
    "1_2": "TTGGAACCC",
    "1_3": "GGGATTCCA",
}


def _make_fastq(path: Path, reads: list[tuple[str, str, str]]) -> None:
    """Write a minimal FASTQ file. reads: list of (read_id, seq, qual)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for read_id, seq, qual in reads:
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")


def _make_gz_fastq(path: Path, reads: list[tuple[str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for read_id, seq, qual in reads:
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")


@pytest.fixture()
def fastq_dir(tmp_path: Path) -> Path:
    """Create a synthetic fastq_pass/barcode06/ folder with 3 barcodes."""
    bdir = tmp_path / "fastq_pass" / "barcode06"
    bdir.mkdir(parents=True)

    # 3 reads per barcode + 1 random unassigned.
    reads: list[tuple[str, str, str]] = []
    for i, (name, bc) in enumerate(BARCODES.items(), start=1):
        for j in range(3):
            read_id = f"read_{name}_{j}"
            # Prefix matches barcode exactly; pad to 200 bp.
            seq = bc + "ACGT" * 50
            qual = "I" * len(seq)
            reads.append((read_id, seq, qual))
    # Unassigned read — random prefix.
    reads.append(("unassigned_1", "CCCCCCCCCA" + "ACGT" * 50, "I" * 210))

    _make_fastq(bdir / "reads.fastq", reads)
    return bdir


# ---------------------------------------------------------------------------
# Unit tests: helpers
# ---------------------------------------------------------------------------


def test_validate_custom_barcodes_accepts_valid() -> None:
    _validate_custom_barcodes({"well_1": "ACGTACGT"})  # should not raise


def test_validate_custom_barcodes_rejects_empty() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        _validate_custom_barcodes({})


def test_validate_custom_barcodes_rejects_short_seq() -> None:
    with pytest.raises(ValueError, match="invalid"):
        _validate_custom_barcodes({"w1": "ACG"})  # < 5 chars


def test_validate_custom_barcodes_rejects_non_dna() -> None:
    with pytest.raises(ValueError, match="invalid"):
        _validate_custom_barcodes({"w1": "ACGTZZZ"})


def test_validate_error_tolerance_clamps() -> None:
    assert _validate_error_tolerance(0.0) == 0.0
    assert _validate_error_tolerance(0.5) == 0.5
    with pytest.raises(ValueError):
        _validate_error_tolerance(0.6)
    with pytest.raises(ValueError):
        _validate_error_tolerance(-0.1)


def test_hamming_prefix_exact_match() -> None:
    assert _hamming_prefix("ACGTACGT" + "N" * 10, "ACGTACGT") == 0


def test_hamming_prefix_one_mismatch() -> None:
    # First base differs.
    assert _hamming_prefix("TCGTACGT" + "N" * 10, "ACGTACGT") == 1


def test_hamming_prefix_read_shorter_than_barcode() -> None:
    dist = _hamming_prefix("ACG", "ACGTACGT")
    assert dist > len("ACGTACGT")


def test_hamming_prefix_all_mismatch() -> None:
    barcode = "ACGTACGT"
    read = "TGCATGCA" + "N" * 10
    assert _hamming_prefix(read, barcode) == len(barcode)


# ---------------------------------------------------------------------------
# Pure-Python demux integration
# ---------------------------------------------------------------------------


def test_demux_python_counts(fastq_dir: Path, tmp_path: Path) -> None:
    """Pure-Python fallback assigns reads correctly."""
    output_dir = tmp_path / "demux_out"

    # Force pure-Python path: pretend cutadapt is not available.
    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=fastq_dir,
            custom_barcodes=BARCODES,
            output_dir=output_dir,
            error_tolerance=0.1,
            use_cutadapt=False,
        )

    assert isinstance(result, DemuxResult)
    assert result.n_input_reads == 10  # 9 barcode reads + 1 unassigned
    assert result.n_assigned == 9
    assert result.n_unassigned == 1
    assert result.per_well_counts == {"1_1": 3, "1_2": 3, "1_3": 3}


def test_demux_python_fasta_files_created(fastq_dir: Path, tmp_path: Path) -> None:
    """Each assigned barcode produces a FASTA file."""
    output_dir = tmp_path / "demux_out"

    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=fastq_dir,
            custom_barcodes=BARCODES,
            output_dir=output_dir,
            error_tolerance=0.1,
            use_cutadapt=False,
        )

    for name in BARCODES:
        fasta = result.output_dir / f"{name}.fasta"
        assert fasta.exists(), f"Missing FASTA for {name}"
        lines = fasta.read_text().splitlines()
        headers = [l for l in lines if l.startswith(">")]
        assert len(headers) == 3


def test_demux_python_with_mismatches(tmp_path: Path) -> None:
    """Reads with 1 mismatch within tolerance are still assigned."""
    bdir = tmp_path / "fq"
    bc = "AATCCCACT"
    # Introduce 1 mismatch in position 5 of the barcode (within 10% of 9 chars → ceil=1).
    mutated = bc[:4] + "T" + bc[5:] + "ACGT" * 50
    _make_fastq(bdir / "r.fastq", [("read_mut", mutated, "I" * len(mutated))])

    output_dir = tmp_path / "out"
    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=bdir,
            custom_barcodes={"well_1": bc},
            output_dir=output_dir,
            error_tolerance=0.15,  # ceil(9 * 0.15) = 2 → 1 mismatch allowed
            use_cutadapt=False,
        )

    assert result.n_assigned == 1
    assert result.per_well_counts.get("well_1") == 1


def test_demux_python_no_fastq_raises(tmp_path: Path) -> None:
    """FileNotFoundError when no FASTQ files present."""
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="No FASTQ"):
        demux_native_barcode(
            fastq_dir=empty,
            custom_barcodes=BARCODES,
            output_dir=tmp_path / "out",
            error_tolerance=0.1,
            use_cutadapt=False,
        )


def test_demux_accepts_gz_fastq(tmp_path: Path) -> None:
    """Gzipped FASTQ files are parsed correctly."""
    bdir = tmp_path / "fq"
    bc = "AATCCCACT"
    seq = bc + "ACGT" * 50
    _make_gz_fastq(bdir / "reads.fastq.gz", [("r1", seq, "I" * len(seq))])

    output_dir = tmp_path / "out"
    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=bdir,
            custom_barcodes={"well_1": bc},
            output_dir=output_dir,
            error_tolerance=0.1,
            use_cutadapt=False,
        )
    assert result.n_assigned == 1


def test_demux_cutadapt_fallback_when_not_installed(
    fastq_dir: Path, tmp_path: Path
) -> None:
    """When cutadapt is absent, pure-Python fallback is used silently."""
    output_dir = tmp_path / "out"

    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=fastq_dir,
            custom_barcodes=BARCODES,
            output_dir=output_dir,
            error_tolerance=0.1,
            use_cutadapt=True,  # requested but not available
        )

    assert result.n_assigned == 9


# ---------------------------------------------------------------------------
# parse_custom_barcodes — CSV path
# ---------------------------------------------------------------------------


def test_parse_custom_barcodes_csv(tmp_path: Path) -> None:
    csv = tmp_path / "barcodes.csv"
    csv.write_text("name,sequence\nwell_A,ACGTACGTAC\nwell_B,TGCATGCATG\n")
    result = parse_custom_barcodes(csv)
    assert result == {"well_A": "ACGTACGTAC", "well_B": "TGCATGCATG"}


def test_parse_custom_barcodes_csv_skips_invalid(tmp_path: Path) -> None:
    csv = tmp_path / "b.csv"
    csv.write_text("name,sequence\nok,ACGTACGT\nbad,ZZZZZZ\n")
    result = parse_custom_barcodes(csv)
    assert "ok" in result
    assert "bad" not in result


def test_parse_custom_barcodes_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported barcode file format"):
        parse_custom_barcodes(tmp_path / "barcodes.tsv")


# ---------------------------------------------------------------------------
# Tie-breaking: ambiguous reads go to unassigned
# ---------------------------------------------------------------------------


def test_demux_tie_goes_unassigned(tmp_path: Path) -> None:
    """A read equidistant from two barcodes is counted as unassigned."""
    bdir = tmp_path / "fq"
    # Two barcodes of same length.
    bc1 = "AAAAAAAAAA"
    bc2 = "CCCCCCCCCC"
    # Read: half matches each barcode equally — e.g. AAAAACCCCC (5 mismatches each)
    read_seq = "AAAAACCCCC" + "NNNN" * 20
    _make_fastq(bdir / "r.fastq", [("r1", read_seq, "I" * len(read_seq))])

    output_dir = tmp_path / "out"
    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=bdir,
            custom_barcodes={"b1": bc1, "b2": bc2},
            output_dir=output_dir,
            error_tolerance=0.5,  # allow up to 5 mismatches per 10-char barcode
            use_cutadapt=False,
        )

    # With equal distances to both barcodes, the read should be unassigned.
    assert result.n_unassigned == 1
    assert result.n_assigned == 0
