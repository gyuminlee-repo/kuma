"""Opt-in skip marker for the benchmark tests that read the G002 pilot JSONs.

``al.attribution.signal_quality_degradation`` reads three files under
``benchmark/al/results/qa/g002/``. They are not in the repository and cannot be
regenerated in CI: ``.gitignore`` excludes ``results/`` at every depth, and the
driver that writes them (``al.pilot``) needs ESM-2 embeddings to run.

Without a gate the tests fail with ``FileNotFoundError``, which reads as a
defect in the code under test rather than as absent input data.

``tests/mame/minimap2_support.py`` is the pattern: ask whether the thing can
actually be obtained, not whether some name exists.

A module opts in per test with::

    from al.tests.pilot_data_support import requires_g002_pilot

    @requires_g002_pilot
    def test_something_reading_the_pilots(): ...
"""

from __future__ import annotations

import pytest

SKIP_REASON = (
    "G002 pilot JSONs absent (gitignored under results/, and regenerating "
    "them needs ESM-2 embeddings)"
)


def g002_pilot_available() -> bool:
    """True when every pilot JSON ``signal_quality_degradation`` reads exists."""

    try:
        from al.attribution import _G002_DIR

        return all(
            (_G002_DIR / name).is_file()
            for name in ("pilot.json", "pilot_RASK.json", "pilot_GRB2.json")
        )
    except Exception:
        return False


requires_g002_pilot = pytest.mark.skipif(
    not g002_pilot_available(), reason=SKIP_REASON
)
