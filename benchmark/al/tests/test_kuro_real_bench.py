"""Tests for al.kuro_real_bench — real KURO selector arm wiring.

Cheap tests only; no ESM-2 inference (importorskip for any ESM-2-dependent path).
"""
from __future__ import annotations

import re

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: domain_aware_select returns exactly k distinct variant ids from pool
# ──────────────────────────────────────────────────────────────────────────────

def test_kuro_domain_arm_selects_batch():
    """domain_aware_select with a tiny synthetic pool returns <=k distinct variant ids."""
    from kuma_core.kuro.evolvepro import domain_aware_select

    # rows: (variant_id, y_pred) sorted DESC — positions 1..12
    rows: list[tuple[str, float]] = [
        ("A1C", 9.0),
        ("D2E", 8.5),
        ("F3G", 8.0),
        ("H4I", 7.5),
        ("K5L", 7.0),
        ("M6N", 6.5),
        ("P7Q", 6.0),
        ("R8S", 5.5),
        ("T9V", 5.0),
        ("W10Y", 4.5),
    ]
    domains = [
        {"name": "ntd", "start": 1, "end": 5},
        {"name": "ctd", "start": 6, "end": 10},
    ]
    top_n = 4
    selected_rows, stats_dict = domain_aware_select(rows, domains, top_n=top_n)

    selected_ids = [v for v, _ in selected_rows]
    pool_ids = {v for v, _ in rows}

    # Must not exceed top_n.
    assert len(selected_ids) <= top_n, f"got {len(selected_ids)} > {top_n}"
    # All selected must come from the pool.
    assert all(v in pool_ids for v in selected_ids), "selected variant not in pool"
    # No duplicates.
    assert len(set(selected_ids)) == len(selected_ids), "duplicate ids in selection"
    # stats dict returned.
    assert isinstance(stats_dict, dict)


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: pareto_diversity_select returns k distinct ids; works with ca_coords=None
# ──────────────────────────────────────────────────────────────────────────────

def test_kuro_pareto_arm_selects_batch():
    """pareto_diversity_select returns <=k distinct ids and handles ca_coords=None."""
    from kuma_core.kuro.evolvepro import pareto_diversity_select

    rows: list[tuple[str, float]] = [
        ("A1C", 9.0),
        ("D3E", 8.5),
        ("F5G", 8.0),
        ("H7I", 7.5),
        ("K9L", 7.0),
        ("M11N", 6.5),
        ("P13Q", 6.0),
    ]
    top_n = 4

    # No structure available.
    selected_no_ca, replaced_no_ca = pareto_diversity_select(rows, top_n=top_n, ca_coords=None)
    ids_no_ca = [v for v, _ in selected_no_ca]
    assert len(ids_no_ca) <= top_n
    assert len(set(ids_no_ca)) == len(ids_no_ca), "duplicates with ca_coords=None"
    assert all(v in {v for v, _ in rows} for v in ids_no_ca)
    assert isinstance(replaced_no_ca, int)

    # With synthetic Ca coords (positions 1-20, trivial coords).
    ca_coords = [((float(i), 0.0, 0.0) if i <= 15 else None) for i in range(1, 21)]
    selected_ca, replaced_ca = pareto_diversity_select(rows, top_n=top_n, ca_coords=ca_coords)
    ids_ca = [v for v, _ in selected_ca]
    assert len(ids_ca) <= top_n
    assert len(set(ids_ca)) == len(ids_ca), "duplicates with ca_coords provided"


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: first-position reduction — combo 'L59M:K64W' maps to position 59
# ──────────────────────────────────────────────────────────────────────────────

def test_first_position_reduction_documented():
    """The KURO functions' _POS_RE returns the FIRST (lowest) position of a combo.

    For 'L59M:K64W', domain_aware_select / pareto_diversity_select see position 59.
    This is the documented first-position reduction limitation.
    """
    # Use the same regex that kuma_core.kuro.evolvepro._POS_RE uses.
    _POS_RE = re.compile(r"[A-Z](\d+)[A-Z]")

    combo_a = "L59M:K64W"
    m = _POS_RE.search(combo_a)
    assert m is not None, "_POS_RE should match at least one substitution in a combo"
    extracted_pos = int(m.group(1))
    assert extracted_pos == 59, (
        f"Expected first-position reduction to yield 59, got {extracted_pos}. "
        "This tests the documented limitation: only the first (lowest) position of a "
        "colon-separated combo is used by the KURO selectors."
    )

    # Verify ordering: 'K64W:L59M' (reversed order — should NOT occur since IDs are
    # sorted, but the regex still hits the first match in the string).
    combo_b = "K64W:L59M"
    m2 = _POS_RE.search(combo_b)
    assert m2 is not None
    # String-order first match: 'K64W' -> 64 (would occur if unsorted)
    # Canonical IDs are always sorted, so this path shows the raw regex behavior.
    extracted_b = int(m2.group(1))
    assert extracted_b == 64, (
        f"String-order first match of 'K64W:L59M' should yield 64, got {extracted_b}"
    )

    # Confirm that canonical combo IDs are position-sorted (so first-position reduction
    # is always the *lowest* position).
    from al.real_epistatic import canonical_combo_id, parse_combo
    canonical = canonical_combo_id(parse_combo("K64W:L59M"))
    m3 = _POS_RE.search(canonical)
    assert m3 is not None
    assert int(m3.group(1)) == 59, (
        f"Canonical combo ID should start with lowest position (59), got {m3.group(1)}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: CLI --smoke exits 0
# ──────────────────────────────────────────────────────────────────────────────

def test_cli_smoke_exits_zero():
    """main(['--smoke']) returns 0 without running any ESM-2 embeddings."""
    from al.kuro_real_bench import main
    ret = main(["--smoke"])
    assert ret == 0, f"--smoke exited with {ret}, expected 0"

# ──────────────────────────────────────────────────────────────────────────────
# Test 5: kuro_domain_centroid arm runs and selects k distinct ids
# ──────────────────────────────────────────────────────────────────────────────

def test_kuro_domain_centroid_arm_selects_batch():
    """domain_aware_select(position_mode='centroid') returns <=k distinct variant ids for combos."""
    from kuma_core.kuro.evolvepro import domain_aware_select

    # Combo rows: positions 1+90, 2+85, 10+80, 30+70, 5+60
    # First positions: 1,2,10,30,5 -> all in domain1 (1-40)
    # Centroid positions: ~45, ~43, ~45, ~50, ~32 -> mostly domain2 (41-100)
    rows: list[tuple[str, float]] = [
        ("A1C:K90R", 9.0),
        ("D2E:K85R", 8.5),
        ("F10G:K80R", 8.0),
        ("H30I:K70R", 7.5),
        ("K5L:K60R", 7.0),
        ("M40N", 6.5),   # single-mut in domain1
        ("P55Q", 6.0),   # single-mut in domain2
    ]
    domains = [
        {"name": "domain1", "start": 1, "end": 40},
        {"name": "domain2", "start": 41, "end": 100},
    ]
    top_n = 4
    selected_rows, stats_dict = domain_aware_select(
        rows, domains, top_n=top_n, position_mode="centroid"
    )
    selected_ids = [v for v, _ in selected_rows]
    pool_ids = {v for v, _ in rows}

    assert len(selected_ids) <= top_n, f"got {len(selected_ids)} > {top_n}"
    assert all(v in pool_ids for v in selected_ids), "selected variant not in pool"
    assert len(set(selected_ids)) == len(selected_ids), "duplicate ids in centroid domain selection"
    assert isinstance(stats_dict, dict)


# ──────────────────────────────────────────────────────────────────────────────
# Test 6: kuro_pareto_centroid arm runs and selects k distinct ids
# ──────────────────────────────────────────────────────────────────────────────

def test_kuro_pareto_centroid_arm_selects_batch():
    """pareto_diversity_select(position_mode='centroid') returns <=k distinct ids for combos."""
    from kuma_core.kuro.evolvepro import pareto_diversity_select

    # Combo rows with wide position spread
    rows: list[tuple[str, float]] = [
        ("A1C:K99R", 9.0),   # centroid ~50
        ("D2E:K98R", 8.5),   # centroid ~50  — close to first
        ("F10G:K80R", 8.0),  # centroid ~45
        ("H30I:K70R", 7.5),  # centroid ~50
        ("K40L:K60R", 7.0),  # centroid ~50
        ("M50N", 6.5),       # single-mut pos=50
        ("P15Q:K85R", 6.0),  # centroid ~50
    ]
    top_n = 4

    # Without Ca coords
    selected, replaced = pareto_diversity_select(rows, top_n=top_n, ca_coords=None, position_mode="centroid")
    ids = [v for v, _ in selected]
    assert len(ids) <= top_n
    assert len(set(ids)) == len(ids), "duplicates in centroid pareto selection"
    assert isinstance(replaced, int)

    # With Ca coords
    ca_coords = [None] + [(float(i) * 3.8, 0.0, 0.0) for i in range(1, 101)]
    selected_ca, _ = pareto_diversity_select(rows, top_n=top_n, ca_coords=ca_coords, position_mode="centroid")
    ids_ca = [v for v, _ in selected_ca]
    assert len(ids_ca) <= top_n
    assert len(set(ids_ca)) == len(ids_ca), "duplicates in centroid+3D pareto selection"

# ──────────────────────────────────────────────────────────────────────────────
# Test 7: kuro_struct arm runs + selects k distinct ids
# ──────────────────────────────────────────────────────────────────────────────

def test_kuro_struct_arm_selects_batch():
    """structural_diversity_select returns <=k distinct ids from the pool."""
    from kuma_core.kuro.evolvepro import structural_diversity_select

    # Combo rows with spread positions (no Ca structure).
    rows: list[tuple[str, float]] = [
        ("A1C:K90R", 9.0),
        ("D2E:K85R", 8.5),
        ("F10G:K80R", 8.0),
        ("H30I:K70R", 7.5),
        ("K5L:K60R", 7.0),
        ("M40N:K50R", 6.5),
        ("P15Q:K45R", 6.0),
        ("R20S:K40R", 5.5),
    ]
    top_n = 4

    # No Ca coords, no anchor.
    selected, replaced = structural_diversity_select(rows, top_n=top_n)
    ids = [v for v, _ in selected]
    pool_ids = {v for v, _ in rows}
    assert len(ids) <= top_n, f"got {len(ids)} > {top_n}"
    assert len(set(ids)) == len(ids), "duplicates in kuro_struct selection"
    assert all(v in pool_ids for v in ids), "selected variant not in pool"
    assert isinstance(replaced, int)

    # With anchor (simulate revealed history).
    anchor = ["A1C:K90R", "D2E:K85R"]
    selected_anc, _ = structural_diversity_select(
        rows, top_n=top_n, anchor_variants=anchor
    )
    ids_anc = [v for v, _ in selected_anc]
    assert len(ids_anc) <= top_n
    assert len(set(ids_anc)) == len(ids_anc), "duplicates with anchor"
    assert all(v in pool_ids for v in ids_anc), "anchored selection out of pool"

    # With kappa=0.3 blend.
    selected_bl, _ = structural_diversity_select(rows, top_n=top_n, kappa=0.3)
    ids_bl = [v for v, _ in selected_bl]
    assert len(ids_bl) <= top_n
    assert len(set(ids_bl)) == len(ids_bl), "duplicates in kappa=0.3 blend"


# ──────────────────────────────────────────────────────────────────────────────
# Test 8: kuro_struct ~matches kuro_ca on fixed synthetic seed
# ──────────────────────────────────────────────────────────────────────────────

def test_kuro_struct_matches_kuro_ca_on_fixed_seed():
    """With the same pool, anchor, and Ca coords, kuro_struct should pick
    identically or near-identically to the kuro_ca (embdiv) arm."""
    import numpy as np
    from kuma_core.kuro.evolvepro import structural_diversity_select
    from al.real_epistatic import combo_centroid_descriptor, parse_combo
    from al.acquisition import select_indices

    # Fixed synthetic pool of combo variants.
    variants = [
        "A1C:K50R",
        "D5E:K55R",
        "F10G:K60R",
        "H20I:K70R",
        "K30L:K80R",
        "M40N:K90R",
    ]
    # Fitness scores (descending).
    scores = [6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    rows = list(zip(variants, scores))

    # Simulate Ca coords: 1-based, positions 1-100, linear spacing.
    ca: list = [None] * 102
    for p in range(1, 101):
        ca[p] = (float(p) * 3.8, 0.0, 0.0)

    # Anchor = first 2 variants (simulating revealed history).
    anchor = variants[:2]
    k = 3

    # kuro_struct selection.
    selected_struct, _ = structural_diversity_select(
        rows, top_n=k, ca_coords=ca, anchor_variants=anchor
    )
    ids_struct = set(v for v, _ in selected_struct)

    # kuro_ca selection via select_indices("embdiv").
    desc = {v: combo_centroid_descriptor(parse_combo(v), ca) for v in variants}
    unrev = [v for v in variants if v not in anchor]
    unrev_scores = [s for v, s in rows if v not in anchor]
    feats = np.vstack([desc[v] for v in unrev])
    anc_feats = np.vstack([desc[v] for v in anchor])
    mean_arr = np.array(unrev_scores, dtype=float)
    rng = np.random.default_rng(42)
    idx = select_indices("embdiv", mean=mean_arr, features=feats, anchor_features=anc_feats, n=k, rng=rng)
    ids_ca = set(unrev[j] for j in idx)

    # kuro_struct and kuro_ca should agree on at least 2 out of 3 picks.
    overlap = len(ids_struct & ids_ca)
    assert overlap >= 2, (
        f"kuro_struct and kuro_ca differ too much: struct={ids_struct}, ca={ids_ca}, overlap={overlap}"
    )
