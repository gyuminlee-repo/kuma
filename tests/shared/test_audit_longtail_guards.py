"""Contract tests for two guards that answered without being able to.

Both were confirmed against today's code before being touched: one reports a
clean plate because the statistic it uses cannot reach its own threshold at
small n, the other accepts plate addresses that no 96-well plate has.

Each test was run with its fix reverted and fails on its own assertion.
"""

from __future__ import annotations

import math

import pytest

from kuma_core.mame.activity.plate_layout_xlsx import _WELL_RE
from kuma_core.mame.health import detect_cross_talk_with_status

# ---------------------------------------------------------------------------
# A test that cannot fire must not report "ok"
# ---------------------------------------------------------------------------


def _one_dominant_well(n: int) -> dict[str, int]:
    """One barcode holding almost every read, the rest holding almost none.

    The most extreme cross-talk a distribution of this size can express. If
    the check reports a clean plate on this input, it will report a clean
    plate on anything.
    """
    wells = {f"BC{i:02d}": 1 for i in range(1, n)}
    wells[f"BC{n:02d}"] = 1_000_000
    return wells


@pytest.mark.parametrize("n", [5, 6, 7, 8])
def test_sample_sizes_that_cannot_reach_the_threshold_say_so(n: int) -> None:
    """At the default 2.5, no distribution of 5 to 8 barcodes can flag.

    A z taken against a mean and sd that include the point itself is bounded
    by (n-1)/sqrt(n): 1.79 at n=5, 2.47 at n=8. Reverted, this fails by
    returning "ok", which is the check reporting a clean plate on the most
    extreme input it can be given.
    """
    ceiling = (n - 1) / math.sqrt(n)
    assert ceiling <= 2.5, "this n can reach the threshold, so it is the wrong case"

    candidates, status = detect_cross_talk_with_status(_one_dominant_well(n))

    assert candidates == []
    assert status == "insufficient_data"


def test_a_sample_size_that_can_reach_the_threshold_still_flags() -> None:
    """The control. Without it the test above would pass on a function that
    answered insufficient_data for every input, which measures nothing.

    n=9 caps at 2.67, the first size above the default threshold.
    """
    candidates, status = detect_cross_talk_with_status(_one_dominant_well(9))

    assert status == "ok"
    assert [c.well for c in candidates] == ["BC09"]


def test_a_lower_threshold_lets_a_smaller_plate_be_judged() -> None:
    """The bound is compared against the threshold in force, not a constant.

    A caller passing 1.5 can be answered at n=5, where the ceiling is 1.79.
    """
    candidates, status = detect_cross_talk_with_status(
        _one_dominant_well(5), z_threshold=1.5
    )

    assert status == "ok"
    assert [c.well for c in candidates] == ["BC05"]


def test_an_even_distribution_is_clean_rather_than_unjudgeable() -> None:
    """A flat plate at a judgeable size reports ok with nothing flagged, so
    "no candidates" and "could not look" stay distinguishable."""
    candidates, status = detect_cross_talk_with_status(
        {f"BC{i:02d}": 1000 + i for i in range(1, 13)}
    )

    assert status == "ok"
    assert candidates == []


# ---------------------------------------------------------------------------
# A well address is a place on a plate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("well", ["A1", "A01", "A12", "H12", "H1", "B09"])
def test_real_wells_are_accepted(well: str) -> None:
    assert _WELL_RE.match(well)


@pytest.mark.parametrize("well", ["A0", "A00", "A13", "A96", "A99", "H13"])
def test_addresses_no_plate_has_are_refused(well: str) -> None:
    """Column 0 and columns past 12 are not wells.

    Reverted to [0-9]{1,2} this fails: all six matched, and _normalise_well
    then turned A0 into A00, so a typo became a plate address that nothing
    downstream could match back to a sample.
    """
    assert not _WELL_RE.match(well)


@pytest.mark.parametrize("well", ["I1", "Z5", "a1", "1A", "", "A", "AA1"])
def test_malformed_addresses_are_still_refused(well: str) -> None:
    """The row and shape checks the old pattern already made, kept.

    Narrowing the column range must not have widened anything else.
    """
    assert not _WELL_RE.match(well)
