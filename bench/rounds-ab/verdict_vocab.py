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

import ast
import os
import sys
from collections import Counter
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


def _guard_names():
    """The abort guards this module exports, read off the module itself.

    Typing the three names into a list here would be the same hand-copied
    closed list these checkers exist to remove. A fourth require_* guard added
    later is picked up with no edit.
    """
    return {n for n, o in vars(sys.modules[__name__]).items()
            if n.startswith("require_") and callable(o)}


def guard_sites(path):
    """Return (kind, line) for every always-on abort site in a checker file.

    Parsed out of the file, never declared, so adding or dropping a guard moves
    the number with nobody editing a total. Two kinds count: a call to one of
    this module's require_* guards, and a bare `raise SystemExit(...)`. Both
    stop the run where the violation is, which is why they never show up in the
    known-answer tally.

    LIMIT: the match is by bare name, so a guard reached under an alias
    (`import ... as rt`) or wrapped in a local helper is not seen here.
    """
    names = _guard_names()
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=str(path))
    sites = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id in names):
            sites.append((node.func.id, node.lineno))
        elif (isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name)
                and node.exc.func.id == "SystemExit"):
            sites.append(("inline SystemExit", node.lineno))
    return sorted(sites, key=lambda s: s[1])


def guard_line(path):
    """One line naming the always-on guards of `path`, counted from its source.

    Kept apart from the known-answer tally on purpose. A known-answer check
    asks whether a number equals the declared answer; a guard asks whether the
    tally is structurally possible at all, and merging the two would report one
    protection where there are two.
    """
    sites = guard_sites(path)
    kinds = Counter(k for k, _ in sites)
    detail = ", ".join(f"{k} x{n}" for k, n in sorted(kinds.items()))
    return (f"always-on guards: {len(sites)} abort sites in {Path(path).name} "
            f"({detail}), counted from its source; any violation aborts the "
            f"run before this line")
