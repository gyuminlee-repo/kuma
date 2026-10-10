"""CI-only POSIX frozen probe; no external Python bootstrap or model changes.

The launcher owns the process group and deadline. This entry only accepts the
pinned fixture through run.inference and audits actual native loading twice.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
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
MAX_MAP_BYTES = origins.MAX_MAP_BYTES
MAX_NATIVE_IMAGES = origins.MAX_NATIVE_IMAGES
MAX_PATH_BYTES = origins.MAX_PATH_BYTES
MAX_NATIVE_DIAGNOSTIC_BYTES = origins.MAX_NATIVE_DIAGNOSTIC_BYTES
NATIVE_DIAGNOSTIC_SNAPSHOT = origins.NATIVE_DIAGNOSTIC_SNAPSHOT
REQUIRED_MODULES = origins.REQUIRED_MODULES
LINUX_SYSTEM_NAMES = origins.LINUX_SYSTEM_NAMES
DARWIN_ORIGIN_CONTRACT = origins.DARWIN_ORIGIN_CONTRACT
DARWIN_OS_ROOTS = origins.DARWIN_OS_ROOTS
MH_MAGIC_64 = origins.MH_MAGIC_64
CPU_TYPE_ARM64 = origins.CPU_TYPE_ARM64
CPU_SUBTYPE_MASK = origins.CPU_SUBTYPE_MASK
MH_EXECUTE = origins.MH_EXECUTE
MH_DYLIB = origins.MH_DYLIB
MH_BUNDLE = origins.MH_BUNDLE
MH_DYLIB_IN_CACHE = origins.MH_DYLIB_IN_CACHE
MachHeader64 = origins.MachHeader64
DarwinImage = origins.DarwinImage
NativeOriginError = origins.NativeOriginError
native_diagnostic = origins.native_diagnostic
within = origins.within
SUPPORTED = {("Linux", "x86_64"), ("Darwin", "arm64")}


def bundle_root() -> tuple[Path, Path]:
    if (platform.system(), platform.machine()) not in SUPPORTED or not getattr(sys, "frozen", False):
        raise ValueError("This entry requires frozen Linux x86_64 or Darwin arm64")
    if sys.version_info[:2] != (3, 11):
        raise ValueError("The frozen experiment requires bundled Python 3.11")
    executable = Path(sys.executable).resolve()
    root = executable.parent
    raw_internal = getattr(sys, "_MEIPASS", None)
    if not raw_internal or executable.name != "merizo-frozen-smoke" or not executable.is_file():
        raise ValueError("Unexpected frozen executable or missing _MEIPASS")
    internal = Path(raw_internal).resolve()
    if internal == root or not within(internal, root) or not internal.is_dir():
        raise ValueError("PyInstaller internal directory is outside its onedir bundle")
    return root, internal


def module_origins(modules: Iterable[tuple[str, ModuleType]], internal: Path) -> dict[str, str]:
    return origins.module_origins(modules, internal)


parse_linux_maps = origins.parse_linux_maps
linux_native_paths = origins.linux_native_paths
darwin_native_images = origins.darwin_native_images
runtime_role = origins.runtime_role
is_inference_runtime = origins.is_inference_runtime
system_library = origins.system_library
darwin_cached_os_image = origins.darwin_cached_os_image


def validate_native_paths(paths: list[str], root: Path, system: str, *,
                          darwin_images: tuple[DarwinImage, ...] | None = None) -> dict:
    return origins.validate_posix_native_paths(paths, root, system, darwin_images=darwin_images)


def runtime_provenance() -> dict:
    root, internal = bundle_root()
    modules = [(name, module) for name, module in list(sys.modules.items())
               if module is not None and (name in {"predict", "torch", "model"}
                                          or name.startswith(("torch.", "model.")))]
    origins = module_origins(modules, internal)
    system = platform.system()
    images = darwin_native_images() if system == "Darwin" else None
    paths = [image.path for image in images] if images is not None else linux_native_paths()
    snapshot = tuple(paths)
    try:
        native = (validate_native_paths(paths, root, system, darwin_images=images) if images is not None
                  else validate_native_paths(paths, root, system))
    except ValueError as exc:
        raise NativeOriginError(str(exc), snapshot) from exc
    result = {"frozen": True, "executable": str(Path(sys.executable).resolve()),
            "bundle_root": str(root), "meipass": str(internal), "module_origins": origins,
            "native_module_paths": native, "loaded_native_paths": paths,
            "inventory_mechanism": "proc_self_maps_executable_files" if system == "Linux" else "dyld_stable_indexed_cache_snapshots"}
    if images is not None:
        result.update(native_origin_contract=DARWIN_ORIGIN_CONTRACT,
                      native_origin_claim="trusted_os_dyld_reported_cache_residency",
                      loaded_native_images=[image._asdict() for image in images])
    return result


def wait_for_job_gate() -> None:
    if os.getsid(0) != os.getpid() or os.getpgrp() != os.getpid():
        raise ValueError("The bounded launcher must establish a new POSIX session/group")
    raw = os.environ.get("KUMA_MERIZO_START_GATE")
    if not raw:
        raise ValueError("The bounded POSIX launcher start gate is required")
    gate = Path(raw)
    if not gate.is_absolute() or gate.is_symlink() or gate.resolve().parent != Path.cwd().resolve():
        raise ValueError("Start gate must be in the isolated execution directory")
    deadline = time.monotonic() + 30
    while not gate.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for POSIX process-group start gate")
        time.sleep(0.02)
    if gate.is_symlink() or gate.resolve().parent != Path.cwd().resolve():
        raise ValueError("Start gate changed location")


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
        # Own stdlib-only adapter, followed by heavy imports inside inference.
        from run import COMMIT, inference, verify_weights
        weights = verify_weights(internal / "merizo_weights")
        report = inference(args.fixture.resolve(), internal / "merizo_weights", runtime_provenance)
        report.update(scope="frozen_posix_cpu_public_fixture_smoke_only", source_commit=COMMIT,
                      weights_sha256=weights, package_directory=str(root), bundle_root=str(root), frozen=True)
        report["not_verified"] = ["KUMA integration", "native GUI", "system Python physically removed",
                                  "redistribution rights", "biological accuracy", "product dependency security baseline",
                                  "anonymous executable memory provenance", "thread-safe dyld enumeration"]
        if platform.system() == "Darwin":
            report["not_verified"].append("independent Apple code-signature verification")
        write_report(args.output.resolve(), report)
        return 0
    except Exception as exc:
        failure = {"status": "failed", "scope": "frozen_posix_cpu_public_fixture_smoke_only",
                   "error": f"{type(exc).__name__}: {exc}"[:12000]}
        if isinstance(exc, NativeOriginError):
            try:
                failure.update(native_diagnostic(exc.paths))
            except Exception:
                # Diagnostics must never replace or hide the original failure.
                pass
        write_report(args.output.resolve(), failure)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
