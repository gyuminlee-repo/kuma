"""Build kuma sidecar binaries using PyInstaller.

Builds sidecar_main_<target>.py into standalone binaries and copies them to
src-tauri/binaries/ with the correct Tauri target-triple suffix.

Usage:
    python build_sidecar.py                       # kuro, mame (default)
    python build_sidecar.py --target kuro         # only kuro
    python build_sidecar.py --target mame         # only mame
    python build_sidecar.py --target all          # kuro, mame (explicit)
    python build_sidecar.py --onedir              # standalone diagnostic bundle, not Tauri
"""

import argparse
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from pyinstaller_hooks._lgpl_excluded import EXCLUDED_MODULE as LGPL_EXCLUDED_MODULE

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
TAURI_BINARIES = PROJECT_ROOT / "src-tauri" / "binaries"

TARGETS = {
    "kuro": {
        "entry": "sidecar_main_kuro.py",
        "sidecar_name": "kuro-sidecar",
        "resources": "kuma_core/kuro/resources",
        "hidden_imports": [
            "numpy",
            "primer3",
            "openpyxl",
            # xlrd is imported lazily for legacy .xls tables, in both the
            # preview path (sidecar_kuro/handlers/misc.py:125) and the actual
            # load path (kuma_core/kuro/evolvepro.py:339), so PyInstaller's
            # static analysis cannot see it. Without this entry the packaged
            # sidecar raises ModuleNotFoundError on any .xls source, while a
            # development run succeeds because the wheel is installed.
            "xlrd",
            # truststore backs the OS trust-store SSL context in
            # kuma_core/shared/net.py. Both that import and the backend
            # imports in truststore/_api.py are plain import statements, so
            # PyInstaller is expected to follow them on its own; this entry
            # plus collect_all below are belt-and-braces so that every
            # platform backend (_windows, _macos, _openssl) and py.typed are
            # present regardless. Getting this wrong is silent: the sidecar
            # falls back to the certifi bundle and fails on any network with
            # a TLS-inspecting proxy.
            "truststore",
            "sidecar_kuro",
            "sidecar_kuro.dispatcher",
            "kuma_core.kuro",
            # setuptools vendored packages are accessed under bare names
            # (e.g. `from backports import tarfile` inside jaraco.context).
            # PyInstaller's pre_safe_import_module alias only fires for
            # `backports.tarfile` not bare `backports`, so include the
            # vendored modules explicitly.
            "setuptools._vendor.backports",
            "setuptools._vendor.backports.tarfile",
            "setuptools._vendor.jaraco.context",
            "setuptools._vendor.jaraco.text",
            "setuptools._vendor.jaraco.functools",
        ],
        # setuptools is collected by pyinstaller_hooks/hook-setuptools._vendor.py
        # (same as `--collect-all setuptools`, minus LGPL-3.0 autocommand);
        # `--exclude-module` alone would leave autocommand's .py sources inside
        # the binary as data files.
        "collect_all": ["pydantic", "primer3", "sidecar_kuro", "kuma_core", "truststore"],
        "excludes": [LGPL_EXCLUDED_MODULE],
    },
    "mame": {
        "entry": "sidecar_main_mame.py",
        "sidecar_name": "mame-sidecar",
        "resources": None,
        "hidden_imports": [
            "openpyxl",
            "pandas",
            "Bio.Seq",
            "python_calamine",
            "primer3",
            # edlib is imported lazily inside _best_infix_match
            # (kuma_core/mame/ingest/combinatorial_demux.py:319) for fuzzy
            # barcode matching, so PyInstaller's static analysis cannot see it.
            # Without this entry the packaged sidecar raises ModuleNotFoundError
            # at the demux step, surfaced to the UI as -32603 Internal error.
            "edlib",
            # truststore backs the OS trust-store SSL context in
            # kuma_core/shared/net.py. Both that import and the backend
            # imports in truststore/_api.py are plain import statements, so
            # PyInstaller is expected to follow them on its own; this entry
            # plus collect_all below are belt-and-braces so that every
            # platform backend (_windows, _macos, _openssl) and py.typed are
            # present regardless. Getting this wrong is silent: the sidecar
            # falls back to the certifi bundle and fails on any network with
            # a TLS-inspecting proxy.
            "truststore",
            "sidecar_mame",
            "sidecar_mame.dispatcher",
            "kuma_core.mame",
            # See note on kuro target; same setuptools vendored fix.
            "setuptools._vendor.backports",
            "setuptools._vendor.backports.tarfile",
            "setuptools._vendor.jaraco.context",
            "setuptools._vendor.jaraco.text",
            "setuptools._vendor.jaraco.functools",
        ],
        # setuptools is collected by pyinstaller_hooks/hook-setuptools._vendor.py
        # (same as `--collect-all setuptools`, minus LGPL-3.0 autocommand).
        "collect_all": ["openpyxl", "primer3", "sidecar_mame", "kuma_core", "truststore"],
        "excludes": [
            LGPL_EXCLUDED_MODULE,
            "matplotlib",
            "sklearn",
            "tensorflow",
            "torch",
            "transformers",
            "triton",
        ],
    },
}


def get_target_triple() -> str:
    """Detect the Tauri target-triple suffix for the current platform."""
    machine = platform.machine().lower()
    system = platform.system().lower()

    arch_map = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }
    arch = arch_map.get(machine, machine)

    if system == "windows":
        return f"{arch}-pc-windows-msvc"
    elif system == "darwin":
        return f"{arch}-apple-darwin"
    elif system == "linux":
        return f"{arch}-unknown-linux-gnu"
    else:
        print(f"WARNING: Unknown platform '{system}', using linux triple")
        return f"{arch}-unknown-linux-gnu"


def build_sidecar(target: str, onefile: bool = True) -> Path:
    """Run PyInstaller for one target and return the path to the built binary."""
    cfg = TARGETS[target]
    entry_point = SCRIPT_DIR / cfg["entry"]
    sidecar_name = cfg["sidecar_name"]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--name",
        sidecar_name,
        "--onefile" if onefile else "--onedir",
        # Project hooks: hook-setuptools._vendor.py re-runs collect_all for
        # setuptools with the LGPL-3.0 vendored autocommand filtered out.
        "--additional-hooks-dir",
        str(SCRIPT_DIR / "pyinstaller_hooks"),
    ]

    for hi in cfg["hidden_imports"]:
        cmd += ["--hidden-import", hi]

    for ca in cfg["collect_all"]:
        cmd += ["--collect-all", ca]

    for excluded in cfg["excludes"]:
        cmd += ["--exclude-module", excluded]

    if cfg["resources"]:
        resources_dir = PROJECT_ROOT / cfg["resources"]
        separator = ";" if platform.system() == "Windows" else ":"
        cmd += ["--add-data", f"{resources_dir}{separator}{cfg['resources']}"]

    separator = ";" if platform.system() == "Windows" else ":"
    for src_rel, dest in cfg.get("add_data", []):
        src_abs = PROJECT_ROOT / src_rel
        cmd += ["--add-data", f"{src_abs}{separator}{dest}"]

    # mame only: bundle the platform-appropriate minimap2 binary.
    if target == "mame":
        sep = ";" if platform.system() == "Windows" else ":"
        machine = platform.machine().lower()
        system = platform.system().lower()
        if system == "linux":
            plat = "linux-x64"
        elif system == "darwin":
            plat = "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x64"
        elif system == "windows":
            plat = "windows-x64"
        else:
            plat = "linux-x64"
        exe_name = "minimap2.exe" if system == "windows" else "minimap2"
        vendor_bin = PROJECT_ROOT / "python-core" / "vendor" / "minimap2" / plat / exe_name
        if not vendor_bin.is_file():
            print(
                f"ERROR: vendor minimap2 binary not found for {plat}: {vendor_bin}\n"
                f"Run 'python python-core/scripts/vendor-minimap2.py' to download (linux-x64).\n"
                f"For macOS/Windows, CI must compile the binary and place it at the path above.",
                file=sys.stderr,
            )
            sys.exit(1)
        cmd += ["--add-binary", f"{vendor_bin}{sep}bin"]
        print(f"[{target}] Adding minimap2 binary: {vendor_bin} -> bin/")

    cmd += [
        "--paths", str(PROJECT_ROOT),
        "--paths", str(SCRIPT_DIR),
        "--distpath", str(SCRIPT_DIR / "dist"),
        "--workpath", str(SCRIPT_DIR / "build"),
        "--specpath", str(SCRIPT_DIR),
        str(entry_point),
    ]

    print(f"[{target}] Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(SCRIPT_DIR))

    ext = ".exe" if platform.system() == "Windows" else ""
    if onefile:
        return SCRIPT_DIR / "dist" / f"{sidecar_name}{ext}"
    else:
        return SCRIPT_DIR / "dist" / sidecar_name


def copy_to_tauri(target: str, built_path: Path) -> Path:
    """Copy the built binary to src-tauri/binaries/ with the target-triple suffix."""
    cfg = TARGETS[target]
    sidecar_name = cfg["sidecar_name"]
    triple = get_target_triple()
    ext = ".exe" if platform.system() == "Windows" else ""
    dest_name = f"{sidecar_name}-{triple}{ext}"

    if built_path.is_dir():
        raise ValueError("Tauri externalBin requires --onefile; keep the onedir bundle intact for standalone use")
    TAURI_BINARIES.mkdir(parents=True, exist_ok=True)
    dest = TAURI_BINARIES / dest_name
    shutil.copy2(built_path, dest)
    print(f"[{target}] Copied: {dest}")
    return dest


def find_excluded_license_payload(entry_names: Iterable[str], excluded_module: str) -> list[str]:
    """Return every packaged entry name that belongs to ``excluded_module``.

    ``entry_names`` mixes two shapes seen across onefile and onedir builds:
    dotted module names from the PYZ archive TOC (e.g.
    ``setuptools._vendor.autocommand.autocommand``) and path-like names from
    onedir's loose data files (e.g.
    ``setuptools/_vendor/autocommand-2.2.2.dist-info/METADATA``, or
    backslash-separated on the Windows release runner). Both are split on
    ``.``, ``/`` and ``\\`` so a single pass over path segments catches the
    module directory itself, any of its submodules, and its versioned
    dist-info directory (which is named after the distribution, not the
    dotted module path).
    """
    excluded_parts = tuple(excluded_module.split("."))
    leaf = excluded_parts[-1]
    hits: set[str] = set()
    for name in entry_names:
        segments = tuple(re.split(r"[./\\]", name))
        if segments[: len(excluded_parts)] == excluded_parts:
            hits.add(name)
            continue
        for i, seg in enumerate(segments):
            if seg != leaf and not seg.startswith(f"{leaf}-"):
                continue
            preceding = segments[max(0, i - (len(excluded_parts) - 1)) : i]
            if preceding == excluded_parts[:-1]:
                hits.add(name)
                break
    return sorted(hits)


def _packaged_entry_names(built_path: Path, onefile: bool) -> set[str]:
    """List every archive and data entry a built sidecar ships.

    Onefile embeds compiled modules (PYZ) and raw data files (dist-info,
    vendored .py sources) inside one CArchive, so PyInstaller's own
    ``pkg_archive_contents`` helper is authoritative on its own. Onedir
    additionally extracts data files as loose files next to the executable
    (the COLLECT step) which never enter the archive TOC, so those are
    walked separately.
    """
    from PyInstaller.archive.readers import pkg_archive_contents

    ext = ".exe" if platform.system() == "Windows" else ""
    exe = built_path if onefile else built_path / f"{built_path.name}{ext}"
    entries = set(pkg_archive_contents(str(exe)))
    if not onefile:
        internal = built_path / "_internal"
        if internal.is_dir():
            entries.update(
                str(path.relative_to(internal)) for path in internal.rglob("*") if path.is_file()
            )
    return entries


def check_no_excluded_license_payload(built_path: Path, onefile: bool) -> None:
    """Fail the build if the LGPL-3.0 vendored module made it into the binary.

    ``--exclude-module`` alone cannot prevent this (it only strips the
    compiled module from the PYZ; collect_all's data-file walk still ships
    the raw sources and dist-info), so this checks the actual built payload
    rather than trusting the build flags. See PR #444 and
    pyinstaller_hooks/hook-setuptools._vendor.py.
    """
    entries = _packaged_entry_names(built_path, onefile)
    hits = find_excluded_license_payload(entries, LGPL_EXCLUDED_MODULE)
    if not hits:
        return
    hook_path = SCRIPT_DIR / "pyinstaller_hooks" / "hook-setuptools._vendor.py"
    shown = hits[:20]
    more = f"\n  ... and {len(hits) - 20} more" if len(hits) > 20 else ""
    print(
        f"ERROR: {len(hits)} packaged entr{'y' if len(hits) == 1 else 'ies'} belong to the "
        f"LGPL-3.0 vendored module {LGPL_EXCLUDED_MODULE!r}, which must not ship in the "
        f"sidecar binaries:\n  " + "\n  ".join(shown) + more +
        f"\nFix: update the filter in {hook_path} to also drop these entries.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=["kuro", "mame", "all"],
        default="all",
        help="Which sidecar to build",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="Build a standalone diagnostic directory (not copied to Tauri; releases require onefile)",
    )
    args = parser.parse_args()

    targets = ["kuro", "mame"] if args.target == "all" else [args.target]
    onefile = not args.onedir

    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Target triple: {get_target_triple()}")
    print(f"Targets: {', '.join(targets)}")
    print(f"Mode: {'--onefile' if onefile else '--onedir'}")
    print()

    for target in targets:
        built = build_sidecar(target, onefile=onefile)
        if not built.exists():
            print(f"ERROR: Build output not found at {built}", file=sys.stderr)
            sys.exit(1)
        check_no_excluded_license_payload(built, onefile)
        if not onefile:
            print(f"[{target}] Standalone bundle ready: {built} (keep the entire directory)")
            continue
        dest = copy_to_tauri(target, built)
        print(f"[{target}] Sidecar binary ready: {dest}")
        print()

    if onefile:
        print("Run 'npm run tauri build' to create the installer.")
    else:
        print("For a Tauri installer, rebuild without --onedir.")


if __name__ == "__main__":
    main()
