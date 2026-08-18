"""Opt-in skip marker for the mame tests that actually shell out to minimap2.

``tests/mame/conftest.py`` used to carry a ``pytest_collection_modifyitems``
hook that marked EVERY item under ``tests/mame/`` skipped whenever the aligner
was missing.  That is roughly 1,300 items, of which only the ones reaching
``kuma_core.mame.ingest.align`` need the binary; the rest are pure Python.  The
Windows CI leg (``.github/workflows/ci.yml``, which provisions minimap2 for
Linux and macOS only) therefore reported green while running about half the
suite, on the platform this desktop app ships to.

A module opts in with::

    from tests.mame.minimap2_support import requires_minimap2

    pytestmark = requires_minimap2

``skipif`` is used rather than a named custom mark so no ``markers`` entry is
needed and ``--strict-markers`` cannot trip over it.
"""

from __future__ import annotations

import pytest

SKIP_REASON = (
    "minimap2 binary unavailable (e.g. Windows CI leg); "
    "covered on linux/macos + build.yml"
)


def minimap2_available() -> bool:
    """True when ``align._resolve_minimap2`` can locate an executable."""

    try:
        from kuma_core.mame.ingest.align import _resolve_minimap2

        _resolve_minimap2()
    except Exception:
        return False
    return True


requires_minimap2 = pytest.mark.skipif(not minimap2_available(), reason=SKIP_REASON)
