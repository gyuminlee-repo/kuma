#!/usr/bin/env python3
"""Compare what a built sidecar ships against the notices NOTICE.md is built from.

Usage:
    python scripts/check-notice-coverage.py [--warn-only] \
        [--notice-json NOTICE-python.json] [--bundled NOTICE-bundled.md] \
        <sidecar binary | TOC listing .txt> ...

collect-python-licenses.py follows the declared dependency closure. PyInstaller
ships what its analysis found, including the interpreter and native libraries
that no pip distribution declares. This script reads the shipped entry names
(PyInstaller's CArchive TOC plus the embedded PYZ, or a saved listing with one
name per line, optionally as ``type<TAB>size<TAB>name``) and reports every
component that is shipped but has no notice:

* a Python package is covered when its distribution appears in NOTICE-python.json
  with legal files (and, for native libraries a wheel vendors, when that
  distribution's legal text names the library);
* anything no pip distribution provides (CPython, OpenSSL, ...) is covered only
  by a heading of that name in NOTICE-bundled.md.

It checks names, not licence compatibility, and only the rules below plus the
top-level packages the running environment can map to a distribution.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from importlib import metadata
import json
from pathlib import Path
import re
import sys

from packaging.utils import canonicalize_name

# (component, regex over the normalised entry name, where the notice must be)
# "dist:<name>[:<marker>]" -> NOTICE-python.json package, optionally whose
# legal text contains <marker>; "bundled:<heading>" -> NOTICE-bundled.md heading.
RULES: list[tuple[str, str, str]] = [
    ("numpy", r"^numpy([./]|$)", "dist:numpy"),
    ("numpy / OpenBLAS", r"(^|/)libscipy_openblas", "dist:numpy:OpenBLAS"),
    ("numpy / libgfortran", r"(^|/)libgfortran", "dist:numpy:libgfortran"),
    ("numpy / libquadmath", r"(^|/)libquadmath", "dist:numpy:libquadmath"),
    ("certifi", r"^certifi([./]|$)", "dist:certifi"),
    ("xlrd", r"^xlrd([./]|$)", "dist:xlrd"),
    ("xlwt", r"^xlwt([./]|$)", "dist:xlwt"),
    ("CPython", r"(^|/)(libpython3[\d.]*\.(so|dylib)[\d.]*|python3\d*\.dll|Python)$", "bundled:CPython"),
    ("OpenSSL", r"(^|/)(libssl|libcrypto)[-.]", "bundled:OpenSSL"),
    ("libffi", r"(^|/)libffi[-.]", "bundled:libffi"),
    ("bzip2", r"(^|/)libbz2\.", "bundled:bzip2"),
    ("xz / liblzma", r"(^|/)liblzma\.", "bundled:liblzma"),
    ("SQLite", r"(^|/)(libsqlite3\.|sqlite3\.dll$)", "bundled:SQLite"),
    ("ncurses / libtinfo", r"(^|/)libtinfo\.", "bundled:ncurses"),
    ("libuuid", r"(^|/)libuuid\.", "bundled:libuuid"),
    ("zlib", r"(^|/)libz\.(so|\d)", "bundled:zlib"),
    ("GCC runtime (libstdc++, libgcc_s)", r"(^|/)(libstdc\+\+|libgcc_s)[-.]", "bundled:GCC runtime"),
    ("Microsoft Visual C++ / UCRT runtime", r"(?i)(^|/)(vcruntime140|msvcp140|ucrtbase|api-ms-win-)", "bundled:Microsoft Visual C++ runtime"),
]
PROJECT_DIST = "kuma"


def read_entries(path: Path) -> list[str]:
    """Entry names from a saved listing (.txt) or from a built sidecar."""
    if path.suffix.lower() == ".txt":
        lines = path.read_text(encoding="utf8").splitlines()
        names = [line.split("\t")[-1].strip() for line in lines if line.strip()]
    else:
        from PyInstaller.archive.readers import pkg_archive_contents

        names = list(pkg_archive_contents(str(path)))
    return [name.replace("\\", "/") for name in names]


def notice_index(notice_json: Path, bundled: Path) -> tuple[dict[str, str], set[str]]:
    """Map canonical dist name -> concatenated legal text; set of bundled headings."""
    report = json.loads(notice_json.read_text(encoding="utf8"))
    dists: dict[str, str] = {
        str(canonicalize_name(pkg["name"])): "\n".join(doc["text"] for doc in pkg["files"])
        for pkg in report["packages"]
        if pkg.get("files")
    }
    headings: set[str] = {
        m.group(1).strip().lower()
        for m in re.finditer(r"^#{2,4}\s+(.+?)\s*$", bundled.read_text(encoding="utf8"), re.M)
    }
    return dists, headings


def covered(source: str, dists: dict[str, str], headings: set[str]) -> bool:
    kind, _, rest = source.partition(":")
    if kind == "bundled":
        return rest.lower() in headings
    name, _, marker = rest.partition(":")
    text = dists.get(canonicalize_name(name))
    return text is not None and (not marker or marker in text)


def check(entries: list[str], dists: dict[str, str], headings: set[str],
          top_level_dists: Mapping[str, list[str]]) -> tuple[list[str], list[str], list[str]]:
    """Return (covered, missing, absent) components for one entry list.

    A rule with no matching entry is "absent", which is not the same as covered:
    a listing without PYZ module names cannot show pure-Python packages.
    """
    ok: list[str] = []
    missing: list[str] = []
    absent: list[str] = []
    seen: set[str] = {PROJECT_DIST}
    for component, pattern, source in RULES:
        rx = re.compile(pattern)
        hits = [e for e in entries if rx.search(e)]
        if not hits:
            absent.append(component)
            continue
        if source.startswith("dist:"):
            seen.add(canonicalize_name(source.split(":")[1]))
        label = f"{component} [{source}] e.g. {hits[0]}"
        (ok if covered(source, dists, headings) else missing).append(label)
    # Generic layer: any shipped top-level package the environment can map to a
    # distribution must have that distribution in the Python notice.
    for entry in entries:
        top = re.split(r"[./]", entry, maxsplit=1)[0]
        for dist in top_level_dists.get(top, []):
            key = canonicalize_name(dist)
            if key in seen:
                continue
            seen.add(key)
            label = f"{dist} [dist:{dist}] e.g. {entry}"
            (ok if key in dists else missing).append(label)
    return ok, missing, absent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="+", type=Path, help="built sidecar binaries or TOC listings (.txt)")
    parser.add_argument("--notice-json", type=Path, default=Path("NOTICE-python.json"))
    parser.add_argument("--bundled", type=Path, default=Path("NOTICE-bundled.md"))
    parser.add_argument("--warn-only", action="store_true", help="report missing notices but exit 0")
    args = parser.parse_args()

    dists, headings = notice_index(args.notice_json, args.bundled)
    top_level_dists = metadata.packages_distributions()
    print(f"[notice-coverage] {len(RULES)} explicit rules, {len(dists)} Python notices, "
          f"{len(headings)} bundled headings, {len(top_level_dists)} importable top-level names")
    any_missing = False
    for path in args.paths:
        entries = read_entries(path)
        ok, missing, absent = check(entries, dists, headings, top_level_dists)
        print(f"\n== {path.name}: {len(entries)} entries, {len(ok)} covered, {len(missing)} missing")
        for label in missing:
            print(f"  MISSING  {label}")
        for label in ok:
            print(f"  ok       {label}")
        print(f"  absent   {', '.join(absent) or '(none)'}")
        any_missing = any_missing or bool(missing)
    if any_missing:
        level = "WARNING" if args.warn_only else "ERROR"
        print(f"\n[notice-coverage] {level}: shipped components without a notice (see MISSING above). "
              "Add Python texts through license-supplements.json and non-pip components as a "
              "heading in NOTICE-bundled.md.", file=sys.stderr)
        return 0 if args.warn_only else 1
    print("\n[notice-coverage] every checked component has a notice")
    return 0


if __name__ == "__main__":
    sys.exit(main())
