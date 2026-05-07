"""Tests for kuma_core.shared.output_hash.write_output_checksum.

Covers:
- Correct SHA-256 hex digest for known bytes
- Output file named ``<input>.sha256`` (extension appended, not replaced)
- File format: ``<hex>  <basename>\\n`` (two spaces, text-mode marker)
- shasum -c compatibility (subprocess check when shasum is on PATH)
- FileNotFoundError raised when input is absent (explicit error, no silent skip)
- ValueError raised for unsupported algorithm
- Returns the checksum file Path
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from kuma_core.shared.output_hash import write_output_checksum

# ---------------------------------------------------------------------------
# Known-bytes fixture
# ---------------------------------------------------------------------------

_KNOWN_BYTES = b"hello kuma!\n"
_KNOWN_SHA256 = hashlib.sha256(_KNOWN_BYTES).hexdigest()


@pytest.fixture
def known_file(tmp_path: Path) -> Path:
    """Write a small file with known bytes."""
    p = tmp_path / "export.csv"
    p.write_bytes(_KNOWN_BYTES)
    return p


# ---------------------------------------------------------------------------
# Core correctness
# ---------------------------------------------------------------------------


def test_returns_checksum_path(known_file: Path) -> None:
    cpath = write_output_checksum(known_file)
    assert isinstance(cpath, Path)


def test_checksum_file_exists(known_file: Path) -> None:
    cpath = write_output_checksum(known_file)
    assert cpath.exists(), f"Expected {cpath} to be created"


def test_checksum_filename_is_name_plus_sha256(known_file: Path) -> None:
    """Filename must be ``<output_name>.sha256``, not ``<stem>.sha256``."""
    cpath = write_output_checksum(known_file)
    assert cpath.name == "export.csv.sha256"


def test_checksum_digest_is_correct(known_file: Path) -> None:
    cpath = write_output_checksum(known_file)
    text = cpath.read_text(encoding="utf-8")
    hex_in_file = text.split("  ")[0]
    assert hex_in_file == _KNOWN_SHA256


def test_checksum_format_two_spaces(known_file: Path) -> None:
    """Two spaces separate digest from filename (text-mode marker)."""
    cpath = write_output_checksum(known_file)
    text = cpath.read_text(encoding="utf-8")
    # Pattern: 64 hex chars + exactly two spaces + basename + newline
    pattern = re.compile(r"^[0-9a-f]{64}  export\.csv\n$")
    assert pattern.match(text), f"Format mismatch: {text!r}"


def test_checksum_basename_only_not_full_path(known_file: Path) -> None:
    """The filename portion in the .sha256 file must be basename only."""
    cpath = write_output_checksum(known_file)
    text = cpath.read_text(encoding="utf-8")
    _, name_part = text.rstrip("\n").split("  ", 1)
    # Must not contain a path separator
    assert "/" not in name_part and "\\" not in name_part


def test_checksum_ends_with_newline(known_file: Path) -> None:
    cpath = write_output_checksum(known_file)
    raw = cpath.read_bytes()
    assert raw.endswith(b"\n")


# ---------------------------------------------------------------------------
# shasum -c compatibility (subprocess; skipped if shasum not on PATH)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("shasum") is None, reason="shasum not on PATH")
def test_shasum_c_passes(known_file: Path) -> None:
    write_output_checksum(known_file)
    result = subprocess.run(
        ["shasum", "-a", "256", "-c", known_file.name + ".sha256"],
        cwd=known_file.parent,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"shasum -c failed: {result.stderr}"


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="sha256sum not on PATH")
def test_sha256sum_check_passes(known_file: Path) -> None:
    write_output_checksum(known_file)
    result = subprocess.run(
        ["sha256sum", "--check", known_file.name + ".sha256"],
        cwd=known_file.parent,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"sha256sum --check failed: {result.stderr}"


# ---------------------------------------------------------------------------
# Extension variants: xlsx should also work
# ---------------------------------------------------------------------------


def test_xlsx_extension_appended(tmp_path: Path) -> None:
    xlsx = tmp_path / "plate.xlsx"
    xlsx.write_bytes(b"fake xlsx content")
    cpath = write_output_checksum(xlsx)
    assert cpath.name == "plate.xlsx.sha256"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    """Absent output file must raise FileNotFoundError — no silent skip."""
    with pytest.raises(FileNotFoundError):
        write_output_checksum(tmp_path / "nonexistent.csv")


def test_unsupported_algorithm_raises_value_error(known_file: Path) -> None:
    with pytest.raises(ValueError, match="sha256"):
        write_output_checksum(known_file, algorithm="md5")


def test_returns_resolved_absolute_path(tmp_path: Path) -> None:
    f = tmp_path / "out.csv"
    f.write_bytes(b"data")
    cpath = write_output_checksum(f)
    assert cpath.is_absolute()
