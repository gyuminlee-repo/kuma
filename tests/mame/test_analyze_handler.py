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


def _plate_workbook(
    path: Path,
    plate_rows: list[tuple[str, str]],
    expected_ids: list[str],
    *,
    with_plate_sheet: bool = True,
) -> Path:
    """A KURO-shaped export: a primer plate sheet plus ``expected_mutations``."""
    from openpyxl import Workbook

    wb = Workbook()
    first = wb.worksheets[0]
    if with_plate_sheet:
        first.title = "Fwd List"
        first.append(["Well", "Primer Name", "Mutation"])
        for well, mutation in plate_rows:
            first.append([well, f"{mutation}_F", mutation])
    else:
        first.title = "Sheet1"
    strict = wb.create_sheet("expected_mutations")
    # The full ten-column header, not an abbreviation of it. ``validate_inputs``
    # now reads the workbook the way the run will, so a sheet the strict reader
    # would reject can no longer pass validation and fail at analyze time.
    strict.append(
        [
            "mutant_id",
            "position",
            "wt_aa",
            "mt_aa",
            "wt_codon",
            "mt_codon",
            "group_id",
            "primer_set_ref",
            "notation_type",
            "status",
        ]
    )
    for mutation in expected_ids:
        strict.append(
            [
                mutation,
                int(mutation[1:-1]),
                mutation[0],
                mutation[-1],
                "",
                "",
                "",
                "",
                "",
                "DESIGNED",
            ]
        )
    wb.save(path)
    return path


def _validate(expected: Path, mock_fasta_dir: Path, reference: Path, **extra) -> dict:
    return handle_validate_inputs(
        {
            "input_dir": str(mock_fasta_dir),
            "reference": str(reference),
            "expected": str(expected),
            "cds_end": 0,
            **extra,
        }
    )


class TestPlateOrderFinding:
    """A workbook that disagrees with itself fails validation."""

    def test_a_mismatch_fails_the_validation(
        self, tmp_path: Path, mock_fasta_dir: Path, reference_fasta_path: Path
    ) -> None:
        """The expected sheet and the plate sheet cannot both be the plate."""
        expected = _plate_workbook(
            tmp_path / "reordered.xlsx",
            [("A1", "S11I"), ("B1", "S22T")],
            ["S22T", "S11I"],
        )

        result = _validate(expected, mock_fasta_dir, reference_fasta_path)

        assert result["valid"] is False
        # The error names both sheets, so the operator knows which file to fix
        # rather than which setting to hunt for.
        assert any(
            "Fwd List" in message and "expected_mutations" in message
            for message in result["errors"]
        )
        finding = result["plate_order"]
        assert finding["severity"] == "blocking"
        assert finding["mismatched"] is True
        assert finding["plate_sheet"] == "Fwd List"
        assert finding["examples"][0] == {
            "well": "A1",
            "plate": "S11I",
            "expected": "S22T",
        }

    def test_a_supplied_sample_map_does_not_soften_it(
        self, tmp_path: Path, mock_fasta_dir: Path, reference_fasta_path: Path
    ) -> None:
        """A sample map places wells; it does not say which plate was pipetted.

        This was graded ``info`` and left the run enabled until 2026-08-05. The
        verdicts were then scored against whichever of the workbook's two plates
        the sample map happened to agree with, and nothing checked that it did.
        """
        expected = _plate_workbook(
            tmp_path / "reordered2.xlsx",
            [("A1", "S11I"), ("B1", "S22T")],
            ["S22T", "S11I"],
        )

        result = _validate(
            expected,
            mock_fasta_dir,
            reference_fasta_path,
            sample_map_xlsx=str(expected),
        )

        assert result["plate_order"]["severity"] == "blocking"
        assert result["valid"] is False

    def test_an_explicit_well_layout_does_not_soften_it_either(
        self, tmp_path: Path, mock_fasta_dir: Path, reference_fasta_path: Path
    ) -> None:
        expected = _plate_workbook(
            tmp_path / "reordered3.xlsx",
            [("A1", "S11I"), ("B1", "S22T")],
            ["S22T", "S11I"],
        )

        result = _validate(
            expected,
            mock_fasta_dir,
            reference_fasta_path,
            well_layout={"A1": "S22T"},
        )

        assert result["plate_order"]["severity"] == "blocking"
        assert result["valid"] is False

    def test_missing_mutants_are_listed(
        self, tmp_path: Path, mock_fasta_dir: Path, reference_fasta_path: Path
    ) -> None:
        expected = _plate_workbook(
            tmp_path / "short.xlsx",
            [("A1", "S11I"), ("B1", "S22T")],
            ["S11I"],
        )

        finding = _validate(expected, mock_fasta_dir, reference_fasta_path)[
            "plate_order"
        ]

        assert finding["missing_from_expected"] == ["S22T"]

    def test_an_agreeing_workbook_says_nothing(
        self, tmp_path: Path, mock_fasta_dir: Path, reference_fasta_path: Path
    ) -> None:
        expected = _plate_workbook(
            tmp_path / "ok.xlsx",
            [("A1", "S11I"), ("B1", "S22T")],
            ["S11I", "S22T"],
        )

        assert _validate(expected, mock_fasta_dir, reference_fasta_path) == {
            "valid": True,
            "errors": [],
        }

    def test_a_workbook_with_no_plate_sheet_says_nothing(
        self, tmp_path: Path, mock_fasta_dir: Path, reference_fasta_path: Path
    ) -> None:
        """Nothing to compare is not a problem to invent."""
        expected = _plate_workbook(
            tmp_path / "plain.xlsx",
            [],
            ["S11I", "S22T"],
            with_plate_sheet=False,
        )

        assert _validate(expected, mock_fasta_dir, reference_fasta_path) == {
            "valid": True,
            "errors": [],
        }


def test_write_reference_fasta_materializes_genbank(tmp_path: Path) -> None:
    fasta_path = _write_reference_fasta(SAMPLE_GBK, tmp_path)
    text = fasta_path.read_text(encoding="utf-8")

    assert fasta_path.suffix == ".fa"
    assert text.startswith(">sample_plasmid")
    assert "ATG" in text
