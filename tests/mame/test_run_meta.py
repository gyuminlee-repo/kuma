"""Tests for kuma_core.mame.ingest.run_meta and __kuma_meta__ sheet export.

Fixture layout mirrors a typical MinKNOW run:

    tmp_path/
      run_xyz/                           <- MinKNOW run dir (has final_summary)
        final_summary_PAX12345_abc.txt
        sample_sheet_PAX12345.csv
        sort_barcode06/                  <- input_dir supplied to discover
          NB01/
"""

from __future__ import annotations

import csv
from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.export.excel_writer import _write_kuma_meta_sheet, write_excel
from kuma_core.mame.export.janus_mapping import (
    export_mame_janus_csv,
    export_mame_janus_xlsx,
)
from kuma_core.mame.ingest.run_meta import NgsRunMeta, discover_run_meta
from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_FINAL_SUMMARY_CONTENT = """\
instrument = PAX12345
position = X3
flow_cell_id = FAW12345
sample_id = my_sample
kit = SQK-LSK109
started = 2024-03-15T10:00:00Z
basecalling_enabled = true
"""

_SAMPLE_SHEET_CONTENT = """\
flow_cell_product_code,FLO-MIN106D
kit,SQK-LSK109
"""


def _make_run_dir(parent: Path, dirname: str = "run_xyz") -> Path:
    """Create a mock MinKNOW run directory under *parent*."""
    run_dir = parent / dirname
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "final_summary_PAX12345_abc.txt").write_text(
        _FINAL_SUMMARY_CONTENT, encoding="utf-8"
    )
    (run_dir / "sample_sheet_PAX12345.csv").write_text(
        _SAMPLE_SHEET_CONTENT, encoding="utf-8"
    )
    return run_dir


def _make_verdict(
    nb: str,
    custom: str,
    verdict: VerdictClass = VerdictClass.PASS,
    size_kb: float = 80.0,
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


# ---------------------------------------------------------------------------
# discover_run_meta tests
# ---------------------------------------------------------------------------


def test_discover_run_meta_from_input_dir(tmp_path: Path) -> None:
    """input_dir is a subdirectory of a MinKNOW run dir — meta is discovered."""
    run_dir = _make_run_dir(tmp_path)
    input_dir = run_dir / "sort_barcode06"
    input_dir.mkdir()

    meta = discover_run_meta(input_dir)

    assert meta is not None
    assert meta.instrument == "PAX12345"
    assert meta.position == "X3"
    assert meta.flow_cell_id == "FAW12345"
    assert meta.sample_id == "my_sample"
    assert meta.kit == "SQK-LSK109"
    assert meta.started == "2024-03-15T10:00:00Z"
    assert meta.basecalling_enabled is True
    assert meta.raw_run_dir is not None
    assert "run_xyz" in meta.raw_run_dir


def test_discover_run_meta_input_dir_is_run_dir(tmp_path: Path) -> None:
    """input_dir itself is the MinKNOW run dir."""
    run_dir = _make_run_dir(tmp_path)
    meta = discover_run_meta(run_dir)
    assert meta is not None
    assert meta.flow_cell_id == "FAW12345"


def test_discover_run_meta_sibling(tmp_path: Path) -> None:
    """Run dir and input_dir are siblings under the same parent."""
    run_dir = _make_run_dir(tmp_path)
    input_dir = tmp_path / "sort_barcode06"
    input_dir.mkdir()

    meta = discover_run_meta(input_dir)

    assert meta is not None
    assert meta.flow_cell_id == "FAW12345"


def test_discover_run_meta_no_run_dir_returns_none(tmp_path: Path) -> None:
    """No MinKNOW artefacts in the search tree — returns None."""
    input_dir = tmp_path / "plain_dir" / "barcode"
    input_dir.mkdir(parents=True)

    meta = discover_run_meta(input_dir)

    assert meta is None


def test_discover_run_meta_nonexistent_dir_returns_none(tmp_path: Path) -> None:
    """Nonexistent input_dir — returns None without raising."""
    input_dir = tmp_path / "does_not_exist"
    meta = discover_run_meta(input_dir)
    assert meta is None


def test_discover_run_meta_basecalling_false(tmp_path: Path) -> None:
    """basecalling_enabled = false is parsed correctly."""
    run_dir = tmp_path / "run2"
    run_dir.mkdir()
    (run_dir / "final_summary_X.txt").write_text(
        "basecalling_enabled = false\nflow_cell_id = ZZZ\n", encoding="utf-8"
    )
    input_dir = run_dir / "sub"
    input_dir.mkdir()
    meta = discover_run_meta(input_dir)
    assert meta is not None
    assert meta.basecalling_enabled is False
    assert meta.flow_cell_id == "ZZZ"


def test_discover_run_meta_kit_from_sample_sheet(tmp_path: Path) -> None:
    """Kit absent from final_summary but present in sample_sheet."""
    run_dir = tmp_path / "run3"
    run_dir.mkdir()
    # final_summary with no kit
    (run_dir / "final_summary_Y.txt").write_text(
        "flow_cell_id = ABC\n", encoding="utf-8"
    )
    (run_dir / "sample_sheet_Y.csv").write_text(
        "kit,SQK-RBK004\n", encoding="utf-8"
    )
    input_dir = run_dir / "barcode01"
    input_dir.mkdir()
    meta = discover_run_meta(input_dir)
    assert meta is not None
    assert meta.kit == "SQK-RBK004"


# ---------------------------------------------------------------------------
# Excel __kuma_meta__ sheet tests
# ---------------------------------------------------------------------------


def test_excel_kuma_meta_sheet_present(tmp_path: Path) -> None:
    """write_excel always includes __kuma_meta__ sheet."""
    vr = _make_verdict("NB01", "1_1", VerdictClass.PASS)
    rr = _make_replicate("V5F", "NB01", "1_1")
    out = tmp_path / "with_meta.xlsx"
    run_dir = _make_run_dir(tmp_path)
    meta = discover_run_meta(run_dir)

    write_excel(
        verdict_records=[vr],
        replicate_results=[rr],
        output_path=out,
        ngs_run_meta=meta,
        kuma_version="1.2.3",
    )

    wb = openpyxl.load_workbook(out)
    assert "__kuma_meta__" in wb.sheetnames, "__kuma_meta__ sheet missing"


def test_excel_kuma_meta_sheet_values(tmp_path: Path) -> None:
    """__kuma_meta__ sheet contains expected flow_cell_id and kit rows."""
    vr = _make_verdict("NB01", "1_1", VerdictClass.PASS)
    rr = _make_replicate("V5F", "NB01", "1_1")
    out = tmp_path / "meta_values.xlsx"
    run_dir = _make_run_dir(tmp_path)
    meta = discover_run_meta(run_dir)
    assert meta is not None

    write_excel(
        verdict_records=[vr],
        replicate_results=[rr],
        output_path=out,
        ngs_run_meta=meta,
        kuma_version="test",
    )

    wb = openpyxl.load_workbook(out)
    ws = wb["__kuma_meta__"]
    kv = {row[0]: row[1] for row in ws.iter_rows(min_row=2, values_only=True) if row[0]}
    assert kv.get("flow_cell_id") == "FAW12345"
    assert kv.get("kit") == "SQK-LSK109"
    assert kv.get("instrument") == "PAX12345"
    assert kv.get("kuma_version") == "test"


def test_excel_kuma_meta_sheet_none_meta(tmp_path: Path) -> None:
    """write_excel with ngs_run_meta=None writes placeholder row."""
    vr = _make_verdict("NB01", "1_1", VerdictClass.PASS)
    out = tmp_path / "no_meta.xlsx"
    write_excel(
        verdict_records=[vr],
        replicate_results=[],
        output_path=out,
        ngs_run_meta=None,
    )
    wb = openpyxl.load_workbook(out)
    assert "__kuma_meta__" in wb.sheetnames
    ws = wb["__kuma_meta__"]
    all_values = [row for row in ws.iter_rows(values_only=True) if any(v for v in row)]
    # Should have header + at least kuma_version + generated_at + placeholder rows
    assert len(all_values) >= 3


def test_excel_legacy_sheets_preserved(tmp_path: Path) -> None:
    """Existing legacy sheets (NB01, Final, NGS 결과, Final (matrix)) are unaffected."""
    vr = _make_verdict("NB01", "1_1", VerdictClass.PASS)
    rr = _make_replicate("V5F", "NB01", "1_1")
    out = tmp_path / "legacy.xlsx"
    write_excel(
        verdict_records=[vr],
        replicate_results=[rr],
        output_path=out,
        ngs_run_meta=None,
    )
    wb = openpyxl.load_workbook(out)
    for name in ("NB01", "Final", "NGS 결과", "Final (matrix)", "__kuma_meta__"):
        assert name in wb.sheetnames, f"Sheet '{name}' missing"


# ---------------------------------------------------------------------------
# Janus mapping meta embedding (G3)
# ---------------------------------------------------------------------------


def test_janus_csv_comment_line_with_meta(tmp_path: Path) -> None:
    """When ngs_run_meta is provided, CSV first line starts with '# kuma_run_meta:'."""
    rr = _make_replicate("V5F", "NB01", "1_1", size_kb=100.0)
    out = tmp_path / "janus_meta.csv"
    meta = NgsRunMeta(
        instrument="PAX12345",
        position="X3",
        flow_cell_id="FAW12345",
        sample_id="sample",
        kit="SQK-LSK109",
        started="2024-03-15T10:00:00Z",
        basecalling_enabled=True,
        raw_run_dir="/data/run_xyz",
    )
    export_mame_janus_csv([rr], out, ngs_run_meta=meta)

    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# kuma_run_meta:"), f"Expected comment line, got: {lines[0]}"
    assert "FAW12345" in lines[0]
    assert "SQK-LSK109" in lines[0]


def test_janus_csv_no_comment_when_meta_none(tmp_path: Path) -> None:
    """When ngs_run_meta=None, CSV starts with header row (no comment line).

    This preserves backward compatibility with csv.DictReader consumers.
    """
    rr = _make_replicate("V5F", "NB01", "1_1", size_kb=100.0)
    out = tmp_path / "janus_no_comment.csv"
    export_mame_janus_csv([rr], out, ngs_run_meta=None)

    with out.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames is not None
        assert reader.fieldnames[0] == "name", (
            f"Expected header row first, got: {reader.fieldnames}"
        )


def test_janus_csv_comment_dict_reader_skips_correctly(tmp_path: Path) -> None:
    """DictReader reading a CSV with comment line must skip it to get data rows."""
    rr = _make_replicate("V5F", "NB01", "1_1", size_kb=100.0)
    out = tmp_path / "janus_skip.csv"
    meta = NgsRunMeta(
        instrument=None, position=None, flow_cell_id="FC1",
        sample_id=None, kit=None, started=None,
        basecalling_enabled=None, raw_run_dir=None,
    )
    export_mame_janus_csv([rr], out, ngs_run_meta=meta)

    with out.open(encoding="utf-8") as fh:
        # Skip comment line before handing to DictReader
        first_line = fh.readline()
        assert first_line.startswith("#")
        reader = csv.DictReader(fh)
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["name"] == "V5F"


def test_janus_xlsx_kuma_meta_sheet_present(tmp_path: Path) -> None:
    """Janus XLSX always contains __kuma_meta__ sheet."""
    rr = _make_replicate("V5F", "NB01", "1_1", size_kb=100.0)
    out = tmp_path / "janus.xlsx"
    export_mame_janus_xlsx([rr], out, ngs_run_meta=None)
    wb = openpyxl.load_workbook(out)
    assert "__kuma_meta__" in wb.sheetnames, "__kuma_meta__ sheet missing from Janus XLSX"


def test_janus_xlsx_kuma_meta_values(tmp_path: Path) -> None:
    """Janus XLSX __kuma_meta__ sheet has flow_cell_id and kit rows."""
    rr = _make_replicate("V5F", "NB01", "1_1", size_kb=100.0)
    meta = NgsRunMeta(
        instrument="P2",
        position="Y1",
        flow_cell_id="FBW99",
        sample_id="samp",
        kit="SQK-RBK004",
        started="2024-06-01T08:00:00Z",
        basecalling_enabled=False,
        raw_run_dir="/data/run_abc",
    )
    out = tmp_path / "janus_kv.xlsx"
    export_mame_janus_xlsx([rr], out, ngs_run_meta=meta, kuma_version="2.0.0")
    wb = openpyxl.load_workbook(out)
    ws = wb["__kuma_meta__"]
    kv = {row[0]: row[1] for row in ws.iter_rows(min_row=2, values_only=True) if row[0]}
    assert kv.get("flow_cell_id") == "FBW99"
    assert kv.get("kit") == "SQK-RBK004"
    assert kv.get("kuma_version") == "2.0.0"
    assert kv.get("basecalling_enabled") == "false"


def test_janus_xlsx_legacy_sheet_intact(tmp_path: Path) -> None:
    """Janus Mapping sheet (data) is still present after meta sheet added."""
    rr = _make_replicate("V5F", "NB01", "1_1", size_kb=100.0)
    out = tmp_path / "janus_legacy.xlsx"
    export_mame_janus_xlsx([rr], out, ngs_run_meta=None)
    wb = openpyxl.load_workbook(out)
    assert "Janus Mapping" in wb.sheetnames
    assert "__kuma_meta__" in wb.sheetnames
