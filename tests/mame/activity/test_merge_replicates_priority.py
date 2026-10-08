"""Tests for kuma_core.mame.activity.merge.merge_replicates_priority.

Cases per spec §7:
  - authoritative 우선
  - fallback only
  - 양쪽 존재 + mismatch
  - 빈 리스트 → ValueError
"""

import pytest
from kuma_core.mame.activity.merge import merge_replicates_priority
from kuma_core.mame.activity.models import Variant


def _v(s: str) -> Variant:
    return Variant(s)


# ---------------------------------------------------------------------------
# Case 1: authoritative 우선 — auth value used, not fallback
# ---------------------------------------------------------------------------

def test_authoritative_takes_priority():
    auth = {_v("F10A"): [1.0, 1.2]}
    fall = {_v("F10A"): [0.5, 0.5]}
    merged, stats = merge_replicates_priority(auth, fall, mismatch_threshold=0.1)
    # auth mean = 1.1, fall mean = 0.5  → diff=0.6 > 0.1 → mismatched
    assert abs(merged[_v("F10A")] - 1.1) < 1e-9
    assert _v("F10A") in stats.mismatched
    assert stats.authoritative_count == 1
    assert stats.fallback_count == 1
    assert stats.merged_count == 1


# ---------------------------------------------------------------------------
# Case 2: fallback only — variant absent from authoritative
# ---------------------------------------------------------------------------

def test_fallback_only_variant_included():
    auth = {}
    fall = {_v("F10B"): [0.8, 0.9, 0.85]}
    merged, stats = merge_replicates_priority(auth, fall)
    expected_mean = (0.8 + 0.9 + 0.85) / 3
    assert abs(merged[_v("F10B")] - expected_mean) < 1e-9
    assert stats.merged_count == 1
    assert stats.mismatched == []


# ---------------------------------------------------------------------------
# Case 3: both exist, within threshold — no mismatch flag
# ---------------------------------------------------------------------------

def test_within_threshold_no_mismatch():
    auth = {_v("F20A"): [1.0]}
    fall = {_v("F20A"): [1.05]}
    merged, stats = merge_replicates_priority(auth, fall, mismatch_threshold=0.1)
    # diff = 0.05 <= 0.1 → no mismatch
    assert abs(merged[_v("F20A")] - 1.0) < 1e-9
    assert stats.mismatched == []


# ---------------------------------------------------------------------------
# Case 4: empty list in authoritative → ValueError
# ---------------------------------------------------------------------------

def test_empty_authoritative_list_raises():
    auth = {_v("F30A"): []}
    fall = {_v("F30A"): [1.0]}
    with pytest.raises(ValueError, match="authoritative.*F30A.*empty"):
        merge_replicates_priority(auth, fall)


# ---------------------------------------------------------------------------
# Case 5: empty list in fallback → ValueError
# ---------------------------------------------------------------------------

def test_empty_fallback_list_raises():
    auth = {_v("F40A"): [1.0]}
    fall = {_v("F40A"): []}
    with pytest.raises(ValueError, match="fallback.*F40A.*empty"):
        merge_replicates_priority(auth, fall)


# ---------------------------------------------------------------------------
# Edge: both dicts empty → merged empty, stats all zeros
# ---------------------------------------------------------------------------

def test_both_empty_dicts():
    merged, stats = merge_replicates_priority({}, {})
    assert merged == {}
    assert stats.merged_count == 0
    assert stats.mismatched == []


# ---------------------------------------------------------------------------
# Edge: variable replicate counts (n=1, 2, 4 in same call)
# ---------------------------------------------------------------------------

def test_variable_replicate_counts():
    auth = {
        _v("F01A"): [1.0],                # n=1
        _v("F02B"): [0.5, 0.7],           # n=2
        _v("F03C"): [1.0, 1.2, 0.8, 1.0], # n=4
    }
    merged, stats = merge_replicates_priority(auth, {})
    assert abs(merged[_v("F01A")] - 1.0) < 1e-9
    assert abs(merged[_v("F02B")] - 0.6) < 1e-9
    assert abs(merged[_v("F03C")] - 1.0) < 1e-9
    assert stats.merged_count == 3
