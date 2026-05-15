"""Tests for sidecar_kuro.handlers.evolvepro."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

import sidecar_kuro.core as _core
from sidecar_kuro.handlers import evolvepro as evolvepro_handlers


def _eq(actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"{actual!r} != {expected!r}")  # noqa: S101


def _is(actual: object, expected: object) -> None:
    if actual is not expected:
        raise AssertionError(f"{actual!r} is not {expected!r}")  # noqa: S101


def _contains(haystack: object, needle: object) -> None:
    if needle not in haystack:  # type: ignore[operator]
        raise AssertionError(f"{needle!r} not in {haystack!r}")  # noqa: S101


@pytest.fixture(autouse=True)
def _reset_state():
    with _core._state_lock:
        _core._state.evolvepro_runs = {}
    yield
    with _core._state_lock:
        _core._state.evolvepro_runs = {}


def test_handle_detect_returns_dict(monkeypatch):
    """handle_evolvepro_detect returns dict with env_found key."""
    fake_status = MagicMock()
    fake_status.env_found = False
    fake_status.env_path = None
    fake_status.evolvepro_version = None
    fake_status.weights_cached = False
    fake_status.weights_path = None
    monkeypatch.setattr(
        evolvepro_handlers.evolvepro_runner, "detect_env", lambda: fake_status
    )
    result = evolvepro_handlers.handle_evolvepro_detect({})
    _contains(result, "env_found")
    _is(result["env_found"], False)


def test_handle_run_validates_request():
    """Invalid params (n_rounds=0) raise ValidationError from Pydantic."""
    bad_params = {
        "input_csv": "x.csv",
        "wt_sequence": "M",
        "n_rounds": 0,
        "output_dir": "out",
        "top_n": 1,
    }
    raised = False
    try:
        evolvepro_handlers.handle_evolvepro_run(bad_params)
    except ValidationError:
        raised = True
    _is(raised, True)


def test_handle_cancel_unknown_run_id():
    """Cancelling unknown run_id returns ok=False with reason."""
    result = evolvepro_handlers.handle_evolvepro_cancel({"run_id": "nonexistent"})
    _is(result["ok"], False)
    _contains(result, "reason")


def test_handle_run_registers_handle(monkeypatch, tmp_path):
    """Successful run() registers RunHandle in core state."""
    fake_handle = MagicMock()
    fake_handle.run_id = "fixed-run-id"

    def fake_run(**kwargs):
        return fake_handle

    monkeypatch.setattr(evolvepro_handlers.evolvepro_runner, "run", fake_run)

    params = {
        "input_csv": str(tmp_path / "in.csv"),
        "wt_sequence": "MKT",
        "n_rounds": 1,
        "output_dir": str(tmp_path / "out"),
        "top_n": 5,
    }
    result = evolvepro_handlers.handle_evolvepro_run(params)
    _eq(result["run_id"], "fixed-run-id")
    with _core._state_lock:
        _is(_core._state.evolvepro_runs["fixed-run-id"], fake_handle)


def test_handle_cancel_known_run_id(monkeypatch):
    """Cancelling a registered run_id calls runner.cancel and returns ok."""
    fake_handle = MagicMock()
    with _core._state_lock:
        _core._state.evolvepro_runs["rid"] = fake_handle
    monkeypatch.setattr(
        evolvepro_handlers.evolvepro_runner, "cancel", lambda h: True
    )
    result = evolvepro_handlers.handle_evolvepro_cancel({"run_id": "rid"})
    _is(result["ok"], True)
