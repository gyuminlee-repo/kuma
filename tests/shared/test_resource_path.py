"""Tests for kuma_core.shared.resource_path.

The frozen branch is the reason this helper exists and the one no ordinary
test run enters, so it is faked here rather than left to a frozen smoke build.
"""

from __future__ import annotations

import sys
from pathlib import Path

from kuma_core.shared.resource_path import resource_path


class TestUnfrozen:
    def test_resolves_next_to_the_calling_module(self, tmp_path):
        module_file = tmp_path / "pkg" / "mod.py"
        result = resource_path(
            "kuma_core.kuro", "resources/x.json", module_file=str(module_file)
        )
        assert result == tmp_path / "pkg" / "resources" / "x.json"

    def test_package_argument_is_ignored_when_not_frozen(self, tmp_path):
        module_file = str(tmp_path / "mod.py")
        a = resource_path("kuma_core.kuro", "r", module_file=module_file)
        b = resource_path("some.other.package", "r", module_file=module_file)
        assert a == b


class TestFrozen:
    def test_rebuilds_the_package_chain_under_meipass(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        result = resource_path(
            "kuma_core.kuro",
            "resources/codon_tables",
            module_file="/nowhere/mod.py",
        )
        assert result == tmp_path / "kuma_core" / "kuro" / "resources" / "codon_tables"

    def test_frozen_without_meipass_falls_back_to_the_module_dir(
        self, monkeypatch, tmp_path
    ):
        # A frozen one-dir build without _MEIPASS must not produce a path
        # rooted at None.
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        module_file = str(tmp_path / "mod.py")
        assert resource_path("kuma_core.kuro", "r", module_file=module_file) == (
            tmp_path / "r"
        )

    def test_frozen_layout_matches_the_shipped_sidecar_declaration(
        self, monkeypatch, tmp_path
    ):
        # scripts/build_sidecar.py declares the resources destination as
        # "kuma_core/kuro/resources", so the frozen path this helper builds has
        # to land on that same directory.
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
        staged = tmp_path / "kuma_core" / "kuro" / "resources" / "codon_tables"
        staged.mkdir(parents=True)
        (staged / "ecoli.json").write_text("{}", encoding="utf-8")
        resolved = resource_path(
            "kuma_core.kuro",
            "resources/codon_tables",
            module_file="/nowhere/mod.py",
        )
        assert sorted(p.name for p in Path(resolved).glob("*.json")) == ["ecoli.json"]
