from pathlib import Path

import pytest

from kuma_core.mame.activity.build_evolvepro_input import _read_long
from kuma_core.mame.activity.detect_measurement_source import detect_measurement_source
from kuma_core.mame.activity.ingest_long_csv import ingest_long_csv


@pytest.mark.parametrize("replicate", ["oops", "inf", "-inf", "nan"])
def test_invalid_replicate_drops_only_its_row(tmp_path: Path, replicate: str) -> None:
    source = tmp_path / "activity.csv"
    source.write_text(
        f"plate_id,well_id,value,replicate_idx\nP1,A1,2,{replicate}\nP1,B1,3,1\n",
        encoding="utf-8",
    )

    table = ingest_long_csv(source, {"P1": []})

    assert [record.well_id for record in table.records] == ["B01"]
    assert [row.reason for row in table.dropped_rows] == ["replicate_idx_unparseable"]


@pytest.mark.parametrize("separator", [",", "\t", ";", "|"])
def test_detected_delimited_activity_is_readable(tmp_path: Path, separator: str) -> None:
    source = tmp_path / "activity.txt"
    source.write_text(f'"variant"{separator}"value"\n89W{separator}2\n', encoding="utf-8")
    assert detect_measurement_source(source).candidates == ["longFormat"]

    values, _, _, _ = _read_long(source, "relative_to_wt", {}, {}, [])

    assert values == {"89W": [2.0]}
