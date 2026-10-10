"""Bounded watchdog protocol/ordering tests; mocks do not prove native Win32."""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from kuma_core.kuro import domain_watchdog as watchdog


@pytest.mark.parametrize("chunks,expected", [
    ([b""], (False, True)), ([None, b"S", None, b""], (True, True)),
    ([b"X"], (False, False)), ([b"SS"], (False, False)),
    ([b"S", b"S"], (False, False)), ([b"S", b"X"], (False, False)),
])
def test_control_is_bounded_and_accepts_only_one_finished_marker(
    monkeypatch: pytest.MonkeyPatch, chunks: list[bytes | None], expected: tuple[bool, bool],
) -> None:
    incoming = iter(chunks)
    monkeypatch.setattr(watchdog, "_read_pipe", lambda api, fd: next(incoming))
    monkeypatch.setattr(watchdog.time, "sleep", lambda seconds: None)
    assert watchdog._wait_lifetime(None, 0) == expected


@pytest.mark.parametrize("normal,valid", [(False, True), (True, True), (False, False)])
def test_terminal_proof_requires_no_remaining_creator_then_empty_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, normal: bool, valid: bool,
) -> None:
    events: list[Any] = []
    calls = 0

    class Api:
        def GetCurrentProcess(self):
            return 123

        def IsProcessInJob(self, process, job, member):
            member._obj.value = 0
            return 1

        def WaitForSingleObject(self, handle, milliseconds):
            nonlocal calls
            assert handle == 99
            calls += 1
            events.append(("parent", calls))
            return 258 if calls == 1 else 0

        def TerminateJobObject(self, handle, code):
            assert handle == 88
            events.append(("terminate", calls))
            return 1

        def QueryInformationJobObject(self, handle, kind, accounting, size, unused):
            events.append(("query", calls))
            accounting._obj.active = 0
            return 1

        def CloseHandle(self, handle):
            events.append(("close", handle))
            return 1

    class Held:
        helper = {"pid": 123, "created": 12.0}
        root_id = (1, 2)

        def complete(self):
            events.append("terminal")

        def close(self):
            events.append("lease_closed")

    class Writer:
        def __init__(self, *args):
            pass

        def send(self, kind, **fields):
            events.append(kind)

        def finish(self):
            events.append("flushed")

    monkeypatch.setattr(watchdog, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(watchdog, "sys", SimpleNamespace(
        stdin=SimpleNamespace(fileno=lambda: 0), stdout=SimpleNamespace(fileno=lambda: 1)))
    monkeypatch.setattr(watchdog, "_api", Api)
    monkeypatch.setattr(watchdog, "_StatusWriter", Writer)
    monkeypatch.setattr(watchdog, "_read_config", lambda path: {})
    monkeypatch.setattr(watchdog, "_lease_module", lambda: SimpleNamespace(
        HelperLease=SimpleNamespace(claim=lambda config, expected_token: Held())))
    monkeypatch.setattr(watchdog, "_wait_lifetime", lambda api, fd: (normal, valid))
    monkeypatch.setattr(watchdog.time, "sleep", lambda seconds: None)
    result = watchdog.watchdog_main("a" * 64, 88, 99, tmp_path / "config")
    assert result == (0 if valid else 2)
    assert calls == (2 if valid and not normal else 1)
    for iteration in range(1, calls + 1):
        assert events.index(("parent", iteration)) < events.index(("terminate", iteration))
        assert events.index(("terminate", iteration)) < events.index(("query", iteration))
    if valid:
        assert events.index(("query", calls)) < events.index("terminal") < events.index("complete")
        assert events.index("complete") < events.index("flushed") < events.index("lease_closed")
    else:
        assert "terminal" not in events and "complete" not in events


def test_config_refuses_links_special_or_oversized_files(tmp_path: Path) -> None:
    path = tmp_path / "config"
    path.write_text('{"token":"bounded"}')
    assert watchdog._read_config(path) == {"token": "bounded"}
    path.write_bytes(b"x" * (watchdog._LIMIT + 1))
    with pytest.raises(ValueError, match="configuration"):
        watchdog._read_config(path)
    path.unlink()
    path.mkdir()
    with pytest.raises(ValueError, match="configuration"):
        watchdog._read_config(path)
    path.rmdir()
    if os.name != "nt":
        target = tmp_path / "target"
        target.write_text("{}")
        path.symlink_to(target)
        with pytest.raises(ValueError, match="configuration"):
            watchdog._read_config(path)


def test_status_writer_handles_partial_writes_and_broken_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    written = bytearray()

    def partial(fd, value):
        written.extend(value[:7])
        return min(7, len(value))

    monkeypatch.setattr(watchdog.os, "write", partial)
    writer = watchdog._StatusWriter("b" * 64, 123)
    writer.send("complete", tree_exited=True)
    writer.finish()
    assert json.loads(written)["tree_exited"] is True
    assert writer.finished.is_set() and not writer.failed

    def broken(fd, value):
        raise BrokenPipeError()

    monkeypatch.setattr(watchdog.os, "write", broken)
    writer = watchdog._StatusWriter("b" * 64, 123)
    writer.send("complete", tree_exited=True)
    writer.finish()
    assert writer.reader_gone and not writer.failed


def test_status_writer_refuses_oversized_message() -> None:
    read_fd, write_fd = os.pipe()
    try:
        writer = watchdog._StatusWriter("c" * 64, write_fd)
        with pytest.raises(ValueError, match="limit"):
            writer.send("stopping", message="x" * 3000)
        writer.finish()
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_watchdog_abi_uses_fixed_width_fields() -> None:
    assert ctypes.sizeof(watchdog._DWORD) == ctypes.sizeof(watchdog._BOOL) == 4
    assert ctypes.sizeof(watchdog._Accounting) == 48
    assert ctypes.sizeof(watchdog._HANDLE) == ctypes.sizeof(ctypes.c_void_p)
