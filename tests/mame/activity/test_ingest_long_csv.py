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
