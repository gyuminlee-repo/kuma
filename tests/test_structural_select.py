"""Tests for structural_diversity_select and _variant_centroid in kuma_core."""
from __future__ import annotations

import math

import pytest

from kuma_core.kuro.evolvepro import structural_diversity_select, _variant_centroid


# ---------------------------------------------------------------------------
# _variant_centroid helper tests
# ---------------------------------------------------------------------------

def test_variant_centroid_no_ca():
    """Single-mut: positional fallback returns (pos, pos, pos)."""
    c = _variant_centroid("A10C", None)
    assert c == (10.0, 10.0, 10.0)


def test_variant_centroid_combo_no_ca():
    """Combo: positional fallback returns (min, mean, max)."""
    c = _variant_centroid("A10C:K90R", None)
    assert c == (10.0, 50.0, 90.0)


def test_variant_centroid_unparseable():
    """Unrecognisable variant string returns (0, 0, 0)."""
    c = _variant_centroid("UNKNOWN", None)
    assert c == (0.0, 0.0, 0.0)


def test_variant_centroid_with_ca():
    """With Ca coords, returns mean of resolved coordinates."""
    ca = [None] * 20  # 1-based, indices 1-19
    ca[5] = (1.0, 2.0, 3.0)
    ca[10] = (3.0, 4.0, 5.0)
    c = _variant_centroid("A5C:K10R", ca)  # type: ignore[arg-type]
    assert c == (2.0, 3.0, 4.0)


def test_variant_centroid_ca_all_missing_fallback():
    """When all positions missing from Ca coords, falls back to positional."""
    ca = [None] * 5  # positions 5+ are out of range
    c = _variant_centroid("A10C:K20R", ca)  # type: ignore[arg-type]
    # Falls back to positional (10, 15, 20)
    assert c == (10.0, 15.0, 20.0)


# ---------------------------------------------------------------------------
# structural_diversity_select core tests
# ---------------------------------------------------------------------------

def test_returns_top_n_distinct_rows_subset():
    """Returns exactly top_n distinct rows, all from the input."""
    rows = [(f"A{i}C", float(i)) for i in range(1, 21)]
    selected, _ = structural_diversity_select(rows, 5)
    assert len(selected) == 5
    variants = [v for v, _ in selected]
    assert len(set(variants)) == 5, "Selection contains duplicates"
    pool = {v for v, _ in rows}
    assert all(v in pool for v in variants), "Selected variant not in input rows"


def test_returns_at_most_top_n_when_pool_small():
    """Returns all rows when top_n >= len(rows)."""
    rows = [("A1C", 1.0), ("A2C", 2.0)]
    selected, _ = structural_diversity_select(rows, 10)
    assert len(selected) == 2


def test_empty_rows_returns_empty():
    rows: list[tuple[str, float]] = []
    selected, replaced = structural_diversity_select(rows, 5)
    assert selected == []
    assert replaced == 0


def test_top_n_zero_returns_empty():
    rows = [("A1C", 1.0)]
    selected, replaced = structural_diversity_select(rows, 0)
    assert selected == []
    assert replaced == 0


def test_anchor_pushes_selection_away_from_position():
    """Anchor at position 1 — selection should prefer far positions (positional fallback)."""
    # No Ca coords: positional (min, mean, max) used.
    rows = [
        ("A1C", 3.0),   # pos 1 — close to anchor
        ("A50C", 2.0),  # pos 50 — far
        ("A100C", 1.0), # pos 100 — very far
    ]
    anchor = ["A1C"]  # anchor near pos 1
    selected, _ = structural_diversity_select(rows, 1, anchor_variants=anchor)
    variants = [v for v, _ in selected]
    # The variant closest to anchor (A1C) should NOT be the first pick
    assert variants[0] in ("A50C", "A100C"), (
        f"Expected far position to be selected first, got {variants[0]}"
    )


def test_anchor_pushes_away_3d():
    """Anchor in 3D — selection prefers candidate far in 3D Ca space."""
    # Build Ca coords: position 1 at origin, position 100 far away
    ca: list = [None] * 110
    ca[1] = (0.0, 0.0, 0.0)
    ca[100] = (100.0, 0.0, 0.0)

    rows = [("A1C", 2.0), ("A100C", 1.0)]  # A1C has higher fitness
    anchor = ["A1C"]  # anchor at origin

    selected, _ = structural_diversity_select(rows, 1, ca_coords=ca, anchor_variants=anchor)
    variants = [v for v, _ in selected]
    # A100C is far from anchor despite lower fitness
    assert variants[0] == "A100C", f"Expected A100C (far from anchor), got {variants[0]}"


def test_single_mut_variants_work():
    """Single-mutation variants parse correctly and selection completes."""
    rows = [(f"A{i * 10}C", float(i)) for i in range(5, 0, -1)]
    selected, replaced = structural_diversity_select(rows, 3)
    assert len(selected) == 3
    assert isinstance(replaced, int)


def test_kappa_1_collapses_toward_top_n_fitness():
    """kappa=1.0 must select by fitness — identical to Top-N order."""
    # Rows with distinct fitness values in a known order.
    rows = [(f"A{i}C", float(i)) for i in range(1, 11)]
    selected, _ = structural_diversity_select(rows, 5, kappa=1.0)
    selected_fits = sorted([y for _, y in selected], reverse=True)
    top5_fits = sorted([y for _, y in rows], reverse=True)[:5]
    assert selected_fits == top5_fits, (
        f"kappa=1 did not collapse to top-5 fitness: got {selected_fits}, want {top5_fits}"
    )


def test_disjoint_3d_clusters_spreads_across_both():
    """With two clearly separated 3D clusters, selection should span both."""
    # Cluster A: positions 1-3, Ca near (0,0,0)
    # Cluster B: positions 100-102, Ca near (500,0,0)
    ca: list = [None] * 110
    for p in [1, 2, 3]:
        ca[p] = (float(p), 0.0, 0.0)
    for p in [100, 101, 102]:
        ca[p] = (500.0 + float(p), 0.0, 0.0)

    rows = [
        ("A1C", 6.0), ("A2C", 5.0), ("A3C", 4.0),  # cluster A — higher fitness
        ("A100C", 3.0), ("A101C", 2.0), ("A102C", 1.0),  # cluster B
    ]
    selected, _ = structural_diversity_select(rows, 4, ca_coords=ca)
    selected_vars = [v for v, _ in selected]

    cluster_a = {"A1C", "A2C", "A3C"}
    cluster_b = {"A100C", "A101C", "A102C"}
    from_a = sum(1 for v in selected_vars if v in cluster_a)
    from_b = sum(1 for v in selected_vars if v in cluster_b)
    assert from_a >= 1 and from_b >= 1, (
        f"Did not spread across clusters: selected={selected_vars}"
    )


def test_disjoint_positional_clusters_spreads():
    """Positional fallback: wide position ranges should also diversify without Ca."""
    rows = [
        ("A1C", 6.0), ("A2C", 5.0), ("A3C", 4.0),  # low positions
        ("A98C", 3.0), ("A99C", 2.0), ("A100C", 1.0),  # high positions
    ]
    selected, _ = structural_diversity_select(rows, 4)
    selected_vars = [v for v, _ in selected]
    low_pos = {"A1C", "A2C", "A3C"}
    high_pos = {"A98C", "A99C", "A100C"}
    from_low = sum(1 for v in selected_vars if v in low_pos)
    from_high = sum(1 for v in selected_vars if v in high_pos)
    assert from_low >= 1 and from_high >= 1, (
        f"Positional fallback did not spread: selected={selected_vars}"
    )


def test_replaced_count_is_correct():
    """replaced count matches number of selected variants not in pure Top-N."""
    rows = [
        ("A1C", 10.0),  # top fitness
        ("A2C", 9.0),
        ("A3C", 8.0),
        ("A100C", 1.0),  # far position but low fitness
    ]
    # With no anchor and 3D cluster splitting, A100C may be picked for diversity.
    selected, replaced = structural_diversity_select(rows, 3)
    top3_ids = {v for v, _ in sorted(rows, key=lambda r: -r[1])[:3]}
    expected_replaced = sum(1 for v, _ in selected if v not in top3_ids)
    assert replaced == expected_replaced


def test_no_anchor_seed_is_max_fitness():
    """With no anchor, the first selection must be the max-fitness candidate."""
    rows = [
        ("A50C", 5.0),
        ("A1C", 10.0),  # max fitness but low positional diversity
        ("A100C", 3.0),
    ]
    selected, _ = structural_diversity_select(rows, 1)
    # First (and only) pick is max-fitness when no anchor and top_n=1
    assert selected[0][0] == "A1C", (
        f"Without anchor, first pick should be max-fitness A1C, got {selected[0][0]}"
    )
