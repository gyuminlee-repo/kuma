"""Tests for al.pilot pure-function logic (ceiling extrapolation + Gate G1 verdict).

The end-to-end run_pilot_assay (real ESM-2 + EVOLVEpro) is exercised by the live
pilot that writes results/qa/gate_g1.json; here we lock the deterministic logic.
"""

from __future__ import annotations

from al.pilot import CEILING_CPU_HOURS, extrapolate_ceiling, gate_g1


def test_extrapolate_ceiling_math():
    from al import arms as arms_mod
    n_arms = len(arms_mod.ARMS)
    c = extrapolate_ceiling(6.0, n_assays=217, n_signals=2, n_seeds=10)
    # 217 * n_arms * 2 signals * 10 seeds
    assert c["total_cells"] == 217 * n_arms * 2 * 10
    assert c["projected_cpu_hours"] == round(c["total_cells"] * 6.0 / 3600.0, 2)
    assert c["within_ceiling"] is True  # ~43 CPU-hr at 6 arms, still <= 72
    # a slow loop blows the ceiling
    slow = extrapolate_ceiling(60.0)
    assert slow["within_ceiling"] is False


def test_gate_g1_all_pass():
    pilot = [{
        "per_arm": {"topn": {"coverage": {"kcenter_radius": 1.0}},
                     "domain_every": {"coverage": {"kcenter_radius": 0.8}}},
        "axis_relevance": {"axis_relevant": False, "label": "axis-mismatch"},
    }]
    ceiling = extrapolate_ceiling(6.0)
    g = gate_g1(pilot, proxy_spearman=1.0, ceiling=ceiling)
    assert g["passed"] is True
    assert all(g["checks"].values())


def test_gate_g1_fails_on_low_spearman_or_ceiling():
    pilot = [{
        "per_arm": {"topn": {"coverage": {"kcenter_radius": 1.0}},
                     "domain_every": {"coverage": {"kcenter_radius": 0.8}}},
        "axis_relevance": {"axis_relevant": True},
    }]
    # low proxy spearman fails (c)
    g1 = gate_g1(pilot, proxy_spearman=0.90, ceiling=extrapolate_ceiling(6.0))
    assert g1["passed"] is False and g1["checks"]["c_proxy_real_spearman_ge_0_99"] is False
    # blown ceiling fails (d)
    g2 = gate_g1(pilot, proxy_spearman=1.0, ceiling=extrapolate_ceiling(60.0))
    assert g2["passed"] is False and g2["checks"]["d_plate_n_within_ceiling"] is False


def test_ceiling_constant_frozen():
    assert CEILING_CPU_HOURS == 72.0  # plan F6 hard ceiling, frozen
