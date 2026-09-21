"""Hold the primer3 thermodynamic engine to its frozen output.

The corpus in ``tests/fixtures/thermo_golden.json`` records what the currently
bundled primer3 returns for the four entry points kuma calls, under the exact
parameter combinations kuma passes. Regenerate it with

    python3 python-core/scripts/gen_thermo_golden.py

Purpose is a baseline, not a behaviour test. primer3-py is GPL and may be
replaced by a permissive engine; these assertions are the yardstick for whether
a replacement returns the same numbers.

A missing or empty fixture fails at import. Treating it as a skip would let the
corpus rot away silently and report green.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import primer3
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "thermo_golden.json"

# Tolerances.
#
# kuma consumes these numbers already rounded: _check_secondary_structure rounds
# Tm to 0.1 C and dG to 0.01 kcal/mol (10 cal/mol), and it gates on Tm at 40.0 C.
# So a difference smaller than the quantum kuma displays cannot change any
# shipped output. Within one build of the same C library the arithmetic is
# deterministic; across platforms the spread comes from libm exp/log, on the
# order of 1e-13 relative, which at 60 C is ~1e-11 C.
#
# 0.01 C and 1.0 cal/mol therefore sit one decade tighter than kuma's own
# rounding, which is where a real engine difference would first show, and many
# decades looser than platform noise. They are not fitted to any observed
# discrepancy; nothing in this corpus has been seen to move at all.
TM_ABS_TOL = 0.01          # degrees Celsius
DG_ABS_TOL = 1.0           # cal/mol, primer3's native unit for dg


def _load() -> dict:
    if not FIXTURE_PATH.exists():
        raise AssertionError(
            f"golden corpus missing: {FIXTURE_PATH}. "
            "Regenerate with python3 python-core/scripts/gen_thermo_golden.py"
        )
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not data.get("entries"):
        raise AssertionError(
            f"golden corpus has no entries: {FIXTURE_PATH}. An empty corpus "
            "checks nothing and must not be reported as a pass."
        )
    return data


GOLDEN = _load()
PARAM_SETS: dict[str, dict] = GOLDEN["param_sets"]
ENTRIES: list[dict] = GOLDEN["entries"]

_CALLERS = {
    "calc_tm": lambda e, p: primer3.calc_tm(e["seq"], **p),
    "calc_hairpin": lambda e, p: primer3.calc_hairpin(e["seq"], **p),
    "calc_homodimer": lambda e, p: primer3.calc_homodimer(e["seq"], **p),
    "calc_heterodimer": lambda e, p: primer3.calc_heterodimer(e["seq"], e["seq2"], **p),
}


def test_corpus_is_populated() -> None:
    """The corpus must cover every call kuma makes, with structures present.

    A corpus of structure-free sequences would pass against an engine that
    detects nothing, so the positive cases are asserted explicitly.
    """
    calls = {e["call"] for e in ENTRIES}
    assert calls == set(_CALLERS), f"corpus does not cover every call: {calls}"

    found = [e for e in ENTRIES if e["expected"].get("structure_found")]
    assert len(found) >= 5, f"only {len(found)} entries have a detected structure"

    threshold = GOLDEN["_meta"]["warn_tm_threshold_degC"]
    above = [e for e in found if e["expected"]["tm"] >= threshold]
    below = [e for e in found if e["expected"]["tm"] < threshold]
    assert len(above) >= 5, f"only {len(above)} structures at or above {threshold} C"
    assert len(below) >= 5, f"only {len(below)} structures below {threshold} C"


def _load_generator():
    """Import the generator by path; it is a script, not an installed module."""
    path = REPO_ROOT / "python-core" / "scripts" / "gen_thermo_golden.py"
    spec = importlib.util.spec_from_file_location("gen_thermo_golden", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recorded_parameters_still_match_the_code() -> None:
    """Every recorded parameter set must still be the one the code issues.

    Without this, changing a concentration or a salt correction would leave all
    794 entries passing while the corpus quietly stopped describing the
    shipped call sites. The generator already reads those values out of the
    modules and resource files, so re-running its builder is the check.
    """
    from kuma_core.kuro import sdm_engine

    generator = _load_generator()
    live = {
        **generator.build_param_sets(),
        **generator.build_structure_param_sets(),
    }
    assert live == PARAM_SETS, (
        "primer3 parameters in the code no longer match the corpus; regenerate "
        "it with python3 python-core/scripts/gen_thermo_golden.py"
    )
    assert PARAM_SETS["design_concs_only"] == dict(sdm_engine._DESIGN_CONCS)


@pytest.mark.parametrize("entry", ENTRIES, ids=[e["id"] for e in ENTRIES])
def test_thermo_matches_golden(entry: dict) -> None:
    params = PARAM_SETS[entry["param_set"]]
    result = _CALLERS[entry["call"]](entry, params)
    expected = entry["expected"]

    if entry["call"] == "calc_tm":
        assert math.isclose(result, expected["tm"], abs_tol=TM_ABS_TOL), (
            f"{entry['id']}: got {result!r}, golden {expected['tm']!r}"
        )
        return

    assert bool(result.structure_found) == expected["structure_found"], (
        f"{entry['id']}: structure_found {result.structure_found} != "
        f"{expected['structure_found']}"
    )
    assert math.isclose(result.tm, expected["tm"], abs_tol=TM_ABS_TOL), (
        f"{entry['id']}: tm {result.tm!r}, golden {expected['tm']!r}"
    )
    assert math.isclose(result.dg, expected["dg"], abs_tol=DG_ABS_TOL), (
        f"{entry['id']}: dg {result.dg!r}, golden {expected['dg']!r}"
    )


def test_report_corpus_size(capsys: pytest.CaptureFixture[str]) -> None:
    """Print what was checked, so a shrinking corpus is visible in the log."""
    from collections import Counter

    counts = Counter(e["call"] for e in ENTRIES)
    threshold = GOLDEN["_meta"]["warn_tm_threshold_degC"]
    found = [e for e in ENTRIES if e["expected"].get("structure_found")]
    with capsys.disabled():
        print(
            f"\nthermo golden corpus: {len(ENTRIES)} entries, "
            f"{len(GOLDEN['sequences'])} sequences, {len(PARAM_SETS)} parameter sets; "
            f"{dict(sorted(counts.items()))}; "
            f"structures found {len(found)}, "
            f">= {threshold} C {sum(1 for e in found if e['expected']['tm'] >= threshold)}, "
            f"< {threshold} C {sum(1 for e in found if e['expected']['tm'] < threshold)}; "
            f"primer3 {GOLDEN['_meta']['primer3_version']}"
        )
