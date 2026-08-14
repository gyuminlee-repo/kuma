"""Coverage-uniformity and consensus-identity reporting.

These five fields (``depth_cv``, ``depth_p10``, ``depth_min_covered``,
``breadth_at_mix_min_depth``, ``consensus_identity``) are REPORT ONLY. Nothing
here asserts a verdict, and the tests below deliberately never construct one:
if a future change makes any of these a gate input, that change owns the
argument for it, not this file.

The helpers are tested directly rather than through
``compute_well_consensuses`` because that path shells out to the bundled
minimap2 binary, which is absent in a plain checkout. The one case that needs
real CIGAR handling feeds ``per_position_depth`` output into ``_depth_stats``,
so the depth vector under test is the same one ``mean_depth`` is computed from.
"""

from __future__ import annotations

import pytest

from kuma_core.mame.ingest.align import Alignment, _CIGAR_M
from kuma_core.mame.ingest.consensus import DEFAULT_MIX_MIN_DEPTH, per_position_depth
from kuma_core.mame.ingest.well_consensus import _consensus_identity, _depth_stats


def _aln(read_seq: str, r_st: int, ref_len: int) -> Alignment:
    """Minimal full-match alignment starting at ``r_st``."""
    return Alignment(
        read_id=f"r{r_st}",
        read_seq=read_seq,
        mapq=60,
        cigar=[[len(read_seq), _CIGAR_M]],
        r_st=r_st,
        r_en=r_st + len(read_seq),
        q_st=0,
        q_en=len(read_seq),
        strand=1,
        reference_length=ref_len,
    )


# ---------------------------------------------------------------------------
# The case mean_depth cannot express
# ---------------------------------------------------------------------------


def test_even_and_holed_wells_share_a_mean_and_differ_in_cv_and_breadth():
    """Same mean depth, different coverage shape.

    The even well is 100x everywhere. The holed well runs 150x over 400
    positions, 0x over the next 200, and 100x over the last 400, which averages
    to the same 100x. ``mean_depth`` cannot tell them apart; ``depth_cv`` and
    ``breadth_at_mix_min_depth`` both can.
    """
    even = [100] * 1000
    holed = [150] * 400 + [0] * 200 + [100] * 400

    assert sum(even) / len(even) == sum(holed) / len(holed)

    cv_even, p10_even, min_even, breadth_even = _depth_stats(even)
    cv_holed, p10_holed, min_holed, breadth_holed = _depth_stats(holed)

    assert cv_even == pytest.approx(0.0)
    assert cv_holed == pytest.approx(0.2)
    assert breadth_even == pytest.approx(1.0)
    assert breadth_holed == pytest.approx(0.8)

    # The covered positions of the holed well are never shallower than the even
    # one, which is exactly why a minimum over covered positions cannot find a
    # hole and breadth has to.
    assert min_even == 100
    assert min_holed == 100
    assert p10_even == pytest.approx(100.0)
    assert p10_holed == pytest.approx(100.0)


def test_a_flat_hole_is_visible_to_breadth_alone():
    """``depth_cv`` ranges over COVERED positions, so a clean gap leaves it at 0.

    This is the boundary of what the CV can say and is the reason breadth is
    reported next to it rather than instead of it.
    """
    holed = [125] * 800 + [0] * 200

    cv, _p10, min_covered, breadth = _depth_stats(holed)

    assert cv == pytest.approx(0.0)
    assert min_covered == 125
    assert breadth == pytest.approx(0.8)


def test_ragged_well_has_nonzero_cv_at_full_breadth():
    """A well can be fully covered and still uneven; cv is what says so."""
    ragged = [10] * 500 + [200] * 500
    cv, p10, min_covered, breadth = _depth_stats(ragged)

    assert breadth == pytest.approx(1.0)
    assert min_covered == 10
    assert cv is not None and cv > 0.5
    # p10 sits in the thin half, where the mean does not.
    assert p10 == pytest.approx(10.0)


def test_breadth_uses_the_mix_min_depth_threshold_over_the_whole_reference():
    """Denominator is the reference, and the threshold is the shared constant."""
    depths = [DEFAULT_MIX_MIN_DEPTH] * 30 + [DEFAULT_MIX_MIN_DEPTH - 1] * 70
    _cv, _p10, min_covered, breadth = _depth_stats(depths)

    assert breadth == pytest.approx(0.3)
    # Every position is covered, so the shallow 70 are counted by breadth and
    # not by the covered minimum.
    assert min_covered == DEFAULT_MIX_MIN_DEPTH - 1


# ---------------------------------------------------------------------------
# None is not 0.0
# ---------------------------------------------------------------------------


def test_no_covered_position_yields_none_not_zero():
    """Nothing covered means the spread is UNKNOWN, and breadth is a real 0.0."""
    cv, p10, min_covered, breadth = _depth_stats([0] * 100)

    assert cv is None
    assert p10 is None
    assert min_covered is None
    assert breadth == 0.0


def test_empty_reference_yields_none_everywhere():
    assert _depth_stats([]) == (None, None, None, None)


def test_single_covered_position_yields_zero_cv_not_an_error():
    """Population deviation: n=1 is a flat sample, not an undefined one."""
    cv, p10, min_covered, breadth = _depth_stats([0] * 99 + [42])

    assert cv == pytest.approx(0.0)
    assert p10 == pytest.approx(42.0)
    assert min_covered == 42
    assert breadth == pytest.approx(0.01)


# ---------------------------------------------------------------------------
# Consensus identity
# ---------------------------------------------------------------------------


def test_wt_like_consensus_scores_identity_one():
    ref = "ACGT" * 25
    assert _consensus_identity(ref, ref) == pytest.approx(1.0)


def test_uncalled_positions_leave_the_denominator():
    """Ns are not mismatches; they are absent from both sides of the ratio."""
    ref = "ACGTACGTAC"
    consensus = "ACGTNNNNAC"

    # 6 called positions, all matching.
    assert _consensus_identity(consensus, ref) == pytest.approx(1.0)


def test_one_substitution_among_ten_called_positions():
    ref = "ACGTACGTAC"
    consensus = "ACGTACGTAG"

    assert _consensus_identity(consensus, ref) == pytest.approx(0.9)


def test_all_n_consensus_is_unknown_not_zero():
    """A well that called nothing has no identity; 0.0 would claim a mismatch."""
    ref = "ACGTACGTAC"

    assert _consensus_identity("N" * 10, ref) is None
    assert _consensus_identity("", ref) is None


def test_total_mismatch_is_a_real_zero():
    """0.0 is the opposite of None: bases were called and none matched."""
    assert _consensus_identity("AAAA", "TTTT") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Same depth vector as mean_depth
# ---------------------------------------------------------------------------


def test_stats_read_the_per_position_depth_vector():
    """Feed real alignments through per_position_depth into _depth_stats.

    Two reads cover positions 0-19, one read covers 20-39, so the reference is
    fully covered but half of it at half the depth. The gap-free case above is
    synthetic; this one goes through the CIGAR walk that produces
    ``mean_depth``.
    """
    ref_len = 40
    alignments = [
        _aln("A" * 20, 0, ref_len),
        _aln("A" * 20, 0, ref_len),
        _aln("A" * 20, 20, ref_len),
    ]
    depths = per_position_depth(alignments, ref_len)
    assert depths[:20] == [2] * 20
    assert depths[20:] == [1] * 20

    cv, p10, min_covered, breadth = _depth_stats(depths, mix_min_depth=2)

    assert min_covered == 1
    assert cv is not None and cv > 0.0
    assert p10 == pytest.approx(1.0)
    # Only the doubly covered half reaches the threshold.
    assert breadth == pytest.approx(0.5)
