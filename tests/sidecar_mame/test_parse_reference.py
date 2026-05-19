"""Tests for ``mame.ingest.parse_reference`` JSON-RPC handler."""

from __future__ import annotations

from pathlib import Path

import pytest

from sidecar_mame.handlers.ingest import handle_parse_reference


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_GBK = REPO_ROOT / "src-tauri" / "samples" / "sample_plasmid.gb"
SAMPLE_FASTA = REPO_ROOT / "tests" / "mame" / "fixtures" / "reference.fasta"


def test_parse_reference_genbank_returns_cds_candidates() -> None:
    if not SAMPLE_GBK.exists():
        pytest.skip(f"GenBank fixture not present: {SAMPLE_GBK}")
    result = handle_parse_reference({"path": str(SAMPLE_GBK)})

    assert result["format"] == "genbank"
    assert result["sequence_length"] > 0
    assert isinstance(result["cds_candidates"], list)
    assert len(result["cds_candidates"]) >= 1
    first = result["cds_candidates"][0]
    for key in ("start", "end", "label", "aa_length", "source"):
        assert key in first, f"missing key {key!r} in candidate"
    assert first["end"] > first["start"]
    assert first["aa_length"] > 0


def test_parse_reference_fasta_returns_empty_candidates() -> None:
    if not SAMPLE_FASTA.exists():
        pytest.skip(f"FASTA fixture not present: {SAMPLE_FASTA}")
    result = handle_parse_reference({"path": str(SAMPLE_FASTA)})

    assert result["format"] == "fasta"
    assert result["sequence_length"] > 0
    # Plain FASTA carries no annotated CDS features; UI falls back to manual.
    assert result["cds_candidates"] == []


def test_parse_reference_missing_path_raises() -> None:
    with pytest.raises(ValueError):
        handle_parse_reference({})


def test_parse_reference_unknown_extension_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "not_a_sequence.txt"
    bogus.write_text("not a sequence file")
    with pytest.raises(Exception):
        handle_parse_reference({"path": str(bogus)})
