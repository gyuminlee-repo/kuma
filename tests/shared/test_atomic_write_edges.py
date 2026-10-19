# ruff: noqa: S101
from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from kuma_core.shared import atomic_write as aw

posix_only = pytest.mark.skipif(os.name != "posix", reason="permissions are kept only on POSIX")


def test_unknown_encoding_fails_before_a_staging_file_exists(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    with pytest.raises(LookupError):
        aw.atomic_write_text(target, "x", encoding="no-such-codec")
    assert list(tmp_path.iterdir()) == []


def test_staging_name_adds_at_most_eighteen_characters(tmp_path: Path) -> None:
    target = tmp_path / "workspace.json"
    assert len(aw._temp_path_for(target).name) - len(target.name) <= 18


@posix_only
@pytest.mark.parametrize("code", [errno.EPERM, errno.ENOTSUP])
def test_replacing_on_a_share_that_refuses_chmod_still_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")

    def refuse(fd: int, mode: int) -> None:
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(aw.os, "fchmod", refuse)
    aw.atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]


@posix_only
def test_other_chmod_failures_still_abort_and_keep_the_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "out.txt"
    target.write_text("old", encoding="utf-8")

    def broken(fd: int, mode: int) -> None:
        raise OSError(errno.EIO, os.strerror(errno.EIO))

    monkeypatch.setattr(aw.os, "fchmod", broken)
    with pytest.raises(OSError):
        aw.atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "old"
    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]
