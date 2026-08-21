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
from sidecar_kuro.handlers.design import (
    _LEN_FLOOR,
    _relaxed_floor,
    handle_design_sdm_primers,
)

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


def test_relaxed_floor_resolves_the_profile_before_lowering():
    """The caller usually leaves lengths to the polymerase profile.

    `p.rev_len_min` is None in that case, so the floor has to be resolved the
    way design_single_sdm resolves it before anything is taken off. Subtracting
    from None, or treating None as the fallback while a profile value exists,
    both produce the wrong floor.
    """
    # Explicit request wins over the profile.
    assert _relaxed_floor(24, 19, 19) == 22
    # No request: the profile value is the starting point.
    assert _relaxed_floor(None, 19, 17) == 17
    # Neither: the documented fallback is the starting point.
    assert _relaxed_floor(None, None, 19) == 17
    # The absolute floor is never crossed.
    assert _relaxed_floor(15, None, 19) == _LEN_FLOOR
    assert _relaxed_floor(None, 15, 19) == _LEN_FLOOR


def test_auto_relax_opens_the_length_axis(mutation_text, restore_state):
    """A primer pinned at its shortest allowed length cannot get cooler.

    Widening Tm and GC alone leaves those mutations rejected, because the only
    thing those axes can offer is a window wide enough to accept a primer far
    hotter than the rest of the plate. The length floor has to move too.
    """
    relaxed = _design(mutation_text, auto_relax=True)
    rescued = [
        entry["original"] if isinstance(entry, dict) else entry
        for entry in relaxed["rescued_mutations"]
    ]
    assert rescued, "fixture must rescue something for this to mean anything"

    by_mutation = {r["mutation"]: r for r in relaxed["results"]}
    for name in rescued:
        row = by_mutation[name]
        assert row["rev_len"] >= _LEN_FLOOR
        assert row["fwd_len"] >= _LEN_FLOOR


def test_relax_length_floor_reaches_the_engine(mutation_text, restore_state):
    """The lowered floor has to arrive at design_single_sdm, not just be computed.

    Demanding long primers makes the point visible: anything the relax pass
    recovers comes back SHORTER than the demand, because shortening is the only
    thing the lowered floor buys. A floor that never reached the engine would
    leave every primer at or above the demand and this would fail.
    """
    demanded = 26
    res = handle_design_sdm_primers({
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "mutations_csv_or_text": mutation_text,
        "polymerase": "KOD",
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": True,
        "rev_len_min": demanded,
        "rev_len_max": 30,
    })

    floor = _relaxed_floor(demanded, None, 19)
    assert floor == demanded - 2

    rescued = [
        entry["original"] if isinstance(entry, dict) else entry
        for entry in res["rescued_mutations"]
    ]
    assert rescued, "fixture must rescue something for this to mean anything"

    by_mutation = {r["mutation"]: r for r in res["results"]}
    for name in rescued:
        rev_len = by_mutation[name]["rev_len"]
        assert rev_len < demanded, (
            f"{name} came back at {rev_len} nt, which the unrelaxed floor "
            f"of {demanded} already allowed, so the relaxed floor did nothing"
        )
        assert rev_len >= floor
