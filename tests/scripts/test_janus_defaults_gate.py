"""``scripts/sync-check-janus-defaults.mjs`` must see what ``toRpcParams`` sends.

The gate restates the field -> RPC key table and checks ``toRpcParams`` against
it with a regex. The regex matched only a prefix, so ``volume: settings.volume
* 1000`` put 70000 on the wire and the gate still printed OK. Each case copies
the script into a throwaway repo with a mutated ``janusSettings.ts``; the real
source is only read.
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


def _run(tmp_path: Path, ts_source: str) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
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
    ],
)
def test_a_mapper_that_changes_the_wire_value_fails(tmp_path: Path, mutated: str) -> None:
    source = _source()
    original = "volume: settings.volume,"
    assert source.count(original) == 1
    result = _run(tmp_path, source.replace(original, mutated))

    assert result.returncode != 0, result.stdout
    assert "volume" in result.stdout + result.stderr
