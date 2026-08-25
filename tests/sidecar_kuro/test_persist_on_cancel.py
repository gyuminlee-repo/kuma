"""Cancelling a design keeps what it already produced, when Settings says to.

The Settings control offers "Keep partial results" and "Discard all results",
and defaults to keeping. It kept nothing: every cancellation point returned an
empty response and the handler had already cleared the state, so stopping a run
at 90 of 96 mutations threw away all 90. The control stored a preference and
changed no behaviour, the same shape as the fill-on-failure box that let a run
pinned to 18 nt come back with 17mers.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import sidecar_kuro.core as _core
import sidecar_kuro.handlers.design as design_module
from kuma_core.kuro.sdm_engine import design_sdm_primers as real_design_sdm_primers
from sidecar_kuro.handlers.design import handle_design_sdm_primers

from tests.conftest import TARGET_START

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
GENBANK = FIXTURES_DIR / "pSHCE-dmpR.gb"
EVOLVEPRO_CSV = FIXTURES_DIR / "dmpR_evolvepro.csv"

# Stop after this many mutations, leaving the rest of the fixture undesigned.
CANCEL_AFTER = 3


@pytest.fixture
def restore_state():
    with _core._state_lock:
        saved = (list(_core._state.results), dict(_core._state.candidates),
                 list(_core._state.plate_mappings), dict(_core._state.dedup_info or {}))
    yield
    with _core._state_lock:
        (_core._state.results, _core._state.candidates,
         _core._state.plate_mappings, _core._state.dedup_info) = saved


@pytest.fixture(scope="module")
def mutations() -> str:
    with EVOLVEPRO_CSV.open() as fh:
        text = "\n".join(row["mutation"] for row in csv.DictReader(fh))
    assert len(text.strip().split("\n")) > CANCEL_AFTER + 1, (
        "fixture must be long enough that cancelling leaves work undone"
    )
    return text


@pytest.fixture
def preferences(tmp_path, monkeypatch):
    """Point the sidecar at a throwaway preferences file."""
    path = tmp_path / "preferences.json"
    monkeypatch.setenv("KUMA_PREFERENCES_PATH", str(path))

    def write(persist_on_cancel: str | None) -> None:
        if persist_on_cancel is None:
            return  # leave the file absent: a first run has no preferences
        path.write_text(
            json.dumps({"sidecar": {"persist_on_cancel": persist_on_cancel}}),
            encoding="utf-8",
        )

    return write


@pytest.fixture
def cancel_midway(monkeypatch):
    """Trip the run's cancel flag once CANCEL_AFTER mutations are designed.

    Driven from the progress callback the engine already invokes once per
    mutation, so the cancellation lands where a user's would: partway through,
    with finished primers already in hand.
    """
    holder: dict[str, object] = {}
    real_begin = _core._begin_design_job

    def begin():
        event = real_begin()
        holder["event"] = event
        return event

    monkeypatch.setattr(_core, "_begin_design_job", begin)

    def design_with_cancel(*args, **kwargs):
        on_progress = kwargs.get("on_progress")

        def wrapped(i, total, raw):
            if i >= CANCEL_AFTER:
                holder["event"].set()  # type: ignore[union-attr]
            if on_progress:
                on_progress(i, total, raw)

        kwargs["on_progress"] = wrapped
        return real_design_sdm_primers(*args, **kwargs)

    monkeypatch.setattr(design_module, "design_sdm_primers", design_with_cancel)


def _design(mutation_text: str) -> dict:
    return handle_design_sdm_primers({
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "mutations_csv_or_text": mutation_text,
        "polymerase": "KOD",
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": False,
    })


@pytest.mark.usefixtures("restore_state", "cancel_midway")
def test_partial_results_are_kept_when_the_setting_says_keep(mutations, preferences):
    preferences("partial")
    res = _design(mutations)

    assert res["cancelled"] is True
    assert res["success_count"] > 0, "cancelling discarded every finished primer"
    with _core._state_lock:
        assert len(_core._state.results) == res["success_count"]
        assert _core._state.plate_mappings, "kept results need a plate map"
        assert _core._state.design_provenance is not None, (
            "kept results without provenance are primers no record explains"
        )


@pytest.mark.usefixtures("restore_state", "cancel_midway")
def test_partial_results_are_dropped_when_the_setting_says_discard(mutations, preferences):
    preferences("discard")
    res = _design(mutations)

    assert res["cancelled"] is True
    assert res["success_count"] == 0
    with _core._state_lock:
        assert _core._state.results == []
        assert _core._state.design_provenance is None


@pytest.mark.usefixtures("restore_state", "cancel_midway")
def test_absent_preferences_file_keeps_partial_results(mutations, preferences):
    """A first run has no preferences file, and the declared default is to keep."""
    preferences(None)
    res = _design(mutations)

    assert res["cancelled"] is True
    assert res["success_count"] > 0
