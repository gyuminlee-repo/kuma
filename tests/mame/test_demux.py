"""Tests for A1 custom barcode demultiplexer (kuma_core.mame.ingest.demux)."""

from __future__ import annotations

import gzip
from pathlib import Path
from unittest.mock import patch

import pytest

from kuma_core.mame.ingest.demux import (
    DemuxResult,
    _hamming_prefix,
    _rc,
    _trim_rev_primer,
    _validate_custom_barcodes,
    _validate_error_tolerance,
    detect_native_barcode_dirs,
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
    for name, bc in BARCODES.items():
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


# ---------------------------------------------------------------------------
# R6.5: _rc helper
# ---------------------------------------------------------------------------


def test_rc_simple() -> None:
    assert _rc("ACGT") == "ACGT"


def test_rc_asymmetric() -> None:
    assert _rc("AACCGG") == "CCGGTT"


def test_rc_empty() -> None:
    assert _rc("") == ""


# ---------------------------------------------------------------------------
# R6.5: _trim_rev_primer
# ---------------------------------------------------------------------------


def test_trim_rev_primer_exact_hit() -> None:
    """Exact match trims sequence to position before primer."""
    primer_rc = "TTTTTT"
    seq = "ACGT" * 20 + primer_rc + "EXTRA"
    trimmed = _trim_rev_primer(seq, primer_rc, max_mismatches=0)
    assert not trimmed.endswith(primer_rc)
    assert len(trimmed) < len(seq)


def test_trim_rev_primer_no_hit_returns_original() -> None:
    """No primer match returns original sequence unchanged."""
    primer_rc = "ZZZZZZ"  # impossible sequence
    seq = "ACGT" * 20
    trimmed = _trim_rev_primer(seq, primer_rc, max_mismatches=0)
    assert trimmed == seq


def test_trim_rev_primer_with_one_mismatch() -> None:
    """One mismatch within tolerance is still trimmed."""
    primer_rc = "AAAAAA"
    # One mismatch: AAGAAA
    seq = "ACGT" * 20 + "AAGAAA"
    trimmed = _trim_rev_primer(seq, primer_rc, max_mismatches=1)
    assert len(trimmed) < len(seq)


# ---------------------------------------------------------------------------
# R6.5: normalize_headers
# ---------------------------------------------------------------------------


def test_normalize_headers_on(fastq_dir: Path, tmp_path: Path) -> None:
    """With normalize_headers=True, all FASTA headers equal the well name."""
    output_dir = tmp_path / "norm_out"

    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=fastq_dir,
            custom_barcodes=BARCODES,
            output_dir=output_dir,
            error_tolerance=0.1,
            use_cutadapt=False,
            normalize_headers=True,
        )

    for well_name in result.per_well_counts:
        fasta = result.output_dir / f"{well_name}.fasta"
        assert fasta.exists()
        for line in fasta.read_text().splitlines():
            if line.startswith(">"):
                assert line == f">{well_name}", (
                    f"Expected header '>{well_name}', got {line!r}"
                )


def test_normalize_headers_off(fastq_dir: Path, tmp_path: Path) -> None:
    """With normalize_headers=False, FASTA headers preserve original read IDs."""
    output_dir = tmp_path / "raw_headers_out"

    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=fastq_dir,
            custom_barcodes=BARCODES,
            output_dir=output_dir,
            error_tolerance=0.1,
            use_cutadapt=False,
            normalize_headers=False,
        )

    for well_name in result.per_well_counts:
        fasta = result.output_dir / f"{well_name}.fasta"
        assert fasta.exists()
        for line in fasta.read_text().splitlines():
            if line.startswith(">"):
                # Headers should NOT equal the well name (they are read IDs).
                assert line != f">{well_name}", (
                    f"Expected read ID header, got well name for {well_name}"
                )


# ---------------------------------------------------------------------------
# R6.5: linked_trim validation
# ---------------------------------------------------------------------------


def test_linked_trim_without_rev_primer_raises(fastq_dir: Path, tmp_path: Path) -> None:
    """linked_trim=True without rev_primer_universal raises ValueError."""
    with pytest.raises(ValueError, match="rev_primer_universal"):
        demux_native_barcode(
            fastq_dir=fastq_dir,
            custom_barcodes=BARCODES,
            output_dir=tmp_path / "out",
            use_cutadapt=False,
            linked_trim=True,
            rev_primer_universal=None,
        )


def test_linked_trim_with_rev_primer_python(tmp_path: Path) -> None:
    """linked_trim=True with rev primer trims from 3′ end (pure-Python path)."""
    bdir = tmp_path / "fq"
    bc = "AATCCCACT"
    rev_primer = "TTTTTT"
    rev_rc = _rc(rev_primer)  # AAAAAA

    # Build read: barcode + amplicon body + rev primer RC (to be trimmed)
    amplicon_body = "GCGCGCGC" * 10  # 80 bp
    seq = bc + amplicon_body + rev_rc
    _make_fastq(bdir / "r.fastq", [("r1", seq, "I" * len(seq))])

    output_dir = tmp_path / "out"
    with patch("kuma_core.mame.ingest.demux.shutil.which", return_value=None):
        result = demux_native_barcode(
            fastq_dir=bdir,
            custom_barcodes={"well_1": bc},
            output_dir=output_dir,
            error_tolerance=0.1,
            use_cutadapt=False,
            linked_trim=True,
            rev_primer_universal=rev_primer,
            normalize_headers=False,
        )

    assert result.n_assigned == 1
    fasta = result.output_dir / "well_1.fasta"
    lines = [l for l in fasta.read_text().splitlines() if not l.startswith(">")]
    trimmed_seq = "".join(lines)
    # Rev primer RC should have been removed from the 3′ end.
    assert not trimmed_seq.endswith(rev_rc), "Rev primer RC was not trimmed"
    # Amplicon body should still be present.
    assert amplicon_body in trimmed_seq


# ---------------------------------------------------------------------------
# Existing tie test (unchanged)
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


# ---------------------------------------------------------------------------
# detect_native_barcode_dirs
# ---------------------------------------------------------------------------


def test_detect_nb_dirs_minkow_style(tmp_path: Path) -> None:
    """MinKNOW-style barcode01/barcode02 + unclassified → 2 NB dirs, unclassified excluded."""
    root = tmp_path / "fastq_pass"
    (root / "barcode01").mkdir(parents=True)
    (root / "barcode02").mkdir(parents=True)
    (root / "unclassified").mkdir(parents=True)

    result = detect_native_barcode_dirs(root)
    names = [p.name for p in result]

    assert names == ["barcode01", "barcode02"]
    assert "unclassified" not in names


def test_detect_nb_dirs_post_processed_style(tmp_path: Path) -> None:
    """Post-processed NB01/NB02/NB03 dirs → 3 NB dirs detected."""
    root = tmp_path / "run"
    (root / "NB01").mkdir(parents=True)
    (root / "NB02").mkdir(parents=True)
    (root / "NB03").mkdir(parents=True)

    result = detect_native_barcode_dirs(root)
    names = [p.name for p in result]

    assert len(names) == 3
    assert names == ["NB01", "NB02", "NB03"]


def test_detect_nb_dirs_single_nb_no_subdirs(tmp_path: Path) -> None:
    """Directory containing FASTQ files directly (single-NB) → empty list."""
    root = tmp_path / "barcode06"
    root.mkdir(parents=True)
    (root / "reads.fastq").write_text("")  # FASTQ file, not a barcode subdir

    result = detect_native_barcode_dirs(root)

    assert result == []


def test_detect_nb_dirs_mixed_non_standard_names(tmp_path: Path) -> None:
    """Only barcode*/NB* matching dirs are returned; non-matching dirs are ignored."""
    root = tmp_path / "mixed"
    (root / "barcode01").mkdir(parents=True)
    (root / "barcode02").mkdir(parents=True)
    (root / "foo").mkdir(parents=True)
    (root / "barcode_bad").mkdir(parents=True)
    (root / "not_a_barcode").mkdir(parents=True)

    result = detect_native_barcode_dirs(root)
    names = [p.name for p in result]

    assert names == ["barcode01", "barcode02"]
    assert "foo" not in names
    assert "barcode_bad" not in names


def test_detect_nb_dirs_numeric_sort(tmp_path: Path) -> None:
    """Sorting is numeric, not lexicographic: barcode10 follows barcode02."""
    root = tmp_path / "run"
    (root / "barcode02").mkdir(parents=True)
    (root / "barcode10").mkdir(parents=True)
    (root / "barcode01").mkdir(parents=True)

    result = detect_native_barcode_dirs(root)
    names = [p.name for p in result]

    # Numeric order: 01, 02, 10 — not 01, 10, 02 (lexicographic)
    assert names == ["barcode01", "barcode02", "barcode10"]


def test_detect_nb_dirs_excludes_barcode00(tmp_path: Path) -> None:
    """barcode00 is a non-standard placeholder and must be excluded."""
    root = tmp_path / "run"
    (root / "barcode00").mkdir(parents=True)
    (root / "barcode01").mkdir(parents=True)

    result = detect_native_barcode_dirs(root)
    names = [p.name for p in result]

    assert "barcode00" not in names
    assert names == ["barcode01"]


def test_detect_nb_dirs_case_insensitive(tmp_path: Path) -> None:
    """Pattern matching is case-insensitive: BARCODE01 and nb01 both match."""
    root = tmp_path / "run"
    (root / "BARCODE01").mkdir(parents=True)
    (root / "nb01").mkdir(parents=True)

    result = detect_native_barcode_dirs(root)

    assert len(result) == 2


def test_detect_nb_dirs_not_a_directory(tmp_path: Path) -> None:
    """Non-existent path returns empty list (single-NB fallback)."""
    result = detect_native_barcode_dirs(tmp_path / "does_not_exist")
    assert result == []
