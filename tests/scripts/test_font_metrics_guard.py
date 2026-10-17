"""Generic font-table guards; no installed/user font or external process is read."""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def table_function(font):
    path = Path(__file__).resolve().parents[2] / "scripts/gen-font-metrics.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes: list[ast.stmt] = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "table"]
    scope: dict[str, Any] = {"TTFont": lambda *args, **kwargs: font, "CHARS": "AB"}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), scope)
    return scope["table"]


class Font:
    def __init__(self, units=1000, cmap=None):
        self.units = units
        self.cmap = cmap
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def __getitem__(self, name):
        if name == "head":
            return SimpleNamespace(unitsPerEm=self.units)
        if name == "hmtx":
            return {"A": (500, 0)}
        return SimpleNamespace(getDebugName=lambda _: "test font")

    def getBestCmap(self):
        return self.cmap


def test_missing_character_map_is_explicit_and_font_is_closed():
    font = Font()
    with pytest.raises(ValueError, match="character map"):
        table_function(font)("inert.ttf")
    assert font.closed


def test_invalid_units_are_refused_before_division():
    font = Font(units=0, cmap={65: "A"})
    with pytest.raises(ValueError, match="units per em"):
        table_function(font)("inert.ttf")
    assert font.closed


def test_valid_font_widths_remain_identical_and_font_is_closed():
    font = Font(cmap={65: "A"})
    assert table_function(font)("inert.ttf") == ({"A": 500}, "test font")
    assert font.closed
