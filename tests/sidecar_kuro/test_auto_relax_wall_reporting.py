"""A failure that survived auto-relax has to say how far the retry went.

The engine's reason states the constraint the main pass applied and nothing
else, so a GC-rich site reads as if the design had never been retried. An
operator who only sees "closest Tm 71.1C at 19 bp, outside 58+-4.0C" reaches
for the codon or the tolerance without knowing that both axes were already
widened and where each one stops.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from kuma_core.kuro.sdm_engine import DEFAULT_REV_LEN_MIN
from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.design import (
    _GC_CEIL,
    _GC_FLOOR,
    _LEN_FLOOR,
    _MAX_TOL_MAX,
    _RELAX_GC_DELTA,
    _RELAX_TOL_DELTA,
    _auto_relax_wall_clause,
    _axis_state,
    _poly_registry,
    _resolved_floor,
    handle_design_sdm_primers,
)
from sidecar_kuro.models import DesignSdmPrimersParams

from tests.conftest import TARGET_START

# What a request carries when the caller sends none of these, which is what
# `_design_synthetic` below does for GC. Read from the model so a changed
# default shows up here rather than in a message nobody checks.
_DEFAULT_GC_MIN: float = DesignSdmPrimersParams.model_fields["gc_min"].default
_DEFAULT_GC_MAX: float = DesignSdmPrimersParams.model_fields["gc_max"].default
_DEFAULT_TOL: float = DesignSdmPrimersParams.model_fields["tol_max"].default

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
GENBANK = FIXTURES_DIR / "sample_sdm_template.gb"
EVOLVEPRO_CSV = FIXTURES_DIR / "sdm_template_evolvepro.csv"

RELAX_MARKER = "- auto-relax: retried at tolerance"

# A synthetic construct that reproduces the reported case on its own terms: the
# 30 bp immediately 5' of the target codon are 90% GC, so every reverse primer
# the length window allows is far above the Tm window, while the rest of the
# sequence is ordinary. Codons are drawn from a fixed balanced set with a fixed
# seed, so the construct is the same on every machine.
_BALANCED = ("GCT", "ACA", "TTG", "CAA", "GAT", "ATC", "AAG", "TCA",
             "CTT", "ATG", "AAC", "TGT")
_GC_RUN = "GCCGGCGCGCCGGCCGGCGCCGGCCGCGGC"
_SYNTHETIC_POLYMERASE = "KOD"
_SYNTHETIC_TARGET_START = 30
_SYNTHETIC_HOT_POSITION = 31
_SYNTHETIC_MILD_POSITION = 50


def _balanced_block(rng: random.Random, codons: int) -> str:
    return "".join(rng.choice(_BALANCED) for _ in range(codons))


@pytest.fixture(scope="module")
def gc_rich_template(tmp_path_factory) -> Path:
    """GenBank template whose target codon sits behind a 90% GC run."""
    rng = random.Random(7)
    head = ["ATG"] + [rng.choice(_BALANCED) for _ in range(19)]
    tail = [rng.choice(_BALANCED) for _ in range(30)]
    # The control site, far enough downstream that no primer around it reaches
    # the GC run, and surrounded by balanced codons on both sides.
    tail[_SYNTHETIC_MILD_POSITION - _SYNTHETIC_HOT_POSITION - 1] = "AAG"
    cds = "".join(head) + _GC_RUN + "AAA" + "".join(tail)
    sequence = _balanced_block(rng, 10) + cds + _balanced_block(rng, 10)
    record = SeqRecord(
        Seq(sequence), id="gcrich", name="gcrich", description="synthetic",
        annotations={"molecule_type": "DNA", "topology": "linear"},
    )
    path = tmp_path_factory.mktemp("gcrich") / "gc_rich_template.gb"
    SeqIO.write(record, str(path), "genbank")
    return path


def _design_synthetic(
    template: Path, mutation: str, *, auto_relax: bool, tol_max: float = 4.0,
) -> dict:
    return handle_design_sdm_primers({
        "fasta_path": str(template),
        "target_start": _SYNTHETIC_TARGET_START,
        "mutations_csv_or_text": mutation,
        "polymerase": _SYNTHETIC_POLYMERASE,
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": auto_relax,
        "tol_max": tol_max,
    })


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


def _design(mutation_text: str, *, auto_relax: bool, tol_max: float = 4.0) -> dict:
    return handle_design_sdm_primers({
        "fasta_path": str(GENBANK),
        "target_start": TARGET_START,
        "mutations_csv_or_text": mutation_text,
        "polymerase": _SYNTHETIC_POLYMERASE,
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": auto_relax,
        "tol_max": tol_max,
    })


def test_clause_names_only_the_axis_that_reached_its_limit():
    """Each axis has three states and the clause must not conflate them."""
    # Tolerance widened with room left: the remaining room is the actionable
    # part, and no tolerance wall is claimed.
    relaxed_tol = _DEFAULT_TOL + _RELAX_TOL_DELTA
    relaxed_gc = (_DEFAULT_GC_MIN - _RELAX_GC_DELTA, _DEFAULT_GC_MAX + _RELAX_GC_DELTA)
    headroom = _auto_relax_wall_clause(
        _DEFAULT_TOL, relaxed_tol, [("forward", 22, 20), ("reverse", 22, 20)],
        (_DEFAULT_GC_MIN, relaxed_gc[0], _DEFAULT_GC_MAX, relaxed_gc[1]),
    )
    assert "raised by hand" in headroom
    assert "maximum" not in headroom.replace(f"+-{_MAX_TOL_MAX:.1f}C.", "")
    assert f"{_LEN_FLOOR} bp" not in headroom
    # All three widened axes are named, with the values the deltas produce.
    assert f"tolerance +-{_DEFAULT_TOL:.1f}->+-{relaxed_tol:.1f}C" in headroom
    assert "forward 22->20 bp, reverse 22->20 bp" in headroom
    assert (f"GC {_DEFAULT_GC_MIN:g}-{_DEFAULT_GC_MAX:g}->"
            f"{relaxed_gc[0]:g}-{relaxed_gc[1]:g}%") in headroom
    assert f"opens it no further than {_GC_FLOOR}-{_GC_CEIL}%" in headroom

    # Tolerance clamped by the relax pass, both length floors at the minimum.
    clamped = _auto_relax_wall_clause(
        9.0, _MAX_TOL_MAX, [("forward", 19, _LEN_FLOOR), ("reverse", 19, _LEN_FLOOR)],
        (40.0, 35.0, 60.0, 65.0),
    )
    assert f"+-{_MAX_TOL_MAX:.1f}C maximum" in clamped
    assert "had no room" not in clamped
    assert f"forward and reverse length floors are at the {_LEN_FLOOR} bp" in clamped

    # Tolerance was already at the cap, so widening was never possible.
    capped = _auto_relax_wall_clause(
        _MAX_TOL_MAX, _MAX_TOL_MAX, [("forward", 22, 20), ("reverse", 19, _LEN_FLOOR)],
        (40.0, 35.0, 60.0, 65.0),
    )
    assert "had no room" in capped
    # Only the side that reached the floor is named.
    assert f"reverse length floor is at the {_LEN_FLOOR} bp" in capped
    assert "forward and reverse length" not in capped
    assert "forward 22->20 bp" in capped


def test_clause_separates_the_three_states_of_the_gc_axis():
    """GC is widened on both sides, so each end can reach its limit alone."""
    floors = [("forward", 22, 20), ("reverse", 22, 20)]

    # Only the floor was reached: the ceiling still has room, and naming both
    # would tell an operator the window is shut when half of it is not.
    at_floor = _auto_relax_wall_clause(
        4.0, 6.0, floors,
        (float(_GC_FLOOR) + 2, float(_GC_FLOOR),
         _DEFAULT_GC_MAX, _DEFAULT_GC_MAX + _RELAX_GC_DELTA),
    )
    assert (f"GC window is at the {_GC_FLOOR}% edge relaxation does not open "
            "past.") in at_floor
    assert f"{_GC_CEIL}%" not in at_floor

    at_ceiling = _auto_relax_wall_clause(
        4.0, 6.0, floors,
        (_DEFAULT_GC_MIN, _DEFAULT_GC_MIN - _RELAX_GC_DELTA,
         float(_GC_CEIL) - 2, float(_GC_CEIL)),
    )
    assert f"GC window is at the {_GC_CEIL}% edge" in at_ceiling

    both_ends = _auto_relax_wall_clause(
        4.0, 6.0, floors,
        (float(_GC_FLOOR) + 2, float(_GC_FLOOR), float(_GC_CEIL) - 2, float(_GC_CEIL)),
    )
    assert f"GC window is at the {_GC_FLOOR}% and {_GC_CEIL}% edges" in both_ends

    # The request already spanned the whole range relaxation opens, so the
    # relax pass had nothing to widen rather than having widened up to a wall.
    no_room = _auto_relax_wall_clause(
        4.0, 6.0, floors,
        (float(_GC_FLOOR), float(_GC_FLOOR), float(_GC_CEIL), float(_GC_CEIL)),
    )
    assert f"GC window already spanned {_GC_FLOOR}-{_GC_CEIL}%" in no_room
    assert "is at the" not in no_room


def test_clause_prints_a_request_wider_than_relaxation_opens():
    """A request may ask for more GC than the relax pass will hand the engine.

    `gc_min`/`gc_max` accept 0-100 while the relax pass clamps to
    _GC_FLOOR.._GC_CEIL, so a 10-90 request is narrowed rather than widened.
    The clause prints both numbers instead of implying the window grew, and
    fractional bounds survive the formatting rather than being rounded away.
    """
    narrowed = _auto_relax_wall_clause(
        4.0, 6.0, [("forward", 22, 20), ("reverse", 22, 20)],
        (10.5, float(_GC_FLOOR), 90.0, float(_GC_CEIL)),
    )
    assert f"GC 10.5-90->{_GC_FLOOR}-{_GC_CEIL}%" in narrowed
    assert "lower and upper ends were tightened rather than widened" in narrowed
    # The request was outside the bounds, not level with them, so the clause
    # must not claim the window already spanned what relaxation opens.
    assert "already spanned" not in narrowed
    assert "does not open past" not in narrowed


def test_a_clamp_that_tightens_is_never_reported_as_a_wall():
    """The three inputs where relaxation constrains more than the request.

    Each clamp is max(limit, x - d) or min(limit, x + d), so a request outside
    the limit comes back tighter. Saying the search reached a wall there states
    the opposite of what the relax pass did with that run's settings.
    """
    floors = [("forward", 22, 20), ("reverse", 22, 20)]

    # One GC bound outside the limit, the other with room left.
    one_end = _auto_relax_wall_clause(
        4.0, 6.0, floors, (10.0, float(_GC_FLOOR), 60.0, 65.0),
    )
    assert f"keeps GC inside {_GC_FLOOR}-{_GC_CEIL}%" in one_end
    assert "its lower end was tightened rather than widened" in one_end
    assert "upper" not in one_end
    assert "does not open past" not in one_end

    # The widest window the model accepts, which relaxation shrinks on both
    # sides. The old wording called this "already spanned 20-80%".
    both_ends = _auto_relax_wall_clause(
        4.0, 6.0, floors, (0.0, float(_GC_FLOOR), 100.0, float(_GC_CEIL)),
    )
    assert f"GC 0-100->{_GC_FLOOR}-{_GC_CEIL}%" in both_ends
    assert "lower and upper ends were tightened" in both_ends
    assert "already spanned" not in both_ends

    # rev_len_min accepts 10, which the relax pass raises to the 18 bp floor.
    # The forward side is untouched at the floor and keeps the wall wording,
    # so one clause carries both statements without conflating them.
    raised = _auto_relax_wall_clause(
        4.0, 6.0,
        [("forward", _LEN_FLOOR, _LEN_FLOOR), ("reverse", 10, _LEN_FLOOR)],
        (40.0, 35.0, 60.0, 65.0),
    )
    assert (f"reverse length floor was raised to the {_LEN_FLOOR} bp minimum "
            "relaxation keeps to, not lowered.") in raised
    assert f"forward length floor is at the {_LEN_FLOOR} bp minimum" in raised
    assert "forward and reverse" not in raised


@pytest.mark.parametrize(
    ("requested", "relaxed", "limit", "higher_is_looser", "expected"),
    [
        # Length floor and GC lower bound: a smaller number is the looser one.
        (10, _LEN_FLOOR, _LEN_FLOOR, False, "narrowed"),
        (_LEN_FLOOR, _LEN_FLOOR, _LEN_FLOOR, False, "no_room"),
        (_LEN_FLOOR + 1, _LEN_FLOOR, _LEN_FLOOR, False, "at_limit"),
        (22, 20, _LEN_FLOOR, False, "room"),
        # Tolerance and GC upper bound: a larger number is the looser one.
        (_MAX_TOL_MAX + 1, _MAX_TOL_MAX, _MAX_TOL_MAX, True, "narrowed"),
        (_MAX_TOL_MAX, _MAX_TOL_MAX, _MAX_TOL_MAX, True, "no_room"),
        (_MAX_TOL_MAX - 1, _MAX_TOL_MAX, _MAX_TOL_MAX, True, "at_limit"),
        (4.0, 6.0, _MAX_TOL_MAX, True, "room"),
    ],
)
def test_axis_state_judges_every_axis_by_one_rule(
    requested, relaxed, limit, higher_is_looser, expected,
):
    """One judgement for all three axes, read in both directions."""
    assert _axis_state(
        requested, relaxed, limit, higher_is_looser=higher_is_looser,
    ) == expected


def test_gc_rich_site_reports_the_length_wall(gc_rich_template, restore_state):
    """Reverse primer too hot behind a 90% GC run, the reported case.

    At default settings the length axis is the one that ran out: both floors
    sit on 18 bp. Tolerance was widened to 6.0C and has room left to 10.0C,
    which is what an operator can still act on, so the message says so rather
    than claiming a wall the relax pass did not reach.
    """
    res = _design_synthetic(
        gc_rich_template, f"K{_SYNTHETIC_HOT_POSITION}N", auto_relax=True,
    )
    assert res["success_count"] == 0
    reason = res["failed_mutations"][0]["reason"]
    assert reason.startswith("No valid primer pair - reverse: closest Tm")
    assert RELAX_MARKER in reason
    # Where that floor comes from, resolved the way the handler resolves it.
    # The request leaves the length to the polymerase, so the KOD profile
    # supplies it and DEFAULT_REV_LEN_MIN is only the last fallback. The two
    # happen to hold the same number, so naming the wrong one would pass.
    expected_rev_floor = _resolved_floor(
        None, _poly_registry.get(_SYNTHETIC_POLYMERASE).rev_len_min,
        DEFAULT_REV_LEN_MIN,
    )
    assert f"reverse {expected_rev_floor}->{_LEN_FLOOR} bp" in reason
    assert f"length floors are at the {_LEN_FLOOR} bp minimum" in reason
    assert f"raised by hand to +-{_MAX_TOL_MAX:.1f}C" in reason
    # The settings the relax pass actually used, derived from the deltas rather
    # than written out, so changing a delta fails here instead of silently
    # shipping a message that describes the old one.
    assert (f"tolerance +-{_DEFAULT_TOL:.1f}->"
            f"+-{_DEFAULT_TOL + _RELAX_TOL_DELTA:.1f}C") in reason
    assert (f"GC {_DEFAULT_GC_MIN:g}-{_DEFAULT_GC_MAX:g}->"
            f"{_DEFAULT_GC_MIN - _RELAX_GC_DELTA:g}-"
            f"{_DEFAULT_GC_MAX + _RELAX_GC_DELTA:g}%") in reason


def test_tolerance_cap_is_named_when_the_request_already_sat_on_it(
    gc_rich_template, restore_state,
):
    """At the cap the Tm axis had no room, and the message must not offer it."""
    res = _design_synthetic(
        gc_rich_template, f"K{_SYNTHETIC_HOT_POSITION}N",
        auto_relax=True, tol_max=_MAX_TOL_MAX,
    )
    reason = res["failed_mutations"][0]["reason"]
    assert f"+-{_MAX_TOL_MAX:.1f}->+-{_MAX_TOL_MAX:.1f}C" in reason
    assert "had no room" in reason
    assert "raised by hand" not in reason


def test_ordinary_site_in_the_same_construct_designs(
    gc_rich_template, restore_state,
):
    """Negative control: outside the GC run the same template designs."""
    res = _design_synthetic(
        gc_rich_template, f"K{_SYNTHETIC_MILD_POSITION}N", auto_relax=True,
    )
    assert res["success_count"] == 1
    assert res["failed_mutations"] == []


def test_gc_rich_site_says_nothing_about_relax_when_it_is_off(
    gc_rich_template, restore_state,
):
    res = _design_synthetic(
        gc_rich_template, f"K{_SYNTHETIC_HOT_POSITION}N", auto_relax=False,
    )
    assert res["failed_mutations"]
    assert RELAX_MARKER not in res["failed_mutations"][0]["reason"]


def test_nothing_is_appended_when_auto_relax_is_off(mutation_text, restore_state):
    """Negative control: the clause must not ride on every failure."""
    res = _design(mutation_text, auto_relax=False)
    assert res["failed_mutations"]
    for failed in res["failed_mutations"]:
        assert RELAX_MARKER not in failed["reason"]


def test_designed_mutations_are_untouched(mutation_text, restore_state):
    """Negative control: a normal-GC site designs and never reaches the list."""
    res = _design(mutation_text, auto_relax=True)
    failed_names = {f["mutation"] for f in res["failed_mutations"]}
    designed = {r["mutation"] for r in res["results"]}
    assert designed
    assert not (designed & failed_names)


def test_unparsed_row_keeps_its_own_reason(mutation_text, restore_state):
    """A row the relax pass never designed must not claim it was retried."""
    res = _design(mutation_text + "\nnot-a-mutation", auto_relax=True)
    bad = [f for f in res["failed_mutations"] if f["mutation"] == "not-a-mutation"]
    assert bad, "the malformed row must still be reported"
    assert RELAX_MARKER not in bad[0]["reason"]


def test_failed_entry_keys_are_unchanged(mutation_text, restore_state):
    """The clause rides inside reason; no new key crosses the layer boundary."""
    res = _design(mutation_text, auto_relax=True)
    for failed in res["failed_mutations"]:
        assert set(failed) == {"mutation", "rank", "reason"}
