"""Build EvolveProprimer sidecar binary using PyInstaller.

Builds sidecar_main.py into a standalone binary and copies it to
src-tauri/binaries/ with the correct Tauri target-triple suffix.

Usage:
    python build_sidecar.py            # --onefile (default)
    python build_sidecar.py --onedir   # multi-file mode
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent
TAURI_BINARIES = PROJECT_ROOT / "src-tauri" / "binaries"
ENTRY_POINT = SCRIPT_DIR / "sidecar_main.py"
SIDECAR_NAME = "evolveproprimer-sidecar"


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


def build_sidecar(onefile: bool = True) -> Path:
    """Run PyInstaller and return the path to the built binary."""
    resources_dir = PROJECT_ROOT / "evolveprimer" / "resources"
    separator = ";" if platform.system() == "Windows" else ":"
    add_data = f"{resources_dir}{separator}evolveprimer/resources"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--name",
        SIDECAR_NAME,
        "--onefile" if onefile else "--onedir",
        "--hidden-import",
        "numpy",
        "--hidden-import",
        "primer3",
        "--hidden-import",
        "openpyxl",
        "--collect-all",
        "primer3",
        "--add-data",
        add_data,
        "--paths",
        str(PROJECT_ROOT),
        "--distpath",
        str(SCRIPT_DIR / "dist"),
        "--workpath",
        str(SCRIPT_DIR / "build"),
        "--specpath",
        str(SCRIPT_DIR),
        str(ENTRY_POINT),
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(SCRIPT_DIR))

    ext = ".exe" if platform.system() == "Windows" else ""
    if onefile:
        return SCRIPT_DIR / "dist" / f"{SIDECAR_NAME}{ext}"
    else:
        return SCRIPT_DIR / "dist" / SIDECAR_NAME / f"{SIDECAR_NAME}{ext}"


def copy_to_tauri(built_path: Path) -> Path:
    """Copy the built binary to src-tauri/binaries/ with the target-triple suffix."""
    triple = get_target_triple()
    ext = ".exe" if platform.system() == "Windows" else ""
    dest_name = f"{SIDECAR_NAME}-{triple}{ext}"

    TAURI_BINARIES.mkdir(parents=True, exist_ok=True)

    if built_path.is_dir():
        dest_dir = TAURI_BINARIES / f"{SIDECAR_NAME}-{triple}"
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(built_path.parent / SIDECAR_NAME, dest_dir)
        src_exe = dest_dir / f"{SIDECAR_NAME}{ext}"
        dest_exe = TAURI_BINARIES / dest_name
        if dest_exe.exists():
            dest_exe.unlink()
        shutil.copy2(src_exe, dest_exe)
        print(f"Copied directory: {dest_dir}")
        print(f"Copied executable: {dest_exe}")
        return dest_exe
    else:
        dest = TAURI_BINARIES / dest_name
        shutil.copy2(built_path, dest)
        print(f"Copied: {dest}")
        return dest


def main() -> None:
    onefile = "--onedir" not in sys.argv

    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Target triple: {get_target_triple()}")
    print(f"Mode: {'--onefile' if onefile else '--onedir'}")
    print()

    built = build_sidecar(onefile=onefile)
    if not built.exists():
        print(f"ERROR: Build output not found at {built}", file=sys.stderr)
        sys.exit(1)

    dest = copy_to_tauri(built)

    print()
    print(f"Sidecar binary ready: {dest}")
    print("Run 'npm run tauri build' to create the installer.")


if __name__ == "__main__":
    main()
