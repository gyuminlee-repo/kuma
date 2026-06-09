"""Build kuma sidecar binaries using PyInstaller.

Builds sidecar_main_<target>.py into standalone binaries and copies them to
src-tauri/binaries/ with the correct Tauri target-triple suffix.

Usage:
    python build_sidecar.py                       # kuro, mame (default)
    python build_sidecar.py --target kuro         # only kuro
    python build_sidecar.py --target mame         # only mame
    python build_sidecar.py --target all          # kuro, mame (explicit)
    python build_sidecar.py --onedir              # multi-file mode (applies to all targets)
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

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
        "collect_all": ["pydantic", "primer3", "sidecar_kuro", "kuma_core", "setuptools"],
        "excludes": [],
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
        "collect_all": ["openpyxl", "primer3", "sidecar_mame", "kuma_core", "setuptools"],
        "excludes": [
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
        return SCRIPT_DIR / "dist" / sidecar_name / f"{sidecar_name}{ext}"


def copy_to_tauri(target: str, built_path: Path) -> Path:
    """Copy the built binary to src-tauri/binaries/ with the target-triple suffix."""
    cfg = TARGETS[target]
    sidecar_name = cfg["sidecar_name"]
    triple = get_target_triple()
    ext = ".exe" if platform.system() == "Windows" else ""
    dest_name = f"{sidecar_name}-{triple}{ext}"

    TAURI_BINARIES.mkdir(parents=True, exist_ok=True)

    if built_path.is_dir():
        dest_dir = TAURI_BINARIES / f"{sidecar_name}-{triple}"
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(built_path.parent / sidecar_name, dest_dir)
        src_exe = dest_dir / f"{sidecar_name}{ext}"
        dest_exe = TAURI_BINARIES / dest_name
        if dest_exe.exists():
            dest_exe.unlink()
        shutil.copy2(src_exe, dest_exe)
        print(f"[{target}] Copied directory: {dest_dir}")
        print(f"[{target}] Copied executable: {dest_exe}")
        return dest_exe
    else:
        dest = TAURI_BINARIES / dest_name
        shutil.copy2(built_path, dest)
        print(f"[{target}] Copied: {dest}")
        return dest


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
        help="Build in directory mode instead of onefile",
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
        dest = copy_to_tauri(target, built)
        print(f"[{target}] Sidecar binary ready: {dest}")
        print()

    print("Run 'npm run tauri build' to create the installer.")


if __name__ == "__main__":
    main()
