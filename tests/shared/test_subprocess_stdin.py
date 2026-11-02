"""Every child process started from sidecar code must not inherit stdin.

The sidecar's stdin is the host's JSON-RPC pipe. A child that inherits it can
read request bytes meant for the dispatcher, and it keeps the pipe's read end
open, so the host's writer cannot see the sidecar exit while the child lives.
Each subprocess call in ``kuma_core`` and the sidecar adapters therefore states
its stdin (``subprocess.DEVNULL``, a pipe, or ``input=``).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNED = [ROOT / "kuma_core", ROOT / "python-core" / "sidecar_kuro", ROOT / "python-core" / "sidecar_mame"]
SPAWNERS = {"run", "Popen", "call", "check_call", "check_output"}


def _calls_without_stdin(source: str) -> list[int]:
    missing = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in SPAWNERS
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        ):
            continue
        keywords = {kw.arg for kw in node.keywords}
        if not keywords & {"stdin", "input"}:
            missing.append(node.lineno)
    return missing


def test_detector_flags_an_inherited_stdin() -> None:
    assert _calls_without_stdin("import subprocess\nsubprocess.run(['x'])\n") == [2]
    assert _calls_without_stdin("import subprocess\nsubprocess.run(['x'], stdin=subprocess.DEVNULL)\n") == []
    assert _calls_without_stdin("import subprocess\nsubprocess.run(['x'], input='y')\n") == []


def test_sidecar_subprocesses_do_not_inherit_stdin() -> None:
    offenders = []
    files = [path for base in SCANNED for path in sorted(base.rglob("*.py"))]
    assert files, "scan found no sources"
    for path in files:
        for line in _calls_without_stdin(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(ROOT)}:{line}")
    assert offenders == []
