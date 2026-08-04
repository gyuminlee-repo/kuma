from __future__ import annotations

import gzip
from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.ingest.amplicon_reference import (
    check_coverage_reachable,
    resolve_amplicon_reference,
)

_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"
_COMPLEMENT = str.maketrans("ACGTacgt", "TGCAtgca")


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(_COMPLEMENT)[::-1]


def _write_barcodes(path: Path) -> None:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["target_f_1", "AATCCCACTAC" + _F_TAIL])
    sheet.append(["target_f_2", "TGAACTGAGCG" + _F_TAIL])
    sheet.append(["target_r_1", "CCCTATGACA" + _R_TAIL])
    sheet.append(["target_r_2", "TAATGGCAAG" + _R_TAIL])
    workbook.save(path)


def test_whole_plasmid_is_reduced_to_primer_bounded_amplicon(tmp_path: Path) -> None:
    coding = "ATG" + "GCT" * 19 + "TAA"
    amplicon = _F_TAIL + coding + _reverse_complement(_R_TAIL)
    plasmid = "G" * 80 + amplicon + "C" * 70
    reference = tmp_path / "plasmid.fa"
    reference.write_text(f">plasmid\n{plasmid}\n", encoding="utf-8")
    barcodes = tmp_path / "barcodes.xlsx"
    _write_barcodes(barcodes)

    resolution = resolve_amplicon_reference(reference, barcodes, tmp_path / "out")

    assert resolution.extracted is True
    assert resolution.span is not None
    assert resolution.span.start == 80
    assert resolution.span.end == 80 + len(amplicon)
    written = "".join(
        line.strip()
        for line in resolution.reference_fasta.read_text(encoding="utf-8").splitlines()
        if not line.startswith(">")
    )
    assert written == amplicon.upper()
    assert resolution.cds_start == len(_F_TAIL)
    assert resolution.cds_end == len(_F_TAIL) + len(coding)


def test_existing_amplicon_reference_is_left_unchanged(tmp_path: Path) -> None:
    reference = tmp_path / "amplicon.fa"
    reference.write_text(">amplicon\nATGGCTGCTTAA\n", encoding="utf-8")
    barcodes = tmp_path / "barcodes.xlsx"
    _write_barcodes(barcodes)

    resolution = resolve_amplicon_reference(reference, barcodes, tmp_path / "out")

    assert resolution.extracted is False
    assert resolution.reference_fasta == reference
    assert resolution.cds_start == 0
    assert resolution.cds_end == 0


# ---------------------------------------------------------------------------
# Coverage-reachability guard (silent whole-plasmid fallback)
# ---------------------------------------------------------------------------

_COVERAGE_FRACTION = 0.98


def _write_platemap_barcodes(path: Path) -> None:
    """A workbook whose rows do NOT follow the ``*_f_<n>`` / ``*_r_<n>`` rule."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["A1", "variant_001"])
    sheet.append(["A2", "variant_002"])
    workbook.save(path)


def _write_run(run_dir: Path, read_length: int, n_reads: int = 4) -> Path:
    barcode_dir = run_dir / "fastq_pass" / "barcode01"
    barcode_dir.mkdir(parents=True, exist_ok=True)
    fastq = barcode_dir / "reads.fastq.gz"
    with gzip.open(fastq, "wt") as handle:
        for index in range(n_reads):
            sequence = ("ACGT" * read_length)[:read_length]
            handle.write(f"@read{index}\n{sequence}\n+\n{'I' * read_length}\n")
    return run_dir


def test_whole_plasmid_reference_cannot_reach_the_coverage_gate(tmp_path: Path) -> None:
    reference = tmp_path / "plasmid.fa"
    reference.write_text(">plasmid\n" + "ACGT" * 225 + "\n", encoding="utf-8")
    run_dir = _write_run(tmp_path / "run", read_length=200)

    reachability = check_coverage_reachable(reference, run_dir, _COVERAGE_FRACTION)

    assert reachability.reference_length == 900
    assert reachability.required_span == 882
    assert reachability.sampled_reads == 4
    assert reachability.longest_read_length == 200
    assert reachability.reachable is False


def test_short_amplicon_reference_still_reaches_the_coverage_gate(tmp_path: Path) -> None:
    reference = tmp_path / "amplicon.fa"
    reference.write_text(">amplicon\n" + "ACGT" * 50 + "\n", encoding="utf-8")
    run_dir = _write_run(tmp_path / "run", read_length=200)

    reachability = check_coverage_reachable(reference, run_dir, _COVERAGE_FRACTION)

    assert reachability.reference_length == 200
    assert reachability.required_span == 196
    assert reachability.reachable is True


def test_reachability_does_not_block_when_no_reads_are_found(tmp_path: Path) -> None:
    reference = tmp_path / "plasmid.fa"
    reference.write_text(">plasmid\n" + "ACGT" * 225 + "\n", encoding="utf-8")
    empty_run = tmp_path / "empty_run"
    (empty_run / "fastq_pass").mkdir(parents=True)

    reachability = check_coverage_reachable(reference, empty_run, _COVERAGE_FRACTION)

    assert reachability.sampled_reads == 0
    assert reachability.reachable is True


def test_extracted_amplicon_reference_reaches_the_gate(tmp_path: Path) -> None:
    """A proper barcodes workbook extracts the amplicon, so the run proceeds."""
    coding = "ATG" + "GCT" * 55 + "TAA"
    amplicon = _F_TAIL + coding + _reverse_complement(_R_TAIL)
    plasmid = "G" * 400 + amplicon + "C" * 400
    reference = tmp_path / "plasmid.fa"
    reference.write_text(f">plasmid\n{plasmid}\n", encoding="utf-8")
    barcodes = tmp_path / "barcodes.xlsx"
    _write_barcodes(barcodes)
    run_dir = _write_run(tmp_path / "run", read_length=len(amplicon))

    resolution = resolve_amplicon_reference(reference, barcodes, tmp_path / "out")
    assert resolution.extracted is True

    whole = check_coverage_reachable(reference, run_dir, _COVERAGE_FRACTION)
    extracted = check_coverage_reachable(
        resolution.reference_fasta, run_dir, _COVERAGE_FRACTION
    )

    assert whole.reachable is False
    assert extracted.reachable is True


def test_analyze_refuses_a_whole_plasmid_reference_with_platemap_barcodes(
    tmp_path: Path,
) -> None:
    from sidecar_mame.handlers.analyze import handle_analyze

    reference = tmp_path / "plasmid.fa"
    reference.write_text(">plasmid\n" + "ACGT" * 1625 + "\n", encoding="utf-8")
    barcodes = tmp_path / "platemap.xlsx"
    _write_platemap_barcodes(barcodes)
    expected = tmp_path / "expected.xlsx"
    openpyxl.Workbook().save(expected)
    run_dir = _write_run(tmp_path / "run", read_length=1700)

    with pytest.raises(ValueError) as excinfo:
        handle_analyze(
            {
                "input_dir": str(run_dir),
                "reference": str(reference),
                "expected": str(expected),
                "output": str(tmp_path / "result.xlsx"),
                "custom_barcodes_xlsx": str(barcodes),
            }
        )

    message = str(excinfo.value)
    assert "shared primer tails could not be derived" in message
    assert "_f_<n>" in message
    assert "6500 bp" in message
    assert "0.98" in message
    assert "6370 bp" in message
    assert "1700 bp" in message
