"""Tests for ESM-2 integration in pareto_diversity_select."""

from __future__ import annotations

import pytest

from kuro.evolvepro import pareto_diversity_select


def _make_embedding(n: int, dim: int = 4) -> list[list[float]]:
    """Create a simple embedding. Each residue has a unique direction."""
    emb = []
    for i in range(n):
        vec = [0.0] * dim
        vec[i % dim] = 1.0 + i * 0.1
        emb.append(vec)
    return emb


class TestParetoWithEsm:
    """Test pareto_diversity_select with esm_embedding parameter."""

    def test_without_embedding_uses_1d(self):
        """Without embedding, 1D position distance should be used."""
        rows = [
            ("A10C", 1.0),
            ("A11D", 0.9),
            ("A50E", 0.8),
            ("A51F", 0.7),
            ("A100G", 0.6),
        ]
        selected, replaced = pareto_diversity_select(rows, 3)
        variants = [v for v, _ in selected]
        # Should pick spread-out positions
        assert len(selected) == 3
        assert rows[0][0] in variants  # best fitness always first

    def test_with_embedding_changes_selection(self):
        """With ESM embedding, structurally distant residues should be preferred."""
        # Create variants at positions 1-5
        rows = [
            ("A1C", 1.0),
            ("A2D", 0.95),
            ("A3E", 0.90),
            ("A4F", 0.85),
            ("A5G", 0.80),
        ]
        # Embedding: positions 1 and 5 are orthogonal, 2,3,4 are similar to 1
        emb = [
            [1.0, 0.0, 0.0, 0.0],  # pos 1
            [0.9, 0.1, 0.0, 0.0],  # pos 2 ~ similar to 1
            [0.8, 0.2, 0.0, 0.0],  # pos 3 ~ similar to 1
            [0.7, 0.3, 0.0, 0.0],  # pos 4 ~ similar to 1
            [0.0, 0.0, 1.0, 0.0],  # pos 5 ~ orthogonal to 1
        ]
        selected_esm, _ = pareto_diversity_select(rows, 3, esm_embedding=emb)
        selected_1d, _ = pareto_diversity_select(rows, 3)

        esm_variants = [v for v, _ in selected_esm]
        # ESM should pick pos 5 earlier because it is structurally distant
        assert "A5G" in esm_variants

    def test_embedding_fallback_for_unknown_positions(self):
        """Variants without parseable positions should fall back gracefully."""
        rows = [
            ("A1C", 1.0),
            ("UNKNOWN", 0.9),  # no position
            ("A3E", 0.8),
        ]
        emb = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
        selected, _ = pareto_diversity_select(rows, 3, esm_embedding=emb)
        assert len(selected) == 3

    def test_embedding_none_uses_1d(self):
        """esm_embedding=None should behave identically to no embedding."""
        rows = [("A10C", 1.0), ("A20D", 0.9), ("A30E", 0.8)]
        sel_none, rep_none = pareto_diversity_select(rows, 3, esm_embedding=None)
        sel_default, rep_default = pareto_diversity_select(rows, 3)
        assert [v for v, _ in sel_none] == [v for v, _ in sel_default]

    def test_empty_embedding(self):
        """Empty embedding list should fall back to 1D distance."""
        rows = [("A10C", 1.0), ("A20D", 0.9)]
        selected, _ = pareto_diversity_select(rows, 2, esm_embedding=[])
        assert len(selected) == 2
