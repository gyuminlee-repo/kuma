"""Tests for sort_barcode combinatorial demultiplexer.

Fixtures
--------
- Synthetic FASTQ files with known barcode sequences.
- Minimal combinatorial xlsx: 12 fwd (egfp_f_1..12) + 8 rev (egfp_r_1..8).

All tests use pure-Python path (no cutadapt dependency).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# openpyxl is required for xlsx fixture generation.
openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")

from kuma_core.mame.ingest.sort_barcode import (
    SortBarcodeResult,
    _hamming_suffix_window,
    _make_well_filename,
    _nb_to_sort_barcode_name,
    parse_combinatorial_barcodes,
    parse_sample_map,
    sort_barcode_run,
)


# ---------------------------------------------------------------------------
# FASTQ helpers (copied from test_demux.py pattern)
# ---------------------------------------------------------------------------


def _make_fastq(path: Path, reads: list[tuple[str, str, str]]) -> None:
    """Write a minimal FASTQ file. reads: list of (read_id, seq, qual)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for read_id, seq, qual in reads:
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")



# ---------------------------------------------------------------------------
# xlsx fixture helper
# ---------------------------------------------------------------------------

# Deterministic barcode sequences for testing.
_FWD_SEQS: dict[int, str] = {
    1:  "AATCCCACTACCACAGGAGGTTAAACC",   # egfp_f_1 (unique length per spec)
    2:  "TGAACTGAGCGCACAGGAGGTTAAACC",   # egfp_f_2 (unique length per spec)
    3:  "AAACGTCACAGGAGGTTAAACC",
    4:  "TTGCAATCACAGGAGGTTAAACC",
    5:  "CCAGTTTTCACAGGAGGTTAAACC",
    6:  "GGTAACAGCACAGGAGGTTAAACC",
    7:  "AAGCTATACAGGAGGTTAAACC",
    8:  "TTCAACGCACAGGAGGTTAAACC",
    9:  "CCGTGATACAGGAGGTTAAACC",
    10: "GGCATTTCACAGGAGGTTAAACC",
    11: "AACCGTTCACAGGAGGTTAAACC",
    12: "TTGGAAACAGGAGGTTAAACC",
}

_REV_SEQS: dict[int, str] = {
    1: "GCATGCATGCAT",
    2: "AGTCAGTCAGTC",
    3: "TTAGTTAGTTAG",
    4: "CCAACCAACCAA",
    5: "GGTGGGTGGGTG",
    6: "AACCTTAACCTT",
    7: "TTGGAATTGGAA",
    8: "CCGGTTCCGGTT",
}


def _make_barcode_xlsx(path: Path) -> None:
    """Write a minimal combinatorial barcode xlsx (12 fwd + 8 rev = 20 rows)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet1"

    for n, seq in _FWD_SEQS.items():
        ws.append([f"egfp_f_{n}", seq])

    for n, seq in _REV_SEQS.items():
        ws.append([f"egfp_r_{n}", seq])

    wb.save(str(path))


def _make_barcode_xlsx_missing_fwd(path: Path) -> None:
    """xlsx with only 11 fwd barcodes (egfp_f_12 missing)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet1"
    for n, seq in _FWD_SEQS.items():
        if n == 12:
            continue
        ws.append([f"egfp_f_{n}", seq])
    for n, seq in _REV_SEQS.items():
        ws.append([f"egfp_r_{n}", seq])
    wb.save(str(path))


def _make_barcode_xlsx_missing_rev(path: Path) -> None:
    """xlsx with only 7 rev barcodes (egfp_r_8 missing)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet1"
    for n, seq in _FWD_SEQS.items():
        ws.append([f"egfp_f_{n}", seq])
    for n, seq in _REV_SEQS.items():
        if n == 8:
            continue
        ws.append([f"egfp_r_{n}", seq])
    wb.save(str(path))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def barcode_xlsx(tmp_path: Path) -> Path:
    p = tmp_path / "barcodes_sequence.xlsx"
    _make_barcode_xlsx(p)
    return p


def _build_read(
    fwd_n: int,
    rev_n: int,
    body: str = "GCGCGCGC" * 20,
) -> tuple[str, str, str]:
    """Build a synthetic read: [fwd][body][rc(rev)].

    Returns (read_id, seq, qual).
    """
    from kuma_core.mame.ingest.demux import _rc

    fwd = _FWD_SEQS[fwd_n]
    rev_rc = _rc(_REV_SEQS[rev_n])
    seq = fwd + body + rev_rc
    qual = "I" * len(seq)
    return f"read_f{fwd_n}_r{rev_n}", seq, qual


@pytest.fixture()
def run_dir_single_nb(tmp_path: Path, barcode_xlsx: Path) -> tuple[Path, Path]:
    """MinKNOW run dir with fastq_pass/barcode06/ containing reads for wells A01 and B02."""
    run_dir = tmp_path / "run"
    nb_dir = run_dir / "fastq_pass" / "barcode06"
    nb_dir.mkdir(parents=True)

    reads = [
        _build_read(1, 1),   # A01
        _build_read(1, 1),   # A01 again
        _build_read(2, 2),   # B02
        ("unassigned_1", "CCCCCCCCCCCCCC" + "ACGT" * 40, "I" * 174),
    ]
    _make_fastq(nb_dir / "reads.fastq", reads)
    return run_dir, barcode_xlsx


@pytest.fixture()
def run_dir_multi_nb(tmp_path: Path, barcode_xlsx: Path) -> tuple[Path, Path]:
    """MinKNOW run dir with fastq_pass/barcode06/ and fastq_pass/barcode07/."""
    run_dir = tmp_path / "run"

    nb06 = run_dir / "fastq_pass" / "barcode06"
    nb07 = run_dir / "fastq_pass" / "barcode07"
    nb06.mkdir(parents=True)
    nb07.mkdir(parents=True)

    reads06 = [_build_read(1, 1)]   # A01
    reads07 = [_build_read(3, 2)]   # B03

    _make_fastq(nb06 / "reads.fastq", reads06)
    _make_fastq(nb07 / "reads.fastq", reads07)
    return run_dir, barcode_xlsx


# ---------------------------------------------------------------------------
# Unit tests: _nb_to_sort_barcode_name
# ---------------------------------------------------------------------------


class TestNbToSortBarcodeName:
    def test_barcode06_style(self) -> None:
        assert _nb_to_sort_barcode_name("barcode06") == "sort_barcode06"

    def test_nb06_style(self) -> None:
        assert _nb_to_sort_barcode_name("NB06") == "sort_barcode06"

    def test_barcode100_three_digit(self) -> None:
        assert _nb_to_sort_barcode_name("barcode100") == "sort_barcode100"

    def test_nb100_three_digit(self) -> None:
        assert _nb_to_sort_barcode_name("NB100") == "sort_barcode100"

    def test_invalid_name_raises(self) -> None:
        with pytest.raises(ValueError, match="sort_barcode name"):
            _nb_to_sort_barcode_name("unclassified")

    def test_invalid_name_no_digits_raises(self) -> None:
        with pytest.raises(ValueError, match="sort_barcode name"):
            _nb_to_sort_barcode_name("somefolder")

    def test_case_insensitive(self) -> None:
        assert _nb_to_sort_barcode_name("BARCODE01") == "sort_barcode01"


# ---------------------------------------------------------------------------
# Unit tests: parse_combinatorial_barcodes
# ---------------------------------------------------------------------------


class TestParseCombinatorial:
    def test_normal_96_wells(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "barcodes.xlsx"
        _make_barcode_xlsx(xlsx)
        result = parse_combinatorial_barcodes(xlsx)
        assert len(result) == 96
        # A01 = fwd_1, rev_1
        assert result["A01"] == (_FWD_SEQS[1], _REV_SEQS[1])
        # H12 = fwd_12, rev_8
        assert result["H12"] == (_FWD_SEQS[12], _REV_SEQS[8])

    def test_missing_fwd_raises(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "barcodes_miss_fwd.xlsx"
        _make_barcode_xlsx_missing_fwd(xlsx)
        with pytest.raises(ValueError, match="Missing forward barcodes"):
            parse_combinatorial_barcodes(xlsx)

    def test_missing_rev_raises(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "barcodes_miss_rev.xlsx"
        _make_barcode_xlsx_missing_rev(xlsx)
        with pytest.raises(ValueError, match="Missing reverse barcodes"):
            parse_combinatorial_barcodes(xlsx)

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_combinatorial_barcodes(tmp_path / "nonexistent.xlsx")

    def test_invalid_prefix_skipped(self, tmp_path: Path) -> None:
        """Rows with neither egfp_f_ nor egfp_r_ prefix are silently skipped."""
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Sheet1"
        # Add valid fwd + rev
        for n, seq in _FWD_SEQS.items():
            ws.append([f"egfp_f_{n}", seq])
        for n, seq in _REV_SEQS.items():
            ws.append([f"egfp_r_{n}", seq])
        # Add an unrecognised row — should be silently skipped
        ws.append(["random_barcode", "ACGTACGTAC"])
        xlsx = tmp_path / "barcodes_extra.xlsx"
        wb.save(str(xlsx))
        # Should not raise — unrecognised prefix is skipped
        result = parse_combinatorial_barcodes(xlsx)
        assert len(result) == 96

    def test_well_id_mapping(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "barcodes.xlsx"
        _make_barcode_xlsx(xlsx)
        result = parse_combinatorial_barcodes(xlsx)
        # row=1 col=1 → A01; row=1 col=2 → A02; row=2 col=1 → B01
        assert result["A02"] == (_FWD_SEQS[2], _REV_SEQS[1])
        assert result["B01"] == (_FWD_SEQS[1], _REV_SEQS[2])


# ---------------------------------------------------------------------------
# Unit tests: _hamming_suffix_window
# ---------------------------------------------------------------------------


class TestHammingSuffixWindow:
    def test_exact_match_at_end(self) -> None:
        barcode = "GCATGCAT"
        seq = "ACGT" * 20 + barcode
        dist, _pos = _hamming_suffix_window(seq, barcode)
        assert dist == 0

    def test_one_mismatch(self) -> None:
        barcode = "GCATGCAT"
        mutated = "GCTTGCAT"  # 1 mismatch at position 2
        seq = "ACGT" * 20 + mutated
        dist, _pos = _hamming_suffix_window(seq, barcode)
        assert dist == 1

    def test_poor_match_exceeds_strict_threshold(self) -> None:
        """A low-similarity sequence exceeds strict error_tolerance threshold.

        _hamming_suffix_window returns the minimum Hamming distance over all
        windows in the tail; it does NOT guarantee dist > len(barcode) for
        sequences longer than the barcode. The meaningful contract is that
        dist > ceil(len * error_tolerance) when similarity is low, preventing
        a false assignment. Using error_tolerance=0.1 → max_mm=1; dist should
        be well above 1 for an unrelated sequence.
        """
        import math
        barcode = "GCATGCAT"
        seq = "AAAAAAAAAAAAAAAAAAAAAAAAAAAA"  # no similarity to barcode
        dist, _pos = _hamming_suffix_window(seq, barcode)
        max_mm = math.ceil(len(barcode) * 0.1)
        assert dist > max_mm, (
            f"Expected dist ({dist}) > max_mm ({max_mm}) for low-similarity read"
        )

    def test_read_shorter_than_barcode(self) -> None:
        barcode = "GCATGCATGCATGCAT"
        seq = "ACG"
        dist, _pos = _hamming_suffix_window(seq, barcode)
        assert dist > len(barcode)


# ---------------------------------------------------------------------------
# Integration tests: sort_barcode_run
# ---------------------------------------------------------------------------


class TestSortBarcodeRun:
    def test_single_nb_basic(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        run_dir, xlsx = run_dir_single_nb
        out = tmp_path / "out"
        result = sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
        )
        assert isinstance(result, SortBarcodeResult)
        assert "barcode06" in result.nb_dirs_processed
        assert result.n_total_reads == 4   # 3 assigned + 1 unassigned

    def test_single_nb_output_structure(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """sort_barcode06/A01_F1_R1.fasta must exist with 2 reads."""
        run_dir, xlsx = run_dir_single_nb
        out = tmp_path / "out"
        sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
        )
        a01_fasta = out / "sort_barcode06" / "A01_F1_R1.fasta"
        assert a01_fasta.exists(), f"Expected {a01_fasta} to exist"
        headers = [
            ln for ln in a01_fasta.read_text().splitlines() if ln.startswith(">")
        ]
        assert len(headers) == 2  # two reads assigned to A01

    def test_single_nb_b02_fasta(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """sort_barcode06/B02_F2_R2.fasta must exist with 1 read."""
        run_dir, xlsx = run_dir_single_nb
        out = tmp_path / "out"
        sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
        )
        b02_fasta = out / "sort_barcode06" / "B02_F2_R2.fasta"
        assert b02_fasta.exists(), f"Expected {b02_fasta} to exist"
        headers = [
            ln for ln in b02_fasta.read_text().splitlines() if ln.startswith(">")
        ]
        assert len(headers) == 1

    def test_multi_nb(
        self, run_dir_multi_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        run_dir, xlsx = run_dir_multi_nb
        out = tmp_path / "out"
        result = sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
        )
        assert "barcode06" in result.nb_dirs_processed
        assert "barcode07" in result.nb_dirs_processed
        # A01_F1_R1.fasta from barcode06
        assert (out / "sort_barcode06" / "A01_F1_R1.fasta").exists()
        # B03_F3_R2.fasta from barcode07
        assert (out / "sort_barcode07" / "B03_F3_R2.fasta").exists()

    def test_nb_override(
        self, run_dir_multi_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """nb_override limits processing to only the specified NB dirs."""
        run_dir, xlsx = run_dir_multi_nb
        out = tmp_path / "out"
        result = sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            nb_override=["barcode06"],
            error_tolerance=0.1,
            use_cutadapt=False,
        )
        assert result.nb_dirs_processed == ["barcode06"]
        # barcode07 was NOT processed
        assert not (out / "sort_barcode07").exists()

    def test_missing_run_dir_raises(self, tmp_path: Path, barcode_xlsx: Path) -> None:
        with pytest.raises(FileNotFoundError, match="minknow_run_dir"):
            sort_barcode_run(
                minknow_run_dir=tmp_path / "nonexistent",
                custom_barcode_xlsx=barcode_xlsx,
                output_dir=tmp_path / "out",
            )

    def test_missing_fastq_pass_raises(self, tmp_path: Path, barcode_xlsx: Path) -> None:
        run_dir = tmp_path / "run"
        run_dir.mkdir()  # exists but no fastq_pass/
        with pytest.raises(FileNotFoundError, match="fastq_pass"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=barcode_xlsx,
                output_dir=tmp_path / "out",
            )

    def test_missing_xlsx_raises(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run"
        (run_dir / "fastq_pass").mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="custom_barcode_xlsx"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=tmp_path / "missing.xlsx",
                output_dir=tmp_path / "out",
            )

    def test_zero_nb_dirs_raises(self, tmp_path: Path, barcode_xlsx: Path) -> None:
        """fastq_pass/ exists but no barcode*/NB* subdirs → ValueError."""
        run_dir = tmp_path / "run"
        (run_dir / "fastq_pass" / "unclassified").mkdir(parents=True)
        with pytest.raises(ValueError, match="No native barcode dirs"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=barcode_xlsx,
                output_dir=tmp_path / "out",
            )

    def test_error_tolerance_out_of_range(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        run_dir, xlsx = run_dir_single_nb
        with pytest.raises(ValueError, match="error_tolerance"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=xlsx,
                output_dir=tmp_path / "out",
                error_tolerance=0.6,
            )

    def test_nb_override_nonexistent_raises(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        run_dir, xlsx = run_dir_single_nb
        with pytest.raises(FileNotFoundError):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=xlsx,
                output_dir=tmp_path / "out",
                nb_override=["barcode99"],
            )

    def test_counts_sum_correctly(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        run_dir, xlsx = run_dir_single_nb
        out = tmp_path / "out"
        result = sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
        )
        assert result.n_total_assigned + result.n_total_unassigned == result.n_total_reads

    def test_fasta_header_contains_read_id(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """FASTA headers preserve original read IDs (not well names)."""
        run_dir, xlsx = run_dir_single_nb
        out = tmp_path / "out"
        sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
        )
        a01_fasta = out / "sort_barcode06" / "A01_F1_R1.fasta"
        headers = [
            ln[1:] for ln in a01_fasta.read_text().splitlines() if ln.startswith(">")
        ]
        # Headers should be read IDs, not well names.
        for h in headers:
            assert h != "A01", f"Header should be read_id, not well name: {h}"


# ---------------------------------------------------------------------------
# Security tests: path traversal + nb_override validation
# ---------------------------------------------------------------------------


class TestSecurityPathTraversal:
    def test_sort_barcode_rejects_path_traversal(
        self, barcode_xlsx: Path, tmp_path: Path
    ) -> None:
        """output_dir with '..' component must raise ValueError before any I/O."""
        run_dir = tmp_path / "run"
        (run_dir / "fastq_pass" / "barcode06").mkdir(parents=True)

        # Construct an output_dir whose Path.parts contains '..'
        traversal_dir = tmp_path / "foo" / ".." / "etc" / "sort"
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=barcode_xlsx,
                output_dir=traversal_dir,
            )

    def test_sort_barcode_rejects_nb_override_with_slash(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """nb_override entry containing '/' must raise ValueError."""
        run_dir, xlsx = run_dir_single_nb
        with pytest.raises(ValueError, match="plain directory name"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=xlsx,
                output_dir=tmp_path / "out",
                nb_override=["barcode06/../../../etc"],
            )

    def test_sort_barcode_rejects_nb_override_with_traversal_basename(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """nb_override entry of '..' must raise ValueError."""
        run_dir, xlsx = run_dir_single_nb
        with pytest.raises(ValueError, match="plain directory name"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=xlsx,
                output_dir=tmp_path / "out",
                nb_override=[".."],
            )

    def test_validate_combinatorial_xlsx_path_traversal(
        self, tmp_path: Path
    ) -> None:
        """custom_barcode_xlsx path with '..' must raise ValueError."""
        run_dir = tmp_path / "run"
        (run_dir / "fastq_pass" / "barcode06").mkdir(parents=True)

        traversal_xlsx = tmp_path / "foo" / ".." / "secrets" / "barcodes.xlsx"
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=traversal_xlsx,
                output_dir=tmp_path / "out",
            )

    def test_sample_map_path_traversal_raises(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """sample_map_path with '..' must raise ValueError."""
        run_dir, xlsx = run_dir_single_nb
        traversal = tmp_path / "foo" / ".." / "secrets" / "map.xlsx"
        with pytest.raises(ValueError, match="[Pp]ath traversal"):
            sort_barcode_run(
                minknow_run_dir=run_dir,
                custom_barcode_xlsx=xlsx,
                output_dir=tmp_path / "out",
                sample_map_path=traversal,
            )


# ---------------------------------------------------------------------------
# Unit tests: parse_sample_map
# ---------------------------------------------------------------------------


def _make_sample_map_xlsx(path: Path, entries: list[tuple[str, str]]) -> None:
    """Write a sample map xlsx. entries: [(sample_name, well_pos)]."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Sheet1"
    for name, pos in entries:
        ws.append([name, pos])
    wb.save(str(path))


class TestParseSampleMap:
    def test_basic_mapping(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(xlsx, [("V5F", "A1"), ("K53R", "B2"), ("WT", "H12")])
        result = parse_sample_map(xlsx)
        assert result["A01"] == "V5F"
        assert result["B02"] == "K53R"
        assert result["H12"] == "WT"

    def test_zero_padded_position(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(xlsx, [("MUT1", "A01"), ("MUT2", "A1")])
        result = parse_sample_map(xlsx)
        # Both "A01" and "A1" → same key; first wins
        assert result["A01"] == "MUT1"

    def test_invalid_well_positions_skipped(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(xlsx, [
            ("V5F", "A1"),
            ("BAD", "Z9"),    # invalid row letter
            ("OK", "B3"),
        ])
        result = parse_sample_map(xlsx)
        assert "A01" in result
        assert "B03" in result
        assert len(result) == 2  # Z9 skipped

    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="sample_map_path"):
            parse_sample_map(tmp_path / "missing.xlsx")


# ---------------------------------------------------------------------------
# Unit tests: _make_well_filename
# ---------------------------------------------------------------------------


class TestMakeWellFilename:
    def test_without_sample_map(self) -> None:
        assert _make_well_filename("A01", 1, 1, None) == "A01_F1_R1"

    def test_with_sample_map_match(self) -> None:
        assert _make_well_filename("A01", 1, 1, {"A01": "V5F"}) == "A01_V5F_F1_R1"

    def test_with_sample_map_no_match(self) -> None:
        assert _make_well_filename("C05", 5, 3, {"A01": "V5F"}) == "C05_F5_R3"

    def test_fwd_rev_indices_in_name(self) -> None:
        stem = _make_well_filename("H12", 12, 8, {"H12": "WT"})
        assert stem == "H12_WT_F12_R8"


# ---------------------------------------------------------------------------
# Integration tests: sort_barcode_run with sample_map_path
# ---------------------------------------------------------------------------


class TestSortBarcodeRunWithSampleMap:
    def test_filename_includes_sample_name(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        run_dir, xlsx = run_dir_single_nb
        # A01 = fwd1 × rev1, B02 = fwd2 × rev2
        sample_map = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(sample_map, [("V5F", "A1"), ("K53R", "B2")])
        out = tmp_path / "out"
        sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
            sample_map_path=sample_map,
        )
        assert (out / "sort_barcode06" / "A01_V5F_F1_R1.fasta").exists()
        assert (out / "sort_barcode06" / "B02_K53R_F2_R2.fasta").exists()

    def test_unmapped_well_falls_back_to_no_sample(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        """Well not in sample map → A01_F1_R1.fasta (no sample name)."""
        run_dir, xlsx = run_dir_single_nb
        sample_map = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(sample_map, [("V5F", "A1")])  # B02 not listed
        out = tmp_path / "out"
        sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
            sample_map_path=sample_map,
        )
        assert (out / "sort_barcode06" / "A01_V5F_F1_R1.fasta").exists()
        assert (out / "sort_barcode06" / "B02_F2_R2.fasta").exists()

    def test_per_well_counts_keyed_by_filename_stem(
        self, run_dir_single_nb: tuple[Path, Path], tmp_path: Path
    ) -> None:
        run_dir, xlsx = run_dir_single_nb
        sample_map = tmp_path / "sample_map.xlsx"
        _make_sample_map_xlsx(sample_map, [("V5F", "A1"), ("K53R", "B2")])
        out = tmp_path / "out"
        result = sort_barcode_run(
            minknow_run_dir=run_dir,
            custom_barcode_xlsx=xlsx,
            output_dir=out,
            error_tolerance=0.1,
            use_cutadapt=False,
            sample_map_path=sample_map,
        )
        counts = result.per_nb_per_well_counts["barcode06"]
        assert counts.get("A01_V5F_F1_R1") == 2
        assert counts.get("B02_K53R_F2_R2") == 1
