"""What the design handler owes a multi-substitution row.

Three separate promises, each of which was broken before:

- a malformed row is reported as a failure and never handed to the pool
  rescue, which answers a failure by designing a DIFFERENT substitution and
  would turn a typo into a genotype nobody requested;
- the relax pass re-designs the mutation the batch parsed rather than a fresh
  parse of its notation, so the source row survives the rescue;
- retry_failed refuses a design that held combination rows instead of
  committing a result whose group has quietly gone.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.design import (
    handle_design_sdm_primers,
    handle_retry_failed,
)

from tests.conftest import TARGET_START

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
GENBANK = FIXTURES_DIR / "sample_sdm_template.gb"


@pytest.fixture
def restore_state():
    """Design mutates module-level sidecar state; restore it afterwards."""
    with _state_lock:
        saved = (
            list(_state.results), dict(_state.candidates),
            list(_state.plate_mappings), dict(_state.dedup_info or {}),
            _state.design_had_groups,
        )
    yield
    with _state_lock:
        (_state.results, _state.candidates, _state.plate_mappings,
         _state.dedup_info, _state.design_had_groups) = saved


def _first_mutation() -> str:
    """One substitution the sample template designs cleanly."""
    import csv

    with (FIXTURES_DIR / "sdm_template_evolvepro.csv").open() as fh:
        return next(iter(csv.DictReader(fh)))["mutation"]


def _design(mutation_text: str, **extra) -> dict:
    params = {
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "mutations_csv_or_text": mutation_text,
        "polymerase": "Q5",
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": False,
    }
    params.update(extra)
    return handle_design_sdm_primers(params)


def test_a_malformed_row_is_reported_and_not_rescued(restore_state) -> None:
    """`X1Y` disagrees with the template, and position 1 has a pool entry.

    The pool is keyed by position, so a parse failure that carries a number is
    exactly the case that reaches it: the handler would design `M1A`, a
    substitution this input never asked for, and record it as having rescued
    the typo.
    """
    good = _first_mutation()
    response = _design(f"{good}\nX1Y", rescue_pool=["M1A"])
    failed = {f["mutation"] for f in response["failed_mutations"]}
    assert "X1Y" in failed, "the malformed row must still be reported"
    assert not any(
        r["original"] == "X1Y" for r in response["rescued_mutations"]
    )
    assert "M1A" not in {r["mutation"] for r in response["results"]}


def test_retry_is_refused_after_a_design_that_held_a_combination(
    restore_state,
) -> None:
    good = _first_mutation()
    other = _second_mutation(good)
    _design(f"{good}/{other}")
    with _state_lock:
        assert _state.design_had_groups is True
    before = len(_state.candidates)

    with pytest.raises(ValueError, match="multi-substitution"):
        handle_retry_failed({
            "mutation": good,
            "fasta_path": str(GENBANK),
            "target_start": TARGET_START,
            "polymerase": "Q5",
            "overlap_len": 18,
            "overlap_mode": "partial",
        })
    # Refused before touching anything, so nothing was recorded.
    with _state_lock:
        assert len(_state.candidates) == before
        assert _state.interventions == []


def test_retry_still_works_after_a_design_without_combinations(
    restore_state,
) -> None:
    good = _first_mutation()
    _design(good)
    with _state_lock:
        assert _state.design_had_groups is False

    result = handle_retry_failed({
        "mutation": good,
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "polymerase": "Q5",
        "overlap_len": 18,
        "overlap_mode": "partial",
    })
    assert "candidates" in result


def _second_mutation(exclude: str) -> str:
    """Another substitution from the fixture, at a different position."""
    import csv

    with (FIXTURES_DIR / "sdm_template_evolvepro.csv").open() as fh:
        for row in csv.DictReader(fh):
            if row["mutation"] != exclude:
                return row["mutation"]
    raise AssertionError("fixture must hold at least two mutations")
