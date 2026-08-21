"""A swapped primer must take its own diagnostics with it.

``handle_swap_primer`` copies a chosen alternative primer onto the current
result one direction at a time. The field list it copied held five entries
(sequence, binding portion, Tm, length, GC), so hairpin, homodimer, synthesis
score, per-direction tolerance and off-target hits stayed behind. The workbook
and the UI then showed the departed primer's numbers next to the new primer's
sequence, and nothing in the record said so.

Every field asserted here is computed from one direction's sequence alone in
``kuma_core.kuro.sdm_engine`` (``_check_secondary_structure``,
``_check_synthesis``, ``check_offtarget``), which is why it has to travel.
``penalty`` and ``warnings`` are asserted NOT to travel: penalty is one ranking
score summed over both primers, and warnings is one list carrying entries for
both directions.
"""

from __future__ import annotations

import csv
from dataclasses import replace as dc_replace
from pathlib import Path

import pytest

from kuma_core.kuro.sdm_engine import OffTargetHit, SdmPrimerResult
from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.design import (
    _SWAP_FIELDS,
    handle_commit_design_result,
    handle_design_sdm_primers,
    handle_swap_primer,
)
from tests.conftest import TARGET_START

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
GENBANK = FIXTURES_DIR / "pSHCE-dmpR.gb"
EVOLVEPRO_CSV = FIXTURES_DIR / "dmpR_evolvepro.csv"


@pytest.fixture
def restore_state():
    """A real design mutates module-level state; put it back afterwards."""
    with _state_lock:
        saved = (
            list(_state.results),
            dict(_state.candidates),
            list(_state.plate_mappings),
            dict(_state.dedup_info or {}),
            _state.design_provenance,
            list(_state.interventions),
        )
    yield
    with _state_lock:
        (
            _state.results,
            _state.candidates,
            _state.plate_mappings,
            _state.dedup_info,
            _state.design_provenance,
            _state.interventions,
        ) = saved


@pytest.fixture
def designed(restore_state) -> SdmPrimerResult:
    """One real designed result, taken from the engine rather than hand-built."""
    with EVOLVEPRO_CSV.open() as fh:
        mutations = [row["mutation"] for row in csv.DictReader(fh)][:6]
    response = handle_design_sdm_primers({
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "mutations_csv_or_text": "\n".join(mutations),
        "polymerase": "KOD",
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": False,
    })
    assert response["success_count"] > 0, "fixture must design at least one primer"
    raw = response["results"][0]["mutation"]
    with _state_lock:
        return next(r for r in _state.results if r.mutation.raw == raw)


# Values chosen far outside anything the engine produces, so a stale number is
# unmistakable in the assertion output.
_ALT_FWD = dict(
    tolerance_fwd=3.5,
    synthesis_score_fwd=41.0,
    hairpin_tm_fwd=71.5,
    hairpin_dg_fwd=-9.75,
    homodimer_tm_fwd=66.5,
    homodimer_dg_fwd=-8.25,
)
_ALT_REV = dict(
    tolerance_rev=2.5,
    synthesis_score_rev=44.0,
    hairpin_tm_rev=72.5,
    hairpin_dg_rev=-9.25,
    homodimer_tm_rev=65.5,
    homodimer_dg_rev=-7.75,
)
_HIT = OffTargetHit(position=42, strand="sense", match_seq="ACGTACGTACGT", tm=55.5, match_length=12)


def _alternative(current: SdmPrimerResult) -> SdmPrimerResult:
    """A candidate whose every per-direction diagnostic differs from `current`."""
    return dc_replace(
        current,
        forward_seq=current.forward_seq + "AAA",
        reverse_seq=current.reverse_seq + "TTT",
        forward_binding=current.forward_binding + "AAA",
        reverse_binding=current.reverse_binding + "TTT",
        tm_fwd=current.tm_fwd + 3.0,
        tm_rev=current.tm_rev + 3.0,
        penalty=current.penalty + 100.0,
        offtarget_fwd=[_HIT],
        offtarget_rev=[_HIT],
        has_offtarget=True,
        warnings=[
            "Fwd hairpin Tm=71.5C (candidate)",
            "Rev synthesis score 44/100 (candidate)",
            "candidate-only warning",
        ],
        **_ALT_FWD,
        **_ALT_REV,
    )


def _seed(current: SdmPrimerResult) -> tuple[SdmPrimerResult, SdmPrimerResult]:
    """Put `current` in results and one distinguishable alternative in candidates."""
    alt = _alternative(current)
    with _state_lock:
        _state.results = [current]
        _state.candidates = {current.mutation.raw: [alt]}
    return current, alt


def _swap(mutation: str, swap_type: str) -> dict:
    return handle_swap_primer({
        "mutation": mutation, "candidate_idx": 0, "swap_type": swap_type,
    })


@pytest.mark.parametrize("field", sorted(_ALT_FWD))
def test_fwd_swap_carries_the_forward_diagnostics(designed, field):
    current, alt = _seed(designed)
    result = _swap(current.mutation.raw, "fwd")
    assert result[field] == getattr(alt, field), (
        f"{field} still describes the forward primer that was replaced"
    )


@pytest.mark.parametrize("field", sorted(_ALT_REV))
def test_fwd_swap_leaves_the_reverse_diagnostics_alone(designed, field):
    current, _alt = _seed(designed)
    result = _swap(current.mutation.raw, "fwd")
    assert result[field] == pytest.approx(getattr(current, field))


@pytest.mark.parametrize("field", sorted(_ALT_REV))
def test_rev_swap_carries_the_reverse_diagnostics(designed, field):
    current, alt = _seed(designed)
    result = _swap(current.mutation.raw, "rev")
    assert result[field] == getattr(alt, field), (
        f"{field} still describes the reverse primer that was replaced"
    )


@pytest.mark.parametrize("field", sorted(_ALT_FWD))
def test_rev_swap_leaves_the_forward_diagnostics_alone(designed, field):
    current, _alt = _seed(designed)
    result = _swap(current.mutation.raw, "rev")
    assert result[field] == pytest.approx(getattr(current, field))


def test_fwd_swap_carries_the_forward_offtarget_hits(designed):
    current, _alt = _seed(designed)
    assert current.offtarget_fwd == [], "engine candidates start with no hits"
    result = _swap(current.mutation.raw, "fwd")
    assert [h["position"] for h in result["offtarget_fwd"]] == [_HIT.position]
    assert result["offtarget_rev"] == []
    # has_offtarget is the OR over both lists, so it has to follow the swap.
    assert result["has_offtarget"] is True


def test_swapped_offtarget_list_is_not_shared_with_the_candidate(designed):
    current, alt = _seed(designed)
    _swap(current.mutation.raw, "fwd")
    with _state_lock:
        swapped = _state.results[0]
    assert swapped.offtarget_fwd == alt.offtarget_fwd
    assert swapped.offtarget_fwd is not alt.offtarget_fwd


def test_tolerance_used_rises_to_the_swapped_direction(designed):
    """The inequality alone passes on stale data, so pin the value itself."""
    current, alt = _seed(designed)
    assert current.tolerance_used < alt.tolerance_fwd, "fixture must force a rise"
    result = _swap(current.mutation.raw, "fwd")
    assert result["tolerance_fwd"] == alt.tolerance_fwd
    assert result["tolerance_used"] == alt.tolerance_fwd


def test_pair_level_fields_do_not_travel_with_one_primer(designed):
    current, alt = _seed(designed)
    result = _swap(current.mutation.raw, "fwd")
    # penalty is one score summed over both primers, warnings one list for both.
    assert result["penalty"] == pytest.approx(round(current.penalty, 1))
    assert result["penalty"] != pytest.approx(round(alt.penalty, 1))
    # An unprefixed warning has no direction to belong to, so it stays put.
    assert "candidate-only warning" not in result["warnings"]
    assert result["tm_overlap"] == pytest.approx(round(current.tm_overlap, 1))
    assert result["overlap_seq"] == current.overlap_window.sequence


@pytest.mark.parametrize("field", sorted(_ALT_REV))
def test_rev_swap_propagates_diagnostics_to_same_position_mutations(designed, field):
    """A rev swap rewrites every mutation at that position, diagnostics included."""
    current, alt = _seed(designed)
    neighbour = dc_replace(
        current,
        mutation=dc_replace(current.mutation, raw=current.mutation.raw + "b"),
    )
    with _state_lock:
        _state.results = [current, neighbour]
    _swap(current.mutation.raw, "rev")
    with _state_lock:
        updated = next(r for r in _state.results if r.mutation.raw == neighbour.mutation.raw)
    assert updated.reverse_seq == alt.reverse_seq, "propagation precondition"
    assert getattr(updated, field) == getattr(alt, field), (
        f"{field} on the same-position neighbour still describes the old reverse primer"
    )


def test_fwd_swap_takes_the_forward_warnings_and_keeps_the_reverse_ones(designed):
    """Numbers and warning text must describe the same primer after a swap."""
    current, alt = _seed(designed)
    kept = [w for w in current.warnings if w.startswith(("Rev", "Reverse"))]
    dropped = [w for w in current.warnings if w.startswith(("Fwd", "Forward"))]
    assert dropped, "fixture must carry at least one forward warning to drop"

    result = _swap(current.mutation.raw, "fwd")

    assert "Fwd hairpin Tm=71.5C (candidate)" in result["warnings"]
    for text in dropped:
        assert text not in result["warnings"], (
            "a forward warning for the replaced primer survived the swap"
        )
    for text in kept:
        assert text in result["warnings"], "a reverse warning was lost to a fwd swap"
    assert "Rev synthesis score 44/100 (candidate)" not in result["warnings"]


def test_rev_swap_takes_the_reverse_warnings_and_keeps_the_forward_ones(designed):
    current, _alt = _seed(designed)
    kept = [w for w in current.warnings if w.startswith(("Fwd", "Forward"))]
    dropped = [w for w in current.warnings if w.startswith(("Rev", "Reverse"))]
    assert dropped, "fixture must carry at least one reverse warning to drop"

    result = _swap(current.mutation.raw, "rev")

    assert "Rev synthesis score 44/100 (candidate)" in result["warnings"]
    for text in dropped:
        assert text not in result["warnings"]
    for text in kept:
        assert text in result["warnings"]
    assert "Fwd hairpin Tm=71.5C (candidate)" not in result["warnings"]


def test_swapped_warning_list_is_not_shared_with_the_previous_result(designed):
    current, _alt = _seed(designed)
    _swap(current.mutation.raw, "fwd")
    with _state_lock:
        swapped = _state.results[0]
    assert swapped.warnings is not current.warnings


@pytest.mark.parametrize("field", sorted({**_ALT_FWD, **_ALT_REV}))
def test_both_swap_replaces_the_whole_result(designed, field):
    """swap_type='both' takes the candidate whole, diagnostics included."""
    current, alt = _seed(designed)
    result = _swap(current.mutation.raw, "both")
    assert result[field] == getattr(alt, field)


# ---------------------------------------------------------------------------
# The two reverse-propagation paths must not drift apart again
# ---------------------------------------------------------------------------
#
# handle_swap_primer and handle_commit_design_result both rewrite every OTHER
# mutation sharing the swapped position, because those mutations share one
# reverse primer. Each used to carry its own hardcoded list of five fields.
# These tests read the field list from the module, so a path that goes back to
# a hardcoded list fails here the moment _SWAP_FIELDS gains an entry.

def _propagate_by_swap(mutation: str) -> None:
    handle_swap_primer({"mutation": mutation, "candidate_idx": 0, "swap_type": "rev"})


def _propagate_by_commit(mutation: str) -> None:
    handle_commit_design_result({"mutation": mutation, "candidate_idx": 0})


_PROPAGATION_PATHS = {
    "handle_swap_primer": _propagate_by_swap,
    "handle_commit_design_result": _propagate_by_commit,
}


def _seed_with_neighbour(current: SdmPrimerResult) -> SdmPrimerResult:
    """results = [current, same-position neighbour], candidates = [alternative]."""
    alt = _alternative(current)
    neighbour = dc_replace(
        current,
        mutation=dc_replace(current.mutation, raw=current.mutation.raw + "b"),
    )
    with _state_lock:
        _state.results = [current, neighbour]
        _state.candidates = {current.mutation.raw: [alt]}
    return alt


def _neighbour_of(current: SdmPrimerResult) -> SdmPrimerResult:
    with _state_lock:
        return next(
            r for r in _state.results
            if r.mutation.raw == current.mutation.raw + "b"
        )


@pytest.mark.parametrize("path", sorted(_PROPAGATION_PATHS))
@pytest.mark.parametrize("field", _SWAP_FIELDS["rev"])
def test_every_propagation_path_carries_every_reverse_field(designed, path, field):
    current = designed
    alt = _seed_with_neighbour(current)
    _PROPAGATION_PATHS[path](current.mutation.raw)
    updated = _neighbour_of(current)
    assert getattr(updated, field) == getattr(alt, field), (
        f"{path} dropped {field} when propagating to a same-position mutation, "
        "which means that path is not using _SWAP_FIELDS"
    )


@pytest.mark.parametrize("field", sorted(_ALT_FWD))
def test_no_propagation_path_touches_the_forward_direction(designed, field):
    """A neighbour keeps its own forward primer whichever path ran."""
    current = designed
    _seed_with_neighbour(current)
    _PROPAGATION_PATHS["handle_swap_primer"](current.mutation.raw)
    assert getattr(_neighbour_of(current), field) == getattr(current, field)


def test_the_two_propagation_paths_produce_the_same_neighbour(designed):
    """Same input, same result. Per-path tests alone cannot catch a divergence."""
    current = designed
    _seed_with_neighbour(current)
    _PROPAGATION_PATHS["handle_swap_primer"](current.mutation.raw)
    after_swap = _neighbour_of(current)

    _seed_with_neighbour(current)
    _PROPAGATION_PATHS["handle_commit_design_result"](current.mutation.raw)
    after_commit = _neighbour_of(current)

    assert after_swap == after_commit, (
        "handle_swap_primer and handle_commit_design_result disagree on what a "
        "same-position neighbour looks like after a reverse propagation"
    )


# ---------------------------------------------------------------------------
# Cross-layer: the store repeats this propagation on the rows it already holds
# ---------------------------------------------------------------------------
#
# swap_primer replies with the clicked mutation only, so
# src/store/slices/designSlice.helpers.ts has to rewrite the same-position
# neighbours itself. That is a third copy of the field list, in another
# language, and it was four fields behind before this. It cannot be executed
# from here (the frontend runner is off limits on this shared-folder checkout),
# so pin it by reading the file: the names are checked, the arithmetic is not.

_FRONTEND_HELPERS = (
    Path(__file__).parent.parent.parent / "src" / "store" / "slices"
    / "designSlice.helpers.ts"
)

# Backend field -> the name the same value travels under on the wire.
# tm_rev is renamed by _serialize_result; everything else keeps its name.
_BACKEND_TO_FRONTEND = {
    "reverse_seq": "reverse_seq",
    "tm_rev": "tm_no_rev",
    "rev_len": "rev_len",
    "gc_rev": "gc_rev",
    "tolerance_rev": "tolerance_rev",
    "synthesis_score_rev": "synthesis_score_rev",
    "hairpin_tm_rev": "hairpin_tm_rev",
    "hairpin_dg_rev": "hairpin_dg_rev",
    "homodimer_tm_rev": "homodimer_tm_rev",
    "homodimer_dg_rev": "homodimer_dg_rev",
    "offtarget_rev": "offtarget_rev",
}
# Never serialized, so the frontend has no such value to keep in step.
_BACKEND_ONLY = {"reverse_binding"}


def test_reverse_binding_really_is_backend_only():
    """The frontend exemption below is only honest while this holds."""
    from sidecar_kuro.models import SdmPrimerResultModel

    assert "reverse_binding" not in SdmPrimerResultModel.model_fields
    assert "forward_binding" not in SdmPrimerResultModel.model_fields


def test_the_wire_name_table_covers_the_whole_reverse_swap():
    """Adding a reverse field to _SWAP_FIELDS forces a decision about the UI."""
    assert set(_SWAP_FIELDS["rev"]) == set(_BACKEND_TO_FRONTEND) | _BACKEND_ONLY, (
        "a reverse field was added or removed on the backend without saying "
        "what the frontend does with it"
    )


@pytest.mark.parametrize("frontend_field", sorted(set(_BACKEND_TO_FRONTEND.values())))
def test_the_store_propagates_every_reverse_field_the_backend_does(frontend_field):
    body = _FRONTEND_HELPERS.read_text(encoding="utf-8")
    start = body.index("export function applyReversePropagation")
    helper = body[start:]
    # Name presence, not formatting: the field has to be written on the result
    # and its value has to come from the incoming primer.
    assert f"{frontend_field}:" in helper, (
        f"designSlice.helpers.ts does not set {frontend_field} on a "
        "same-position neighbour, so the table will disagree with the export"
    )
    assert f"source.{frontend_field}" in helper, (
        f"designSlice.helpers.ts sets {frontend_field} from something other "
        "than the incoming reverse primer"
    )


def test_the_store_rederives_what_the_backend_rederives():
    body = _FRONTEND_HELPERS.read_text(encoding="utf-8")
    start = body.index("export function applyReversePropagation")
    helper = body[start:]
    for derived in ("has_offtarget:", "tolerance_used:", "warnings:"):
        assert derived in helper, f"{derived} is not re-derived in the store"
    # Copying these instead of re-deriving them is the specific mistake.
    assert "has_offtarget: source.has_offtarget" not in helper
    assert "tolerance_used: source.tolerance_used" not in helper
    assert "warnings: source.warnings" not in helper
