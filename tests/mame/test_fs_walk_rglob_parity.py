"""``rglob_entries`` must enumerate exactly what ``Path.rglob`` enumerated.

The demux hot paths replaced two full recursive walks with one bucketed walk.
That is only a safe swap if the *set* of files each pattern sees is unchanged,
so this module builds a tree stocked with the cases where a hand-rolled walk
usually drifts from ``pathlib`` (dot-files, directories that look like data
files, symlinks to files, symlinks to directories, dangling symlinks, nested
depth, case variants) and asserts equality against ``Path.rglob`` itself rather
than against a hard-coded expectation.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kuma_core.shared.fs_walk import rglob_entries, rglob_paths

_PATTERNS = ("*.fastq", "*.fastq.gz")


def _supports_symlinks(tmp_path: Path) -> bool:
    try:
        (tmp_path / "_probe_target").write_text("x", encoding="utf-8")
        (tmp_path / "_probe_link").symlink_to(tmp_path / "_probe_target")
    except (OSError, NotImplementedError):
        return False
    (tmp_path / "_probe_link").unlink()
    (tmp_path / "_probe_target").unlink()
    return True


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    """A MinKNOW-shaped tree seeded with the awkward cases."""
    root = tmp_path / "fastq_pass"
    (root / "barcode01").mkdir(parents=True)
    (root / "barcode02" / "nested").mkdir(parents=True)
    (root / "empty").mkdir()

    for rel in (
        "barcode01/PAY_0.fastq",
        "barcode01/PAY_1.fastq.gz",
        "barcode01/.hidden.fastq",
        "barcode01/notes.txt",
        "barcode01/PAY_2.FASTQ",
        "barcode02/PAY_0.fastq.gz",
        "barcode02/nested/PAY_9.fastq",
        "barcode02/nested/PAY_9.fastq.gz",
        "top_level.fastq",
    ):
        path = root / rel
        path.write_text(f"@{rel}\nACGT\n+\n!!!!\n", encoding="utf-8")

    # A directory whose *name* matches the pattern: rglob returns it, so the
    # single-pass walk must return it too.
    (root / "decoy.fastq").mkdir()
    (root / "decoy.fastq" / "inner.fastq").write_text("x", encoding="utf-8")
    return root


def test_matches_rglob_per_pattern(tree: Path) -> None:
    got = rglob_paths(tree, _PATTERNS)
    for pattern in _PATTERNS:
        assert sorted(got[pattern]) == sorted(tree.rglob(pattern)), pattern


def test_matches_rglob_with_symlinks(tree: Path, tmp_path: Path) -> None:
    if not _supports_symlinks(tmp_path):
        pytest.skip("filesystem does not support symlinks")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "linked.fastq").write_text("x", encoding="utf-8")

    (tree / "link_to_file.fastq").symlink_to(outside / "linked.fastq")
    (tree / "link_to_dir").symlink_to(outside, target_is_directory=True)
    (tree / "dangling.fastq").symlink_to(tmp_path / "does_not_exist")
    # A symlink pointing back at an ancestor: a walk that follows linked
    # directories would recurse forever here. ``Path.rglob`` does not follow it.
    (tree / "loop").symlink_to(tree, target_is_directory=True)

    got = rglob_paths(tree, _PATTERNS)
    for pattern in _PATTERNS:
        assert sorted(got[pattern]) == sorted(tree.rglob(pattern)), pattern


def test_entry_stat_size_matches_path_stat(tree: Path) -> None:
    """``DirEntry.stat().st_size`` is the value the old ``Path.stat()`` gave."""
    matches = rglob_entries(tree, _PATTERNS)
    seen = 0
    for pattern in _PATTERNS:
        for path, entry in matches[pattern]:
            if not path.is_file():
                continue
            assert entry.stat().st_size == path.stat().st_size
            seen += 1
    assert seen > 0


def test_missing_root_is_empty_not_an_error(tmp_path: Path) -> None:
    got = rglob_paths(tmp_path / "nope", _PATTERNS)
    assert got == {pattern: [] for pattern in _PATTERNS}


def test_root_that_is_a_file_is_empty(tmp_path: Path) -> None:
    target = tmp_path / "afile"
    target.write_text("x", encoding="utf-8")
    assert rglob_paths(target, _PATTERNS) == {pattern: [] for pattern in _PATTERNS}


def test_unreadable_subdirectory_prunes_that_branch(tmp_path: Path) -> None:
    if os.name != "posix" or os.geteuid() == 0:
        pytest.skip("POSIX directory permissions required (and root bypasses them)")
    root = tmp_path / "run"
    (root / "open").mkdir(parents=True)
    (root / "open" / "a.fastq").write_text("x", encoding="utf-8")
    closed = root / "closed"
    closed.mkdir()
    (closed / "b.fastq").write_text("x", encoding="utf-8")
    closed.chmod(0o000)
    try:
        got = rglob_paths(root, ("*.fastq",))
        assert got["*.fastq"] == [root / "open" / "a.fastq"]
    finally:
        closed.chmod(0o755)


def test_pattern_matching_two_buckets_lands_in_both(tree: Path) -> None:
    """Overlapping patterns behave like separate ``rglob`` calls, not a break."""
    got = rglob_paths(tree, ("*.fastq.gz", "*.gz"))
    assert sorted(got["*.fastq.gz"]) == sorted(tree.rglob("*.fastq.gz"))
    assert sorted(got["*.gz"]) == sorted(tree.rglob("*.gz"))
    assert got["*.fastq.gz"] and got["*.gz"]
