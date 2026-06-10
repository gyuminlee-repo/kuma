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
