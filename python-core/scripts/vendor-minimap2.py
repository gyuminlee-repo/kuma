"""Download minimap2 2.30 (r1287) pre-built binaries into the vendor layout.

Vendor layout:
    python-core/vendor/minimap2/<plat>/minimap2[.exe]

Supported <plat> values:
    linux-x64      -- official release binary available
    macos-x64      -- no official binary for v2.30; CI must supply (slot only)
    macos-arm64    -- no official binary for v2.30; CI must supply (slot only)
    windows-x64    -- no official binary for v2.30; CI must supply (slot only)

Usage:
    python python-core/scripts/vendor-minimap2.py        # auto-detect OS
    python python-core/scripts/vendor-minimap2.py --all  # report all plats

Idempotent: binary already present and correct version => skip re-download.
"""

from __future__ import annotations

import argparse
import hashlib
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

MINIMAP2_VERSION = "2.30"
MINIMAP2_VERSION_SUFFIX = "r1287"
MINIMAP2_TAG = f"v{MINIMAP2_VERSION}"
MINIMAP2_RELEASE_BASE = (
    f"https://github.com/lh3/minimap2/releases/download/{MINIMAP2_TAG}"
)

# Only linux-x64 has an official pre-built binary in the v2.30 release.
# macos-x64, macos-arm64, windows-x64 have no official binaries:
#   CI (GitHub Actions) is responsible for compiling and placing them at
#   python-core/vendor/minimap2/<plat>/minimap2[.exe]
ASSETS: dict[str, tuple[str, str]] = {
    "linux-x64": (
        f"{MINIMAP2_RELEASE_BASE}/minimap2-{MINIMAP2_VERSION}_x64-linux.tar.bz2",
        f"minimap2-{MINIMAP2_VERSION}_x64-linux/minimap2",
    ),
}


def script_root() -> Path:
    return Path(__file__).parent.parent.parent.resolve()


def vendor_dir() -> Path:
    return script_root() / "python-core" / "vendor" / "minimap2"


def expected_version_string() -> str:
    return f"{MINIMAP2_VERSION}-{MINIMAP2_VERSION_SUFFIX}"


def check_version(binary: Path) -> tuple[bool, str]:
    """Run `binary --version` and return (ok, version_line)."""
    try:
        result = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = (result.stdout or result.stderr or "").strip()
        ok = expected_version_string() in out
        return ok, out
    except Exception as exc:
        return False, str(exc)


def is_already_present(dest: Path) -> bool:
    """Return True if dest exists, is executable, and reports the right version."""
    if not dest.is_file():
        return False
    ok, ver = check_version(dest)
    if ok:
        print(f"  [skip] {dest} already at {ver}")
    else:
        print(f"  [stale] {dest} version mismatch ({ver}), will re-download")
    return ok


def download_with_progress(url: str, dest_file: Path) -> None:
    print(f"  Downloading {url}")

    def _progress(count: int, block_size: int, total: int) -> None:
        if total > 0:
            pct = min(100, count * block_size * 100 // total)
            print(f"\r  {pct}%", end="", flush=True)

    urllib.request.urlretrieve(url, str(dest_file), _progress)
    print()


def install_linux_x64() -> None:
    url, inner = ASSETS["linux-x64"]
    plat_dir = vendor_dir() / "linux-x64"
    dest = plat_dir / "minimap2"

    if is_already_present(dest):
        return

    plat_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "minimap2.tar.bz2"
        download_with_progress(url, archive)

        print(f"  Extracting {inner} ...")
        with tarfile.open(archive, "r:bz2") as tf:
            member = tf.getmember(inner)
            with tf.extractfile(member) as src, open(dest, "wb") as out:  # type: ignore[arg-type]
                shutil.copyfileobj(src, out)

    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    ok, ver = check_version(dest)
    sha256 = hashlib.sha256(dest.read_bytes()).hexdigest()[:16]
    print(f"  Version check: {ver}")
    print(f"  SHA256 (first 16): {sha256}")
    if not ok:
        dest.unlink(missing_ok=True)
        raise RuntimeError(
            f"Version check failed for {dest}. Got: {ver!r}. "
            f"Expected to contain: {expected_version_string()!r}"
        )
    print(f"  OK: {dest}")


def skip_platform(plat: str, reason: str) -> None:
    """Print status of a CI-supplied platform slot."""
    plat_dir = vendor_dir() / plat
    exe_name = "minimap2.exe" if "windows" in plat else "minimap2"
    dest = plat_dir / exe_name
    if dest.is_file():
        ok, ver = check_version(dest)
        print(f"  [found] {dest}: {ver} (pre-placed by CI or user)")
    else:
        print(f"  [slot] {plat}: {reason}")
        print(f"         Expected path: {dest}")
        print(f"         CI must compile and place the binary before building.")


def detect_current_plat() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "linux":
        return "linux-x64"
    elif system == "darwin":
        return "macos-arm64" if machine in ("arm64", "aarch64") else "macos-x64"
    elif system == "windows":
        return "windows-x64"
    else:
        return "linux-x64"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Report status of all platform slots (not just current platform)",
    )
    args = parser.parse_args()

    print(f"minimap2 vendor script -- target version: {expected_version_string()}")
    print(f"Vendor directory: {vendor_dir()}")
    print()

    current_plat = detect_current_plat()
    print(f"Current platform: {current_plat}")
    print()

    if args.all or current_plat == "linux-x64":
        print("=== linux-x64 ===")
        install_linux_x64()
        print()

    ci_slots = {
        "macos-x64": "No official v2.30 macOS binary; CI must compile from source.",
        "macos-arm64": "No official v2.30 macOS arm64 binary; CI must compile from source.",
        "windows-x64": "No official v2.30 Windows binary; CI must compile from source.",
    }

    if args.all:
        for plat, reason in ci_slots.items():
            print(f"=== {plat} ===")
            skip_platform(plat, reason)
            print()
    elif current_plat in ci_slots:
        print(f"=== {current_plat} ===")
        skip_platform(current_plat, ci_slots[current_plat])
        print()

    print("Done.")


if __name__ == "__main__":
    main()
