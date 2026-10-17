# ruff: noqa: S101, S603, S607
"""Tracked files carry only synthetic Oxford Nanopore flow cell and device IDs.

This repository is public and its history cannot be rewritten, so a MinKNOW
report or summary copied from a real run must never be committed. Fixtures use
the synthetic IDs below; any other ID of the same shape fails this test.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ID = re.compile(rb"(?<![A-Za-z0-9])[FP][A-Z]{2}[0-9]{5}(?![0-9])")
_SYNTHETIC = {b"FAX00001", b"FAX00002", b"FAX12345", b"FAW12345", b"PAX12345"}


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=_ROOT, check=True, capture_output=True
    ).stdout
    return [_ROOT / p.decode() for p in out.split(b"\0") if p]


def _unknown_ids(data: bytes) -> set[bytes]:
    return {m for m in _ID.findall(data) if m not in _SYNTHETIC}


def test_pattern_catches_a_real_flow_cell_id() -> None:
    # Assembled at run time so this file never holds a matching literal.
    fake = b"FB" + b"Q" + b"98765"
    assert _unknown_ids(b'"flow_cell_id": "' + fake + b'"') == {fake}
    assert _unknown_ids(b"report_" + fake + b"_20260101.json") == {fake}
    assert _unknown_ids(b"flow_cell_id = FAX00001") == set()


def test_tracked_files_hold_only_synthetic_ids() -> None:
    found: dict[str, set[bytes]] = {}
    for path in _tracked_files():
        if not path.is_file():
            continue
        data = path.read_bytes()
        # Binary files (images, archives) only have their name checked.
        body = b"" if b"\0" in data[:8192] else data
        hits = _unknown_ids(path.name.encode()) | _unknown_ids(body)
        if hits:
            found[str(path.relative_to(_ROOT))] = hits
    assert not found, f"real run identifiers in tracked files: {found}"
