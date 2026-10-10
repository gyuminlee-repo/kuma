"""CI-only legal evidence, never distribution approval or a binary artifact."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import sys

MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_LEGAL_BYTES = 4 * 1024 * 1024


def requirements(path: Path) -> list[str]:
    values = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.lstrip().startswith("#")]
    if not values or any("==" not in value or value.startswith("-") for value in values):
        raise ValueError("Expected explicit pinned requirement lines")
    return values


def original_text(path: Path, label: str) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(MAX_LEGAL_BYTES + 1)
    if len(raw) > MAX_LEGAL_BYTES or not raw.strip():
        raise ValueError("Legal source is empty or exceeds limit")
    return {"path": label, "sha256": hashlib.sha256(raw).hexdigest(),
            "text": raw.decode("utf-8-sig")}


def collect(source: Path) -> dict:
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("kuma_legal_collector", here.parent / "collect-python-licenses.py")
    if spec is None or spec.loader is None:
        raise ValueError("Missing existing legal collector")
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    # Validate official source/model identity before attributing any legal text.
    from run import COMMIT, verify_upstream
    pins = verify_upstream(source.resolve())
    torch = "torch==2.0.1" if platform.system() == "Darwin" else "torch==2.0.1+cpu"
    roots = {"runtime": [torch, *requirements(here / "requirements.txt")],
             "packaging": requirements(here / "freezer-requirements.txt")}
    records, missing = [], []
    for dist, roles in collector.dependency_closure(roots):
        try:
            files = collector.legal_files(dist)
        except (OSError, ValueError, UnicodeError) as exc:
            files = []
            missing.append({"name": dist.metadata["Name"], "version": dist.version,
                            "error": str(exc)[:2048]})
        records.append({"name": dist.metadata["Name"], "version": dist.version,
                        "roles": roles,
                        "declared_license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                        "legal_files": files})
    python_legal = None
    candidates = (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE",
                  Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "LICENSE.txt")
    for candidate in candidates:
        if candidate.is_file():
            python_legal = original_text(candidate, "installed-python/" + candidate.name)
            break
    if python_legal is None:
        missing.append({"name": "CPython", "version": platform.python_version(),
                        "error": "Installed interpreter legal text not located; separate evidence required"})
    return {"schema": "kuma-merizo-legal-inventory-v1", "distribution_cleared": False,
            "scope": "installed_dependency_legal_texts_not_binary_content_or_legal_clearance",
            "system": platform.system(), "machine": platform.machine(),
            "python_version": platform.python_version(), "roots": roots,
            "source_commit": COMMIT, "weights_sha256": pins, "pins_verified_before_collection": True,
            "collection_status": "incomplete" if missing else "package_texts_collected",
            "truncated": False,
            "upstream_root_license": original_text(source / "LICENSE", "Merizo/LICENSE"),
            "python_legal": python_legal, "distributions": records, "missing_evidence": missing,
            "separate_gates": ["weights license applicability", "native library legal inventory",
                               "source correspondence and redistribution obligations", "product runtime security baseline"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = collect(args.source)
    raw = json.dumps(report, indent=2, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("Legal evidence exceeds bounded text artifact limit")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(raw + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
