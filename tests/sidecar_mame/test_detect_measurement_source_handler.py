"""``mame.activity.detect_measurement_source`` over the dispatcher.

The core detector has its own labelled corpus
(``tests/mame/activity/test_detect_measurement_source.py``).  This covers the
adapter: the method is registered, the response is JSON-serialisable, and a
bad path is refused the way every other activity input is.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sidecar_mame.dispatcher import _METHODS

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
METHOD = "mame.activity.detect_measurement_source"


def _call(**params) -> dict:
    return _METHODS[METHOD](params)


def test_method_is_registered() -> None:
    assert METHOD in _METHODS


def test_unambiguous_workbook_round_trips_as_json() -> None:
    result = _call(measurement_path=str(TEMPLATES / "11_mame_gc_fid_round1_raw.xlsx"))
    assert result["candidates"] == ["rawReport"]
    assert result["ambiguous"] is False
    assert result["reason"] == ""
    # The evidence dict crosses JSON-RPC, so it has to survive the encoder.
    assert json.loads(json.dumps(result))["evidence"]["fid1b_signature"] is True


def test_ambiguous_workbook_reports_both_readings() -> None:
    result = _call(measurement_path=str(TEMPLATES / "10_mame_gc_prenormalised.xlsx"))
    assert result["candidates"] == ["gcSheet", "longFormat"]
    assert result["ambiguous"] is True


def test_unrecognised_file_answers_rather_than_raising(tmp_path: Path) -> None:
    path = tmp_path / "not_a_measurement.csv"
    path.write_text("alpha,beta\n1,2\n", encoding="utf-8")
    result = _call(measurement_path=str(path))
    assert result["candidates"] == []
    assert result["reason"]
    assert result["evidence"]["header"] == ["alpha", "beta"]


def test_missing_path_is_refused() -> None:
    with pytest.raises(ValueError):
        _call(measurement_path=str(TEMPLATES / "no_such_file.xlsx"))


def test_wrong_extension_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "measurements.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        _call(measurement_path=str(path))


def test_unknown_parameter_is_refused() -> None:
    with pytest.raises(ValueError):
        _call(
            measurement_path=str(TEMPLATES / "07_mame_activity_long.csv"),
            format="gcSheet",
        )
