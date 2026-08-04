from __future__ import annotations

from pathlib import Path

import openpyxl

from kuma_core.mame.ingest.amplicon_reference import resolve_amplicon_reference

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
