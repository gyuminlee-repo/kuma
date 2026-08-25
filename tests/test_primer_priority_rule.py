"""Bench priority order for writing an SDM primer (Hyemin, 2026-08-24).

The order used at the bench when the automatic run misses the spec:

1. primer length is at least 18 nt,
2. Tm sits as close to the target as possible,
3. between two that sit about equally close, take the one below the target.

Priority 1 is a hard bound and is asserted against the resolved profiles and
the rescue floor. Priorities 2 and 3 are the ranking, and _tm_score carries
both: it is the distance to the target with a surcharge on running hot, so a
hotter candidate wins only when it is meaningfully closer.
"""
from __future__ import annotations

import pytest

from kuma_core.kuro.sdm_engine import (
    DEFAULT_FWD_LEN_MIN,
    DEFAULT_REV_LEN_MIN,
    _TM_OVERSHOOT_WEIGHT,
    _tm_score,
)
from kuma_core.kuro.polymerase import PolymeraseRegistry

MIN_PRIMER_LEN = 18


def test_priority_1_every_builtin_profile_floors_at_18():
    registry = PolymeraseRegistry()
    for name in registry.list_names():
        profile = registry.get(name)
        # None means "take the engine fallback", which the next test pins at 18.
        # A built-in that leaves the floor unset would still be safe, but every
        # one of them states it, so an unset floor here is a profile that lost
        # its length spec rather than one deferring on purpose.
        assert profile.fwd_len_min is not None, name
        assert profile.rev_len_min is not None, name
        assert profile.fwd_len_min >= MIN_PRIMER_LEN, name
        assert profile.rev_len_min >= MIN_PRIMER_LEN, name


def test_priority_1_engine_fallbacks_floor_at_18():
    assert DEFAULT_FWD_LEN_MIN >= MIN_PRIMER_LEN
    assert DEFAULT_REV_LEN_MIN >= MIN_PRIMER_LEN


def test_priority_2_closer_to_target_scores_lower():
    target = 62.0
    assert _tm_score(61.5, target) < _tm_score(59.0, target)
    assert _tm_score(62.5, target) < _tm_score(65.0, target)
    assert _tm_score(target, target) == 0.0


@pytest.mark.parametrize("delta", [0.1, 0.5, 1.0, 2.0, 4.0])
def test_priority_3_equal_distance_goes_to_the_cooler_primer(delta):
    target = 62.0
    assert _tm_score(target - delta, target) < _tm_score(target + delta, target)


def test_priority_3_yields_when_the_hotter_primer_is_clearly_closer():
    """Rule 3 breaks a near-tie. It does not outrank rule 2.

    The surcharge is a fixed relative weight, so the hot candidate wins exactly
    when the cool one sits more than (1 + weight) times further away.
    """
    target = 62.0
    hot_dev = 1.0
    boundary = hot_dev * (1.0 + _TM_OVERSHOOT_WEIGHT)
    assert _tm_score(target + hot_dev, target) < _tm_score(target - boundary - 0.1, target)
    assert _tm_score(target + hot_dev, target) > _tm_score(target - boundary + 0.1, target)
