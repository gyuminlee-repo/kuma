"""End-to-end CLI smoke tests (analyze / translate / export)."""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl

from kuma_core.mame.cli import main as cli_main


def test_analyze_help_exits_zero(capsys) -> None:
    try:
        cli_main(["analyze", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    out = capsys.readouterr().out
    assert "analyze" in out.lower() or "input-dir" in out.lower()


def test_analyze_end_to_end_smoke(
    tmp_path: Path,
    mock_fasta_dir: Path,
    reference_fasta_path: Path,
    kuro_xlsx_path: Path,
) -> None:
    out = tmp_path / "analysis.xlsx"
    rc = cli_main(
        [
            "analyze",
            "--input-dir",
            str(mock_fasta_dir),
            "--reference",
            str(reference_fasta_path),
            "--expected",
            str(kuro_xlsx_path),
            "--output",
            str(out),
            "--mode",
            "amplicon",
            "--cds-start",
            "0",
            "--cds-end",
            "210",
        ]
    )
    assert rc == 0
    assert out.exists()

    wb = openpyxl.load_workbook(out)
    assert {"NB01", "NB02", "NB03", "Final"}.issubset(set(wb.sheetnames))


def test_translate_and_export_roundtrip(
    tmp_path: Path,
    mock_fasta_dir: Path,
    reference_fasta_path: Path,
    kuro_xlsx_path: Path,
) -> None:
    # Run analyze to produce a sidecar verdicts JSON then re-export from it.
    out = tmp_path / "analysis.xlsx"
    assert (
        cli_main(
            [
                "analyze",
                "--input-dir",
                str(mock_fasta_dir),
                "--reference",
                str(reference_fasta_path),
                "--expected",
                str(kuro_xlsx_path),
                "--output",
                str(out),
                "--cds-end",
                "210",
            ]
        )
        == 0
    )
    side = out.with_suffix(".verdicts.json")
    assert side.exists()

    reexport = tmp_path / "reformatted.xlsx"
    assert (
        cli_main(
            [
                "export",
                "--verdict-json",
                str(side),
                "--output",
                str(reexport),
            ]
        )
        == 0
    )
    assert reexport.exists()

    # Translate subcommand JSON dump.
    translate_out = tmp_path / "translated.json"
    assert (
        cli_main(
            [
                "translate",
                "--input-dir",
                str(mock_fasta_dir),
                "--reference",
                str(reference_fasta_path),
                "--cds-end",
                "210",
                "--output-json",
                str(translate_out),
            ]
        )
        == 0
    )
    data = json.loads(translate_out.read_text())
    assert len(data) == 12
