"""Test-only frozen entry: direct inference with bundled-runtime provenance.

Never calls the development CLI's sys.executable bootstrap. PowerShell owns the
whole-process deadline and a kill-on-close Job Object before opening the gate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType
from typing import Iterable

# Direct-script/frozen builds use the sibling import. File-based test loaders
# can import through the checkout's namespace package without changing sys.path.
try:
    import runtime_origins as origins
except ModuleNotFoundError as exc:
    if exc.name != "runtime_origins":
        raise
    from scripts.merizo_windows_smoke import runtime_origins as origins

MAX_REPORT_BYTES = 1024 * 1024


def within(path: Path, root: Path) -> bool:
    return origins.within(path, root)


def bundle_root() -> tuple[Path, Path]:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        raise ValueError("This entry requires a frozen native Windows executable")
    executable = Path(sys.executable).resolve()
    internal = Path(getattr(sys, "_MEIPASS", "")).resolve()
    root = executable.parent
    if executable.name != "merizo-frozen-smoke.exe" or not executable.is_file():
        raise ValueError("Unexpected frozen executable")
    if internal == root or not within(internal, root) or not internal.is_dir():
        raise ValueError("PyInstaller internal directory is outside its onedir bundle")
    return root, internal


def module_origins(modules: Iterable[tuple[str, ModuleType]], internal: Path) -> dict[str, str]:
    # Preserve the fixed Windows probe's namespace-only container semantics.
    return origins.module_origins(modules, internal, check_namespace_paths=False)


def loaded_native_paths() -> list[str]:
    return origins.windows_loaded_native_paths()


def validate_native_paths(paths: list[str], root: Path, windows: Path) -> dict[str, list[str]]:
    return origins.validate_windows_native_paths(paths, root, windows)


def runtime_provenance() -> dict:
    root, internal = bundle_root()
    modules = [(name, module) for name, module in list(sys.modules.items())
               if module is not None and (name == "predict" or name == "torch" or name.startswith("torch.")
                                          or name == "model" or name.startswith("model."))]
    origins = module_origins(modules, internal)
    windows = Path(os.environ["SystemRoot"]).resolve()
    native = validate_native_paths(loaded_native_paths(), root, windows)
    return {"frozen": True, "executable": str(Path(sys.executable).resolve()),
            "bundle_root": str(root), "meipass": str(internal),
            "module_origins": origins, "native_module_paths": native}


def wait_for_job_gate() -> None:
    raw = os.environ.get("KUMA_MERIZO_START_GATE")
    if raw is None:
        raise ValueError("The bounded PowerShell Job Object launcher is required")
    gate = Path(raw).resolve()
    if not within(gate, Path.cwd()) or gate.parent != Path.cwd().resolve():
        raise ValueError("Start gate must be in the isolated execution directory")
    deadline = time.monotonic() + 30
    while not gate.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for the Windows Job Object start gate")
        time.sleep(0.02)


def write_report(path: Path, report: dict) -> None:
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if len(text.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("Frozen diagnostic JSON exceeds size limit")
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root, internal = bundle_root()
        wait_for_job_gate()
        # Import only after the launcher owns the full process tree.
        from run import COMMIT, inference, verify_weights
        weights = verify_weights(internal / "merizo_weights")
        report = inference(args.fixture.resolve(), internal / "merizo_weights", runtime_provenance)
        report["scope"] = "frozen_windows_cpu_public_fixture_smoke_only"
        report["source_commit"] = COMMIT
        report["weights_sha256"] = weights
        report["package_directory"] = str(root)
        report["bundle_root"] = str(root)
        report["frozen"] = True
        report["not_verified"] = ["KUMA integration", "native GUI", "clean machine without system Python installed",
                                  "redistribution rights", "biological accuracy", "product dependency security baseline"]
        write_report(args.output.resolve(), report)
        return 0
    except Exception as exc:
        write_report(args.output.resolve(), {"status": "failed", "scope": "frozen_windows_cpu_public_fixture_smoke_only",
                     "error": f"{type(exc).__name__}: {exc}"[:12000]})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
