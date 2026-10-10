"""Bounded watchdog protocol/ordering tests; mocks do not prove native Win32."""
from __future__ import annotations

import ctypes
import importlib.util
import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys
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


def test_windows_source_helper_bypasses_venv_redirector_without_mutating_runtime_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    launcher, base = tmp_path / "venv python.exe", tmp_path / "base python.exe"
    launcher.write_bytes(b"fixture")
    base.write_bytes(b"fixture")
    private = {"PATH": "private-empty-path", "SystemRoot": "trusted-os-path"}
    monkeypatch.setenv("PYTHONPATH", "ambient-value-must-not-enter-helper")
    monkeypatch.setattr(watchdog, "os", SimpleNamespace(name="nt", path=os.path))
    monkeypatch.setattr(watchdog, "sys", SimpleNamespace(executable=str(launcher), _base_executable=str(base)))
    executable, helper_env = watchdog._helper_interpreter(private)
    assert executable == str(base)
    assert helper_env == {**private, "__PYVENV_LAUNCHER__": str(launcher)}
    assert helper_env is not private
    assert "__PYVENV_LAUNCHER__" not in private and "PYTHONPATH" not in helper_env


@pytest.mark.parametrize("frozen,platform_name", [(True, "nt"), (False, "posix")])
def test_frozen_or_nonwindows_helper_preserves_interpreter_and_environment(
    monkeypatch: pytest.MonkeyPatch, frozen: bool, platform_name: str,
) -> None:
    monkeypatch.setattr(watchdog, "os", SimpleNamespace(name=platform_name))
    monkeypatch.setattr(watchdog, "sys", SimpleNamespace(
        executable="trusted-frozen-or-posix", frozen=frozen, _base_executable="do-not-use"))
    original = {"PATH": "private"}
    executable, copied = watchdog._helper_interpreter(original)
    assert executable == "trusted-frozen-or-posix" and copied == original and copied is not original


def test_same_windows_interpreter_uses_case_normalized_comparison(monkeypatch: pytest.MonkeyPatch) -> None:
    paths = SimpleNamespace(isabs=ntpath.isabs, isfile=lambda path: True, normcase=ntpath.normcase)
    monkeypatch.setattr(watchdog, "os", SimpleNamespace(name="nt", path=paths))
    monkeypatch.setattr(watchdog, "sys", SimpleNamespace(
        executable=r"C:\Python\python.exe", _base_executable=r"c:\python\PYTHON.EXE"))
    executable, env = watchdog._helper_interpreter({})
    assert executable == r"C:\Python\python.exe" and env == {}


@pytest.mark.parametrize("base", [None, "", "relative.exe", "bad\0path"])
def test_windows_helper_refuses_unestablished_base_interpreter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, base: str | None,
) -> None:
    launcher = tmp_path / "python.exe"
    launcher.write_bytes(b"fixture")
    monkeypatch.setattr(watchdog, "os", SimpleNamespace(name="nt", path=os.path))
    monkeypatch.setattr(watchdog, "sys", SimpleNamespace(executable=str(launcher), _base_executable=base))
    with pytest.raises(RuntimeError, match="trusted Windows helper"):
        watchdog._helper_interpreter({})


def test_windows_helper_refuses_missing_base_executable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    launcher = tmp_path / "python.exe"
    launcher.write_bytes(b"fixture")
    monkeypatch.setattr(watchdog, "os", SimpleNamespace(name="nt", path=os.path))
    monkeypatch.setattr(watchdog, "sys", SimpleNamespace(
        executable=str(launcher), _base_executable=str(tmp_path / "missing.exe")))
    with pytest.raises(RuntimeError, match="trusted Windows helper"):
        watchdog._helper_interpreter({})


def test_redirector_child_identity_cannot_weaken_exact_ready_pid_guard() -> None:
    helper: Any = object.__new__(watchdog.WindowsLeaseWatchdog)
    helper.token = "f" * 64
    helper.ready = False
    helper.lease = SimpleNamespace(root_id=(1, 2))
    helper.process = SimpleNamespace(pid=123)
    message = {"version": 1, "token": helper.token, "type": "ready",
               "lease": {"token": helper.token, "root_dev": 1, "root_ino": 2},
               "helper": {"pid": 124, "created": 1234.0}}
    with pytest.raises(ValueError, match="ownership was not established"):
        helper._accept(json.dumps(message).encode("ascii"))
    assert helper.ready is False


@pytest.mark.skipif(os.name == "nt", reason="Non-Windows negative control only; native venv probe has its own CI gate")
def test_native_venv_probe_refuses_nonwindows_without_cleanup_claim(tmp_path: Path) -> None:
    path = Path(__file__).resolve().parents[1] / "scripts/domain_runtime_smoke/windows_venv_probe.py"
    report_path = tmp_path / "native.json"
    completed = subprocess.run([sys.executable, "-I", str(path), "--report", str(report_path)],
                               capture_output=True, timeout=10)
    assert completed.returncode == 1 and completed.stderr == b""
    report = json.loads(report_path.read_text())
    assert report["schema"] == "kuma-windows-venv-domain-contract-v1"
    assert report["status"] == "failed" and report["stage"] == "validate_host"
    assert report["checks"] == {} and report["cleanup_verified"] is False
    assert len(report_path.read_bytes()) < 16384
    assert all(set(json.loads(line)) == {"schema", "stage"} for line in completed.stdout.splitlines())


@pytest.mark.parametrize("failure_stage", ["raw_redirector", "leased_source_lifecycle"])
def test_native_probe_preserves_workspace_when_child_cleanup_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_stage: str,
) -> None:
    path = Path(__file__).resolve().parents[1] / "scripts/domain_runtime_smoke/windows_venv_probe.py"
    spec = importlib.util.spec_from_file_location("native_venv_negative_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    original_path = list(sys.path)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
    work = tmp_path / "keep workspace"
    work.mkdir()
    marker = work / "unverified-child-cwd"
    marker.write_text("preserve")
    monkeypatch.setattr(module, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(module, "sys", SimpleNamespace(
        version_info=(3, 11, 9), prefix="venv", base_prefix="base", executable="venv-python"))
    monkeypatch.setattr(module.psutil, "__version__", "7.2.2")
    monkeypatch.setattr(module.tempfile, "mkdtemp", lambda **kwargs: str(work))
    monkeypatch.setattr(module.domain_process, "_environment", lambda private: {})

    def timeout(*args):
        raise subprocess.TimeoutExpired("owned-redirector", 10)

    if failure_stage == "raw_redirector":
        monkeypatch.setattr(module, "_interpreter_probe", timeout)
    else:
        topology = iter([{"popen_pid_matches_python": False}, {"popen_pid_matches_python": True}])
        monkeypatch.setattr(module, "_interpreter_probe", lambda *args: next(topology))
        monkeypatch.setattr(module.domain_watchdog, "_helper_interpreter", lambda env: ("direct-base", dict(env)))
        monkeypatch.setattr(module, "_source_lifecycle", lambda: {
            "status": "failed", "stage": "cancel", "checks": {"success": {"passed": True}},
            "temporary_files_removed": False, "error": "DO_NOT_FORWARD_PRIVATE_PATH",
            "cleanup_error": "DO_NOT_FORWARD_PRIVATE_DIAGNOSTIC"})
    report = module.run_probe(tmp_path / "native.json")
    assert report["status"] == "failed" and report["stage"] == failure_stage
    assert report["cleanup_verified"] is False and report["private_workspace_removed"] is False
    assert marker.read_text() == "preserve"
    if failure_stage == "leased_source_lifecycle":
        assert report["lifecycle_outcome"] == {"stage": "cancel", "passed": False,
            "temporary_files_removed": False, "error_present": True, "cleanup_error_present": True}
        assert "DO_NOT_FORWARD" not in (tmp_path / "native.json").read_text()
