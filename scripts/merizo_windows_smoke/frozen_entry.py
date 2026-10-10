"""Test-only frozen entry: direct inference with bundled-runtime provenance.

Never calls the development CLI's sys.executable bootstrap. PowerShell owns the
whole-process deadline and a kill-on-close Job Object before opening the gate.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
import time
from types import ModuleType
from typing import Iterable

MAX_REPORT_BYTES = 1024 * 1024


def within(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


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
    origins = {}
    for name, module in modules:
        origin = getattr(module, "__file__", None)
        # Namespace-only model containers may have no __file__; their children
        # are checked individually, and required concrete modules cannot omit it.
        if origin is None:
            if name in {"torch", "predict", "model.network", "model.utils.features"}:
                raise ValueError(f"Required module has no bundled origin: {name}")
            continue
        path = Path(origin).resolve()
        if not within(path, internal):
            raise ValueError(f"Module resolved outside the frozen bundle: {name}: {path}")
        origins[name] = str(path)
    required = {"torch", "predict", "model.network", "model.utils.features"}
    if not required <= origins.keys():
        raise ValueError("Required inference modules were not loaded from the bundle")
    return origins


def loaded_native_paths() -> list[str]:
    """Enumerate actual loaded Windows native modules, including Python/Torch."""
    if sys.platform != "win32":
        raise ValueError("Native module enumeration requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE),
                                          wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
    psapi.EnumProcessModulesEx.restype = wintypes.BOOL
    psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    psapi.GetModuleFileNameExW.restype = wintypes.DWORD
    process = kernel.GetCurrentProcess()
    capacity = 2048
    modules = (wintypes.HMODULE * capacity)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcessModulesEx(process, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3):
        raise ctypes.WinError(ctypes.get_last_error())
    if needed.value > ctypes.sizeof(modules):
        raise ValueError("Native module inventory exceeds bounded capacity")
    paths = []
    for index in range(needed.value // ctypes.sizeof(wintypes.HMODULE)):
        buffer = ctypes.create_unicode_buffer(32768)
        length = psapi.GetModuleFileNameExW(process, modules[index], buffer, len(buffer))
        if not length or length >= len(buffer) - 1:
            raise ValueError("Cannot resolve a loaded native module path")
        paths.append(str(Path(buffer.value).resolve()))
    return sorted(set(paths), key=str.casefold)


def validate_native_paths(paths: list[str], root: Path, windows: Path) -> dict[str, list[str]]:
    required = {"python311.dll", "torch_cpu.dll", "c10.dll"}
    bundled, system = [], []
    found = set()
    for raw in paths:
        path = Path(raw).resolve()
        name = path.name.casefold()
        is_runtime = bool(re.fullmatch(r"python\d*(?:_d)?\.dll", name)) or name.startswith(("torch", "c10"))
        if within(path, root):
            bundled.append(str(path))
            found.add(name)
        elif within(path, windows) and not is_runtime:
            system.append(str(path))
        else:
            raise ValueError(f"Loaded native module is outside bundle/Windows: {path}")
    if not required <= found:
        raise ValueError(f"Required bundled native modules missing: {sorted(required - found)}")
    return {"bundled": bundled, "windows_system": system}


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
