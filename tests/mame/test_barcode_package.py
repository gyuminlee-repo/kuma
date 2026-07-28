"""Tests for kuma_core.mame.ingest.barcode_package.

Coverage:
- parse_barcode_seeds: happy path, missing fwd seeds, duplicate sequences
- design_flanking_primers: happy path, Tm window, GC clamp, warnings fallback,
  out-of-bounds, gene range violations
- generate_mame_package: full integration, multi-sequence FASTA warning
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed")
primer3 = pytest.importorskip("primer3", reason="primer3-py not installed")

from kuma_core.mame.ingest.barcode_package import (
    MamePackageResult,
    design_flanking_primers,
    generate_mame_package,
    parse_barcode_seeds,
)
from kuma_core.mame.ingest.polymerase import get_profile

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_FWD_SEEDS: dict[int, str] = {
    1: "TATCTGACCTT",
    2: "GCATACGTAAC",
    3: "AACTTGCATAG",
    4: "TGACCTAAGGT",
    5: "CCGTATATAAC",
    6: "GTAACCTGCAT",
    7: "AAGCTTACCAT",
    8: "TTCCGGATCAT",
    9: "CCATTAGCATG",
    10: "GGTTAACCATG",
    11: "AATCCGTTAGC",
    12: "GAACATACGGT",
}

_REV_SEEDS: dict[int, str] = {
    1: "CCCTATGACAG",
    2: "GCTATAGCCTT",
    3: "TTGCAATCGAT",
    4: "CCAGTATCGGT",
    5: "GGTACCTAATG",
    6: "AAGCTATCGCT",
    7: "TTCCAGCTTAG",
    8: "AGAGTGCGGCT",
}


def _make_seeds_xlsx(path: Path, fwd: dict[int, str], rev: dict[int, str]) -> None:
    """Write a barcode_seeds.xlsx using fwd/rev dicts."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Seeds"
    # header row (skipped by parser via prefix match)
    ws.append(["name", "sequence"])
    for i in range(1, 13):
        ws.append([f"fwd_{i}", fwd.get(i, "")])
    for i in range(1, 9):
        ws.append([f"rev_{i}", rev.get(i, "")])
    wb.save(str(path))


def _make_fasta(path: Path, records: list[tuple[str, str]]) -> None:
    """Write a FASTA with one or more records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for header, seq in records:
            fh.write(f">{header}\n{seq}\n")


# ---------------------------------------------------------------------------
# CDS that provides adequate flanking room on both sides of the gene.
#
# Layout:
#   - Total length: 1200 bp
#   - Gene region: [500, 800]
#   - Upstream flank available: 500 bp  (gene_start - flank_max = 500 - 400 = 100 >= 0)
#   - Downstream flank available: 400 bp (gene_end + flank_max = 800 + 400 = 1200 <= 1200)
#
# Sequence is a fixed mixed-composition string to give realistic Tm values.
# ---------------------------------------------------------------------------
_UNIT = "ATGCGTACGATCGTAGCTAGCTAGCATGCGTACGATCGTAGCTAGCTAGC"  # 50 bp
_CDS_1200 = (_UNIT * 24)[:1200]  # 1200 bp


def _make_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a minimal project tree and return (fasta, seeds, project_root)."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    fasta = project_root / "cds.fa"
    _make_fasta(fasta, [("egfp_cds", _CDS_1200)])
    seeds = project_root / "seeds.xlsx"
    _make_seeds_xlsx(seeds, _FWD_SEEDS, _REV_SEEDS)
    return fasta, seeds, project_root


# ---------------------------------------------------------------------------
# parse_barcode_seeds
# ---------------------------------------------------------------------------

class TestParseBarcodeSeeds:
    def test_happy_path(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "seeds.xlsx"
        _make_seeds_xlsx(xlsx, _FWD_SEEDS, _REV_SEEDS)
        result = parse_barcode_seeds(xlsx)
        assert len(result) == 20
        assert result["fwd_1"] == "TATCTGACCTT"
        assert result["rev_8"] == "AGAGTGCGGCT"

    def test_missing_fwd_seeds_raises(self, tmp_path: Path) -> None:
        # provide only 11 fwd seeds (missing fwd_12)
        fwd_incomplete = {k: v for k, v in _FWD_SEEDS.items() if k != 12}
        xlsx = tmp_path / "seeds_incomplete.xlsx"
        _make_seeds_xlsx(xlsx, fwd_incomplete, _REV_SEEDS)
        with pytest.raises(ValueError, match="Missing forward barcode seeds"):
            parse_barcode_seeds(xlsx)

    def test_duplicate_sequence_raises(self, tmp_path: Path) -> None:
        # Make fwd_2 share the same sequence as fwd_1
        fwd_dup = dict(_FWD_SEEDS)
        fwd_dup[2] = _FWD_SEEDS[1]
        xlsx = tmp_path / "seeds_dup.xlsx"
        _make_seeds_xlsx(xlsx, fwd_dup, _REV_SEEDS)
        with pytest.raises(ValueError, match="Duplicate seed sequence"):
            parse_barcode_seeds(xlsx)

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            parse_barcode_seeds(tmp_path / "nonexistent.xlsx")


# ---------------------------------------------------------------------------
# design_flanking_primers
# ---------------------------------------------------------------------------

class TestDesignFlankingPrimers:
    """
    CDS layout:
      total = 1200 bp, gene = [500, 800]
      upstream available: 500 bp (> flank_max=400)
      downstream available: 400 bp (== flank_max=400)
    """

    _PROFILE = get_profile("Q5")
    _GENE_START = 500
    _GENE_END = 800

    def test_happy_path_returns_lowercase(self) -> None:
        fwd, rev, warns = design_flanking_primers(
            _CDS_1200,
            gene_start=self._GENE_START,
            gene_end=self._GENE_END,
            profile=self._PROFILE,
        )
        assert fwd == fwd.lower(), "fwd primer must be lowercase"
        assert rev == rev.lower(), "rev primer must be lowercase"

    def test_happy_path_lengths_in_range(self) -> None:
        fwd, rev, warns = design_flanking_primers(
            _CDS_1200,
            gene_start=self._GENE_START,
            gene_end=self._GENE_END,
            profile=self._PROFILE,
            binding_min_len=18,
            binding_max_len=35,
        )
        assert 18 <= len(fwd) <= 35, f"fwd length {len(fwd)} out of [18, 35]"
        assert 18 <= len(rev) <= 35, f"rev length {len(rev)} out of [18, 35]"

    def test_tm_in_window_when_possible(self) -> None:
        """When a valid Tm window is achievable, warnings list should be empty."""
        fwd, rev, warns = design_flanking_primers(
            _CDS_1200,
            gene_start=self._GENE_START,
            gene_end=self._GENE_END,
            profile=self._PROFILE,
            tm_min=55.0,
            tm_max=68.0,
        )
        # If no warnings, primers are within the Tm window
        if not warns:
            fwd_tm = primer3.calc_tm(
                fwd.upper(),
                mv_conc=self._PROFILE.mv_conc,
                dv_conc=self._PROFILE.dv_conc,
                dntp_conc=self._PROFILE.dntp_conc,
                dna_conc=self._PROFILE.dna_conc,
            )
            rev_tm = primer3.calc_tm(
                rev.upper(),
                mv_conc=self._PROFILE.mv_conc,
                dv_conc=self._PROFILE.dv_conc,
                dntp_conc=self._PROFILE.dntp_conc,
                dna_conc=self._PROFILE.dna_conc,
            )
            assert 55.0 <= fwd_tm <= 68.0, f"fwd Tm {fwd_tm:.1f} outside [55, 68]"
            assert 55.0 <= rev_tm <= 68.0, f"rev Tm {rev_tm:.1f} outside [55, 68]"

    def test_gc_clamp_enforced(self) -> None:
        """With require_gc_clamp=True, the 3-prime base must be G or C."""
        fwd, rev, warns = design_flanking_primers(
            _CDS_1200,
            gene_start=self._GENE_START,
            gene_end=self._GENE_END,
            profile=self._PROFILE,
            require_gc_clamp=True,
        )
        # If a GC-clamped primer was found (no warning about gc_clamp), verify
        fwd_warned = any("require_gc_clamp=True" in w and "forward" in w.lower() for w in warns)
        rev_warned = any("require_gc_clamp=True" in w and "reverse" in w.lower() for w in warns)
        if not fwd_warned:
            assert fwd[-1].upper() in "GC", f"fwd primer {fwd!r} lacks GC clamp"
        if not rev_warned:
            assert rev[-1].upper() in "GC", f"rev primer {rev!r} lacks GC clamp"

    def test_impossible_tm_produces_warnings(self) -> None:
        """An impossible Tm window (e.g. tm_min=99.0) must produce non-empty warnings."""
        _fwd, _rev, warns = design_flanking_primers(
            _CDS_1200,
            gene_start=self._GENE_START,
            gene_end=self._GENE_END,
            profile=self._PROFILE,
            tm_min=99.0,
            tm_max=100.0,
        )
        assert len(warns) > 0, "Expected warnings when Tm window is unachievable"

    def test_gene_start_too_close_to_boundary_raises(self) -> None:
        """gene_start - flank_max < 0 must raise ValueError."""
        with pytest.raises(ValueError, match="too short upstream"):
            design_flanking_primers(
                _CDS_1200,
                gene_start=50,   # 50 - 400 = -350 < 0
                gene_end=800,
                profile=self._PROFILE,
            )

    def test_gene_end_too_close_to_boundary_raises(self) -> None:
        """gene_end + flank_max > len(cds_sequence) must raise ValueError."""
        with pytest.raises(ValueError, match="too short downstream"):
            design_flanking_primers(
                _CDS_1200,
                gene_start=500,
                gene_end=900,    # 900 + 400 = 1300 > 1200
                profile=self._PROFILE,
            )

    def test_gene_start_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="gene_start must be >= 0"):
            design_flanking_primers(
                _CDS_1200,
                gene_start=-1,
                gene_end=800,
                profile=self._PROFILE,
            )

    def test_gene_end_exceeds_seq_raises(self) -> None:
        with pytest.raises(ValueError, match="gene_end.*exceeds sequence length"):
            design_flanking_primers(
                _CDS_1200,
                gene_start=500,
                gene_end=1500,
                profile=self._PROFILE,
            )

    def test_start_equals_end_raises(self) -> None:
        with pytest.raises(ValueError, match="gene_start.*must be < gene_end"):
            design_flanking_primers(
                _CDS_1200,
                gene_start=500,
                gene_end=500,
                profile=self._PROFILE,
            )


# ---------------------------------------------------------------------------
# Circular topology: origin-wrapping search windows
# ---------------------------------------------------------------------------

_CDS_CIRCULAR_6494 = (_UNIT * 130)[:6494]  # matches the real reproduction plasmid length
_CDS_100 = (_UNIT * 2)[:100]  # 100 bp (must be >= 100 for a real 100 bp fixture)


class TestCircularSliceHelper:
    """Unit tests for the private modular-slice helper used by circular wrap."""

    def test_wraps_negative_start(self) -> None:
        from kuma_core.mame.ingest.barcode_package import _circular_slice

        seq = "ABCDEFGHIJ"  # len 10
        assert _circular_slice(seq, -3, 5, 10) == "HIJAB"

    def test_wraps_past_end(self) -> None:
        from kuma_core.mame.ingest.barcode_package import _circular_slice

        seq = "ABCDEFGHIJ"  # len 10
        assert _circular_slice(seq, 8, 4, 10) == "IJAB"

    def test_no_wrap_matches_plain_slice(self) -> None:
        from kuma_core.mame.ingest.barcode_package import _circular_slice

        seq = "ABCDEFGHIJ"
        assert _circular_slice(seq, 2, 4, 10) == seq[2:6]


class TestCircularTopology:
    """design_flanking_primers(topology="circular") allows origin-wrapping windows."""

    _PROFILE = get_profile("Q5")

    def test_forward_window_wraps_origin(self) -> None:
        """Reproduction case: gene_start=267 with flank_max=400 on a 6494 bp
        circular plasmid puts the forward window at [-133, 167), which must
        wrap instead of raising."""
        fwd, rev, warns = design_flanking_primers(
            _CDS_CIRCULAR_6494,
            gene_start=267,
            gene_end=1950,
            profile=self._PROFILE,
            topology="circular",
        )
        assert fwd and fwd == fwd.lower()
        assert rev and rev == rev.lower()
        assert 18 <= len(fwd) <= 35
        assert 18 <= len(rev) <= 35

    def test_reverse_window_wraps_origin(self) -> None:
        """gene_end=1100 with flank_max=400 on a 1200 bp circular sequence puts
        the reverse window end at 1500 (> seq_len=1200), which must wrap."""
        fwd, rev, warns = design_flanking_primers(
            _CDS_1200,
            gene_start=800,
            gene_end=1100,
            profile=self._PROFILE,
            topology="circular",
        )
        assert fwd and fwd == fwd.lower()
        assert rev and rev == rev.lower()
        assert 18 <= len(fwd) <= 35
        assert 18 <= len(rev) <= 35

    def test_linear_topology_still_raises_for_same_coordinates(self) -> None:
        """The same coordinates that succeed under circular topology must still
        raise the original error under (default) linear topology."""
        with pytest.raises(ValueError, match="too short upstream"):
            design_flanking_primers(
                _CDS_CIRCULAR_6494,
                gene_start=267,
                gene_end=1950,
                profile=self._PROFILE,
            )
        with pytest.raises(ValueError, match="too short downstream"):
            design_flanking_primers(
                _CDS_1200,
                gene_start=800,
                gene_end=1100,
                profile=self._PROFILE,
                topology="linear",
            )

    def test_degenerate_window_wider_than_sequence_raises(self) -> None:
        """flank_max - flank_min > seq_len must raise a clear error naming
        seq_len rather than emit a primer that reads bases twice."""
        with pytest.raises(ValueError, match=r"seq_len=100"):
            design_flanking_primers(
                _CDS_100,
                gene_start=10,
                gene_end=20,
                profile=self._PROFILE,
                flank_min=0,
                flank_max=150,
                topology="circular",
            )

    def test_degenerate_binding_length_longer_than_sequence_raises(self) -> None:
        """binding_max_len > seq_len must raise the same guard."""
        with pytest.raises(ValueError, match=r"seq_len=100"):
            design_flanking_primers(
                _CDS_100,
                gene_start=10,
                gene_end=20,
                profile=self._PROFILE,
                binding_min_len=18,
                binding_max_len=150,
                topology="circular",
            )

    def test_invalid_topology_literal_raises(self) -> None:
        with pytest.raises(ValueError, match="topology must be"):
            design_flanking_primers(
                _CDS_1200,
                gene_start=500,
                gene_end=800,
                profile=self._PROFILE,
                topology="mobius",
            )


# ---------------------------------------------------------------------------
# generate_mame_package (integration)
# ---------------------------------------------------------------------------

class TestGenerateMamePackage:
    def test_happy_path_row_count(self, tmp_path: Path) -> None:
        fasta, seeds, project_root = _make_project(tmp_path)
        output_dir = project_root / "design"

        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=output_dir,
            project_root=project_root,
            gene_name="egfp",
        )

        assert isinstance(result, MamePackageResult)
        assert result.barcodes_xlsx.exists()
        assert result.amplicon_fa.exists()
        assert result.sample_map_template.exists()
        assert result.context_json.exists()

        # barcodes_sequence.xlsx must have 1 header + 20 data rows = 21 rows
        wb = openpyxl.load_workbook(str(result.barcodes_xlsx), read_only=True)
        ws = wb.worksheets[0]
        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()
        # filter out fully-empty trailing rows openpyxl may append
        data_rows = [r for r in all_rows if any(c is not None for c in r)]
        assert len(data_rows) == 21  # 1 header + 20 seed rows

    def test_result_has_warnings_field(self, tmp_path: Path) -> None:
        """MamePackageResult.warnings must be present (list, possibly empty)."""
        fasta, seeds, project_root = _make_project(tmp_path)
        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=project_root / "design",
            project_root=project_root,
        )
        assert isinstance(result.warnings, list)

    def test_sequence_composition(self, tmp_path: Path) -> None:
        """Each barcode row sequence must start with the uppercase seed."""
        fasta, seeds, project_root = _make_project(tmp_path)
        output_dir = project_root / "design"

        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=output_dir,
            project_root=project_root,
        )

        wb = openpyxl.load_workbook(str(result.barcodes_xlsx), read_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        # Skip header
        data = [(str(r[0]), str(r[1])) for r in rows[1:] if r[0] is not None]
        assert len(data) == 20

        for i, (name, seq) in enumerate(data[:12]):
            seed_key = f"fwd_{i + 1}"
            expected_seed = _FWD_SEEDS[i + 1].upper()
            assert seq.startswith(expected_seed), (
                f"Row {name}: sequence {seq!r} should start with seed {expected_seed!r}"
            )

    def test_context_json_schema(self, tmp_path: Path) -> None:
        fasta, seeds, project_root = _make_project(tmp_path)
        output_dir = project_root / "design"

        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=output_dir,
            project_root=project_root,
        )

        ctx = json.loads(result.context_json.read_text(encoding="utf-8"))
        assert ctx["schema"] == 1
        assert "published_at" in ctx
        assert ctx["custom_barcodes_path"] == "design/barcodes_sequence.xlsx"
        assert ctx["sample_map_template_path"] == "design/sample_map_template.xlsx"

    def test_multi_sequence_fasta_warns(self, tmp_path: Path) -> None:
        """Multi-record FASTA must issue a UserWarning but not raise."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        fasta = project_root / "multi.fa"
        _make_fasta(fasta, [("seq1", _CDS_1200), ("seq2", _CDS_1200)])
        seeds = project_root / "seeds.xlsx"
        _make_seeds_xlsx(seeds, _FWD_SEEDS, _REV_SEEDS)
        output_dir = project_root / "design"

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = generate_mame_package(
                fasta_path=fasta,
                gene_start=500,
                gene_end=800,
                barcode_seeds_path=seeds,
                output_dir=output_dir,
                project_root=project_root,
            )

        assert result.barcodes_xlsx.exists()
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert any("2 sequences" in str(w.message) for w in user_warnings), (
            "Expected UserWarning about multiple sequences"
        )

    def test_amplicon_range_out_of_bounds_raises(self, tmp_path: Path) -> None:
        fasta, seeds, project_root = _make_project(tmp_path)
        output_dir = project_root / "design"
        with pytest.raises(ValueError):
            generate_mame_package(
                fasta_path=fasta,
                gene_start=500,
                gene_end=900,    # 900 + 400 = 1300 > 1200
                barcode_seeds_path=seeds,
                output_dir=output_dir,
                project_root=project_root,
            )

    def test_fasta_not_found_raises(self, tmp_path: Path) -> None:
        project_root = tmp_path / "project"
        project_root.mkdir()
        seeds = project_root / "seeds.xlsx"
        _make_seeds_xlsx(seeds, _FWD_SEEDS, _REV_SEEDS)
        with pytest.raises(FileNotFoundError):
            generate_mame_package(
                fasta_path=project_root / "missing.fa",
                gene_start=500,
                gene_end=800,
                barcode_seeds_path=seeds,
                output_dir=project_root / "design",
                project_root=project_root,
            )

    def test_gene_name_flows_to_row_names_and_filename(self, tmp_path: Path) -> None:
        """Custom gene_name must propagate to xlsx row names and amplicon filename.

        Round-trips through ``sort_barcode.parse_combinatorial_barcodes`` to
        verify the gene-agnostic reader still accepts non-ispS prefixes.
        """
        from kuma_core.mame.ingest.sort_barcode import parse_combinatorial_barcodes

        fasta, seeds, project_root = _make_project(tmp_path)
        output_dir = project_root / "design"

        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=output_dir,
            project_root=project_root,
            gene_name="MYGENE",
        )

        # Amplicon FASTA filename + header must use the gene name.
        assert result.amplicon_fa.name == "MYGENE_amplicon.fa"
        header = result.amplicon_fa.read_text(encoding="utf-8").splitlines()[0]
        assert header.startswith(">MYGENE_amplicon")

        # Barcode xlsx rows must use the sanitized gene prefix (mygene_f_*, mygene_r_*).
        wb = openpyxl.load_workbook(str(result.barcodes_xlsx), read_only=True)
        try:
            ws = wb.worksheets[0]
            rows = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
        names = [str(r[0]) for r in rows[1:] if r[0] is not None]
        assert "mygene_f_1" in names
        assert "mygene_r_8" in names
        assert not any(n.startswith("isps_") for n in names)

        # Reader must still parse the custom-prefix xlsx into the 96-well map.
        well_map = parse_combinatorial_barcodes(result.barcodes_xlsx)
        assert len(well_map) == 96
        assert "A01" in well_map and "H12" in well_map

    def test_empty_gene_name_raises(self, tmp_path: Path) -> None:
        """Empty gene_name must raise ValueError, never silently fall back."""
        fasta, seeds, project_root = _make_project(tmp_path)
        with pytest.raises(ValueError, match="sanitize"):
            generate_mame_package(
                fasta_path=fasta,
                gene_start=500,
                gene_end=800,
                barcode_seeds_path=seeds,
                output_dir=project_root / "design",
                project_root=project_root,
                gene_name="   ",
            )


# ---------------------------------------------------------------------------
# sample_map_template pre-fill (expected_mutations_path)
# ---------------------------------------------------------------------------

def _make_expected_mutations_xlsx(path: Path, mutants: list[tuple[str, int, str, str]]) -> None:
    """Write a minimal KURO results xlsx carrying an `expected_mutations` sheet.

    Header order must match kuma_core.mame.io.kuro_reader._EXPECTED_HEADER.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append([
        "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon",
        "mt_codon", "group_id", "primer_set_ref", "notation_type", "status",
    ])
    for mutant_id, position, wt_aa, mt_aa in mutants:
        ws.append([
            mutant_id, position, wt_aa, mt_aa, "", "", "", "", "substitution", "DESIGNED",
        ])
    wb.save(str(path))


def _read_sample_map(path: Path) -> list[tuple[str, str]]:
    """Return the template data rows as (sample_name, well) tuples."""
    wb = openpyxl.load_workbook(str(path), read_only=True)
    try:
        ws = wb.worksheets[0]
        rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
    finally:
        wb.close()
    assert [str(c) for c in rows[0][:2]] == ["sample_name", "well"]
    return [(str(r[0]), str(r[1])) for r in rows[1:]]


class TestSampleMapTemplatePrefill:
    def test_omitted_path_keeps_header_only_template(self, tmp_path: Path) -> None:
        """Default behaviour is unchanged: headers, no data rows."""
        fasta, seeds, project_root = _make_project(tmp_path)
        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=project_root / "design",
            project_root=project_root,
        )
        assert result.sample_map_prefilled_rows == 0
        assert _read_sample_map(result.sample_map_template) == []

    def test_prefill_places_mutants_column_major_with_wt_last(self, tmp_path: Path) -> None:
        """Rows follow build_draft_layout: column-major wells, WT after the last mutant."""
        fasta, seeds, project_root = _make_project(tmp_path)
        expected_xlsx = project_root / "kuro_results.xlsx"
        _make_expected_mutations_xlsx(
            expected_xlsx,
            [("V5F", 5, "V", "F"), ("K53N", 53, "K", "N"), ("A77G", 77, "A", "G")],
        )

        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=project_root / "design",
            project_root=project_root,
            expected_mutations_path=expected_xlsx,
        )

        rows = _read_sample_map(result.sample_map_template)
        assert rows == [
            ("V5F", "A1"),
            ("K53N", "B1"),
            ("A77G", "C1"),
            ("WT", "D1"),
        ]
        assert result.sample_map_prefilled_rows == 4

    def test_prefill_emits_verification_warning(self, tmp_path: Path) -> None:
        """The draft placement is an assumption, so the operator must be told."""
        fasta, seeds, project_root = _make_project(tmp_path)
        expected_xlsx = project_root / "kuro_results.xlsx"
        _make_expected_mutations_xlsx(expected_xlsx, [("V5F", 5, "V", "F")])

        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=project_root / "design",
            project_root=project_root,
            expected_mutations_path=expected_xlsx,
        )
        assert any("pre-filled" in w and "Verify" in w for w in result.warnings)

    def test_prefill_matches_build_draft_layout(self, tmp_path: Path) -> None:
        """Template and the mame.build_well_layout RPC must not drift apart."""
        from kuma_core.mame.io.kuro_reader import read_expected_mutations
        from kuma_core.mame.layout import build_draft_layout

        fasta, seeds, project_root = _make_project(tmp_path)
        expected_xlsx = project_root / "kuro_results.xlsx"
        _make_expected_mutations_xlsx(
            expected_xlsx, [(f"M{i}", i, "A", "G") for i in range(1, 13)]
        )

        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=project_root / "design",
            project_root=project_root,
            expected_mutations_path=expected_xlsx,
        )

        layout = build_draft_layout(read_expected_mutations(expected_xlsx))
        assert _read_sample_map(result.sample_map_template) == [
            (sample, well) for well, sample in layout.items()
        ]

    def test_missing_expected_file_raises(self, tmp_path: Path) -> None:
        """A supplied but unreadable path is an error, not a blank-template fallback."""
        fasta, seeds, project_root = _make_project(tmp_path)
        with pytest.raises((FileNotFoundError, ValueError)):
            generate_mame_package(
                fasta_path=fasta,
                gene_start=500,
                gene_end=800,
                barcode_seeds_path=seeds,
                output_dir=project_root / "design",
                project_root=project_root,
                expected_mutations_path=project_root / "does_not_exist.xlsx",
            )

    def test_expected_sheet_without_designed_rows_raises(self, tmp_path: Path) -> None:
        """An expected_mutations sheet with no DESIGNED rows must fail loudly."""
        fasta, seeds, project_root = _make_project(tmp_path)
        expected_xlsx = project_root / "kuro_results.xlsx"
        _make_expected_mutations_xlsx(expected_xlsx, [])
        with pytest.raises(ValueError, match="No DESIGNED expected mutations"):
            generate_mame_package(
                fasta_path=fasta,
                gene_start=500,
                gene_end=800,
                barcode_seeds_path=seeds,
                output_dir=project_root / "design",
                project_root=project_root,
                expected_mutations_path=expected_xlsx,
            )

    def test_existing_filled_template_is_preserved(self, tmp_path: Path) -> None:
        """Operator well assignments must survive a re-run of package generation."""
        fasta, seeds, project_root = _make_project(tmp_path)
        output_dir = project_root / "design"
        expected_xlsx = project_root / "kuro_results.xlsx"
        _make_expected_mutations_xlsx(expected_xlsx, [("V5F", 5, "V", "F")])

        # First run drafts the template; the operator then corrects a placement.
        first = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=output_dir,
            project_root=project_root,
            expected_mutations_path=expected_xlsx,
        )
        assert first.sample_map_preserved is False
        wb = openpyxl.load_workbook(str(first.sample_map_template))
        ws = wb.worksheets[0]
        ws["B2"] = "H12"  # operator moves V5F to the physical well
        wb.save(str(first.sample_map_template))
        wb.close()

        # Re-running (e.g. to adjust the gene range) must not discard that edit.
        second = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=790,
            barcode_seeds_path=seeds,
            output_dir=output_dir,
            project_root=project_root,
            expected_mutations_path=expected_xlsx,
        )
        assert second.sample_map_preserved is True
        assert second.sample_map_prefilled_rows == 0
        assert _read_sample_map(second.sample_map_template) == [("V5F", "H12"), ("WT", "B1")]
        assert any("left unchanged" in w for w in second.warnings)

    def test_header_only_template_is_replaced(self, tmp_path: Path) -> None:
        """A template holding no operator work carries no value worth preserving."""
        fasta, seeds, project_root = _make_project(tmp_path)
        output_dir = project_root / "design"
        expected_xlsx = project_root / "kuro_results.xlsx"
        _make_expected_mutations_xlsx(expected_xlsx, [("V5F", 5, "V", "F")])

        generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=output_dir,
            project_root=project_root,
        )  # header-only template

        result = generate_mame_package(
            fasta_path=fasta,
            gene_start=500,
            gene_end=800,
            barcode_seeds_path=seeds,
            output_dir=output_dir,
            project_root=project_root,
            expected_mutations_path=expected_xlsx,
        )
        assert result.sample_map_preserved is False
        assert _read_sample_map(result.sample_map_template) == [("V5F", "A1"), ("WT", "B1")]
