"""Tests for al.attribution (Phase D — attribution and ablation, G004).

All four tests are cheap (no ESM-2, no network); coverage_attribution tests
that need real embeddings are guarded by pytest.importorskip / skipif.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_G002_DIR = Path(__file__).resolve().parents[2] / "results" / "qa" / "g002"


def _pilot_json(name: str) -> dict:
    import json
    paths = {
        "F7YBW8": _G002_DIR / "pilot.json",
        "RASK": _G002_DIR / "pilot_RASK.json",
        "GRB2": _G002_DIR / "pilot_GRB2.json",
    }
    return json.loads(paths[name].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# test 1: signal_quality_degradation returns correct per-assay values
# ---------------------------------------------------------------------------

def test_signal_quality_degradation_runs():
    """Returns per-assay diversity_benefit dict; values match G002 pilot JSONs."""
    from al.attribution import signal_quality_degradation

    result = signal_quality_degradation()

    # Must have per_assay for each G002 assay + IspS
    assert "per_assay" in result
    per = result["per_assay"]
    assert set(["F7YBW8", "RASK", "GRB2", "IspS_G003"]).issubset(per)

    # Diversity benefits must match the pilot JSONs.
    for name in ("F7YBW8", "RASK", "GRB2"):
        pilot = _pilot_json(name)
        kuro = pilot["per_arm_norm_best_mean"]["kuro_ca"]
        topn = pilot["per_arm_norm_best_mean"]["topn"]
        expected_benefit = kuro - topn

        actual_benefit = per[name]["diversity_benefit"]
        assert math.isfinite(actual_benefit), f"{name}: diversity_benefit must be finite"
        assert abs(actual_benefit - expected_benefit) < 1e-9, (
            f"{name}: expected {expected_benefit:.6f}, got {actual_benefit:.6f}"
        )

    # GRB2 is AGAINST: benefit must be negative.
    assert per["GRB2"]["diversity_benefit"] < 0, "GRB2 AGAINST cell must have negative benefit"

    # F7YBW8 and RASK are FOR: benefit must be positive.
    assert per["F7YBW8"]["diversity_benefit"] > 0
    assert per["RASK"]["diversity_benefit"] > 0

    # trend_verdict must be a string
    assert isinstance(result["trend_verdict"], str)
    assert len(result["trend_verdict"]) > 0

    # power_note must mention N=4
    assert "N=4" in result["power_note"]


# ---------------------------------------------------------------------------
# test 2: budget_round_sweep returns finite float deltas
# ---------------------------------------------------------------------------

def test_budget_round_sweep_runs():
    """Returns per-budget sigma_kuro-vs-topn deltas on synthetic NK; each a finite float."""
    from al.attribution import budget_round_sweep

    # Small seeds for speed; one budget setting.
    result = budget_round_sweep(
        K=4,
        n_sites=8,
        n_alleles=2,
        seeds=5,
        budget_settings=((4, 3), (8, 4)),
    )

    assert "per_budget" in result
    pb = result["per_budget"]
    assert len(pb) == 2, "Expected 2 budget settings"

    for label, entry in pb.items():
        delta = entry["sigma_kuro_minus_topn_delta"]
        assert math.isfinite(delta), f"{label}: delta must be a finite float, got {delta}"
        assert isinstance(entry["kuro_wins"], bool)
        assert entry["n_seeds"] == 5

    # deltas_by_budget_asc must be a list of finite floats.
    assert all(math.isfinite(d) for d in result["deltas_by_budget_asc"])
    assert "trend_verdict" in result


# ---------------------------------------------------------------------------
# test 3: esm_fidelity_note bounds claims to ESM-2 35M
# ---------------------------------------------------------------------------

def test_esm_fidelity_note_bounds_to_35M():
    """esm_fidelity_note returns a dict: model=35M, ran_650M=False, non-empty bias_direction."""
    from al.attribution import esm_fidelity_note

    note = esm_fidelity_note()

    assert note["model"] == "esm2_t12_35M_UR50D", (
        f"model must be 'esm2_t12_35M_UR50D', got {note['model']!r}"
    )
    assert note["ran_650M"] is False, "ran_650M must be False (compute-bound)"
    assert isinstance(note["bias_direction"], str) and len(note["bias_direction"]) > 0, (
        "bias_direction must be a non-empty string"
    )
    assert "optimistic" in note["bias_direction"].lower() or "upper bound" in note["bias_direction"].lower(), (
        "bias_direction must state 35M is an optimistic/upper-bound"
    )
    assert note["claims_bounded_to"] == "esm2_t12_35M_UR50D"


# ---------------------------------------------------------------------------
# test 4: CLI --smoke exits 0
# ---------------------------------------------------------------------------

def test_cli_smoke_exits_zero():
    """main(['--smoke']) returns 0 (synthetic-only, no embeddings required)."""
    from al.attribution import main

    exit_code = main(["--smoke"])
    assert exit_code == 0, f"--smoke must exit 0, got {exit_code}"
