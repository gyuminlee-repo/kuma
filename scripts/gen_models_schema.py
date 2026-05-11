"""Dump combined JSON schema for all Pydantic models in sidecar_kuro.models.

Usage:
    PYTHONPATH=python-core python3 scripts/gen_models_schema.py > schema.json

The schema is a single wrapper with `definitions` containing every BaseModel
subclass defined in `sidecar_kuro.models`. Consumed by `gen-models.mjs`
which pipes it into `json-schema-to-typescript`.
"""

import json
import sys

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

import sidecar_kuro.models as kuro_models


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
    """Pydantic emits per-field `title` on every property; json2ts promotes those
    to type aliases (e.g. `type AaPosition = number`). Strip them while keeping
    the definition-level title that json2ts needs for the interface name.
    """
    if isinstance(node, dict):
        # depth 0 = definition root (keep title); deeper = inner subschema
        if depth >= 1:
            node.pop("title", None)
        for v in node.values():
            _strip_property_titles(v, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _strip_property_titles(v, depth + 1)


def main() -> None:
    models = collect(kuro_models)
    _, schema = models_json_schema(
        [(m, "serialization") for m in models],
        ref_template="#/definitions/{model}",
    )
    definitions = schema.get("$defs", {})
    for defn in definitions.values():
        _strip_property_titles(defn, depth=0)
    # Reference every definition from the root so json2ts emits them as
    # named interfaces (instead of hoisting per-field aliases).
    properties = {name: {"$ref": f"#/definitions/{name}"} for name in definitions}
    wrapper = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "KuroModels",
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "definitions": definitions,
    }
    json.dump(wrapper, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
