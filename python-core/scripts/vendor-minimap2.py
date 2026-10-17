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

A Linux binary already in place is reused offline only when its bytes match
the pinned digest of the executable inside the pinned official archive.
Anything else is replaced from a freshly downloaded and verified archive.
Preplaced platform slots are reported without executing unverified binaries.
"""

from __future__ import annotations

import argparse
import hashlib
import os
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


# Reviewed upstream GitHub release-asset digest, pinned in source rather than
# downloaded alongside the asset at install time. Asset 264213542, v2.30:
# https://api.github.com/repos/lh3/minimap2/releases/assets/264213542
# Recorded 2026-10-05. A version change requires reviewing a new full digest.
ARCHIVE_SHA256 = {
    "linux-x64": "b4c0677f282f448dac7bc1cd2fe5a45d12cb07a8b1edc316a45a26bbf75b7f07",
}

# SHA256 of the executable member ASSETS names inside the archive pinned above,
# so a vendored copy can be recognised without downloading. Derived 2026-10-06
# by hashing that member of an archive whose digest equalled ARCHIVE_SHA256.
# It is bound to that archive: every install re-checks the extracted member
# against it, and a version change must replace both digests together.
BINARY_SHA256 = {
    "linux-x64": "176de991772f37d1ecc7701d60354c3856bd487bdd927824f8c76e02018d1225",
}


def file_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    actual = file_sha256(path)
    if len(expected) != 64 or actual != expected:
        raise RuntimeError(f"SHA256 mismatch for {path}: expected {expected}, got {actual}")


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


def is_already_present(dest: Path, expected_sha256: str) -> bool:
    """Compare bytes with the pinned digest; never execute to establish trust."""
    if not dest.is_file():
        return False
    if file_sha256(dest) != expected_sha256:
        print(f"  [stale] {dest} differs from the verified release, will replace")
        return False
    if not dest.stat().st_mode & stat.S_IXUSR:
        print(f"  [stale] {dest} has verified bytes but is not executable; will replace")
        return False
    print(f"  [skip] {dest} matches the verified release SHA256")
    return True


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

    # No network when the vendored bytes already equal the pinned executable.
    if is_already_present(dest, BINARY_SHA256["linux-x64"]):
        return

    plat_dir.mkdir(parents=True, exist_ok=True)

    # Keep staging on the destination filesystem; failures preserve the old
    # vendor file.
    with tempfile.TemporaryDirectory(dir=plat_dir, prefix=".verify-") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / "minimap2.tar.bz2"
        download_with_progress(url, archive)
        verify_sha256(archive, ARCHIVE_SHA256["linux-x64"])

        staged = tmp_path / "minimap2"
        print(f"  Extracting verified {inner} ...")
        with tarfile.open(archive, "r:bz2") as tf:
            member = tf.getmember(inner)
            if not member.isfile():
                raise RuntimeError(f"Expected a regular executable archive member: {inner}")
            source = tf.extractfile(member)
            if source is None:
                raise RuntimeError(f"Missing executable archive member: {inner}")
            with source, staged.open("wb") as out:
                shutil.copyfileobj(source, out)
        binary_sha256 = file_sha256(staged)
        if binary_sha256 != BINARY_SHA256["linux-x64"]:
            raise RuntimeError(
                f"{inner} in the verified archive does not match the pinned binary "
                f"SHA256: expected {BINARY_SHA256['linux-x64']}, got {binary_sha256}"
            )

        staged.chmod(staged.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        # Only the executable from the pinned, verified archive is probed.
        ok, ver = check_version(staged)
        print(f"  Version check: {ver}")
        print(f"  Verified binary SHA256: {binary_sha256}")
        if not ok:
            raise RuntimeError(
                f"Version check failed for verified {staged}. Got: {ver!r}. "
                f"Expected to contain: {expected_version_string()!r}"
            )
        os.replace(staged, dest)
    print(f"  OK: {dest}")


def skip_platform(plat: str, reason: str) -> None:
    """Print status of a CI-supplied platform slot."""
    plat_dir = vendor_dir() / plat
    exe_name = "minimap2.exe" if "windows" in plat else "minimap2"
    dest = plat_dir / exe_name
    if dest.is_file():
        # These slots have no pinned reproducible binary digest yet. Reporting
        # their existence is not verification and must not execute their bytes.
        print(f"  [unverified] {dest}: pre-placed by CI or user; not executed")
        print(f"  SHA256 (untrusted observation): {file_sha256(dest)}")
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
