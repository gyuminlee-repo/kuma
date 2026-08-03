"""Focused tests for scripts/validate_combinatorial_demux.py.

These tests exercise parser construction, CDS selection logic, and reference
FASTA extraction using purely synthetic data; no external files or network
access are required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the script importable from any working directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

from Bio.Seq import Seq
from Bio.SeqFeature import FeatureLocation, SeqFeature
from Bio.SeqRecord import SeqRecord

from scripts.validate_combinatorial_demux import (
    _cds_label,
    _format_candidates,
    build_parser,
    count_reads_in_fasta,
    extract_cds_reference,
    select_cds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(cds_list: list[dict]) -> SeqRecord:
    """Return a synthetic SeqRecord with CDS features built from *cds_list*.

    Each dict may contain: ``start``, ``end``, ``strand``, ``gene``,
    ``locus_tag``.
    """
    seq = Seq("ATGCATGCATGC" * 200)
    record = SeqRecord(seq, id="SYNTH001", name="SYNTH001")
    record.annotations["molecule_type"] = "DNA"
    for spec in cds_list:
        start = spec.get("start", 0)
        end = spec.get("end", 12)
        strand = spec.get("strand", 1)
        qualifiers: dict[str, list[str]] = {}
        if "gene" in spec:
            qualifiers["gene"] = [spec["gene"]]
        if "locus_tag" in spec:
            qualifiers["locus_tag"] = [spec["locus_tag"]]
        feature = SeqFeature(
            FeatureLocation(start, end, strand=strand),
            type="CDS",
            qualifiers=qualifiers,
        )
        record.features.append(feature)
    return record


# ---------------------------------------------------------------------------
# _cds_label
# ---------------------------------------------------------------------------


class TestCdsLabel:
    def test_gene_takes_priority_over_locus_tag(self):
        f = SeqFeature(
            FeatureLocation(0, 12),
            type="CDS",
            qualifiers={"gene": ["myGene"], "locus_tag": ["LT_001"]},
        )
        assert _cds_label(f) == "myGene"

    def test_locus_tag_fallback(self):
        f = SeqFeature(
            FeatureLocation(0, 12),
            type="CDS",
            qualifiers={"locus_tag": ["LT_001"]},
        )
        assert _cds_label(f) == "LT_001"

    def test_product_fallback(self):
        feature = SeqFeature(
            FeatureLocation(0, 12),
            type="CDS",
            qualifiers={"product": ["Target protein"]},
        )
        assert _cds_label(feature) == "Target_protein"

    def test_fallback_to_cds_string(self):
        f = SeqFeature(FeatureLocation(0, 12), type="CDS", qualifiers={})
        assert _cds_label(f) == "cds"

    def test_sanitizes_annotation_for_filename(self):
        feature = SeqFeature(
            FeatureLocation(0, 12),
            type="CDS",
            qualifiers={"gene": ["../Target protein"]},
        )
        assert _cds_label(feature) == "Target_protein"


# ---------------------------------------------------------------------------
# _format_candidates
# ---------------------------------------------------------------------------


class TestFormatCandidates:
    def test_returns_string_with_each_feature(self):
        record = _make_record(
            [
                {"start": 0, "end": 12, "gene": "geneA", "locus_tag": "lt1"},
                {"start": 12, "end": 24, "gene": "geneB", "locus_tag": "lt2"},
            ]
        )
        cds = [f for f in record.features if f.type == "CDS"]
        result = _format_candidates(cds)
        assert "geneA" in result
        assert "geneB" in result
        assert "lt1" in result
        assert "lt2" in result

    def test_empty_list_returns_none_marker(self):
        result = _format_candidates([])
        assert "(none)" in result


# ---------------------------------------------------------------------------
# select_cds — single CDS, no selector
# ---------------------------------------------------------------------------


class TestSelectCdsSingleNoSelector:
    def test_single_cds_succeeds(self):
        record = _make_record([{"start": 0, "end": 12, "gene": "IspS"}])
        feature = select_cds(record)
        assert feature.qualifiers["gene"] == ["IspS"]

    def test_zero_cds_exits(self):
        record = _make_record([])
        with pytest.raises(SystemExit):
            select_cds(record)

    def test_multiple_cds_exits_with_diagnostic(self, capsys):
        record = _make_record(
            [
                {"start": 0, "end": 12, "gene": "geneA"},
                {"start": 12, "end": 24, "gene": "geneB"},
            ]
        )
        with pytest.raises(SystemExit):
            select_cds(record)
        err = capsys.readouterr().err
        assert "geneA" in err or "2 CDS" in err


# ---------------------------------------------------------------------------
# select_cds — by gene
# ---------------------------------------------------------------------------


class TestSelectCdsByGene:
    def test_matching_gene_returns_feature(self):
        record = _make_record(
            [
                {"start": 0, "end": 12, "gene": "geneA"},
                {"start": 12, "end": 24, "gene": "geneB"},
            ]
        )
        feature = select_cds(record, gene="geneA")
        assert feature.qualifiers["gene"] == ["geneA"]

    def test_nonexistent_gene_exits(self, capsys):
        record = _make_record([{"start": 0, "end": 12, "gene": "geneA"}])
        with pytest.raises(SystemExit):
            select_cds(record, gene="nonexistent")
        err = capsys.readouterr().err
        assert "nonexistent" in err

    def test_ambiguous_gene_exits(self, capsys):
        """Two CDS features share the same gene name → must fail safely."""
        record = _make_record(
            [
                {"start": 0, "end": 12, "gene": "dupGene"},
                {"start": 12, "end": 24, "gene": "dupGene"},
            ]
        )
        with pytest.raises(SystemExit):
            select_cds(record, gene="dupGene")
        err = capsys.readouterr().err
        assert "dupGene" in err


# ---------------------------------------------------------------------------
# select_cds — by locus_tag
# ---------------------------------------------------------------------------


class TestSelectCdsByLocusTag:
    def test_matching_locus_tag_returns_feature(self):
        record = _make_record(
            [
                {"start": 0, "end": 12, "locus_tag": "LT_001"},
                {"start": 12, "end": 24, "locus_tag": "LT_002"},
            ]
        )
        feature = select_cds(record, locus_tag="LT_002")
        assert feature.qualifiers["locus_tag"] == ["LT_002"]

    def test_nonexistent_locus_tag_exits(self, capsys):
        record = _make_record([{"start": 0, "end": 12, "locus_tag": "LT_001"}])
        with pytest.raises(SystemExit):
            select_cds(record, locus_tag="MISSING")
        err = capsys.readouterr().err
        assert "MISSING" in err


# ---------------------------------------------------------------------------
# select_cds — combined selectors
# ---------------------------------------------------------------------------


class TestSelectCdsCombinedSelectors:
    def test_both_selectors_match_same_feature(self):
        record = _make_record(
            [
                {"start": 0, "end": 12, "gene": "geneA", "locus_tag": "lt_a"},
                {"start": 12, "end": 24, "gene": "geneB", "locus_tag": "lt_b"},
            ]
        )
        feature = select_cds(record, gene="geneA", locus_tag="lt_a")
        assert feature.qualifiers["gene"] == ["geneA"]

    def test_conflicting_selectors_exit(self):
        record = _make_record(
            [
                {"start": 0, "end": 12, "gene": "geneA", "locus_tag": "lt_a"},
                {"start": 12, "end": 24, "gene": "geneB", "locus_tag": "lt_b"},
            ]
        )
        with pytest.raises(SystemExit):
            select_cds(record, gene="geneA", locus_tag="lt_b")


# ---------------------------------------------------------------------------
# extract_cds_reference — integration with synthetic GenBank file
# ---------------------------------------------------------------------------


class TestExtractCdsReference:
    def _write_synthetic_gb(self, tmp_path: Path) -> Path:
        """Write a minimal GenBank file with two CDS features."""
        from Bio import SeqIO

        record = _make_record(
            [
                {"start": 0, "end": 12, "gene": "geneA", "locus_tag": "lt_a"},
                {"start": 12, "end": 24, "gene": "geneB", "locus_tag": "lt_b"},
            ]
        )
        gb_path = tmp_path / "synth.gb"
        with gb_path.open("w") as fh:
            SeqIO.write(record, fh, "genbank")
        return gb_path

    def test_extracts_correct_fasta_by_gene(self, tmp_path):
        gb_path = self._write_synthetic_gb(tmp_path)
        dest_dir = tmp_path / "ref"
        fasta = extract_cds_reference(gb_path, dest_dir, gene="geneA")
        assert fasta.exists()
        assert fasta.name == "geneA.fasta"
        content = fasta.read_text()
        assert content.startswith(">geneA")

    def test_existing_reference_is_refreshed_from_current_input(self, tmp_path):
        gb_path = self._write_synthetic_gb(tmp_path)
        dest_dir = tmp_path / "ref"
        fasta1 = extract_cds_reference(gb_path, dest_dir, gene="geneA")
        fasta1.write_text(">stale\nAAAA\n")

        fasta2 = extract_cds_reference(gb_path, dest_dir, gene="geneA")

        assert fasta2 == fasta1
        assert fasta2.read_text().startswith(">geneA\n")

    def test_fails_without_selector_when_multiple_cds(self, tmp_path):
        gb_path = self._write_synthetic_gb(tmp_path)
        dest_dir = tmp_path / "ref"
        with pytest.raises(SystemExit):
            extract_cds_reference(gb_path, dest_dir)

    def test_single_cds_succeeds_without_selector(self, tmp_path):
        from Bio import SeqIO

        record = _make_record([{"start": 0, "end": 12, "gene": "onlyGene"}])
        gb_path = tmp_path / "single.gb"
        with gb_path.open("w") as fh:
            SeqIO.write(record, fh, "genbank")

        dest_dir = tmp_path / "ref"
        fasta = extract_cds_reference(gb_path, dest_dir)
        assert fasta.name == "onlyGene.fasta"


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_required_args_accepted(self):
        p = build_parser()
        args = p.parse_args(
            [
                "--fastq-dir", "/tmp/fq",
                "--barcodes-xlsx", "/tmp/bc.xlsx",
                "--genbank", "/tmp/rec.gb",
            ]
        )
        assert args.fastq_dir == "/tmp/fq"
        assert args.barcodes_xlsx == "/tmp/bc.xlsx"
        assert args.genbank == "/tmp/rec.gb"
        assert args.output_dir is None
        assert args.reference_output_dir is None
        assert args.cds_gene is None
        assert args.cds_locus_tag is None

    def test_all_optional_args_parsed(self):
        p = build_parser()
        args = p.parse_args(
            [
                "--fastq-dir", "/tmp/fq",
                "--barcodes-xlsx", "/tmp/bc.xlsx",
                "--genbank", "/tmp/rec.gb",
                "--output-dir", "/tmp/out",
                "--reference-output-dir", "/tmp/ref",
                "--cds-gene", "MyGene",
                "--cds-locus-tag", "LT_999",
            ]
        )
        assert args.output_dir == "/tmp/out"
        assert args.reference_output_dir == "/tmp/ref"
        assert args.cds_gene == "MyGene"
        assert args.cds_locus_tag == "LT_999"

    def test_missing_required_arg_exits(self):
        p = build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["--fastq-dir", "/tmp/fq"])


# ---------------------------------------------------------------------------
# count_reads_in_fasta
# ---------------------------------------------------------------------------


class TestCountReadsInFasta:
    def test_counts_header_lines(self, tmp_path):
        fasta = tmp_path / "seqs.fasta"
        fasta.write_text(">seq1\nATGC\n>seq2\nGCTA\n>seq3\nTTTT\n")
        assert count_reads_in_fasta(fasta) == 3

    def test_empty_file_returns_zero(self, tmp_path):
        fasta = tmp_path / "empty.fasta"
        fasta.write_text("")
        assert count_reads_in_fasta(fasta) == 0

    def test_no_header_returns_zero(self, tmp_path):
        fasta = tmp_path / "noheader.fasta"
        fasta.write_text("ATGCATGC\n")
        assert count_reads_in_fasta(fasta) == 0
