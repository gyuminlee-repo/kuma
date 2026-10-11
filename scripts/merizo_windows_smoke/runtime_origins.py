"""Stdlib-only loaded-origin checks shared by both frozen Merizo probes.

This module imports no entry point, build harness, upstream model or scientific
package. Callers own executable/layout checks and take the inventory once; a
Darwin validation must receive that same indexed, stable dyld snapshot.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import re
import sys
from types import ModuleType
from typing import Iterable, NamedTuple

MAX_MAP_BYTES = 1024 * 1024
MAX_NATIVE_IMAGES = 2048
MAX_PATH_BYTES = 4096
MAX_NATIVE_DIAGNOSTIC_BYTES = 256 * 1024
NATIVE_DIAGNOSTIC_SNAPSHOT = "rejected_validation_snapshot"
REQUIRED_MODULES = {"torch", "predict", "model.network", "model.utils.features"}
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

LINUX_INVENTORY_MECHANISM = "proc_self_maps_executable_files"
DARWIN_INVENTORY_MECHANISM = "dyld_stable_indexed_cache_snapshots"
WINDOWS_INVENTORY_MECHANISM = "enum_process_modules_ex"



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


class MissingNativeRolesError(ValueError):
    """All original native path checks passed; required roles remain absent.

    Ordinary callers still fail. Only the archive adapter may separately prove
    its exact declared normalized Python copy; this class grants no exception.
    """
    def __init__(self, missing: set[str], validated: dict):
        super().__init__(f"Required bundled native modules missing: {sorted(missing)}")
        self.missing = frozenset(missing)
        self.validated = validated


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


def module_origins(modules: Iterable[tuple[str, ModuleType]], internal: Path, *,
                   check_namespace_paths: bool = True) -> dict[str, str]:
    """Require bundled inference modules; only the legacy Windows probe opts
    out of checking namespace-only containers' search locations.
    """
    origins = {}
    for name, module in modules:
        origin = getattr(module, "__file__", None)
        if origin is None:
            if name in REQUIRED_MODULES:
                raise ValueError(f"Required module has no bundled origin: {name}")
            # Namespace packages must still have every search location inside.
            for location in getattr(module, "__path__", ()) if check_namespace_paths else ():
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


def validate_posix_native_paths(paths: list[str], root: Path, system: str, *,
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
    validated = {"bundled": sorted(set(bundled)), "posix_system": sorted(set(system_paths)),
                 "required_bundled": required}
    if missing:
        raise MissingNativeRolesError(missing, validated)
    return validated


def windows_loaded_native_paths() -> list[str]:
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


def validate_windows_native_paths(paths: list[str], root: Path, windows: Path) -> dict[str, list[str]]:
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
