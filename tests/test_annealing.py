"""Tests for kuro.annealing per-enzyme annealing temperature (Ta).

Covers the 4-field contract for all 8 built-in profiles: the Ta formula and
mode, the 2-step promotion thresholds (tested at the exact boundary), the
DreamTaq Wallace/NN length cutoff, the TAKARA_GXL discrete fixed step, KOD
touchdown, and graceful None for rule-less / empty inputs.

Design invariance (the design-time Tm scale is untouched) is proven separately
in the completion report by diffing tm_no_fwd/tm_no_rev/tm_overlap before and
after; Ta is an additive output only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.kuro import neb_tm
from kuma_core.kuro.annealing import (
    _apply_rule,
    _binding_tm,
    compute_annealing,
    wallace_tm,
)
from kuma_core.kuro.polymerase import PolymeraseProfile, PolymeraseRegistry
from kuma_core.kuro.sdm_engine import design_sdm_primers

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(scope="module")
def registry() -> PolymeraseRegistry:
    return PolymeraseRegistry()


@pytest.fixture(scope="module")
def offsets() -> dict:
    return neb_tm.load_offsets()


def _rule(registry: PolymeraseRegistry, name: str) -> dict:
    rule = registry.get(name).ta_rule
    assert rule is not None, f"{name} must carry a ta_rule"
    return rule


# --------------------------------------------------------------------------
# Wallace helper
# --------------------------------------------------------------------------

def test_wallace_formula_exact():
    # 2*(A+T) + 4*(G+C) - 5
    assert wallace_tm("AAAA") == 2 * 4 - 5          # 3
    assert wallace_tm("GGGG") == 4 * 4 - 5          # 11
    assert wallace_tm("ATGC") == 2 * 2 + 4 * 2 - 5  # 7


def test_wallace_is_case_insensitive():
    assert wallace_tm("atgc") == wallace_tm("ATGC")


# --------------------------------------------------------------------------
# _apply_rule: pure decision logic at exact thresholds
# --------------------------------------------------------------------------

def test_benchling_3step_minus5(registry):
    out = _apply_rule(60.0, _rule(registry, "Benchling"))
    assert out["ta_mode"] == "3step"
    assert out["recommended_ta"] == 55.0  # 60 - 5
    assert out["ta_touchdown"] is None


def test_taq_3step_minus5(registry):
    out = _apply_rule(64.0, _rule(registry, "Taq"))
    assert out["ta_mode"] == "3step"
    assert out["recommended_ta"] == 59.0  # 64 - 5


def test_phusion_3step_plus3_below_threshold(registry):
    out = _apply_rule(65.0, _rule(registry, "Phusion"))
    assert out["ta_mode"] == "3step"
    assert out["recommended_ta"] == 68.0  # 65 + 3


def test_phusion_2step_at_exactly_72(registry):
    out = _apply_rule(72.0, _rule(registry, "Phusion"))
    assert out["ta_mode"] == "2step"
    assert out["recommended_ta"] == 72.0
    assert "2-step" in out["ta_detail"]


def test_phusion_3step_just_below_72(registry):
    out = _apply_rule(71.9, _rule(registry, "Phusion"))
    assert out["ta_mode"] == "3step"


def test_q5_3step_plus1(registry):
    out = _apply_rule(66.0, _rule(registry, "Q5"))
    assert out["ta_mode"] == "3step"
    assert out["recommended_ta"] == 67.0  # 66 + 1


def test_q5_2step_at_exactly_72(registry):
    out = _apply_rule(72.0, _rule(registry, "Q5"))
    assert out["ta_mode"] == "2step"
    assert out["recommended_ta"] == 72.0


def test_q5_sdm_no_2step_even_above_72(registry):
    # Q5 SDM has no two_step_threshold: stays 3-step at high Tm.
    out = _apply_rule(75.0, _rule(registry, "Q5 SDM"))
    assert out["ta_mode"] == "3step"
    assert out["recommended_ta"] == 78.0  # 75 + 3


def test_kod_3step_minus5_with_touchdown(registry):
    out = _apply_rule(70.0, _rule(registry, "KOD"))
    assert out["ta_mode"] == "3step"
    assert out["recommended_ta"] == 65.0  # 70 - 5
    assert out["ta_touchdown"] == "74→72→70→68°C (step-down, ~5 cyc each)"


def test_kod_2step_at_exactly_73(registry):
    out = _apply_rule(73.0, _rule(registry, "KOD"))
    assert out["ta_mode"] == "2step"
    assert out["recommended_ta"] == 68.0
    # touchdown is always emitted for KOD (manufacturer step-down)
    assert out["ta_touchdown"] is not None


def test_gxl_fixed_low_at_boundary_55(registry):
    # <=55 -> low (55); >55 -> high (60)
    out = _apply_rule(55.0, _rule(registry, "TAKARA_GXL"))
    assert out["ta_mode"] == "fixed"
    assert out["recommended_ta"] == 55.0


def test_gxl_fixed_high_above_55(registry):
    out = _apply_rule(57.0, _rule(registry, "TAKARA_GXL"))
    assert out["ta_mode"] == "fixed"
    assert out["recommended_ta"] == 60.0


def test_dreamtaq_3step_minus5(registry):
    out = _apply_rule(60.0, _rule(registry, "DreamTaq"))
    assert out["ta_mode"] == "3step"
    assert out["recommended_ta"] == 55.0  # 60 - 5


# --------------------------------------------------------------------------
# _binding_tm: source dispatch and the DreamTaq Wallace/NN cutoff
# --------------------------------------------------------------------------

def test_dreamtaq_wallace_below_25nt(registry, offsets):
    profile = registry.get("DreamTaq")
    seq24 = "ATGCATGCATGCATGCATGCATGC"  # 24 nt -> Wallace
    assert len(seq24) == 24
    got = _binding_tm(seq24, profile, profile.ta_rule, offsets)
    assert got == wallace_tm(seq24)


def test_dreamtaq_nn_at_25nt(registry, offsets):
    profile = registry.get("DreamTaq")
    seq25 = "ATGCATGCATGCATGCATGCATGCA"  # 25 nt -> NN (>= cutoff)
    assert len(seq25) == 25
    got = _binding_tm(seq25, profile, profile.ta_rule, offsets)
    assert got != wallace_tm(seq25)  # nearest-neighbour, not Wallace


def test_neb_source_matches_calibrated_path(registry, offsets):
    profile = registry.get("Q5")
    seq = "GCTAGCTAGCGGATCCAAAGGTGCTGACC"
    got = _binding_tm(seq, profile, profile.ta_rule, offsets)
    assert got == pytest.approx(neb_tm.neb_estimated_tm(seq, "q5"))


# --------------------------------------------------------------------------
# compute_annealing: graceful handling
# --------------------------------------------------------------------------

def test_none_when_no_ta_rule(offsets):
    custom = PolymeraseProfile(
        name="Custom", tm_method="santalucia", salt_correction="owczarzy",
        opt_tm=60.0, min_tm=55.0, max_tm=65.0, opt_size=20, min_size=15,
        max_size=25, min_gc=40.0, max_gc=60.0, salt_monovalent=50.0,
        salt_divalent=1.5, dntp_conc=0.8, dna_conc=250.0, max_tm_diff=3.0,
    )
    out = compute_annealing("ATGCATGCATGCATGCAT", "ATGCATGCATGCATGCAT", custom, offsets)
    assert out == {
        "recommended_ta": None, "ta_mode": None,
        "ta_detail": None, "ta_touchdown": None,
    }


def test_none_on_empty_sequence(registry, offsets):
    profile = registry.get("Q5")
    out = compute_annealing("", "ATGCATGCATGCATGCAT", profile, offsets)
    assert out["recommended_ta"] is None


def test_uses_lower_of_pair(registry, offsets):
    # A weak reverse primer must pull Ta down (min of the pair, not fwd only).
    profile = registry.get("Benchling")
    strong = "GCGCGCGCGCGCGCGCGCGCGC"
    weak = "ATATATATATATATATAT"
    out_pair = compute_annealing(strong, weak, profile, offsets)
    out_weak_only = compute_annealing(weak, weak, profile, offsets)
    assert out_pair["recommended_ta"] == out_weak_only["recommended_ta"]


# --------------------------------------------------------------------------
# End-to-end on the fixture: every profile yields a physical Ta
# --------------------------------------------------------------------------

_ALL_PROFILES = [
    "Benchling", "Taq", "Phusion", "Q5", "KOD", "DreamTaq", "TAKARA_GXL", "Q5 SDM",
]


@pytest.mark.parametrize("name", _ALL_PROFILES)
def test_end_to_end_physical_ta(registry, offsets, name):
    gb = FIXTURES / "pSHCE-dmpR.gb"
    muts = FIXTURES / "mutation_list_insilico_test.csv"
    kw = {"overlap_mode": "full"} if name == "Q5 SDM" else {}
    results, _c, _f = design_sdm_primers(
        fasta_path=gb, target_start=1790, mutations_csv=muts, polymerase=name, **kw,
    )
    assert results, f"{name} produced no primers on the fixture"
    profile = registry.get(name)
    r = results[0]
    out = compute_annealing(r.forward_seq, r.reverse_seq, profile, offsets)
    assert out["recommended_ta"] is not None
    # Physical window: never the pre-fix 81.5-style artefact.
    assert 40.0 <= out["recommended_ta"] <= 80.0
    assert out["ta_mode"] in ("3step", "2step", "fixed")
    assert out["ta_detail"]


def test_gxl_end_to_end_is_discrete(registry, offsets):
    gb = FIXTURES / "pSHCE-dmpR.gb"
    muts = FIXTURES / "mutation_list_insilico_test.csv"
    results, _c, _f = design_sdm_primers(
        fasta_path=gb, target_start=1790, mutations_csv=muts, polymerase="TAKARA_GXL",
    )
    profile = registry.get("TAKARA_GXL")
    for r in results:
        out = compute_annealing(r.forward_seq, r.reverse_seq, profile, offsets)
        assert out["ta_mode"] == "fixed"
        assert out["recommended_ta"] in (55.0, 60.0)  # discrete steps only
