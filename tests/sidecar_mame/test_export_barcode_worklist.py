"""``mame.export_barcode_worklist``, end to end from the two workbooks.

What is pinned here is the join, not the arithmetic: the pairing itself is
covered in ``tests/mame/test_barcode_worklist.py``. This asks whether the sheet
describes the plate the RUN would score, which is the only reason to compute it
in the sidecar rather than in the frontend. So the selection is applied through
the same ``apply_well_selection`` the run uses, and the fixture selects wells
that a re-seating rule would have filled differently.
"""

from pathlib import Path

import openpyxl
import pytest

from sidecar_mame.dispatcher import _METHODS
from sidecar_mame.handlers.barcode_worklist import handle_export_barcode_worklist


def _expected(dest: Path, mutants: int) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append(["mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
               "group_id", "primer_set_ref", "notation_type", "status"])
    for index in range(mutants):
        position = index + 2
        mutant_id = f"G{position}A"
        ws.append([mutant_id, position, "G", "A", "GGG", "GCG", "", mutant_id,
                   "substitution", "DESIGNED"])
    wb.save(dest)
    return dest


def _barcodes(dest: Path) -> Path:
    """A barcode workbook shaped the way the package generator writes one."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["name", "sequence"])
    tail = "GGGGGGGGGGGGGGGGGGGG"
    for i in range(1, 13):
        ws.append([f"ispS_f_{i}", f"{'ACGTACGTAC'}{i:02d}{tail}"])
    for i in range(1, 9):
        ws.append([f"ispS_r_{i}", f"{'TGCATGCATG'}{i:02d}{tail}"])
    wb.save(dest)
    return dest


def test_the_method_is_registered_under_the_name_the_frontend_sends() -> None:
    """A handler no dispatcher entry reaches answers -32601 and nothing else."""
    assert _METHODS["mame.export_barcode_worklist"] is handle_export_barcode_worklist


def test_the_sheet_names_the_wells_the_run_would_score(tmp_path: Path) -> None:
    """Selection applied through the run rule, so no well is invented.

    Four mutants draft onto A1..D1 and the control onto H12. Declaring A1, C1
    and H12 keeps those three where they are. Under the re-seating rule this
    replaced, the same declaration would have put the first three occupants on
    them instead, so the samples discriminate between the two rules.
    """
    expected = _expected(tmp_path / "expected.xlsx", 4)
    output = tmp_path / "out" / "worklist.csv"

    result = handle_export_barcode_worklist({
        "expected_mutations_xlsx": str(expected),
        "custom_barcodes_xlsx": str(_barcodes(tmp_path / "barcodes.xlsx")),
        "selected_wells": ["A1", "C1", "H12"],
        "output_path": str(output),
    })

    assert result["rows"] == 3
    lines = Path(result["output_path"]).read_text(encoding="utf-8").splitlines()
    # Names arrive lower-cased, which is what `load_barcode_prefixes` does to
    # every name it reads. Written as it comes rather than re-cased here: the
    # workbook is the one place a seed is named, and a second normalisation
    # would be a second answer to what a primer is called.
    assert lines[1].startswith("A1,G2A,1_1,1,isps_r_1,1,isps_f_1")
    assert lines[2].startswith("C1,G4A,3_1,3,isps_r_3,1,isps_f_1")
    # Four mutants fill A1..D1, so the control is in H12, and it is barcoded
    # like any other well because it is sequenced like one.
    assert lines[3].startswith("H12,WT,8_12,8,isps_r_8,12,isps_f_12")
    # Two columns of the plate now that the control sits in the last well.
    assert result["forward_indices"] == [1, 12]
    assert result["reverse_indices"] == [1, 3, 8]
    assert result["missing_seeds"] == []
    # The same statement the review screen makes, so the two cannot disagree.
    assert result["excluded_occupants"] == {"B1": "G3A", "D1": "G5A"}


def test_the_pairing_is_written_without_a_barcode_workbook(tmp_path: Path) -> None:
    """It is a fact about the plate, so only the names are lost."""
    expected = _expected(tmp_path / "expected.xlsx", 1)
    output = tmp_path / "worklist.csv"

    result = handle_export_barcode_worklist({
        "expected_mutations_xlsx": str(expected),
        "output_path": str(output),
    })

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[1] == "A1,G2A,1_1,1,,1,"
    # The control takes the last well by default since 2026-08-18.
    assert lines[2] == "H12,WT,8_12,8,,12,"
    assert result["rows"] == 2


def test_an_empty_declaration_is_refused_rather_than_written(tmp_path: Path) -> None:
    """A campaign with no wells uses no barcodes, so there is nothing to write."""
    expected = _expected(tmp_path / "expected.xlsx", 1)

    with pytest.raises(ValueError, match="selected_wells is empty"):
        handle_export_barcode_worklist({
            "expected_mutations_xlsx": str(expected),
            "selected_wells": [],
            "output_path": str(tmp_path / "worklist.csv"),
        })

    assert not (tmp_path / "worklist.csv").exists()


def test_a_campaign_that_does_not_fit_one_plate_is_refused(tmp_path: Path) -> None:
    """No layout was drafted, so there is no pairing to state."""
    expected = _expected(tmp_path / "expected.xlsx", 96)

    with pytest.raises(ValueError, match="do not fit one plate"):
        handle_export_barcode_worklist({
            "expected_mutations_xlsx": str(expected),
            "output_path": str(tmp_path / "worklist.csv"),
        })
