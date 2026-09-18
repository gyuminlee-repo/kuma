#!/usr/bin/env python3
"""Collect installed dependency closure and original legal texts, not an allowlist.

Usage: python scripts/collect-python-licenses.py --include-build
Reads pyproject.toml; follows Requires-Dist with environment markers and extras.
The build closure is identified separately, since packaging tools are not all
runtime code. This inventory is not a binary-content audit or legal clearance.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Callable, Any

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

LEGAL = re.compile(r"^(licen[cs]e|copying|notice|copyright)([._-].*)?$", re.I)


def dependency_closure(
    roots: dict[str, list[str]],
    lookup: Callable = metadata.distribution,
    environment: dict[str, str] | None = None,
) -> list[tuple[Any, list[str]]]:
    """Resolve installed versions; revisit packages when another extra is needed."""
    env = default_environment() if environment is None else environment
    queue: deque = deque()
    for role, requirements in roots.items():
        for raw in requirements:
            req = Requirement(raw)
            if req.marker is None or req.marker.evaluate({**env, "extra": ""}):
                queue.append((req, role))
    seen: dict[tuple[str, str], set[str]] = {}
    distributions: dict[str, Any] = {}
    roles: dict[str, set[str]] = {}
    while queue:
        req, role = queue.popleft()
        name = canonicalize_name(req.name)
        dist = distributions.setdefault(name, lookup(name))
        if canonicalize_name(dist.metadata["Name"]) != name:
            raise ValueError(f"Distribution identity mismatch: {name}")
        if req.specifier and not req.specifier.contains(dist.version, prereleases=True):
            raise ValueError(f"Installed {name} {dist.version} does not satisfy {req}")
        roles.setdefault(name, set()).add(role)
        key = (name, role)
        extras = set(req.extras) | {""}
        previous = seen.get(key)
        if previous is not None and extras <= previous:
            continue
        extras |= previous or set()
        seen[key] = extras
        for raw in dist.requires or []:
            child = Requirement(raw)
            if child.marker is None or any(child.marker.evaluate({**env, "extra": e}) for e in extras):
                queue.append((child, role))
    if not distributions:
        raise ValueError("Dependency inventory is empty")
    return [(distributions[n], sorted(roles[n])) for n in sorted(distributions)]


def legal_files(dist: Any) -> list[dict[str, str]]:
    """Read RECORD-listed legal files, including PEP 639 and bundled native notices."""
    found = []
    for entry in sorted(dist.files or [], key=str):
        path = Path(str(entry))
        # Include all files in a legal-text directory, even nonstandard names.
        in_legal = any(p.lower() in {"licenses", "license_files", "legal"} for p in path.parts[:-1])
        if not LEGAL.match(path.name) and not in_legal:
            continue
        raw = Path(dist.locate_file(entry)).read_bytes()
        text = raw.decode("utf-8-sig")
        if not text.strip():
            raise ValueError(f"Empty legal file in {dist.metadata['Name']}: {entry}")
        found.append({"path": path.as_posix(), "sha256": hashlib.sha256(raw).hexdigest(), "text": text})
    # Some legacy distributions put the complete grant in the License field.
    # A short identifier (MIT, BSD, UNKNOWN, etc.) is never a substitute for text.
    declared = dist.metadata.get("License", "")
    if not found and len(declared) > 200 and "\n" in declared:
        raw = declared.encode("utf8")
        found.append({"path": "METADATA:License", "sha256": hashlib.sha256(raw).hexdigest(), "text": declared})
    if not found:
        raise ValueError(f"No license text for {dist.metadata['Name']} {dist.version}; inspect the distribution")
    return found


def collect(roots: dict[str, list[str]], lookup: Callable = metadata.distribution,
            environment: dict[str, str] | None = None) -> list[dict]:
    records = []
    for dist, roles in dependency_closure(roots, lookup, environment):
        declared = dist.metadata.get("License-Expression") or dist.metadata.get("License")
        if not declared:
            declared = "; ".join(x for x in dist.metadata.get_all("Classifier", []) if x.startswith("License ::"))
        records.append({"name": dist.metadata["Name"], "version": dist.version,
                        "roles": roles, "license": declared or "Not declared; review legal texts",
                        "files": legal_files(dist)})
    return records


def render(records: list[dict]) -> str:
    lines = ["# Python dependency licenses", "", "Installed runtime closure, plus explicitly requested packaging dependencies.",
             "Original package legal texts follow. This is not a binary audit or legal clearance.", ""]
    for pkg in records:
        lines += [f"## {pkg['name']} {pkg['version']}", f"Scope: {', '.join(pkg['roles'])}", "Declared license:", pkg["license"], ""]
        for doc in pkg["files"]:
            fence = "`" * max([3] + [len(x) + 1 for x in re.findall(r"`+", doc["text"])])
            lines += [f"### {doc['path']}", f"SHA256: {doc['sha256']}", "", fence, doc["text"], fence, ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("pyproject.toml"))
    parser.add_argument("--output", type=Path, default=Path("NOTICE-python.md"))
    parser.add_argument("--include-build", action="store_true")
    args = parser.parse_args()
    project = tomllib.loads(args.project.read_text(encoding="utf8"))["project"]
    roots = {"runtime": project["dependencies"]}
    if args.include_build:
        roots["packaging"] = project.get("optional-dependencies", {}).get("build", [])
        if not roots["packaging"]:
            raise ValueError("--include-build requested but no build dependencies declared")
    records = collect(roots)
    report = {"schema_version": 1, "legal_clearance": False,
              "environment": default_environment(), "roots": roots, "packages": records}
    notice = render(records)
    args.output.write_text(notice, encoding="utf8")
    args.output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(f"[collect-python-licenses] {len(records)} packages -> {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, metadata.PackageNotFoundError) as exc:
        print(f"[collect-python-licenses] {exc}", file=sys.stderr)
        sys.exit(1)
