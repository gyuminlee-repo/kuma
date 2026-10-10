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
import re
import sys
import time
from types import ModuleType
from typing import Iterable, NamedTuple

MAX_REPORT_BYTES = 1024 * 1024
MAX_MAP_BYTES = 1024 * 1024
MAX_NATIVE_IMAGES = 2048
MAX_PATH_BYTES = 4096
MAX_NATIVE_DIAGNOSTIC_BYTES = 256 * 1024
NATIVE_DIAGNOSTIC_SNAPSHOT = "rejected_validation_snapshot"
REQUIRED_MODULES = {"torch", "predict", "model.network", "model.utils.features"}
SUPPORTED = {("Linux", "x86_64"), ("Darwin", "arm64")}
# OS ABI dependencies only. Neither these roots nor a familiar library name
# alone is sufficient. Python, Torch and numerical runtimes are checked first.
LINUX_SYSTEM_NAMES = re.compile(
    r"(?:ld-linux-x86-64\.so\.2|ld-[0-9.]+\.so|"
    r"lib(?:c|m|dl|pthread|rt|util|resolv|gcc_s|stdc\+\+)\.so(?:\.[0-9]+)+)"
)
# Public mach-o/dyld.h and mach-o/loader.h ABI. This is trusted-OS evidence,
# not independent Apple code-signature verification or a hostile-code sandbox.
DARWIN_ORIGIN_CONTRACT = "darwin_dyld_shared_cache_v2"
DARWIN_OS_ROOTS = (Path("/usr/lib"), Path("/System/Library"))
MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_MASK = 0xFF000000
MH_EXECUTE, MH_DYLIB, MH_BUNDLE = 2, 6, 8
MH_DYLIB_IN_CACHE = 0x80000000


class MachHeader64(ctypes.Structure):
    _fields_ = [("magic", ctypes.c_uint32), ("cputype", ctypes.c_int32),
                ("cpusubtype", ctypes.c_int32), ("filetype", ctypes.c_uint32),
                ("ncmds", ctypes.c_uint32), ("sizeofcmds", ctypes.c_uint32),
                ("flags", ctypes.c_uint32), ("reserved", ctypes.c_uint32)]


class DarwinImage(NamedTuple):
    image_index: int
    path: str
    header_address: int
    magic: int
    cputype: int
    cpusubtype: int
    filetype: int
    flags: int
    shared_cache_member: bool


class NativeOriginError(ValueError):
    """Keep the exact rejected inventory, never trigger another enumeration."""

    def __init__(self, message: str, paths: tuple[str, ...]):
        super().__init__(message)
        self.paths = paths


def native_diagnostic(paths: tuple[str, ...]) -> dict:
    """A bounded subset of the rejected snapshot, not approved provenance."""
    selected = []
    # Reserve JSON field/indent overhead; charge escaped JSON bytes per path.
    remaining = MAX_NATIVE_DIAGNOSTIC_BYTES - 1024
    for path in paths[:MAX_NATIVE_IMAGES]:
        if (not isinstance(path, str) or not path.startswith("/")
                or any(character in path for character in "\x00\r\n")
                or len(path.encode("utf-8")) > MAX_PATH_BYTES):
            continue
        cost = len(json.dumps(path).encode("utf-8")) + 8
        if cost > remaining:
            break
        selected.append(path)
        remaining -= cost
    diagnostic = {"native_diagnostic_paths": selected, "native_diagnostic_total": len(paths),
                  "native_diagnostic_truncated": len(selected) != len(paths),
                  "native_diagnostic_snapshot": NATIVE_DIAGNOSTIC_SNAPSHOT}
    if len(json.dumps(diagnostic, indent=2, allow_nan=False).encode("utf-8")) > MAX_NATIVE_DIAGNOSTIC_BYTES:
        raise ValueError("Native diagnostic exceeds byte limit")
    return diagnostic


def within(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


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
    origins = {}
    for name, module in modules:
        origin = getattr(module, "__file__", None)
        if origin is None:
            if name in REQUIRED_MODULES:
                raise ValueError(f"Required module has no bundled origin: {name}")
            # Namespace packages must still have every search location inside.
            for location in getattr(module, "__path__", ()):
                if not within(Path(location), internal):
                    raise ValueError(f"Namespace search path escapes the bundle: {name}")
            continue
        path = Path(origin).resolve()
        if not within(path, internal):
            raise ValueError(f"Module resolved outside the frozen bundle: {name}: {path}")
        origins[name] = str(path)
    if not REQUIRED_MODULES <= origins.keys():
        raise ValueError("Required inference modules were not loaded from the bundle")
    return origins


def parse_linux_maps(raw: str) -> list[str]:
    """Read executable file mappings, preserving spaces and rejecting ambiguity.

    Anonymous mappings are not file provenance. Kernel pseudo-mappings such as
    [vdso] are recorded by neither this file inventory nor its OS library claim.
    Proc's newline escape and deleted suffix are ambiguous: fail closed.
    """
    if len(raw.encode("utf-8")) > MAX_MAP_BYTES:
        raise ValueError("Native maps exceeds byte limit")
    lines = raw.splitlines()
    if len(lines) > MAX_NATIVE_IMAGES * 16:
        raise ValueError("Native maps exceeds line limit")
    paths = set()
    for line in lines:
        fields = line.split(maxsplit=5)
        if len(fields) < 5 or not re.fullmatch(r"[0-9a-fA-F]+-[0-9a-fA-F]+", fields[0]) \
                or not re.fullmatch(r"[r-][w-][x-][ps]", fields[1]) \
                or not re.fullmatch(r"[0-9a-fA-F]+", fields[2]) \
                or not re.fullmatch(r"[0-9a-fA-F]+:[0-9a-fA-F]+", fields[3]) \
                or not fields[4].isdigit():
            raise ValueError("Malformed native maps record")
        if "x" not in fields[1]:
            continue
        if len(fields) == 5:
            if fields[4] != "0":
                raise ValueError("Executable file mapping has no pathname")
            continue
        name = fields[5]
        if name.startswith("[") and name.endswith("]") and fields[4] == "0":
            continue
        if " (deleted)" in name or "\\012" in name or "\x00" in name:
            raise ValueError("Deleted or ambiguous executable mapping")
        # /proc maps only documents newline escaping. A literal \\040 could be
        # a filename, not a space: never silently attribute it to another file.
        if "\\" in name or not name.startswith("/") or len(name.encode("utf-8")) > MAX_PATH_BYTES:
            raise ValueError("Unresolved executable mapping path")
        paths.add(name)
        if len(paths) > MAX_NATIVE_IMAGES:
            raise ValueError("Native image inventory exceeds limit")
    if not paths:
        raise ValueError("No executable native file mappings found")
    return sorted(paths)


def linux_native_paths() -> list[str]:
    with Path("/proc/self/maps").open("rb") as stream:
        raw = stream.read(MAX_MAP_BYTES + 1)
    if len(raw) > MAX_MAP_BYTES:
        raise ValueError("Native maps exceeds byte limit")
    return parse_linux_maps(raw.decode("utf-8", errors="strict"))


def darwin_native_images() -> tuple[DarwinImage, ...]:
    """Two matching indexed snapshots of the trusted process's public dyld API.

    Only pointers returned directly by dyld are read, never JSON addresses.
    Fixed-size headers and bounded NUL-terminated paths are copied immediately.
    Enumeration is not thread-safe; instability fails closed, not a locking claim.
    """
    if ctypes.sizeof(ctypes.c_void_p) != 8 or sys.byteorder != "little":
        raise ValueError("Unsupported native Mach-O arm64 ABI")
    try:
        dyld = ctypes.CDLL(None)
        dyld._dyld_image_count.argtypes = []
        dyld._dyld_image_count.restype = ctypes.c_uint32
        dyld._dyld_get_image_name.argtypes = [ctypes.c_uint32]
        # c_char_p would copy an unbounded string before Python can check it.
        dyld._dyld_get_image_name.restype = ctypes.POINTER(ctypes.c_char)
        dyld._dyld_get_image_header.argtypes = [ctypes.c_uint32]
        dyld._dyld_get_image_header.restype = ctypes.c_void_p
        dyld._dyld_shared_cache_contains_path.argtypes = [ctypes.c_char_p]
        dyld._dyld_shared_cache_contains_path.restype = ctypes.c_bool
    except (AttributeError, OSError) as exc:
        raise ValueError("Required public dyld cache/header API unavailable") from exc
    previous = None
    for _ in range(4):
        count = dyld._dyld_image_count()
        if not 0 < count <= MAX_NATIVE_IMAGES:
            raise ValueError("dyld image inventory exceeds bounds")
        images = []
        for index in range(count):
            pointer = dyld._dyld_get_image_name(index)
            if not pointer:
                raise ValueError("Unresolved dyld image path")
            raw = bytearray()
            for offset in range(MAX_PATH_BYTES + 1):
                character = pointer[offset]
                if character == b"\x00":
                    break
                if offset == MAX_PATH_BYTES:
                    raise ValueError("dyld image path exceeds byte limit")
                raw.extend(character)
            name = raw.decode("utf-8", errors="strict")
            if not name.startswith("/") or any(character in name for character in "\x00\r\n"):
                raise ValueError("dyld did not report an absolute image path")
            address = dyld._dyld_get_image_header(index)
            if not address or address % ctypes.alignment(MachHeader64):
                raise ValueError("Unresolved or misaligned dyld image header")
            # The sole address dereference is adjacent to its dyld getter.
            header = MachHeader64.from_buffer_copy(ctypes.string_at(address, ctypes.sizeof(MachHeader64)))
            if (header.magic != MH_MAGIC_64 or header.cputype != CPU_TYPE_ARM64
                    or (header.cpusubtype & (0xFFFFFFFF ^ CPU_SUBTYPE_MASK)) not in {0, 1, 2}
                    or header.filetype not in {MH_EXECUTE, MH_DYLIB, MH_BUNDLE}):
                raise ValueError("Invalid native Mach-O arm64 image header")
            member = dyld._dyld_shared_cache_contains_path(bytes(raw))
            images.append(DarwinImage(index, name, address, header.magic, header.cputype,
                                      header.cpusubtype, header.filetype, header.flags, member))
        # Do not sort/deduplicate: changing index/path/header associations must
        # invalidate a snapshot even when its set of filenames stays the same.
        current = tuple(images)
        if dyld._dyld_image_count() == count:
            if current == previous:
                return current
            previous = current
        else:
            previous = None
    raise ValueError("dyld image inventory did not stabilize")


def runtime_role(path: Path, system: str) -> str | None:
    name = path.name
    if system == "Linux" and re.fullmatch(r"libpython3\.11\.so(?:\.[0-9]+)*", name):
        return "python"
    if system == "Darwin" and (name == "libpython3.11.dylib" or
            (name == "Python" and "Python.framework" in path.parts and "3.11" in path.parts)):
        return "python"
    suffix = ".so" if system == "Linux" else ".dylib"
    if name == "libtorch_cpu" + suffix:
        return "torch_cpu"
    if name == "libc10" + suffix:
        return "c10"
    return None


def is_inference_runtime(path: Path) -> bool:
    name = path.name.casefold()
    return (name.startswith(("libpython", "python", "libtorch", "libc10", "libomp", "libgomp",
                             "libiomp", "libopenblas", "libmkl"))
            or any(part.casefold() in {"python.framework", "torch", "site-packages"} for part in path.parts))


def system_library(path: Path, system: str) -> bool:
    # Darwin has no path-only exception. Its OS-root check also needs the
    # exact stable dyld record's membership, header type and cache flag below.
    if system != "Linux":
        return False
    roots = (Path("/lib"), Path("/lib64"), Path("/usr/lib"), Path("/usr/lib64"))
    return bool(LINUX_SYSTEM_NAMES.fullmatch(path.name)) and any(within(path, root) for root in roots)


def darwin_cached_os_image(raw: Path, resolved: Path, image: DarwinImage) -> bool:
    return (all(any(path != root and path.is_relative_to(root) for root in DARWIN_OS_ROOTS)
                for path in (raw, resolved))
            and ".." not in raw.parts
            and image.shared_cache_member is True and image.filetype == MH_DYLIB
            and bool(image.flags & MH_DYLIB_IN_CACHE))


def validate_native_paths(paths: list[str], root: Path, system: str, *,
                          darwin_images: tuple[DarwinImage, ...] | None = None) -> dict:
    bundled, system_paths = [], []
    required = {}
    if not paths or len(paths) > MAX_NATIVE_IMAGES:
        raise ValueError("Native image inventory outside bounds")
    if system == "Darwin" and (darwin_images is None or len(darwin_images) != len(paths)
            or any(not isinstance(image, DarwinImage) or image.image_index != index or image.path != paths[index]
                   for index, image in enumerate(darwin_images))):
        raise ValueError("Native paths require the same indexed dyld evidence snapshot")
    for index, raw in enumerate(paths):
        if (not Path(raw).is_absolute() or any(character in raw for character in "\x00\r\n")
                or len(raw.encode("utf-8")) > MAX_PATH_BYTES):
            raise ValueError("Invalid native image path")
        path = Path(raw).resolve()
        if Path(raw).is_relative_to(root.resolve()) and not within(path, root):
            raise ValueError(f"Bundled native symlink escaped the bundle: {raw}")
        role = runtime_role(path, system)
        if within(path, root):
            # Normal PyInstaller POSIX symlinks are allowed only when their
            # final target remains an actual file inside the bundle.
            if not path.is_file():
                raise ValueError(f"Bundled native image is missing: {path}")
            bundled.append(str(path))
            if role:
                required[role] = str(path)
        elif is_inference_runtime(Path(raw)) or is_inference_runtime(path):
            raise ValueError(f"Python/Torch/numerical runtime escaped the bundle: {path}")
        elif (system_library(path, system) or (system == "Darwin" and darwin_images is not None
                and darwin_cached_os_image(Path(raw), path, darwin_images[index]))):
            # dyld shared-cache OS images need not exist as files on modern
            # macOS. This exception never applies to Python/Torch/bundle paths.
            if system == "Linux" and not path.is_file():
                raise ValueError(f"Loaded Linux system image is missing: {path}")
            system_paths.append(str(path))
        else:
            raise ValueError(f"Loaded native image is outside bundle/OS allowlist: {path}")
    missing = {"python", "torch_cpu", "c10"} - required.keys()
    if missing:
        raise ValueError(f"Required bundled native modules missing: {sorted(missing)}")
    return {"bundled": sorted(set(bundled)), "posix_system": sorted(set(system_paths)),
            "required_bundled": required}


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
