"""Export tests: well mapping, color rules, failed-well behavior."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from kuma_core.mame.export import WellMapper, seq_to_well, write_excel
from kuma_core.mame.export.excel_writer import (
    _SHEET1_HEADER,
    FAILED_FILL,
    VERDICT_FILL,
)
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
