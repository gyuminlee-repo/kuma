"""``scripts/sync-check-janus-defaults.mjs`` must see what ``toRpcParams`` sends.

The gate restates the field -> RPC key table and checks ``toRpcParams`` against
it. A regex did this first and matched only a prefix, so ``volume:
settings.volume * 1000`` put 70000 on the wire and the gate still printed OK;
closed at the value's end it still read a comment as a mapping. The gate now
reads the function's syntax tree with the TypeScript compiler. Each case copies
the script into a throwaway repo with a mutated ``janusSettings.ts``; the real
source is only read.

The compiler comes from ``node_modules/typescript`` of this checkout or of the
main checkout behind a worktree, the order ``.githooks/pre-push`` uses. The CI
Python job installs no Node dependencies, so there the cases skip; the gate
itself runs in the frontend job through ``pnpm sync:check``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = "scripts/sync-check-janus-defaults.mjs"
_TS = "src/lib/mame/janusSettings.ts"


def _typescript() -> Path | None:
    """``node_modules/typescript`` as the gate itself would find it."""
    candidates = [_REPO]
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, check=False, cwd=_REPO,
    )
    if common.returncode == 0 and common.stdout.strip():
        candidates.append((_REPO / common.stdout.strip()).resolve().parent)
    for candidate in candidates:
        found = candidate / "node_modules" / "typescript"
        if (found / "package.json").is_file():
            return found
    return None


def _run(tmp_path: Path, ts_source: str) -> subprocess.CompletedProcess[str]:
    typescript = _typescript()
    if typescript is None:
        pytest.skip("node_modules/typescript is not installed in this checkout")
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "node_modules").mkdir()
    try:
        os.symlink(typescript, root / "node_modules" / "typescript", target_is_directory=True)
    except OSError as exc:  # unprivileged Windows cannot symlink
        pytest.skip(f"cannot link typescript into the throwaway repo: {exc}")
    shutil.copyfile(_REPO / _SCRIPT, root / _SCRIPT)
    (root / _TS).parent.mkdir(parents=True)
    (root / _TS).write_text(ts_source, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHON_BIN"] = sys.executable
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_REPO), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    return subprocess.run(
        ["node", str(root / _SCRIPT)],
        capture_output=True, text=True, timeout=60, check=False, env=env, cwd=root,
    )


def _source() -> str:
    return (_REPO / _TS).read_text(encoding="utf-8")


def test_the_unmodified_source_passes(tmp_path: Path) -> None:
    result = _run(tmp_path, _source())
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "mutated",
    [
        "volume: settings.volume * 1000,",
        "volume: settings.volume ?? 0,",
        "volume: settings.volumeOverride,",
        # The regex read the comment as the mapping.
        "volume: settings.volume * 1000, // volume: settings.volume,",
        # A spread after the mapping overrides it on the wire.
        "volume: settings.volume,\n    ...{ volume: 70000 },",
    ],
    ids=["times-1000", "nullish-fallback", "other-field", "comment", "spread"],
)
def test_a_mapper_that_changes_the_wire_value_fails(tmp_path: Path, mutated: str) -> None:
    source = _source()
    original = "volume: settings.volume,"
    assert source.count(original) == 1
    result = _run(tmp_path, source.replace(original, mutated))

    assert result.returncode != 0, result.stdout
    assert "volume" in result.stdout + result.stderr


def test_a_second_assignment_after_the_literal_fails(tmp_path: Path) -> None:
    """Changing the payload after building it is not a mapping the table sees."""
    source = _source()
    original = "  return {\n    dest_layout"
    assert source.count(original) == 1
    mutated = source.replace(original, "  const out = {\n    dest_layout", 1)
    tail = "    dest_rack: settings.destRack,\n  };\n}"
    assert mutated.count(tail) == 1
    mutated = mutated.replace(
        tail,
        "    dest_rack: settings.destRack,\n  };\n  out.volume = 70000;\n  return out;\n}",
    )
    result = _run(tmp_path, mutated)

    assert result.returncode != 0, result.stdout
    assert "toRpcParams" in result.stdout + result.stderr
