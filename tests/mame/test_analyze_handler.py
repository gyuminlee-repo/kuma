from __future__ import annotations

from pathlib import Path

from sidecar_mame.handlers.analyze import _write_reference_fasta, handle_validate_inputs


REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_GBK = REPO_ROOT / "src-tauri" / "samples" / "sample_plasmid.gb"


def test_validate_inputs_defaults_zero_cds_end_to_reference_length(
    mock_fasta_dir: Path,
    reference_fasta_path: Path,
    kuro_xlsx_path: Path,
) -> None:
    result = handle_validate_inputs(
        {
            "input_dir": str(mock_fasta_dir),
            "reference": str(reference_fasta_path),
            "expected": str(kuro_xlsx_path),
            "cds_end": 0,
        }
    )

    assert result == {"valid": True, "errors": []}


def test_validate_inputs_accepts_genbank_reference(
    mock_fasta_dir: Path,
    kuro_xlsx_path: Path,
) -> None:
    result = handle_validate_inputs(
        {
            "input_dir": str(mock_fasta_dir),
            "reference": str(SAMPLE_GBK),
            "expected": str(kuro_xlsx_path),
            "cds_end": 0,
        }
    )

    assert result == {"valid": True, "errors": []}


def test_write_reference_fasta_materializes_genbank(tmp_path: Path) -> None:
    fasta_path = _write_reference_fasta(SAMPLE_GBK, tmp_path)
    text = fasta_path.read_text(encoding="utf-8")

    assert fasta_path.suffix == ".fa"
    assert text.startswith(">sample_plasmid")
    assert "ATG" in text
