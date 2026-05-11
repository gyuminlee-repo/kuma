# VENDORED from cross-layer-sync skill - DO NOT EDIT.
# Refresh: <dotfiles>/skills/cross-layer-sync/init.mjs --force
"""Dump combined JSON schema for every Pydantic BaseModel in a given module.

Usage:
    PYTHONPATH=<path> python3 gen_models_schema.py <module>

Example:
    PYTHONPATH=python-core python3 gen_models_schema.py sidecar_kuro.models

Output: JSON schema on stdout with every BaseModel-subclass under
`definitions`, plus a root object that `$ref`s each definition so
`json-schema-to-typescript` emits clean named interfaces.
"""

import importlib
import json
import sys

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema


def collect(module) -> list[type[BaseModel]]:
    out: list[type[BaseModel]] = []
    for name in dir(module):
        obj = getattr(module, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
            and obj.__module__ == module.__name__
        ):
            out.append(obj)
    return out


def _strip_property_titles(node, depth: int = 0) -> None:
    """Pydantic emits per-field `title` on every property; json-schema-to-typescript
    promotes those to type aliases (e.g. `type AaPosition = number`). Strip them
    while keeping the definition-level title.
    """
    if isinstance(node, dict):
        if depth >= 1:
            node.pop("title", None)
        for v in node.values():
            _strip_property_titles(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _strip_property_titles(v, depth + 1)


def main() -> None:
    if len(sys.argv) < 2:
        sys.stderr.write("usage: gen_models_schema.py <module>\n")
        sys.exit(2)
    module_name = sys.argv[1]
    module = importlib.import_module(module_name)

    models = collect(module)
    _, schema = models_json_schema(
        [(m, "serialization") for m in models],
        ref_template="#/definitions/{model}",
    )
    definitions = schema.get("$defs", {})
    for defn in definitions.values():
        _strip_property_titles(defn, depth=0)

    properties = {name: {"$ref": f"#/definitions/{name}"} for name in definitions}
    wrapper = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": module_name.replace(".", "_"),
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "definitions": definitions,
    }
    json.dump(wrapper, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
