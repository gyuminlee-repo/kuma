"""Export tests: well mapping, color rules, failed-well behavior, reference sheets, Janus."""

from __future__ import annotations

import csv
from pathlib import Path

import openpyxl

from kuma_core.mame.export import (
    WellMapper,
    export_mame_janus_csv,
    export_mame_janus_xlsx,
    seq_to_well,
    write_excel,
)
from kuma_core.mame.export.excel_writer import (
    _SHEET1_HEADER,
    FAILED_FILL,
    VERDICT_FILL,
)
from kuma_core.mame.export.janus_mapping import _JANUS_HEADER
from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)


def test_seq_to_well_column_major() -> None:
    assert seq_to_well(1) == "A1"
    assert seq_to_well(2) == "B1"
    assert seq_to_well(8) == "H1"
    assert seq_to_well(9) == "A2"
    assert seq_to_well(96) == "H12"


def test_well_mapper_roundtrip() -> None:
    mapper = WellMapper()
    for seq in (1, 2, 8, 9, 17, 96):
        well = mapper.seq_to_well(seq)
        assert mapper.well_to_seq(well) == seq


def _make_verdict(
    nb: str,
    custom: str,
    verdict: VerdictClass,
    size_kb: float = 60.0,
) -> VerdictRecord:
    barcode = BarcodeRecord(
        native_barcode=nb,
        custom_barcode=custom,
        consensus_seq="",
        file_size_kb=size_kb,
        source_path=Path("/tmp/mock.fasta"),
    )
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=[],
        observed_aa_changes=[],
    )
    return VerdictRecord(
        translated=translated,
        expected_mutations=[],
        verdict=verdict,
        verdict_notes="",
    )


def test_excel_sheet_colors(tmp_path: Path) -> None:
    verdicts = [
        _make_verdict("NB01", "1_1", VerdictClass.PASS),
        _make_verdict("NB01", "1_2", VerdictClass.AMBIGUOUS),
        _make_verdict("NB01", "1_3", VerdictClass.FRAMESHIFT),
        _make_verdict("NB01", "1_4", VerdictClass.MANY),
        _make_verdict("NB02", "1_1", VerdictClass.LOWDEPTH, size_kb=5.0),
    ]
    out = tmp_path / "out.xlsx"
    write_excel(
        verdict_records=verdicts,
        replicate_results=[],
        output_path=out,
    )
    wb = openpyxl.load_workbook(out)
    assert set(_SHEET1_HEADER).issubset({c.value for c in wb["NB01"][1]})

    # Look up each verdict row in NB01 / NB02 and confirm fill color.
    expected_fills = {
        "1_1": VERDICT_FILL[VerdictClass.PASS],
        "1_2": VERDICT_FILL[VerdictClass.AMBIGUOUS],
        "1_3": VERDICT_FILL[VerdictClass.FRAMESHIFT],
        "1_4": VERDICT_FILL[VerdictClass.MANY],
    }
    ws = wb["NB01"]
    header = [c.value for c in ws[1]]
    custom_col = header.index("custom_barcode") + 1
    for row in ws.iter_rows(min_row=2):
        label = row[custom_col - 1].value
        if label in expected_fills:
            fg = row[0].fill.fgColor.rgb or ""
            assert fg.endswith(expected_fills[label])


def test_excel_failed_well(tmp_path: Path) -> None:
    # One replicate result that failed -> appears with FAILED and red fill.
    plate_verdicts = {
        "NB01": _make_verdict("NB01", "1_1", VerdictClass.WRONG_AA),
    }
    rr = ReplicateResult(
        mutant_id="N63F",
        plate_verdicts=plate_verdicts,
        selected_plate=None,
        selection_reason="all fail",
        failed=True,
    )
    out = tmp_path / "failed.xlsx"
    write_excel(
        verdict_records=list(plate_verdicts.values()),
        replicate_results=[rr],
        output_path=out,
    )
    wb = openpyxl.load_workbook(out)
    ws = wb["Final"]

    found_failed = False
    for row in ws.iter_rows(min_row=2):
        values = [c.value for c in row]
        if "FAILED" in values:
            found_failed = True
            fg = row[1].fill.fgColor.rgb or ""
            assert fg.endswith(FAILED_FILL)
            break
    assert found_failed, "no FAILED row found in Final sheet"


# ---------------------------------------------------------------------------
# Reference-format sheets (G7 + G2)
# ---------------------------------------------------------------------------


def _make_replicate(
    mutant_id: str,
    nb: str,
    custom: str,
    verdict: VerdictClass = VerdictClass.PASS,
    size_kb: float = 80.0,
) -> ReplicateResult:
    vr = _make_verdict(nb, custom, verdict, size_kb=size_kb)
    return ReplicateResult(
        mutant_id=mutant_id,
        plate_verdicts={nb: vr},
        selected_plate=nb,
        selection_reason="pass",
        failed=False,
    )


def test_reference_sheets_present(tmp_path: Path) -> None:
    """write_excel must include 'NGS 결과' and 'Final (matrix)' sheets."""
    vr = _make_verdict("NB01", "1_1", VerdictClass.PASS)
    rr = _make_replicate("V5F", "NB01", "1_1")
    out = tmp_path / "ref.xlsx"
    write_excel(
        verdict_records=[vr],
        replicate_results=[rr],
        output_path=out,
    )
    wb = openpyxl.load_workbook(out)
    assert "NGS 결과" in wb.sheetnames, "NGS 결과 sheet missing"
    assert "Final (matrix)" in wb.sheetnames, "Final (matrix) sheet missing"
    # Legacy sheets preserved.
    assert "NB01" in wb.sheetnames
    assert "Final" in wb.sheetnames


def test_ngs_result_sheet_header(tmp_path: Path) -> None:
    """NGS 결과 sheet row-1 must match _NGS_RESULT_HEADER exactly."""
    from kuma_core.mame.export.excel_writer import _NGS_RESULT_HEADER

    vr = _make_verdict("NB01", "1_1", VerdictClass.PASS)
    rr = _make_replicate("V5F", "NB01", "1_1")
    out = tmp_path / "ngs.xlsx"
    write_excel(verdict_records=[vr], replicate_results=[rr], output_path=out)
    wb = openpyxl.load_workbook(out)
    ws = wb["NGS 결과"]
    actual_header = [c.value for c in ws[1]]
    assert actual_header == _NGS_RESULT_HEADER


def test_final_matrix_sheet_header(tmp_path: Path) -> None:
    """Final (matrix) sheet row-1 must match _FINAL_MATRIX_HEADER exactly."""
    from kuma_core.mame.export.excel_writer import _FINAL_MATRIX_HEADER

    vr = _make_verdict("NB01", "1_1", VerdictClass.PASS)
    rr = _make_replicate("V5F", "NB01", "1_1")
    out = tmp_path / "matrix.xlsx"
    write_excel(verdict_records=[vr], replicate_results=[rr], output_path=out)
    wb = openpyxl.load_workbook(out)
    ws = wb["Final (matrix)"]
    actual_header = [c.value for c in ws[1]]
    assert actual_header == _FINAL_MATRIX_HEADER


def test_final_matrix_selection_cell(tmp_path: Path) -> None:
    """Selected-plate column must contain 1; other plates blank."""
    vr = _make_verdict("NB02", "2_3", VerdictClass.PASS, size_kb=90.0)
    rr = ReplicateResult(
        mutant_id="K7R",
        plate_verdicts={"NB01": _make_verdict("NB01", "2_3", VerdictClass.AMBIGUOUS), "NB02": vr},
        selected_plate="NB02",
        selection_reason="pass beats ambiguous",
        failed=False,
    )
    out = tmp_path / "matrix2.xlsx"
    write_excel(
        verdict_records=[vr],
        replicate_results=[rr],
        output_path=out,
    )
    wb = openpyxl.load_workbook(out)
    ws = wb["Final (matrix)"]
    # Data row is row 2 (header is row 1).
    row_values = [c.value for c in ws[2]]
    # Columns: index=0, mutant=1, well=2, NB01=3, NB02=4, NB03=5
    assert row_values[4] == 1, "NB02 selection cell should be 1"
    assert row_values[3] in ("", None), "NB01 should be blank"
    assert row_values[5] in ("", None), "NB03 should be blank"


# ---------------------------------------------------------------------------
# Janus mapping export (K4)
# ---------------------------------------------------------------------------


def _make_janus_replicates() -> list[ReplicateResult]:
    """Two confirmed replicates with different sizes (for sort-order test)."""
    rr_high = ReplicateResult(
        mutant_id="V5F",
        plate_verdicts={"NB01": _make_verdict("NB01", "1_1", VerdictClass.PASS, size_kb=200.0)},
        selected_plate="NB01",
        selection_reason="pass",
        failed=False,
    )
    rr_low = ReplicateResult(
        mutant_id="K7R",
        plate_verdicts={"NB02": _make_verdict("NB02", "1_2", VerdictClass.PASS, size_kb=50.0)},
        selected_plate="NB02",
        selection_reason="pass",
        failed=False,
    )
    return [rr_low, rr_high]  # intentionally unsorted to test sort order


def test_janus_csv_header(tmp_path: Path) -> None:
    """CSV output must have the exact Janus header."""
    out = tmp_path / "janus.csv"
    export_mame_janus_csv(_make_janus_replicates(), out)
    with out.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == _JANUS_HEADER


def test_janus_csv_sorted_desc(tmp_path: Path) -> None:
    """Rows must be sorted by priority_score DESC (V5F=200 before K7R=50)."""
    out = tmp_path / "janus_sorted.csv"
    export_mame_janus_csv(_make_janus_replicates(), out)
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["name"] == "V5F", "highest priority_score should come first"
    assert rows[1]["name"] == "K7R"


def test_janus_csv_plate_label(tmp_path: Path) -> None:
    """NB01->P1, NB02->P2 mapping must be applied in source_plate column."""
    out = tmp_path / "janus_plate.csv"
    export_mame_janus_csv(_make_janus_replicates(), out)
    with out.open(encoding="utf-8") as fh:
        rows = {r["name"]: r for r in csv.DictReader(fh)}
    assert rows["V5F"]["source_plate"] == "P1"
    assert rows["K7R"]["source_plate"] == "P2"


def test_janus_xlsx_sheet_name(tmp_path: Path) -> None:
    """XLSX output must have 'Janus Mapping' sheet with correct header."""
    out = tmp_path / "janus.xlsx"
    export_mame_janus_xlsx(_make_janus_replicates(), out)
    wb = openpyxl.load_workbook(out)
    assert "Janus Mapping" in wb.sheetnames
    ws = wb["Janus Mapping"]
    actual_header = [c.value for c in ws[1]]
    assert actual_header == _JANUS_HEADER


def test_janus_excludes_failed(tmp_path: Path) -> None:
    """Failed replicates must not appear in Janus output."""
    failed_rr = ReplicateResult(
        mutant_id="BAD",
        plate_verdicts={"NB01": _make_verdict("NB01", "1_3", VerdictClass.FRAMESHIFT)},
        selected_plate=None,
        selection_reason="all fail",
        failed=True,
    )
    ok_rr = _make_replicate("V5F", "NB01", "1_1")
    out = tmp_path / "janus_no_failed.csv"
    export_mame_janus_csv([failed_rr, ok_rr], out)
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    names = [r["name"] for r in rows]
    assert "BAD" not in names, "failed replicate must be excluded"
    assert "V5F" in names
