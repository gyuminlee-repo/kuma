"""Opt-in skip marker for the benchmark tests that need fair-esm.

Three modules gated on ``importlib.util.find_spec("esm")`` or
``pytest.importorskip("esm")``, which ask whether anything named ``esm`` is
importable. Two different distributions claim that name: ``fair-esm``, which
these tests call through ``esm.pretrained``, and EvolutionaryScale's ``esm``
(ESM3), which has no ``pretrained`` attribute at all. With the second one
installed the gate passes and the test dies at
``AttributeError: module 'esm' has no attribute 'pretrained'``, which reads as
a failure of the code under test rather than as a missing dependency.

Resolving the entry point rather than the name is what
``tests/mame/minimap2_support.py`` already does for the aligner, and this
follows it.

A module opts in per test with::

    from al.tests.fair_esm_support import requires_fair_esm

    @requires_fair_esm
    def test_something_needing_the_model(): ...

``skipif`` is used rather than a named custom mark so no ``markers`` entry is
needed and ``--strict-markers`` cannot trip over it.
"""

from __future__ import annotations

import pytest

SKIP_REASON = (
    "fair-esm unavailable (esm.pretrained does not resolve); "
    "a different distribution may own the 'esm' name"
)


def fair_esm_available() -> bool:
    """True when ``esm.pretrained`` resolves, not merely when ``esm`` imports."""

    try:
        import esm

        return getattr(esm, "pretrained", None) is not None
    except Exception:
        return False


requires_fair_esm = pytest.mark.skipif(
    not fair_esm_available(), reason=SKIP_REASON
)
