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

from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.design import (
    _GC_CEIL,
    _GC_FLOOR,
    _LEN_FLOOR,
    _MAX_TOL_MAX,
    _auto_relax_wall_clause,
    handle_design_sdm_primers,
)

from tests.conftest import TARGET_START

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
        "polymerase": "KOD",
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
        "polymerase": "KOD",
        "overlap_len": 18,
        "rescue_pool": [],
        "auto_relax": auto_relax,
        "tol_max": tol_max,
    })


def test_clause_names_only_the_axis_that_reached_its_limit():
    """Each axis has three states and the clause must not conflate them."""
    # Tolerance widened with room left: the remaining room is the actionable
    # part, and no tolerance wall is claimed.
    headroom = _auto_relax_wall_clause(
        4.0, 6.0, [("forward", 22, 20), ("reverse", 22, 20)], (40.0, 35.0, 60.0, 65.0),
    )
    assert "raised by hand" in headroom
    assert "maximum" not in headroom.replace(f"+-{_MAX_TOL_MAX:.1f}C.", "")
    assert f"{_LEN_FLOOR} bp" not in headroom
    # All three widened axes are named, with the values they were widened to.
    assert "tolerance +-4.0->+-6.0C" in headroom
    assert "forward 22->20 bp, reverse 22->20 bp" in headroom
    assert "GC 40-60->35-65%" in headroom
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
        4.0, 6.0, floors, (float(_GC_FLOOR) + 2, float(_GC_FLOOR), 60.0, 65.0),
    )
    assert f"GC window is at the {_GC_FLOOR}% edge relaxation does not open past." in at_floor
    assert f"{_GC_CEIL}%" not in at_floor

    at_ceiling = _auto_relax_wall_clause(
        4.0, 6.0, floors, (40.0, 35.0, float(_GC_CEIL) - 2, float(_GC_CEIL)),
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
    assert f"GC window already spanned {_GC_FLOOR}-{_GC_CEIL}%" in narrowed


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
    assert f"reverse 19->{_LEN_FLOOR} bp" in reason
    assert f"length floors are at the {_LEN_FLOOR} bp minimum" in reason
    assert f"raised by hand to +-{_MAX_TOL_MAX:.1f}C" in reason


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
