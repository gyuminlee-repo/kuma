"""``.githooks/commit-msg`` has to run on the Bash 3.2 that macOS ships.

``#!/usr/bin/env bash`` resolves to /bin/bash 3.2 on a stock Mac, where
``${var,,}`` is a "bad substitution" and a correctly signed commit is refused.
No Bash 3.2 is available here, so the first test is a static scan for the
Bash 4-only constructs; the second runs the hook to pin the behaviour the
portable rewrite keeps (address compared ignoring case).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_HOOKS = sorted((_REPO / ".githooks").iterdir())

# Bash >= 4 only: case-modifying expansions, associative arrays, mapfile,
# @-operators, and the |& / &>> redirections.
_BASH4 = re.compile(
    r",,\}|\^\^\}|,\}|\^\}|\bmapfile\b|\breadarray\b|declare\s+-A|local\s+-A"
    r"|\$\{[A-Za-z_][A-Za-z0-9_]*@[QEPAaKk]\}|\|&|&>>"
)


@pytest.mark.parametrize("hook", _HOOKS, ids=lambda p: p.name)
def test_hooks_use_no_bash4_only_syntax(hook: Path) -> None:
    hits = [
        f"{hook.name}:{n}: {line.strip()}"
        for n, line in enumerate(hook.read_text(encoding="utf-8").splitlines(), 1)
        if not line.lstrip().startswith("#") and _BASH4.search(line)
    ]
    assert hits == []


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None or shutil.which("git") is None,
    reason="needs a POSIX bash and git",
)
@pytest.mark.parametrize(
    ("signoff", "accepted"),
    [
        ("Signed-off-by: Fixture Author <Fixture@Example.Invalid>", True),
        ("Signed-off-by: Fixture Author <other@example.invalid>", False),
        ("", False),
    ],
)
def test_the_hook_matches_the_address_ignoring_case(
    tmp_path: Path, signoff: str, accepted: bool
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    msg = tmp_path / "MSG"
    msg.write_text(f"subject\n\n{signoff}\n", encoding="utf-8")
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "GIT_AUTHOR_NAME": "Fixture Author",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    }

    result = subprocess.run(
        ["bash", str(_REPO / ".githooks" / "commit-msg"), str(msg)],
        cwd=root, env=env, capture_output=True, text=True, timeout=30, check=False,
    )

    assert (result.returncode == 0) is accepted, result.stderr
