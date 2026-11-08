"""A Mutation rebuilt field by field loses the row that requested it.

``Mutation.group_id`` names the input row a substitution came from, and it is
the only thing that says ``A2V`` was one half of ``A2V/A3G``. It also defaults
to None, so a constructor call that simply omits it is accepted, returns a
Mutation that looks complete and silently drops the identity. That is how the
codon enumeration in ``design_single_sdm`` and the one in
``diagnose_sdm_failure`` dropped it, and how the per-row parse fallback in
``design_sdm_primers`` dropped it again.

A field-by-field rebuild of an existing Mutation is therefore refused here:
``dataclasses.replace`` is the way to change a field. The sites that genuinely
mint a Mutation from something other than a Mutation are named below, and each
one has to state what it means by leaving the group out.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNED = [
    ROOT / "kuma_core",
    ROOT / "python-core" / "sidecar_kuro",
    ROOT / "python-core" / "sidecar_mame",
]
CONSTRUCTORS = {"Mutation", "_Mut"}

# (path relative to ROOT, enclosing function) -> why no group_id belongs there.
ALLOWED: dict[tuple[str, str], str] = {
    ("kuma_core/kuro/sdm_engine.py", "evaluate_custom_primer"): (
        "A placeholder describing an operator-supplied primer. There is no "
        "source row behind it, so there is no group to carry."
    ),
    ("python-core/sidecar_kuro/handlers/design.py", "_build_mutation"): (
        "Pool rescue designs a DIFFERENT substitution than the one that "
        "failed. Inheriting the failed row's group would claim a genotype "
        "nobody asked for, so None is the answer here."
    ),
}


def _offending_calls(source: str) -> list[tuple[int, str]]:
    """Return (line, enclosing function) for each group-less construction."""
    found: list[tuple[int, str]] = []
    stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def _visit_scope(self, node) -> None:
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_FunctionDef = _visit_scope
        visit_AsyncFunctionDef = _visit_scope
        visit_ClassDef = _visit_scope

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            name = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute)
                else None
            )
            if name in CONSTRUCTORS and not any(
                kw.arg == "group_id" for kw in node.keywords
            ):
                found.append((node.lineno, stack[-1] if stack else "<module>"))
            self.generic_visit(node)

    Visitor().visit(ast.parse(source))
    return found


def test_detector_flags_a_rebuild_and_accepts_the_alternatives() -> None:
    rebuild = (
        "def f(m):\n"
        "    return Mutation(raw=m.raw, wt_aa=m.wt_aa, position=m.position,\n"
        "                    mt_aa=m.mt_aa, codon_start=m.codon_start,\n"
        "                    wt_codon=m.wt_codon, mt_codon='GTT')\n"
    )
    assert _offending_calls(rebuild) == [(2, "f")]
    assert _offending_calls("def f(m):\n    return replace(m, mt_codon='GTT')\n") == []
    assert _offending_calls(
        "def f(m):\n    return Mutation(raw=m.raw, group_id=m.group_id)\n"
    ) == []
    # The aliased import the parse fallback used, so renaming the symbol is not
    # a way past this check.
    assert _offending_calls("def f():\n    return _Mut(raw='A2V')\n") == [(2, "f")]


def test_detector_finds_the_pre_fix_sites() -> None:
    """The three sites this guard exists for, as they were before the fix.

    Checked against the real pre-fix text rather than a sketch of it, so the
    guard is known to catch what it was written to catch.
    """
    import subprocess

    for path, function in [
        ("kuma_core/kuro/sdm_engine.py", "design_single_sdm"),
        ("kuma_core/kuro/sdm_engine.py", "diagnose_sdm_failure"),
        ("kuma_core/kuro/sdm_engine.py", "design_sdm_primers"),
    ]:
        proc = subprocess.run(
            ["git", "show", f"origin/main:{path}"],
            cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            import pytest

            pytest.skip("origin/main is not available in this checkout")
        offenders = {name for _line, name in _offending_calls(proc.stdout)}
        assert function in offenders, f"{path}:{function} was expected to offend"


def test_no_mutation_is_rebuilt_field_by_field() -> None:
    files = [path for base in SCANNED for path in sorted(base.rglob("*.py"))]
    assert files, "scan found no sources"
    offenders: list[str] = []
    exercised: set[tuple[str, str]] = set()
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        for line, function in _offending_calls(path.read_text(encoding="utf-8")):
            if (relative, function) in ALLOWED:
                exercised.add((relative, function))
                continue
            offenders.append(f"{relative}:{line} in {function}()")
    # A stale exemption is how a check like this quietly stops checking.
    assert exercised == set(ALLOWED), (
        "ALLOWED names a site that no longer builds a Mutation without a "
        f"group: {sorted(set(ALLOWED) - exercised)}"
    )
    assert offenders == [], (
        "Mutation built without group_id. Use dataclasses.replace to change a "
        "field of an existing Mutation, or add the site to ALLOWED with the "
        "reason it has no source row: " + ", ".join(offenders)
    )
