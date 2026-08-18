import pandas as pd
from pathlib import Path
from kuma_core.mame.activity.ingest_long_csv import ingest_long_csv


def test_ingest_minimal_csv(tmp_path: Path):
    csv = tmp_path / "round1.csv"
    csv.write_text("plate_id,well_id,value,replicate_idx\nP01,A01,1.23,1\nP01,B03,2.45,1\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": ["A01"]})
    assert len(result.records) == 2
    assert result.records[0].is_wt is True
    assert result.records[1].is_wt is False


def test_ingest_invalid_well_id_skipped(tmp_path: Path):
    csv = tmp_path / "bad.csv"
    csv.write_text("plate_id,well_id,value\nP01,XX,1.0\nP01,A01,2.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": ["A01"]})
    assert len(result.records) == 1
    assert result.records[0].well_id == "A01"


def test_ingest_negative_value_skipped(tmp_path: Path):
    csv = tmp_path / "neg.csv"
    csv.write_text("plate_id,well_id,value\nP01,A01,-0.5\nP01,B01,1.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert len(result.records) == 1


def test_ingest_missing_plate_id_rejects(tmp_path: Path):
    csv = tmp_path / "noplate.csv"
    csv.write_text("well_id,value\nA01,1.23\n")
    import pytest
    with pytest.raises(ValueError, match="plate_id"):
        ingest_long_csv(csv, plate_meta_wt_wells={})


def _gc_export_lines(n_rows: int = 4) -> str:
    """GC-FID style raw export: 'Sample Name'/'Area' headers, no plate column."""
    wells = ["A1", "A2", "B12", "H12"][:n_rows]
    areas = [10.0, 20.5, 30.0, 40.0][:n_rows]
    rows = "\n".join(f"{w},{a}" for w, a in zip(wells, areas))
    return f"Sample Name,Area\n{rows}\n"


def test_ingest_gc_export_inherits_plate_from_meta(tmp_path: Path):
    csv = tmp_path / "gc.csv"
    csv.write_text(_gc_export_lines())
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": ["A01"]})
    assert len(result.records) == 4
    # plate_id inherited from the single plate_meta key, not hardcoded.
    assert all(r.plate_id == "P01" for r in result.records)
    # 'Sample Name' -> well_id with A1 -> A01 normalisation.
    assert result.records[0].well_id == "A01"
    # is_wt judged against the inherited plate's WT wells.
    assert result.records[0].is_wt is True
    assert result.records[1].is_wt is False


def test_ingest_area_alias_maps_to_value(tmp_path: Path):
    csv = tmp_path / "gc_area.csv"
    csv.write_text(_gc_export_lines(n_rows=2))
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert [r.value for r in result.records] == [10.0, 20.5]


def test_ingest_no_plate_col_empty_meta_rejects(tmp_path: Path):
    csv = tmp_path / "gc_nometa.csv"
    csv.write_text(_gc_export_lines(n_rows=2))
    import pytest
    with pytest.raises(ValueError, match="plate_meta"):
        ingest_long_csv(csv, plate_meta_wt_wells={})


def test_ingest_no_plate_col_multi_meta_rejects(tmp_path: Path):
    csv = tmp_path / "gc_multi.csv"
    csv.write_text(_gc_export_lines(n_rows=2))
    import pytest
    with pytest.raises(ValueError, match="plate를 특정할 수 없습니다"):
        ingest_long_csv(csv, plate_meta_wt_wells={"P01": ["A01"], "P02": ["B01"]})


def test_ingest_missing_well_column_rejects(tmp_path: Path):
    csv = tmp_path / "nowell.csv"
    csv.write_text("plate_id,value\nP01,1.0\n")
    import pytest
    with pytest.raises(ValueError, match="well 컬럼이 필요합니다"):
        ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})


def test_ingest_keeps_dedicated_wt_replicate_rows(tmp_path: Path):
    """'WT_1'/'WT_2'/'WT_3' rows must survive ingest instead of being dropped.

    Regression: the well parser returned None for a WT label and the row was
    silently skipped, so the WT denominator had to be back-computed from the
    plate-designated WT wells.
    """
    csv = tmp_path / "wt_rows.csv"
    csv.write_text(
        "Sample Name,Area\nWT_1,10.0\nWT_2,12.0\nWT_3,14.0\nB03,20.0\n"
    )
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": ["A01"]})

    # WT labels never enter records (they are not wells).
    assert [r.well_id for r in result.records] == ["B03"]

    assert [r.sample_name for r in result.wt_records] == ["WT_1", "WT_2", "WT_3"]
    assert [r.value for r in result.wt_records] == [10.0, 12.0, 14.0]
    # replicate_idx comes from the label suffix (reports-mode convention).
    assert [r.replicate_idx for r in result.wt_records] == [1, 2, 3]
    assert all(r.plate_id == "P01" for r in result.wt_records)


def test_ingest_wt_row_without_number_still_skipped(tmp_path: Path):
    """Bare 'WT' has no replicate number; WT_PATTERN rejects it, so it drops."""
    csv = tmp_path / "bare_wt.csv"
    csv.write_text("Sample Name,Area\nWT,10.0\nB03,20.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert [r.well_id for r in result.records] == ["B03"]
    assert result.wt_records == []


def test_ingest_wt_row_negative_value_skipped(tmp_path: Path):
    """WT rows share the value guards with well rows."""
    csv = tmp_path / "wt_neg.csv"
    csv.write_text("Sample Name,Area\nWT_1,-1.0\nWT_2,12.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert [r.sample_name for r in result.wt_records] == ["WT_2"]

# --- dropped_rows accounting -------------------------------------------------

def test_dropped_rows_value_unparseable(tmp_path: Path):
    csv = tmp_path / "bad_value.csv"
    csv.write_text("plate_id,well_id,value\nP01,A01,abc\nP01,B01,2.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert len(result.records) == 1
    assert len(result.dropped_rows) == 1
    drop = result.dropped_rows[0]
    assert drop.reason == "value_unparseable"
    assert drop.row_index == 0
    assert drop.well_id == "A01"
    assert drop.plate_id == "P01"
    assert drop.detail == "abc"
    assert drop.source_file == "bad_value.csv"

def test_dropped_rows_value_nan_or_negative(tmp_path: Path):
    """Negative and empty value cells share one reason."""
    csv = tmp_path / "nan_neg.csv"
    csv.write_text("plate_id,well_id,value\nP01,A01,-0.5\nP01,B01,\nP01,C01,3.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert [r.well_id for r in result.records] == ["C01"]
    assert [d.reason for d in result.dropped_rows] == [
        "value_nan_or_negative",
        "value_nan_or_negative",
    ]
    assert [d.row_index for d in result.dropped_rows] == [0, 1]

def test_dropped_rows_well_unparseable(tmp_path: Path):
    """'XX' has no digit part, so the well parser cannot read it at all."""
    csv = tmp_path / "bad_well.csv"
    csv.write_text("plate_id,well_id,value\nP01,XX,1.0\nP01,A01,2.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert [r.well_id for r in result.records] == ["A01"]
    assert [d.reason for d in result.dropped_rows] == ["well_unparseable"]
    assert result.dropped_rows[0].well_id == "XX"

def test_dropped_rows_well_out_of_range(tmp_path: Path):
    """'A25' parses as a coordinate but exceeds both 96- and 384-well plates."""
    csv = tmp_path / "wide_well.csv"
    csv.write_text("plate_id,well_id,value\nP01,A25,1.0\nP01,A01,2.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert [r.well_id for r in result.records] == ["A01"]
    assert [d.reason for d in result.dropped_rows] == ["well_out_of_range"]
    assert result.dropped_rows[0].detail == "A25"

def test_dropped_rows_replicate_idx_skips_instead_of_aborting(tmp_path: Path):
    """Behaviour change: a malformed replicate_idx used to raise out of the whole
    ingest. It now skips its row, is recorded, and neighbours still ingest."""
    csv = tmp_path / "bad_rep.csv"
    csv.write_text(
        "plate_id,well_id,value,replicate_idx\n"
        "P01,A01,1.0,1\nP01,B01,2.0,x\nP01,C01,3.0,2\n"
    )
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert [r.well_id for r in result.records] == ["A01", "C01"]
    assert [r.replicate_idx for r in result.records] == [1, 2]
    assert [d.reason for d in result.dropped_rows] == ["replicate_idx_unparseable"]
    assert result.dropped_rows[0].row_index == 1
    assert result.dropped_rows[0].detail == "x"

def test_wt_replicate_row_is_not_a_drop(tmp_path: Path):
    """'WT_1' rows are kept in wt_records, so they must not count as dropped."""
    csv = tmp_path / "wt_kept.csv"
    csv.write_text("Sample Name,Area\nWT_1,10.0\nB03,20.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert len(result.wt_records) == 1
    assert result.dropped_rows == []

def test_clean_file_reports_no_drops(tmp_path: Path):
    csv = tmp_path / "clean.csv"
    csv.write_text("plate_id,well_id,value\nP01,A01,1.0\nP01,B01,2.0\n")
    result = ingest_long_csv(csv, plate_meta_wt_wells={"P01": []})
    assert len(result.records) == 2
    assert result.dropped_rows == []

def test_activity_table_payload_without_dropped_rows_still_loads():
    """Workspace JSON written before this field must round-trip unchanged."""
    from kuma_core.mame.activity.models import ActivityTable

    legacy = {
        "records": [
            {
                "plate_id": "P01",
                "well_id": "A01",
                "value": 1.0,
                "replicate_idx": 1,
                "is_wt": False,
                "source_file": "old.csv",
            }
        ],
        "plate_meta": {"plates": [{"plate_id": "P01", "wt_wells": []}]},
    }
    table = ActivityTable.model_validate(legacy)
    assert table.dropped_rows == []
    assert table.wt_records == []
    assert table.records[0].well_id == "A01"
