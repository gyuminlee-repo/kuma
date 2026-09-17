import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import load_workbook

from kuma_core.mame.cli import _dump_verdicts
from kuma_core.mame.export import WellMapper, write_excel
from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)


@pytest.mark.parametrize("scenario", ["current", "legacy", "multiple", "ambiguous"])
def test_cli_roundtrip_preserves_selected_well(tmp_path: Path, scenario: str) -> None:
    barcode = BarcodeRecord(
        native_barcode="NB01", custom_barcode="1_1", consensus_seq="ATG",
        file_size_kb=60.0, source_path=tmp_path / "input.fasta",
    )
    translated = TranslatedRecord(
        barcode=barcode, aa_sequence="M", observed_nt_changes=[], observed_aa_changes=["F89W"],
    )
    verdict = VerdictRecord(
        translated=translated, expected_mutations=["F89W"], verdict=VerdictClass.PASS, verdict_notes="",
    )
    replicate = ReplicateResult(
        mutant_id="F89W", plate_verdicts={"NB01": verdict}, selected_plate="NB01",
        selection_reason="audit", failed=False,
    )
    first = tmp_path / "first.xlsx"
    second = tmp_path / "second.xlsx"
    saved = tmp_path / "verdicts.json"
    verdicts = [verdict]
    if scenario in {"multiple", "ambiguous"}:
        verdicts.append(replace(verdict, translated=replace(
            translated, barcode=replace(barcode, custom_barcode="2_1"),
        )))
    write_excel(verdicts, [replicate], first, WellMapper(), mode="amplicon")
    _dump_verdicts(verdicts, [replicate], saved)
    if scenario in {"legacy", "ambiguous"}:
        payload = json.loads(saved.read_text())
        payload["replicates"][0].pop("plate_barcodes", None)
        saved.write_text(json.dumps(payload))
    exported = subprocess.run(
        [sys.executable, "-m", "kuma_core.mame.cli", "export",
         "--verdict-json", str(saved), "--output", str(second)],
        capture_output=True, text=True, check=False,
    )
    if scenario == "ambiguous":
        assert exported.returncode != 0
        assert "Cannot uniquely restore" in exported.stderr
        assert not second.exists()
        return
    assert exported.returncode == 0, exported.stderr
    first_book = load_workbook(first)
    second_book = load_workbook(second)
    try:
        before = list(first_book["Final"].values)[1]
        after = list(second_book["Final"].values)[1]
        print("A1 before", before, "A1 after", after)
        assert before[3] == "F89W"
        assert after == before, "CLI re-export must preserve the selected well and verdict"
    finally:
        first_book.close()
        second_book.close()


def test_cli_help_and_invalid_input(tmp_path: Path) -> None:
    command = [sys.executable, "-m", "kuma_core.mame.cli"]
    help_result = subprocess.run(command + ["--help"], capture_output=True, text=True, check=False)
    assert help_result.returncode == 0
    assert "export" in help_result.stdout
    output = tmp_path / "invalid.xlsx"
    invalid = subprocess.run(
        command + ["export", "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert invalid.returncode == 2
    assert not output.exists()
