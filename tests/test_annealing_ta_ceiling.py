"""Regression guards for the Ta ceiling and the Phusion short-primer branch.

Two defects are pinned here.

1. Annealing above extension. The 3-step branch used to be unbounded for any
   profile whose ``ta_rule`` carried a positive ``delta`` and no two-step
   demotion, so Q5 SDM (delta +3, thresholds null) reported 74 to 79 C on the
   ``pSHCE-dmpR.gb`` fixture while its own NEB E0554 cycling table runs
   extension at 72 C. A program that anneals hotter than it extends is not
   runnable. The same root cause let Q5 escape demotion at Tm(low) 71.7 and
   report 73 C, because the threshold was compared against the raw Tm instead
   of the annealing temperature the NEB text actually names.

2. Phusion short primers. NEB E0553 section 7 / M0530 section 8: primers
   longer than 20 nt anneal at Tm(low) + 3, but "if the primer length is less
   than 20 nucleotides, an annealing temperature equivalent to the Tm of the
   lower primer should be used". The fixture designs 18 to 19 nt primers, so
   the missing branch overheated those pairs by 3 C.

Fixture-level numbers are asserted as properties (a ceiling, a per-profile
count) rather than transcribed tables, so the guard stays true when the
design path legitimately shifts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.kuro import neb_tm
from kuma_core.kuro.annealing import _apply_rule, compute_annealing
from kuma_core.kuro.polymerase import PolymeraseRegistry

FIXTURES = Path(__file__).parent.parent / "fixtures"

# Every NEB profile shares one extension step; the ceiling is read from the
# profiles, never hard-coded here.
_ALL_PROFILES = [
    "Benchling", "Taq", "Phusion", "Q5", "KOD", "DreamTaq", "TAKARA_GXL", "Q5 SDM",
]


@pytest.fixture(scope="module")
def registry() -> PolymeraseRegistry:
    return PolymeraseRegistry()


@pytest.fixture(scope="module")
def offsets() -> dict:
    return neb_tm.load_offsets()


def _rule(registry: PolymeraseRegistry, name: str) -> dict:
    rule = registry.get(name).ta_rule
    assert rule is not None
    return rule


# --------------------------------------------------------------------------
# 1. Ta ceiling
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["Q5", "Q5 SDM", "Phusion"])
def test_neb_profiles_declare_a_two_step_ceiling(registry, name):
    # The bound must come from the profile, not from a constant in the code.
    rule = _rule(registry, name)
    assert rule["two_step_threshold"] is not None
    assert rule["two_step_temp"] is not None
    assert rule["two_step_basis"] == "ta"
    assert rule["detail_2step"]


@pytest.mark.parametrize("name", ["Q5", "Q5 SDM", "Phusion"])
def test_ta_never_exceeds_the_declared_ceiling(registry, name):
    # Sweep the whole plausible Tm range; the 3-step branch must hand off to
    # the 2-step branch before Ta passes the profile ceiling.
    rule = _rule(registry, name)
    ceiling = float(rule["two_step_temp"])
    for tenth in range(400, 901):  # 40.0 to 90.0 C
        out = _apply_rule(tenth / 10.0, rule)
        assert out["recommended_ta"] <= ceiling, (name, tenth / 10.0, out)


def test_q5_demotes_on_computed_ta_not_raw_tm(registry):
    # Q5 delta is +1 and Ta is reported in whole degrees, so the Tm boundary
    # lands near 70.5, not 72. Tm 71.7 (the fixture Y155A pair) used to escape
    # demotion and report 73 C.
    rule = _rule(registry, "Q5")
    assert _apply_rule(70.4, rule)["ta_mode"] == "3step"
    assert _apply_rule(71.7, rule) == {
        **_apply_rule(71.7, rule),
        "ta_mode": "2step",
        "recommended_ta": 72.0,
    }


def test_kod_keeps_its_tm_based_threshold(registry):
    # Toyobo states the KOD One threshold on the primer Tm, not on Ta, so the
    # per-profile basis must leave it alone (Ta would be Tm - 5).
    rule = _rule(registry, "KOD")
    assert rule["two_step_basis"] == "tm"
    assert _apply_rule(73.0, rule)["ta_mode"] == "2step"
    assert _apply_rule(72.9, rule)["ta_mode"] == "3step"


@pytest.mark.parametrize("name", _ALL_PROFILES)
def test_fixture_ta_never_above_extension(registry, offsets, name):
    from kuma_core.kuro.sdm_engine import design_sdm_primers

    kw = {"overlap_mode": "full"} if name == "Q5 SDM" else {}
    designed, _c, _f = design_sdm_primers(
        fasta_path=FIXTURES / "pSHCE-dmpR.gb",
        target_start=1790,
        mutations_csv=FIXTURES / "mutation_list_insilico_test.csv",
        polymerase=name,
        **kw,
    )
    assert designed, f"{name} produced no primers on the fixture"
    profile = registry.get(name)
    for r in designed:
        out = compute_annealing(r.forward_seq, r.reverse_seq, profile, offsets)
        # 72 C is the extension step every one of these enzymes runs.
        assert out["recommended_ta"] <= 72.0, (name, r.mutation.raw, out)


def test_q5_sdm_fixture_yield_claims(registry):
    """Pin the Q5 SDM fixture yield facts that stale prose had inverted.

    Comments and docs asserted "full yield 6/12 to 4/12 (lost: D227A, E335A)"
    and "partial mode is 0/12". Both are false against the fixture. Asserted
    here as properties (which mutations design, which mode wins) so the claim
    lives next to a runnable check instead of in prose. Ta-independent: the
    design path is untouched by the Ta rules.
    """
    from kuma_core.kuro.sdm_engine import design_sdm_primers

    def _designed(mode: str) -> set[str]:
        designed, _c, _f = design_sdm_primers(
            fasta_path=FIXTURES / "pSHCE-dmpR.gb",
            target_start=1790,
            mutations_csv=FIXTURES / "mutation_list_insilico_test.csv",
            polymerase="Q5 SDM",
            overlap_mode=mode,
        )
        return {r.mutation.raw for r in designed}

    full = _designed("full")
    partial = _designed("partial")
    assert {"D227A", "E335A"} <= full     # not "lost"
    assert partial                        # not 0/12
    assert len(full) > len(partial)       # full is the kit default for a reason


# --------------------------------------------------------------------------
# 2. Phusion short-primer branch
# --------------------------------------------------------------------------

def test_phusion_declares_the_short_primer_branch(registry):
    rule = _rule(registry, "Phusion")
    assert rule["short_primer_len"] == 20
    assert rule["short_primer_delta"] == 0


def test_phusion_short_primer_uses_tm_itself(registry):
    rule = _rule(registry, "Phusion")
    # 19 nt: Ta == Tm(low). 20 nt: back to Tm(low) + 3.
    assert _apply_rule(62.0, rule, 19)["recommended_ta"] == 62.0
    assert _apply_rule(62.0, rule, 20)["recommended_ta"] == 65.0
    # No length supplied: unchanged long-primer behaviour.
    assert _apply_rule(62.0, rule)["recommended_ta"] == 65.0


def test_phusion_short_primer_end_to_end(registry, offsets):
    # An 18 nt / 24 nt pair: the 18 nt primer is the weaker one, so the whole
    # pair drops to its Tm with no +3.
    profile = registry.get("Phusion")
    short = "ATATATATATATATATAT"          # 18 nt, low Tm
    long = "GCGCGCGCGCGCGCGCGCGCGCGC"     # 24 nt, high Tm
    out = compute_annealing(short, long, profile, offsets)
    long_only = compute_annealing(long, long, profile, offsets)
    assert out["ta_mode"] == "3step"
    assert out["recommended_ta"] < long_only["recommended_ta"]
    assert "20 nt" in out["ta_detail"]


def test_short_primer_branch_is_opt_in_per_profile(registry):
    # Profiles without the branch ignore the length argument entirely.
    for name in ("Q5", "Taq", "KOD", "DreamTaq", "Benchling"):
        rule = _rule(registry, name)
        assert rule["short_primer_len"] is None
        assert _apply_rule(62.0, rule, 18) == _apply_rule(62.0, rule)
