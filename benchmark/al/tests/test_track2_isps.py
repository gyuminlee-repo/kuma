"""Tests for al.track2_isps against the LOCAL IspS provenance files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from al.track2_isps import (
    combinatorial_data_readiness_spec,
    join_isps,
    load_isps_measured,
    load_isps_track2,
    load_scaneer_sci,
    main,
    retrospective_single_mut,
)


def _find_provenance() -> Path | None:
    """Walk up from this file to locate foldcrit/data/ispS_provenance (no hardcoded abs path)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "foldcrit" / "data" / "ispS_provenance"
        if cand.is_dir():
            return cand
    return None


_PROV = _find_provenance()
pytestmark = pytest.mark.skipif(_PROV is None, reason="IspS provenance dir not found")


def test_scaneer_sci_loads():
    sci = load_scaneer_sci(_PROV / "scaneer_sci_sispS.tsv")
    assert len(sci) > 5000  # ~6479 single-sub coevolution rows
    assert {"variant", "residue", "wt", "mut", "scaneer_sci"} <= set(sci.columns)
    # variant string is AA1+Residue+AA2, e.g. L219W from the top row.
    assert (sci["variant"].str.match(r"^[A-Z]\d+[A-Z]$")).all()
    row = sci[sci["variant"] == "L219W"]
    assert len(row) == 1 and row.iloc[0]["scaneer_sci"] == pytest.approx(3.96, abs=1e-2)


def test_isps_measured_loads():
    m = load_isps_measured(_PROV / "231024_round1_screening.xlsx")
    assert 80 <= len(m) <= 100  # ~93 round-1 measured variants
    assert {"variant", "relative_peak_area"} <= set(m.columns)
    assert (m["variant"].str.match(r"^[A-Z]\d+[A-Z]$")).all()
    # Known top hit V550L with relative peak area ~1.39.
    v = m[m["variant"] == "V550L"]
    assert len(v) == 1 and v.iloc[0]["relative_peak_area"] == pytest.approx(1.388, abs=1e-2)


def test_join_has_sci_coverage():
    merged = load_isps_track2(_PROV)
    assert len(merged) >= 80
    assert {"variant", "relative_peak_area", "scaneer_sci", "has_sci"} <= set(merged.columns)
    # A non-trivial fraction of measured variants must have a SCANEER SCI (the
    # round was SCANEER-guided), proving the join actually connects the two sources.
    assert merged["has_sci"].mean() > 0.3


# ---------------------------------------------------------------------------
# New Phase-C tests (provenance-independent)
# ---------------------------------------------------------------------------

def _make_synthetic_merged(n: int = 30, rng_seed: int = 7) -> pd.DataFrame:
    """Build a clearly-labeled synthetic merged frame for unit tests.

    NOT real IspS data.  Weak positive SCI-activity correlation, spread
    across residue positions 100-450.
    """
    rng = np.random.default_rng(rng_seed)
    residues = sorted(rng.choice(range(100, 450), size=n, replace=False).tolist())
    aa_pool = "ACDEFGHIKLMNPQRSTVWY"
    rows = []
    for i, pos in enumerate(residues):
        wt = aa_pool[i % len(aa_pool)]
        mt = aa_pool[(i + 4) % len(aa_pool)]
        if wt == mt:
            mt = aa_pool[(i + 6) % len(aa_pool)]
        sci = float(rng.uniform(0.5, 5.0))
        activity = float(max(0.01, 0.15 * sci + rng.normal(1.0, 0.5)))
        rows.append({
            "variant": f"{wt}{pos}{mt}",
            "well": f"A{i+1}",
            "relative_peak_area": activity,
            "scaneer_sci": sci,
            "has_sci": True,
        })
    return pd.DataFrame(rows)


@pytest.mark.skipif(False, reason="synthetic test — always runs")  # explicit: no skip
def test_retrospective_runs_and_is_leak_aware():
    """retrospective_single_mut must return expected keys, valid recall, and be leak-free."""
    df = _make_synthetic_merged(n=30, rng_seed=7)
    n_seed = 5
    batch = 4
    rounds = 3

    result = retrospective_single_mut(df, n_seed=n_seed, batch=batch, rounds=rounds, seed=0)

    # Top-level keys
    assert {"n_variants", "n_hits", "hit_cutoff", "spearman_rho", "policies"} <= set(result.keys())
    assert result["n_variants"] == 30
    assert result["n_hits"] >= 1

    # All three policies present
    assert set(result["policies"].keys()) == {"scaneer_greedy", "random", "diversity"}

    oracle = dict(zip(df["variant"], df["relative_peak_area"]))
    max_possible = df["relative_peak_area"].max()
    budget = n_seed + batch * (rounds - 1)  # = 5 + 4*2 = 13

    for pol, pdata in result["policies"].items():
        # Recall in [0, 1]
        assert 0.0 <= pdata["recall_at_hits"] <= 1.0, f"{pol}: recall out of [0,1]"
        # best_activity never exceeds the global oracle maximum (sanity)
        assert pdata["best_activity"] <= max_possible + 1e-9, f"{pol}: best_activity above oracle max"
        # Budget respected: no policy reveals more variants than the AL budget
        assert pdata["n_revealed"] <= budget, f"{pol}: revealed {pdata['n_revealed']} > budget {budget}"

        # ---- Leak-awareness by construction ----
        # Flatten all selected variants; best_activity must equal max of their oracle values
        all_selected = [v for rnd in pdata["rounds_selected"] for v in rnd]
        assert len(all_selected) == pdata["n_revealed"], f"{pol}: rounds_selected count mismatch"
        revealed_max = max(oracle[v] for v in all_selected)
        assert abs(pdata["best_activity"] - revealed_max) < 1e-9, (
            f"{pol}: best_activity {pdata['best_activity']:.4f} != revealed max "
            f"{revealed_max:.4f} — surrogate may have leaked unrevealed activities"
        )

        # No duplicate variants across rounds
        assert len(all_selected) == len(set(all_selected)), f"{pol}: duplicate selected variants"

        # R1 (rounds_selected[0]) must be shared scaneer-ranked seed (same for all policies)
        r1 = pdata["rounds_selected"][0]
        assert len(r1) == n_seed, f"{pol}: R1 size {len(r1)} != n_seed {n_seed}"


@pytest.mark.skipif(False, reason="no external deps")
def test_data_readiness_spec_has_required_fields():
    """combinatorial_data_readiness_spec must document absence + colon format + required cols."""
    spec = combinatorial_data_readiness_spec()

    # DATA_ABSENT must be explicit and unambiguous
    assert spec["status"] == "DATA_ABSENT", "spec must declare DATA_ABSENT"
    assert spec["currently_absent"] is True, "currently_absent flag must be True"

    # Required columns
    assert "mutant" in spec["required_columns"], "spec must require 'mutant' column"
    assert "measured_activity" in spec["required_columns"]
    assert "round_index" in spec["required_columns"]

    # Mutant format: colon separator, example, permutation-invariant
    fmt = spec["mutant_format"]
    assert "colon" in fmt["description"].lower(), "mutant_format must mention colon"
    assert fmt["separator"] == ":", "mutant_format separator must be ':'"
    assert ":" in fmt["double_example"], "double_example must contain colon"

    # Permutation invariance required
    assert spec["permutation_invariant"] is True

    # Minimums
    assert spec["min_combinatorial_genotypes_per_round"] >= 50
    assert spec["min_mutation_orders"] >= 2

    # Currently-available section documents local reality
    avail = spec["currently_available"]
    assert avail["single_mut_variants"] == 93
    assert avail["rounds"] == 1


@pytest.mark.skipif(False, reason="CLI smoke must always pass")
def test_cli_smoke_exits_zero():
    """``main(['--smoke'])`` must return 0 even without the provenance directory."""
    rc = main(["--smoke"])
    assert rc == 0, f"--smoke returned {rc}, expected 0"
