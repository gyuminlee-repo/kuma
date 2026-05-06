"""Tests for kuma_core.mame.activity.sanity_check.

5 cases per spec §6-A.5:
  1. clean           — all layout↔EP match → empty list
  2. 2-swap          — 2 labels swapped → 1 SwapWarning severity=error
  3. 3-cycle         — cyclic 3-label rotation → 1 SwapWarning code=label_swap_cycle
  4. value_collision — same value in 2 prev-EP variants → severity=warning
  5. layout_orphan   — layout label absent from prev EP → severity=warning

Fixture values are synthetic to avoid hardcoding real experimental data.
"""

from kuma_core.mame.activity.sanity_check import detect_label_swap
from kuma_core.mame.activity.models import SwapWarning


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _layout(*pairs: tuple[str, str]) -> list[tuple[str, str]]:
    """Build a layout list from (mutant_internal, well_id) tuples."""
    return list(pairs)


# ---------------------------------------------------------------------------
# Case 1: clean — no mismatches
# ---------------------------------------------------------------------------

def test_clean_returns_empty():
    layout = _layout(("F10A", "A01"), ("F10B", "A02"), ("F10C", "A03"))
    activity_map = {"A01": 0.50, "A02": 0.70, "A03": 0.90}
    # prev EP uses short notation matching the measured values exactly.
    prev_ep = {"10A": 0.50, "10B": 0.70, "10C": 0.90}
    result = detect_label_swap(layout, activity_map, prev_ep)
    assert result == [], f"Expected no warnings, got: {result}"


# ---------------------------------------------------------------------------
# Case 2: 2-swap — two labels exchanged
# ---------------------------------------------------------------------------

def test_two_swap_severity_error():
    # Layout says A01=F10A (short=10A) and A02=F10B (short=10B).
    # But measured values are swapped relative to prev EP:
    #   measured A01=0.70 matches prev_ep 10B
    #   measured A02=0.50 matches prev_ep 10A
    layout = _layout(("F10A", "A01"), ("F10B", "A02"))
    activity_map = {"A01": 0.70, "A02": 0.50}
    prev_ep = {"10A": 0.50, "10B": 0.70}
    result = detect_label_swap(layout, activity_map, prev_ep)
    assert len(result) == 1
    w = result[0]
    assert isinstance(w, SwapWarning)
    assert w.severity == "error"
    assert w.code == "label_swap_cycle"
    # Both swapped variants should appear.
    assert set(w.variants) == {"10A", "10B"}


# ---------------------------------------------------------------------------
# Case 3: 3-cycle — cyclic permutation of three labels
# (mirrors real 426D/E/N data pattern with synthetic values)
# ---------------------------------------------------------------------------

def test_three_cycle_label_swap():
    # Layout: A→10D, B→10E, C→10N
    # Measured: A01=0.81, A02=0.63, A03=0.55
    # Prev EP:  10D=0.63, 10E=0.55, 10N=0.81  (cyclic shift)
    layout = _layout(("F10D", "A01"), ("F10E", "A02"), ("F10N", "A03"))
    activity_map = {"A01": 0.81, "A02": 0.63, "A03": 0.55}
    prev_ep = {"10D": 0.63, "10E": 0.55, "10N": 0.81}
    result = detect_label_swap(layout, activity_map, prev_ep)
    # Expect exactly one swap-cycle warning covering 3 variants.
    swap_warnings = [w for w in result if w.code == "label_swap_cycle"]
    assert len(swap_warnings) >= 1
    cycle_w = swap_warnings[0]
    assert isinstance(cycle_w, SwapWarning)
    assert cycle_w.severity == "error"
    assert len(cycle_w.variants) == 3
    assert set(cycle_w.variants) == {"10D", "10E", "10N"}


# ---------------------------------------------------------------------------
# Case 4: value_collision — same value matches multiple prev-EP variants
# ---------------------------------------------------------------------------

def test_value_collision_warning():
    # Two prev-EP variants have identical activity value.
    layout = _layout(("F20A", "B01"))
    activity_map = {"B01": 1.234}
    prev_ep = {"20A": 1.234, "20B": 1.234}  # value_collision
    result = detect_label_swap(layout, activity_map, prev_ep)
    collision_warnings = [w for w in result if w.code == "value_collision"]
    assert len(collision_warnings) == 1
    w = collision_warnings[0]
    assert w.severity == "warning"
    assert set(w.variants) == {"20A", "20B"}


# ---------------------------------------------------------------------------
# Case 5: layout_orphan — label absent from prev EP
# ---------------------------------------------------------------------------

def test_layout_orphan_warning():
    # New mutant not present in prev EP at all.
    layout = _layout(("F99Z", "C01"))
    activity_map = {"C01": 0.55}
    prev_ep = {"10A": 0.50}  # 99Z absent
    result = detect_label_swap(layout, activity_map, prev_ep)
    orphan_warnings = [w for w in result if w.code == "layout_orphan"]
    assert len(orphan_warnings) == 1
    w = orphan_warnings[0]
    assert w.severity == "warning"
    assert "99Z" in w.variants


# ---------------------------------------------------------------------------
# Edge: WT wells are excluded from swap detection
# ---------------------------------------------------------------------------

def test_wt_wells_excluded():
    # WT in layout must not produce any swap warnings.
    layout = _layout(("WT", "H12"))
    activity_map = {"H12": 1.0}
    prev_ep = {"10A": 1.0}  # Value match but WT is excluded
    result = detect_label_swap(layout, activity_map, prev_ep)
    swap_warnings = [w for w in result if w.code == "label_swap_cycle"]
    assert swap_warnings == []


# ---------------------------------------------------------------------------
# Edge: round_n=1 (empty prev_ep) → always empty result
# ---------------------------------------------------------------------------

def test_round1_empty_prev_ep_returns_empty():
    layout = _layout(("F10A", "A01"), ("F10B", "A02"))
    activity_map = {"A01": 0.50, "A02": 0.70}
    result = detect_label_swap(layout, activity_map, prev_round_evolvepro={})
    assert result == []
