"""``scripts/sync-check-groups.mjs`` partial-stage check, in a throwaway git repo.

Staging both files of a blocking group while one of them still carries
unstaged edits used to pass: a file present in both the staged and the unstaged
diff was not counted as a sibling with unstaged edits. Only ``tmp_path`` is
written.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "sync-check-groups.mjs"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "config", "commit.gpgsign", "false")
    (root / ".cross-layer-sync.json").write_text(
        json.dumps({"groups": [{"id": "pair", "files": ["a.ts", "b.ts"], "severity": "blocking"}]}),
        encoding="utf-8",
    )
    (root / "a.ts").write_text("a0\n", encoding="utf-8")
    (root / "b.ts").write_text("b0\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    # A second commit so HEAD~1 exists; it touches neither group file.
    (root / "other.txt").write_text("x\n", encoding="utf-8")
    _git(root, "add", "other.txt")
    _git(root, "commit", "-q", "-m", "other")
    return root


def _check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["node", str(_SCRIPT)], cwd=root, capture_output=True, text=True, timeout=30,
        check=False,
    )


def _edit(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text, encoding="utf-8")


def test_a_sibling_staged_and_still_edited_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _edit(root, "a.ts", "a1\n")
    _edit(root, "b.ts", "b1\n")
    _git(root, "add", "a.ts", "b.ts")
    _edit(root, "b.ts", "b2\n")

    result = _check(root)

    assert result.returncode == 1, result.stdout
    assert "pair partial-stage" in result.stdout + result.stderr
    assert "b.ts" in result.stdout + result.stderr


def test_an_unstaged_sibling_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _edit(root, "a.ts", "a1\n")
    _git(root, "add", "a.ts")
    _edit(root, "b.ts", "b1\n")

    assert _check(root).returncode == 1


def test_both_fully_staged_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _edit(root, "a.ts", "a1\n")
    _edit(root, "b.ts", "b1\n")
    _git(root, "add", "a.ts", "b.ts")

    result = _check(root)
    assert result.returncode == 0, result.stdout + result.stderr


def test_one_file_partly_staged_with_no_sibling_edit_passes(tmp_path: Path) -> None:
    """Partial staging inside one file is not a sibling left behind."""
    root = _repo(tmp_path)
    _edit(root, "a.ts", "a1\n")
    _git(root, "add", "a.ts")
    _edit(root, "a.ts", "a2\n")

    result = _check(root)
    assert result.returncode == 0, result.stdout + result.stderr
