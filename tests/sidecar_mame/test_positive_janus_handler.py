"""RPC contract of the step 4.1 positive clone JANUS mapping."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

pytest.importorskip("openpyxl")

from sidecar_mame.dispatcher import _METHODS
from sidecar_mame.handlers.activity import (
    handle_export_positive_janus,
    handle_positive_janus_candidates,
)
from tests.mame.test_positive_janus import (
    EXPECTED_PLACEMENT,
    _layout,
    _raw_report,
)


def _sources(tmp_path: Path) -> dict[str, str]:
    return {
        "round1_report_xlsx": str(_raw_report(tmp_path / "round1.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
    }


def test_methods_are_registered():
    assert _METHODS["mame.activity.positive_janus_candidates"] is handle_positive_janus_candidates
    assert _METHODS["mame.activity.export_positive_janus"] is handle_export_positive_janus


def test_candidates_report_every_measured_well_and_the_backend_defaults(tmp_path: Path):
    response = handle_positive_janus_candidates(_sources(tmp_path))
    assert len(response["candidates"]) == 23
    assert response["n_above_wt"] == 20
    first = response["candidates"][0]
    assert set(first) == {"well", "name", "relative", "n_replicates", "above_wt"}
    assert response["defaults"] == {
        "volume": 70.0,
        "source_rack": "final cell stock",
        "dest_rack": "deep well plate",
        "sample_type": "cell stock",
    }


def test_export_writes_the_slide_12_placement(tmp_path: Path):
    sources = _sources(tmp_path)
    listed = handle_positive_janus_candidates(sources)
    selected = [c["well"] for c in listed["candidates"] if c["above_wt"]]
    out = tmp_path / "positive.csv"
    response = handle_export_positive_janus({
        **sources,
        "selected_wells": selected,
        "volume": 70.0,
        "source_rack": "final cell stock",
        "dest_rack": "deep well plate",
        "output_csv": str(out),
    })
    assert response["output_path"] == str(out)
    assert response["row_count"] == 20
    with out.open(newline="", encoding="utf-8") as fh:
        table = list(csv.DictReader(fh))
    assert [(r["Dsp. Posi"], r["Asp. Posi"]) for r in table] == EXPECTED_PLACEMENT


@pytest.mark.parametrize(
    "patch",
    [
        {"selected_wells": []},
        {"selected_wells": ["A12"]},
        {"volume": 0},
        {"output_csv": "positive.xlsx"},
    ],
)
def test_export_refuses_and_writes_nothing(tmp_path: Path, patch):
    sources = _sources(tmp_path)
    out = tmp_path / "positive.csv"
    params = {
        **sources,
        "selected_wells": ["F1"],
        "volume": 70.0,
        "source_rack": "final cell stock",
        "dest_rack": "deep well plate",
        "output_csv": str(out),
        **patch,
    }
    if "output_csv" in patch:
        params["output_csv"] = str(tmp_path / patch["output_csv"])
    with pytest.raises(ValueError):
        handle_export_positive_janus(params)
    assert not out.exists()


def test_unknown_parameter_is_refused(tmp_path: Path):
    with pytest.raises(ValueError):
        handle_positive_janus_candidates({**_sources(tmp_path), "activity_path": "x.csv"})


def test_candidates_response_lists_rows_tied_to_no_well(tmp_path: Path):
    from tests.mame.test_positive_janus import _report_with_untied_rows

    response = handle_positive_janus_candidates({
        "round1_report_xlsx": str(_report_with_untied_rows(tmp_path / "round1.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
    })
    rows = response["excluded_rows"]
    assert [row["sample_name"] for row in rows] == ["BLANK", "BLANK2", "12"]
    assert {row["reason"] for row in rows} == {"non_well_sample", "numeric_calibration"}
    assert set(rows[0]) == {"source", "sample_name", "reason", "row_index", "block_index", "area", "kept"}
    assert all(row["source"] == "round1_report_xlsx" and row["block_index"] is not None for row in rows)
    assert any("'BLANK'" in warning for warning in response["warnings"])
    assert response["n_above_wt"] == 20


def test_export_rows_ignore_the_untied_rows(tmp_path: Path):
    from tests.mame.test_positive_janus import _report_with_untied_rows

    plain = _sources(tmp_path)
    noisy = {**plain, "round1_report_xlsx": str(_report_with_untied_rows(tmp_path / "noisy.xlsx"))}
    wells = [c["well"] for c in handle_positive_janus_candidates(plain)["candidates"] if c["above_wt"]]
    common = {"selected_wells": wells, "volume": 70.0, "source_rack": "final cell stock", "dest_rack": "deep well plate"}
    a = handle_export_positive_janus({**plain, **common, "output_csv": str(tmp_path / "a.csv")})
    b = handle_export_positive_janus({**noisy, **common, "output_csv": str(tmp_path / "b.csv")})
    assert a["rows"] == b["rows"]
