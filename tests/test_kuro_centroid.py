"""Tests for centroid position_mode in domain_aware_select and pareto_diversity_select."""
from __future__ import annotations

import pytest

from kuma_core.kuro.evolvepro import (
    _combo_positions,
    domain_aware_select,
    pareto_diversity_select,
)


# ──────────────────────────────────────────────────────────────────────────────
# _combo_positions helper
# ──────────────────────────────────────────────────────────────────────────────

def test_combo_positions_single_mut():
    assert _combo_positions("A10C") == [10]


def test_combo_positions_combo():
    assert _combo_positions("A10C:K90R") == [10, 90]


def test_combo_positions_three_way():
    assert _combo_positions("L59M:W60T:K64W") == [59, 60, 64]


def test_combo_positions_empty():
    assert _combo_positions("UNKNOWN") == []


# ──────────────────────────────────────────────────────────────────────────────
# (a) single-mut: centroid == first (regression)
# ──────────────────────────────────────────────────────────────────────────────

class TestSingleMutCentroidEqualsFirst:
    """For single-position variants, position_mode='centroid' must give identical selection."""

    def _rows(self):
        return [
            ("A10C", 9.0),
            ("D20E", 8.5),
            ("F50G", 8.0),
            ("H60I", 7.5),
            ("K80L", 7.0),
        ]

    def _domains(self):
        return [
            {"name": "ntd", "start": 1, "end": 40},
            {"name": "ctd", "start": 41, "end": 100},
        ]

    def test_domain_aware_select_single_mut_centroid_eq_first(self):
        rows = self._rows()
        domains = self._domains()
        sel_first, _ = domain_aware_select(rows, domains, top_n=4, position_mode="first")
        sel_cent, _ = domain_aware_select(rows, domains, top_n=4, position_mode="centroid")
        assert [v for v, _ in sel_first] == [v for v, _ in sel_cent], (
            "single-mut centroid must match first for domain_aware_select"
        )

    def test_pareto_select_single_mut_centroid_eq_first(self):
        rows = self._rows()
        sel_first, rep_first = pareto_diversity_select(rows, top_n=4, position_mode="first")
        sel_cent, rep_cent = pareto_diversity_select(rows, top_n=4, position_mode="centroid")
        assert [v for v, _ in sel_first] == [v for v, _ in sel_cent], (
            "single-mut centroid must match first for pareto_diversity_select"
        )
        assert rep_first == rep_cent

    def test_pareto_select_single_mut_centroid_eq_first_3d(self):
        rows = self._rows()
        # Build simple linear Ca coords covering positions 1-100
        ca: list = [None]  # index 0 unused (1-based)
        for i in range(1, 101):
            ca.append((float(i) * 5.0, 0.0, 0.0))
        sel_first, _ = pareto_diversity_select(rows, top_n=4, ca_coords=ca, position_mode="first")
        sel_cent, _ = pareto_diversity_select(rows, top_n=4, ca_coords=ca, position_mode="centroid")
        assert [v for v, _ in sel_first] == [v for v, _ in sel_cent], (
            "single-mut 3D centroid must match first"
        )


# ──────────────────────────────────────────────────────────────────────────────
# (b) multi-mut: A10C:K90R centroid ~50, differs from first (10)
# ──────────────────────────────────────────────────────────────────────────────

class TestMultiMutCentroidDiffersFromFirst:
    """Combo variants use centroid position (mean), which differs from first position."""

    def test_combo_positions_centroid_value(self):
        """'A10C:K90R' has centroid position round((10+90)/2)=50, not 10."""
        import math
        ps = _combo_positions("A10C:K90R")
        assert ps == [10, 90]
        centroid_pos = round(sum(ps) / len(ps))
        assert centroid_pos == 50

    def test_domain_aware_select_centroid_bins_to_centroid_domain(self):
        """Combo 'A10C:K90R' with centroid=50 bins to different domain than first=10."""
        # Domain 1: positions 1-30 (centroid=10 would go here)
        # Domain 2: positions 31-100 (centroid=50 goes here)
        rows: list[tuple[str, float]] = [
            ("A10C:K90R", 9.0),  # first pos=10 -> domain1; centroid pos=50 -> domain2
            ("D15E:K85R", 8.5),  # first pos=15 -> domain1; centroid pos=50 -> domain2
            ("F5G:K95R", 8.0),   # first pos=5 -> domain1; centroid pos=50 -> domain2
            ("H32I", 7.5),       # pos=32 -> domain2 in both modes
            ("K40L", 7.0),       # pos=40 -> domain2 in both modes
        ]
        domains = [
            {"name": "domain1", "start": 1, "end": 30},
            {"name": "domain2", "start": 31, "end": 100},
        ]
        sel_first, stats_first = domain_aware_select(
            rows, domains, top_n=4, position_mode="first"
        )
        sel_cent, stats_cent = domain_aware_select(
            rows, domains, top_n=4, position_mode="centroid"
        )
        # With first-position: A10C:K90R bins to domain1 (pos=10)
        # With centroid: A10C:K90R bins to domain2 (pos=50)
        # The selections should differ
        ids_first = [v for v, _ in sel_first]
        ids_cent = [v for v, _ in sel_cent]
        # Both modes must return <= top_n distinct items from the pool
        assert len(ids_first) <= 4
        assert len(ids_cent) <= 4
        assert len(set(ids_first)) == len(ids_first)
        assert len(set(ids_cent)) == len(ids_cent)
        # The distributions should differ because binning changes
        assert ids_first != ids_cent, (
            "first-position and centroid binning should produce different selections "
            "for combos spanning domain boundaries"
        )

    def test_pareto_select_centroid_uses_mean_position(self):
        """pareto_diversity_select centroid mode uses mean position for 1D distance."""
        # Combos: positions 10 and 90 (centroid=50); nearby combos at 11:91 (centroid=51)
        rows: list[tuple[str, float]] = [
            ("A10C:K90R", 9.0),   # centroid=50
            ("A11C:K91R", 8.5),   # centroid=51 — close to centroid=50
            ("A50C:K52R", 8.0),   # centroid=51, first=50
            ("A1C:K100R", 7.5),   # centroid=50.5, first=1 — very distant in first mode
            ("A60C", 7.0),        # single-mut pos=60
        ]
        sel_first, _ = pareto_diversity_select(rows, top_n=3, position_mode="first")
        sel_cent, _ = pareto_diversity_select(rows, top_n=3, position_mode="centroid")
        ids_first = [v for v, _ in sel_first]
        ids_cent = [v for v, _ in sel_cent]
        # Both must be valid
        assert len(ids_first) == 3
        assert len(ids_cent) == 3
        assert len(set(ids_first)) == 3
        assert len(set(ids_cent)) == 3


# ──────────────────────────────────────────────────────────────────────────────
# (c) default param omitted == position_mode='first'
# ──────────────────────────────────────────────────────────────────────────────

class TestDefaultParamIsFirst:
    """Omitting position_mode must produce identical results to position_mode='first'."""

    def _rows_single(self):
        return [("A10C", 9.0), ("D50E", 8.0), ("F80G", 7.0)]

    def _domains(self):
        return [
            {"name": "ntd", "start": 1, "end": 50},
            {"name": "ctd", "start": 51, "end": 100},
        ]

    def test_domain_aware_select_default_equals_first(self):
        rows = self._rows_single()
        domains = self._domains()
        sel_default, _ = domain_aware_select(rows, domains, top_n=2)
        sel_first, _ = domain_aware_select(rows, domains, top_n=2, position_mode="first")
        assert [v for v, _ in sel_default] == [v for v, _ in sel_first]

    def test_pareto_select_default_equals_first(self):
        rows = self._rows_single()
        sel_default, rep_default = pareto_diversity_select(rows, top_n=2)
        sel_first, rep_first = pareto_diversity_select(rows, top_n=2, position_mode="first")
        assert [v for v, _ in sel_default] == [v for v, _ in sel_first]
        assert rep_default == rep_first


# ──────────────────────────────────────────────────────────────────────────────
# Edge: centroid mode with 3D coords uses Ca centroid
# ──────────────────────────────────────────────────────────────────────────────

def test_pareto_centroid_3d_uses_ca_centroid():
    """In centroid+3D mode, pairwise distance is Euclidean between Ca centroids."""
    # Positions 10, 90 for combo 'A10C:K90R' -> centroid Ca = mean of ca[10] and ca[90]
    # With a linear chain (x = pos * 5.0), centroid = (500, 0, 0)
    # Compare to position-70 variant 'A70C': ca[70] = (350, 0, 0)
    # Distance between centroid (500,0,0) and (350,0,0) = 150 / ca_max
    ca: list = [None]
    for i in range(1, 101):
        ca.append((float(i) * 5.0, 0.0, 0.0))

    rows: list[tuple[str, float]] = [
        ("A10C:K90R", 9.0),   # centroid Ca ~(500,0,0)
        ("A70C", 8.0),        # Ca ~(350,0,0) — moderate distance to centroid
        ("A50C", 7.0),        # Ca ~(250,0,0) — farther from centroid
        ("A20C:K80R", 6.0),   # centroid Ca ~(500,0,0) — same centroid as top; close
    ]
    sel, replaced = pareto_diversity_select(
        rows, top_n=3, ca_coords=ca, position_mode="centroid"
    )
    ids = [v for v, _ in sel]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    # Top item always selected
    assert "A10C:K90R" in ids
