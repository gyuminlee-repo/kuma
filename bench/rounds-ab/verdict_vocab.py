"""The verdict vocabulary these checkers use, read off the product enum.

A hand-typed class list is what these checkers got wrong: one of them carried a
class named NO_READS, which exists nowhere in kuma, and the name spread into the
release README from there. The list is therefore not typed out in any checker.
It is read off VerdictClass in kuma_core/mame/models.py, the same way the two
figure scripts under release_r2/figures/ already read it.

Search order for the kuma checkout: KUMA_REPO_ROOT, then any ancestor of this
file holding kuma_core. The figure scripts also fall back to
$WORKSPACE_ROOT/cc/kuma/..., because they live in the vault and have no kuma
ancestor. This module ships inside the repository it is looking for, so the
ancestor scan always succeeds and that fallback is left out on purpose.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_verdict_class():
    """Return the VerdictClass enum itself. Not finding it is a hard error."""
    cands = []
    env = os.environ.get("KUMA_REPO_ROOT")
    if env:
        cands.append(Path(env))
    cands.extend(HERE.parents)
    for root in cands:
        if (root / "kuma_core" / "mame" / "models.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from kuma_core.mame.models import VerdictClass
            return VerdictClass
    raise ImportError(
        "kuma_core.mame.models not found; set KUMA_REPO_ROOT to a kuma checkout")


VerdictClass = load_verdict_class()

# The vocabulary, in the order the enum declares it.
CLASSES = [v.value for v in VerdictClass]
CLASS_SET = frozenset(CLASSES)


def require_known(verdict, where):
    """Reject a verdict string the product cannot produce, loudly.

    Skipping an unrecognised verdict is how a miscounted class hides: the
    record leaves the numerator and nothing says so. Callers pass `where` so
    the message names the record rather than only the value.
    """
    if verdict not in CLASS_SET:
        raise SystemExit(
            f"ABORT: {where} carries verdict {verdict!r}, which is not a "
            f"VerdictClass member. Declared vocabulary: {CLASSES}")
    return verdict


def require_total(counts, n, where):
    """Require a per-class tally to account for every record it was built from.

    A closed list plus a silent `.get(cls, 0)` reports a plausible table even
    when records fell outside the list. Comparing the tally against the record
    count is what makes that visible.
    """
    total = sum(counts.values())
    if total != n:
        raise SystemExit(
            f"ABORT: {where} tallies {total} records but {n} were read; "
            f"{n - total} went uncounted")
    return total


def require_full_vocabulary(keys, where):
    """Require a hand-declared expectation table to cover exactly the enum.

    The expected values stay hand-written on purpose: they are the known answer
    and reading them off the artefact would make the check examine itself. Only
    the key set is tied to the enum, so a ninth class makes these checkers fail
    instead of quietly reporting an eight-row table.
    """
    got, want = set(keys), set(CLASSES)
    if got != want:
        raise SystemExit(
            f"ABORT: {where} declares {sorted(got)}, the enum declares "
            f"{sorted(want)}; missing {sorted(want - got)}, "
            f"unknown {sorted(got - want)}")
