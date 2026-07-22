"""auto_relax rescue must run even when rescue_pool is empty.

Regression guard: the auto_relax block used to be nested inside the
`if p.rescue_pool` guard, so manual/CSV input modes (which send an empty
rescue pool) never reached it.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.design import handle_design_sdm_primers

from tests.conftest import TARGET_START

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
GENBANK = FIXTURES_DIR / "pSHCE-dmpR.gb"
EVOLVEPRO_CSV = FIXTURES_DIR / "dmpR_evolvepro.csv"


@pytest.fixture
def restore_state():
    """Design mutates module-level sidecar state; restore it afterwards."""
    with _state_lock:
        saved = (list(_state.results), dict(_state.candidates),
                 list(_state.plate_mappings), dict(_state.dedup_info or {}))
    yield
    with _state_lock:
        _state.results, _state.candidates, _state.plate_mappings, _state.dedup_info = (
            saved[0], saved[1], saved[2], saved[3]
        )


@pytest.fixture(scope="module")
def mutation_text() -> str:
    with EVOLVEPRO_CSV.open() as fh:
        return "\n".join(row["mutation"] for row in csv.DictReader(fh))


def _design(mutation_text: str, *, auto_relax: bool) -> dict:
    return handle_design_sdm_primers({
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "mutations_csv_or_text": mutation_text,
        "polymerase": "KOD",
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": auto_relax,
    })


def test_auto_relax_rescues_without_rescue_pool(mutation_text, restore_state):
    baseline = _design(mutation_text, auto_relax=False)
    relaxed = _design(mutation_text, auto_relax=True)

    assert baseline["success_count"] > 0
    assert baseline["failed_mutations"], "fixture must produce failures to rescue"
    assert relaxed["success_count"] > baseline["success_count"]
    assert relaxed["rescue_stats"]["auto_relax"] > 0
    assert (relaxed["success_count"] - baseline["success_count"]
            == relaxed["rescue_stats"]["auto_relax"])


def test_no_rescue_counters_when_auto_relax_disabled(mutation_text, restore_state):
    res = _design(mutation_text, auto_relax=False)
    stats = res["rescue_stats"]
    assert stats["auto_relax"] == 0
    assert stats["pool_cascade"] == 0
    assert stats["positions_attempted"] == 0
    assert stats["pool_variants_tried"] == 0
    assert res["rescued_mutations"] == []
