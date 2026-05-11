from __future__ import annotations

from pathlib import Path

from sidecar_mame.handlers.analyze import handle_validate_inputs


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
