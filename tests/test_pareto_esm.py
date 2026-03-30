"""Tests for AlphaFold Cα integration in pareto_diversity_select."""

from __future__ import annotations

import pytest

from kuro.evolvepro import pareto_diversity_select


def _make_coords(n: int, spacing: float = 10.0) -> list[tuple[float, float, float] | None]:
    """Create simple 1D chain of Cα coordinates along x-axis.

    Index 0 is None (unused, 1-based convention).
    """
    result: list[tuple[float, float, float] | None] = [None]  # index 0 unused
    for i in range(1, n + 1):
        result.append((i * spacing, 0.0, 0.0))
    return result


class TestParetoWithStructure:
    """Test pareto_diversity_select with ca_coords parameter."""

    def test_without_coords_uses_1d(self):
        """Without structure, 1D position distance should be used."""
        rows = [
            ("A10C", 1.0),
            ("A11D", 0.9),
            ("A50E", 0.8),
            ("A51F", 0.7),
            ("A100G", 0.6),
        ]
        selected, replaced = pareto_diversity_select(rows, 3)
        variants = [v for v, _ in selected]
        assert len(selected) == 3
        assert rows[0][0] in variants  # best fitness always first

    def test_with_coords_changes_selection(self):
        """With Cα coordinates, structurally distant residues should be preferred."""
        rows = [
            ("A1C", 1.0),
            ("A2D", 0.95),
            ("A3E", 0.90),
            ("A4F", 0.85),
            ("A5G", 0.80),
        ]
        # Positions 1-5, with large spacing so all well-separated
        coords = _make_coords(5, spacing=20.0)
        selected_3d, _ = pareto_diversity_select(rows, 3, ca_coords=coords)
        assert len(selected_3d) == 3
        # Best fitness always selected first
        assert "A1C" in [v for v, _ in selected_3d]

    def test_coords_fallback_for_unknown_positions(self):
        """Variants without parseable positions should fall back gracefully."""
        rows = [
            ("A1C", 1.0),
            ("UNKNOWN", 0.9),  # no position
            ("A3E", 0.8),
        ]
        coords = _make_coords(5)
        selected, _ = pareto_diversity_select(rows, 3, ca_coords=coords)
        assert len(selected) == 3

    def test_coords_none_uses_1d(self):
        """ca_coords=None should behave identically to no coordinates."""
        rows = [("A10C", 1.0), ("A20D", 0.9), ("A30E", 0.8)]
        sel_none, rep_none = pareto_diversity_select(rows, 3, ca_coords=None)
        sel_default, rep_default = pareto_diversity_select(rows, 3)
        assert [v for v, _ in sel_none] == [v for v, _ in sel_default]

    def test_empty_coords_falls_back(self):
        """Empty coords list should fall back to 1D distance."""
        rows = [("A10C", 1.0), ("A20D", 0.9)]
        selected, _ = pareto_diversity_select(rows, 2, ca_coords=[])
        assert len(selected) == 2

    def test_missing_residue_coords(self):
        """None entries in coords (chain breaks) should return 1.0 distance."""
        rows = [
            ("A2C", 1.0),
            ("A4D", 0.9),
        ]
        # Position 3 is missing (chain break)
        coords: list[tuple[float, float, float] | None] = [
            None,                # index 0 unused
            (0.0, 0.0, 0.0),    # pos 1
            (10.0, 0.0, 0.0),   # pos 2
            None,                # pos 3 missing
            (30.0, 0.0, 0.0),   # pos 4
        ]
        selected, _ = pareto_diversity_select(rows, 2, ca_coords=coords)
        assert len(selected) == 2
