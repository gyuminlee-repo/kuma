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
from typing import Iterable

MAX_REPORT_BYTES = 1024 * 1024
MAX_MAP_BYTES = 1024 * 1024
MAX_NATIVE_IMAGES = 2048
MAX_PATH_BYTES = 4096
REQUIRED_MODULES = {"torch", "predict", "model.network", "model.utils.features"}
SUPPORTED = {("Linux", "x86_64"), ("Darwin", "arm64")}
# OS ABI dependencies only. Neither these roots nor a familiar library name
# alone is sufficient. Python, Torch and numerical runtimes are checked first.
LINUX_SYSTEM_NAMES = re.compile(
    r"(?:ld-linux-x86-64\.so\.2|ld-[0-9.]+\.so|"
    r"lib(?:c|m|dl|pthread|rt|util|resolv|gcc_s|stdc\+\+)\.so(?:\.[0-9]+)+)"
)
DARWIN_DYLIB_NAMES = {
    "libSystem.B.dylib", "libobjc.A.dylib", "libc++.1.dylib", "libc++abi.dylib",
    "libz.1.dylib", "libbz2.1.0.dylib", "libiconv.2.dylib", "libresolv.9.dylib",
    "libsqlite3.dylib", "libcompression.dylib", "libxml2.2.dylib", "libicucore.A.dylib",
    "libDiagnosticMessagesClient.dylib", "libenergytrace.dylib", "libcache.dylib",
    "libnetwork.dylib", "libnetworkextension.dylib", "libapple_nghttp2.dylib",
    "libpcap.A.dylib", "libapple_crypto.dylib", "libbsm.0.dylib", "libxar.1.dylib",
    "liblzma.5.dylib", "libutil.dylib", "libpam.2.dylib", "libncurses.5.4.dylib",
}
DARWIN_SYSTEM_DYLIB_NAMES = {
    "libcache.dylib", "libcommonCrypto.dylib", "libcompiler_rt.dylib", "libcopyfile.dylib",
    "libdispatch.dylib", "libdyld.dylib", "libkeymgr.dylib", "liblaunch.dylib", "libmacho.dylib",
    "libquarantine.dylib", "libremovefile.dylib", "libunwind.dylib", "libxpc.dylib",
    *("libsystem_" + name + ".dylib" for name in (
        "asl", "blocks", "c", "collections", "configuration", "containermanager", "coreservices",
        "darwin", "dnssd", "eligibility", "featureflags", "info", "kernel", "m", "malloc",
        "networkextension", "notify", "platform", "pthread", "sandbox", "secinit", "symptoms", "trace")),
}
DARWIN_FRAMEWORKS = {
    "Accelerate", "CoreFoundation", "Foundation", "Security", "SystemConfiguration",
    "CoreServices", "CFNetwork", "IOKit", "ApplicationServices", "DiskArbitration",
    "CoreGraphics", "CoreText", "ColorSync", "ImageIO", "CoreVideo", "Metal",
    "MetalPerformanceShaders", "MetalPerformanceShadersGraph",
}
DARWIN_PRIVATE_FRAMEWORKS = {
    "AppleSystemInfo", "CoreServicesInternal", "BaseBoard", "CoreAnalytics",
    "CoreAutoLayout", "CoreSVG", "LoggingSupport", "TCC", "SkyLight",
}
DARWIN_NESTED_FRAMEWORKS = {
    "Accelerate": {"vecLib", "vImage"},
    "CoreServices": {"AE", "CarbonCore", "DictionaryServices", "FSEvents", "LaunchServices",
                     "Metadata", "OSServices", "SearchKit", "SharedFileList"},
    "ApplicationServices": {"ATS", "ColorSync", "HIServices", "LangAnalysis", "PrintCore", "QD", "SpeechSynthesis"},
    "MetalPerformanceShaders": {"MPSCore", "MPSImage", "MPSMatrix", "MPSNeuralNetwork", "MPSRayIntersector", "MPSNDArray"},
}
ACCELERATE_VECLIB_IMAGES = {"vecLib", "libBLAS.dylib", "libLAPACK.dylib", "libvDSP.dylib",
                          "libvMisc.dylib", "libBNNS.dylib", "libLinearAlgebra.dylib",
                          "libSparse.dylib", "libSparseBLAS.dylib"}


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


def darwin_native_paths() -> list[str]:
    """Bounded stable dyld snapshots, not a claim of thread-safe enumeration."""
    dyld = ctypes.CDLL(None)
    dyld._dyld_image_count.argtypes = []
    dyld._dyld_image_count.restype = ctypes.c_uint32
    dyld._dyld_get_image_name.argtypes = [ctypes.c_uint32]
    dyld._dyld_get_image_name.restype = ctypes.c_char_p
    previous = None
    for _ in range(4):
        count = dyld._dyld_image_count()
        if not 0 < count <= MAX_NATIVE_IMAGES:
            raise ValueError("dyld image inventory exceeds bounds")
        paths = []
        for index in range(count):
            raw = dyld._dyld_get_image_name(index)
            if not raw or len(raw) > MAX_PATH_BYTES:
                raise ValueError("Unresolved dyld image path")
            name = raw.decode("utf-8", errors="strict")
            if not name.startswith("/") or "\x00" in name or "\n" in name:
                raise ValueError("dyld did not report an absolute image path")
            paths.append(name)
        current = tuple(sorted(set(paths)))
        if dyld._dyld_image_count() == count:
            if current == previous:
                return list(current)
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
    if system == "Linux":
        roots = (Path("/lib"), Path("/lib64"), Path("/usr/lib"), Path("/usr/lib64"))
        return bool(LINUX_SYSTEM_NAMES.fullmatch(path.name)) and any(within(path, root) for root in roots)
    if system != "Darwin":
        return False
    if path.parent == Path("/usr/lib") and path.name in DARWIN_DYLIB_NAMES:
        return True
    if path.parent == Path("/usr/lib/system") and path.name in DARWIN_SYSTEM_DYLIB_NAMES:
        return True
    for prefix, names in ((Path("/System/Library/Frameworks"), DARWIN_FRAMEWORKS),
                          (Path("/System/Library/PrivateFrameworks"), DARWIN_PRIVATE_FRAMEWORKS)):
        if path.is_relative_to(prefix):
            relative = path.relative_to(prefix).as_posix()
            # An approved framework does not approve arbitrary Resources or
            # plugins inside it. Only its named executable and named children.
            match = re.fullmatch(r"([A-Za-z0-9]+)\.framework/(?:Versions/[A-Za-z0-9.]+/)?([A-Za-z0-9]+)", relative)
            if match and match[1] in names and match[2] == match[1]:
                return True
            nested = re.fullmatch(r"([A-Za-z0-9]+)\.framework/(?:Versions/[A-Za-z0-9.]+/)?Frameworks/"
                                  r"([A-Za-z0-9]+)\.framework/(?:Versions/[A-Za-z0-9.]+/)?([^/]+)", relative)
            if nested and nested[1] in names and nested[2] in DARWIN_NESTED_FRAMEWORKS.get(nested[1], set()):
                allowed = ACCELERATE_VECLIB_IMAGES if (nested[1], nested[2]) == ("Accelerate", "vecLib") else {nested[2]}
                if nested[3] in allowed:
                    return True
    return False


def validate_native_paths(paths: list[str], root: Path, system: str) -> dict:
    bundled, system_paths = [], []
    required = {}
    if not paths or len(paths) > MAX_NATIVE_IMAGES:
        raise ValueError("Native image inventory outside bounds")
    for raw in paths:
        if not Path(raw).is_absolute() or len(raw.encode("utf-8")) > MAX_PATH_BYTES:
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
        elif system_library(path, system):
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
    paths = linux_native_paths() if system == "Linux" else darwin_native_paths()
    native = validate_native_paths(paths, root, system)
    return {"frozen": True, "executable": str(Path(sys.executable).resolve()),
            "bundle_root": str(root), "meipass": str(internal), "module_origins": origins,
            "native_module_paths": native, "loaded_native_paths": paths,
            "inventory_mechanism": "proc_self_maps_executable_files" if system == "Linux" else "dyld_stable_snapshots"}


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
        write_report(args.output.resolve(), report)
        return 0
    except Exception as exc:
        write_report(args.output.resolve(), {"status": "failed", "scope": "frozen_posix_cpu_public_fixture_smoke_only",
                     "error": f"{type(exc).__name__}: {exc}"[:12000]})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
