"""``scripts/verify_demux_and_filter.py --out-root`` must not wipe what it is given.

The option used to ``shutil.rmtree`` an existing directory before building the
fixture, so ``--out-root .`` or a data folder lost its contents. Everything this
test deletes lives under ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "verify_demux_and_filter.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_demux_and_filter", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.__file__ is not None
    assert Path(module.__file__).resolve() == _SCRIPT
    return module


def _run(module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, out_root: Path) -> int:
    fake_mm2 = tmp_path / "minimap2"
    fake_mm2.write_text("", encoding="utf-8")
    # main() writes KURO_MINIMAP2 into os.environ; registering it here makes
    # monkeypatch restore it, so the fake binary never reaches later tests.
    monkeypatch.setenv("KURO_MINIMAP2", str(fake_mm2))
    monkeypatch.setattr(
        sys, "argv",
        ["verify_demux_and_filter.py", "--minimap2", str(fake_mm2),
         "--out-root", str(out_root)],
    )
    try:
        return module.main()
    except Exception:  # noqa: BLE001 - the fake minimap2 cannot run a demux
        return -1


def test_a_nonempty_out_root_is_refused_and_left_intact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load()
    out_root = tmp_path / "project"
    out_root.mkdir()
    keep = out_root / "data.txt"
    keep.write_text("operator data", encoding="utf-8")

    status = _run(module, monkeypatch, tmp_path, out_root)

    assert keep.read_text(encoding="utf-8") == "operator data"
    assert status == 2
    assert sorted(p.name for p in out_root.iterdir()) == ["data.txt"]
