"""Tests for al.firewall (oracle leak control, plan F1)."""

from __future__ import annotations

import pytest

from al.firewall import (
    OracleLeak,
    assert_round1_label_invariant,
    round1_select,
    topn_by_score,
)

_VARIANTS = ["A1V", "A1L", "G2D", "G2E", "M3K", "M3R"]
_COLD = {"A1V": 0.9, "A1L": 0.1, "G2D": 0.8, "G2E": 0.2, "M3K": 0.7, "M3R": 0.3}
_ORACLE = {"A1V": 5.0, "A1L": 1.0, "G2D": 4.0, "G2E": 2.0, "M3K": 3.0, "M3R": 0.5}


def test_round1_topn_uses_only_cold_start():
    picks = round1_select(_VARIANTS, _COLD, 3, selector=topn_by_score)
    # By cold-start score: A1V(.9) > G2D(.8) > M3K(.7)
    assert picks == ["A1V", "G2D", "M3K"]


def test_round1_rejects_missing_cold_start():
    with pytest.raises(ValueError):
        round1_select(_VARIANTS, {"A1V": 0.9}, 2, selector=topn_by_score)


def test_permutation_invariance_passes_for_clean_round1():
    # A correct round-1 ranks by cold-start (closure) and IGNORES the oracle arg.
    def clean_round1(_labels):
        return round1_select(_VARIANTS, _COLD, 3, selector=topn_by_score)

    # Must not raise: selection is identical under any oracle permutation.
    assert_round1_label_invariant(clean_round1, _ORACLE, seed=1)


def test_permutation_invariance_detects_a_leaking_round1():
    """A round-1 fn that secretly ranks by the oracle labels must be caught."""
    def leaking_round1(labels):
        # BUG (intentional): ranks by the oracle labels it was handed.
        return sorted(_VARIANTS, key=lambda v: (-labels[v], v))[:3]

    with pytest.raises(OracleLeak):
        assert_round1_label_invariant(leaking_round1, _ORACLE, seed=2)