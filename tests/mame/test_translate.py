"""Translate/diff unit tests (normal, silent, missense)."""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.models import BarcodeRecord
from kuma_core.mame.translate import extract_aa_changes, translate_and_diff


def _br(seq: str, size_kb: float = 60.0) -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq=seq,
        file_size_kb=size_kb,
        source_path=Path("/tmp/mock.fasta"),
    )


def test_translate_normal_passthrough(reference_seq: str, cds_params: dict[str, int]) -> None:
    """Identical query -> no AA changes, AA sequence length matches CDS / 3."""

    rec = _br(reference_seq)
    translated = translate_and_diff(
        record=rec,
        reference_seq=reference_seq,
        cds_start=cds_params["cds_start"],
        cds_end=cds_params["cds_end"],
    )
    assert translated.observed_aa_changes == []
    # Literal reference is 177 bp = 59 codons (58 AA + trailing stop).
    assert len(translated.aa_sequence) >= 50


def test_translate_silent_substitution(reference_seq: str, cds_params: dict[str, int]) -> None:
    """Synonymous codon swap: codon 2 GTG -> GTT (both Val) yields no AA diff."""

    # Codon 2 occupies ref[3:6] and is GTG (Val) in the literal reference.
    assert reference_seq[3:6] == "GTG"
    mutated = reference_seq[:3] + "GTT" + reference_seq[6:]
    rec = _br(mutated)
    translated = translate_and_diff(
        record=rec,
        reference_seq=reference_seq,
        cds_start=cds_params["cds_start"],
        cds_end=cds_params["cds_end"],
    )
    assert translated.observed_aa_changes == []


def test_translate_missense_v2f(reference_seq: str, cds_params: dict[str, int]) -> None:
    """Codon 2 GTG -> TTT = V2F substitution on the literal reference."""

    assert reference_seq[3:6] == "GTG"
    mutated = reference_seq[:3] + "TTT" + reference_seq[6:]
    rec = _br(mutated)
    translated = translate_and_diff(
        record=rec,
        reference_seq=reference_seq,
        cds_start=cds_params["cds_start"],
        cds_end=cds_params["cds_end"],
    )
    assert "V2F" in translated.observed_aa_changes


def test_extract_aa_changes_basic() -> None:
    assert extract_aa_changes("MVFK", "MVFK") == []
    assert extract_aa_changes("MFFK", "MVFK") == ["V2F"]
    assert extract_aa_changes("MV", "MVFK") == ["F3-", "K4-"]
