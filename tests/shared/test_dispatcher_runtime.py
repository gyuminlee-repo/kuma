"""Contract tests for the memory warning both sidecars emit.

This notification crosses three layers: built here, forwarded by the Rust
sidecar as ``sidecar://progress``, and read by ``src/store/appStore.ts``. No
test reached it before, and no ``.cross-layer-sync.json`` group names it, so
the shape was pinned by nothing at all. That is what made moving this code out
of the two dispatchers unsafe: a mistake would have been silent on both sides.

The tests were written before the dispatchers switched over, so they describe
the behaviour that already shipped rather than the behaviour of the move.
"""

from __future__ import annotations

from typing import Any

import pytest

from kuma_core.shared.dispatcher_runtime import build_memory_warning
from kuma_core.shared.memory_monitor import BLOCK_THRESHOLD, WARN_THRESHOLD

#: One gibibyte, so the reported rss_mb is a round number to assert on.
_ONE_GIB = 1024 * 1024 * 1024


def _warning(ratio: float | None, rss_bytes: int = _ONE_GIB) -> dict[str, Any] | None:
    return build_memory_warning(
        ratio,
        rss_bytes,
        warn_threshold=WARN_THRESHOLD,
        block_threshold=BLOCK_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# When it speaks and when it does not
# ---------------------------------------------------------------------------


def test_below_the_warn_threshold_says_nothing() -> None:
    assert _warning(WARN_THRESHOLD - 0.01) is None


def test_at_the_warn_threshold_speaks() -> None:
    """The comparison is >=, so the threshold itself warns.

    Pinned because a later >  would move the boundary by one sample without
    any test noticing.
    """
    message = _warning(WARN_THRESHOLD)
    assert message is not None
    assert message["params"]["level"] == "warn"


def test_at_the_block_threshold_the_level_changes() -> None:
    message = _warning(BLOCK_THRESHOLD)
    assert message is not None
    assert message["params"]["level"] == "block"


def test_just_under_the_block_threshold_is_still_warn() -> None:
    """The control for the test above: without it, a function returning
    "block" for everything above the warn line would pass."""
    message = _warning(BLOCK_THRESHOLD - 0.01)
    assert message is not None
    assert message["params"]["level"] == "warn"


def test_an_unmeasurable_ratio_produces_no_notification() -> None:
    """None means the system total could not be read.

    Not the same as a low ratio: the caller logs that the guard is not being
    enforced. Sending a notification here would report a memory figure nobody
    measured.
    """
    assert _warning(None) is None


# ---------------------------------------------------------------------------
# The shape the other two layers read
# ---------------------------------------------------------------------------


def test_the_envelope_is_what_the_rust_forwarder_matches() -> None:
    """method="progress" is what src-tauri forwards on; a different method
    name is dropped silently rather than rejected."""
    message = _warning(0.9)
    assert message is not None
    assert message["jsonrpc"] == "2.0"
    assert message["method"] == "progress"


def test_the_params_carry_every_field_the_frontend_reads() -> None:
    """type distinguishes this from stage progress; the other three are what
    the notice renders. A missing key reaches the UI as undefined."""
    message = _warning(0.9)
    assert message is not None
    assert set(message["params"]) == {"type", "ratio", "rss_mb", "level"}
    assert message["params"]["type"] == "memory_warning"


def test_the_ratio_is_reported_as_a_fraction_not_a_percentage() -> None:
    """0.9 rather than 90. The store multiplies, so a percentage here would
    render as 9000 percent."""
    message = _warning(0.9)
    assert message is not None
    assert message["params"]["ratio"] == pytest.approx(0.9)


def test_rss_is_reported_in_megabytes() -> None:
    """The field is named rss_mb and the source is bytes, so the conversion
    is part of the contract rather than an implementation detail."""
    message = _warning(0.9, rss_bytes=_ONE_GIB)
    assert message is not None
    assert message["params"]["rss_mb"] == pytest.approx(1024.0)


def test_the_reported_numbers_are_rounded() -> None:
    """Four places on the ratio and one on the megabytes, so the notification
    does not carry a float's full tail into the UI."""
    # Above the warn threshold, because a ratio low enough to show the
    # rounding would emit nothing at all.
    message = _warning(0.623456789, rss_bytes=1_234_567)
    assert message is not None
    assert message["params"]["ratio"] == 0.6235
    assert message["params"]["rss_mb"] == 1.2


def test_the_thresholds_are_read_from_arguments_not_recomputed() -> None:
    """A caller passing its own thresholds gets them honoured.

    This is what lets the two sidecars share the function while keeping the
    freedom to differ, and it is also how the boundary tests above stay
    meaningful if the shipped constants ever move.
    """
    message = build_memory_warning(
        0.3, _ONE_GIB, warn_threshold=0.2, block_threshold=0.25
    )
    assert message is not None
    assert message["params"]["level"] == "block"


def test_the_shipped_thresholds_are_still_the_ones_documented() -> None:
    """The docstrings in both dispatchers quote these numbers."""
    assert WARN_THRESHOLD == 0.50
    assert BLOCK_THRESHOLD == 0.70
