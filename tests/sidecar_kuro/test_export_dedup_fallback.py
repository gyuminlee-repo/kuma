"""Regression tests for the dedup_info fallback ladder in export handlers.

Workspaces saved before ``dedupInfo`` was persisted arrive with an empty
dict (``workspaceMigrate.ts`` fills ``dedupInfo: ws.dedupInfo ?? {}``).
Without a fallback the exporters raise, blocking those users outright.
The handlers recompute the reverse grouping from the design results held
in sidecar state; when nothing is recomputable the explicit plate_mapper
error must still surface.
"""

from __future__ import annotations

import csv
from types import SimpleNamespace
from typing import cast

import pytest

import sidecar_kuro.core as _core
from sidecar_kuro.handlers.export import (
    handle_export_echo_mapping_dry_run,
    handle_export_mapping,
)

SHARED_REV = "CCCGGGAAATTTCCCGGG"
SOLO_REV = "TTTGGGCCCAAATTTGGG"

# M1 and M2 share one reverse primer, so only M1 owns a source well.
SHARED_DEDUP = {SHARED_REV: ["M1", "M2"], SOLO_REV: ["M3"]}


def _mappings() -> list[dict]:
    """Frontend payload where two mutations share a single reverse well."""
    return [
        {"well": "A1", "primer_name": "M1_F", "sequence": "AAATTTCCCGGGAAATTT",
         "primer_type": "forward", "mutation": "M1"},
        {"well": "B1", "primer_name": "M2_F", "sequence": "AAATTTCCCGGGAAAGGG",
         "primer_type": "forward", "mutation": "M2"},
        {"well": "C1", "primer_name": "M3_F", "sequence": "AAATTTCCCGGGAAACCC",
         "primer_type": "forward", "mutation": "M3"},
        {"well": "A1", "primer_name": "M1_R", "sequence": SHARED_REV,
         "primer_type": "reverse", "mutation": "M1"},
        {"well": "B1", "primer_name": "M3_R", "sequence": SOLO_REV,
         "primer_type": "reverse", "mutation": "M3"},
    ]


def _results() -> list[SimpleNamespace]:
    """Design results carrying the mutation to reverse-sequence link.

    ``deduplicate_reverse`` reads ``mutation.raw`` and ``reverse_seq`` only.
    """
    return [
        SimpleNamespace(mutation=SimpleNamespace(raw="M1"), reverse_seq=SHARED_REV),
        SimpleNamespace(mutation=SimpleNamespace(raw="M2"), reverse_seq=SHARED_REV),
        SimpleNamespace(mutation=SimpleNamespace(raw="M3"), reverse_seq=SOLO_REV),
    ]


@pytest.fixture(autouse=True)
def _reset_state():
    with _core._state_lock:
        saved = (
            list(_core._state.results),
            list(_core._state.plate_mappings),
            dict(_core._state.dedup_info or {}),
        )
        _core._state.results = []
        _core._state.plate_mappings = []
        _core._state.dedup_info = {}
    yield
    with _core._state_lock:
        (_core._state.results,
         _core._state.plate_mappings,
         _core._state.dedup_info) = saved


def _seed_results() -> None:
    with _core._state_lock:
        # SimpleNamespace stubs carry only the two attributes the handler reads.
        _core._state.results = cast(list, _results())


def _rev_destinations(csv_path) -> list[str]:
    """Mutation names that received a reverse primer transfer."""
    with open(csv_path, encoding="utf-8") as fh:
        rows = list(csv.reader(fh))[1:]
    return sorted({r[4] for r in rows if r[1].endswith("_R")})


def test_empty_dedup_info_recomputes_from_state_results(tmp_path):
    """Every mutation keeps its reverse transfer when results are available."""
    _seed_results()
    csv_path = tmp_path / "echo.csv"

    handle_export_mapping({
        "filepath": str(csv_path),
        "format": "echo",
        "mappings": _mappings(),
        "dedup_info": {},
    })

    assert _rev_destinations(csv_path) == ["M1", "M2", "M3"]


def test_empty_dedup_info_without_results_still_raises(tmp_path):
    """Nothing to recompute from means the explicit error must survive."""
    csv_path = tmp_path / "echo.csv"

    with pytest.raises(ValueError) as exc:
        handle_export_mapping({
            "filepath": str(csv_path),
            "format": "echo",
            "mappings": _mappings(),
            "dedup_info": {},
        })

    assert "M2" in str(exc.value)
    assert not csv_path.exists()


def test_frontend_dedup_info_is_used_unchanged(tmp_path):
    """Supplied dedup_info keeps working with no design results in state."""
    csv_path = tmp_path / "echo.csv"

    handle_export_mapping({
        "filepath": str(csv_path),
        "format": "echo",
        "mappings": _mappings(),
        "dedup_info": SHARED_DEDUP,
    })

    assert _rev_destinations(csv_path) == ["M1", "M2", "M3"]


def test_dry_run_recomputes_from_state_results():
    """The Echo preview follows the same fallback ladder as the file export."""
    _seed_results()

    res = handle_export_echo_mapping_dry_run({
        "mappings": _mappings(),
        "dedup_info": {},
    })

    rev_muts = sorted({
        row["mutation"] for row in res["rows"]
        if row["source_well_name"].endswith("_R")
    })
    assert rev_muts == ["M1", "M2", "M3"]
