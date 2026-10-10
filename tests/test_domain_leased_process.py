"""Synthetic leased lifecycle integration; native platforms must run their own CI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Any

import psutil
import pytest

from kuma_core.kuro.domain_lease import EXECUTION_RECORD_NAME
from kuma_core.kuro.domain_process import DomainProcessCancelled, DomainProcessError, run_managed_process
from kuma_core.kuro.optional_runtime import OptionalRuntimeError, OptionalRuntimeManager
from tests.test_domain_process import _argv, _assert_gone, child  # noqa: F401
from tests.test_optional_runtime import setup_runtime


@pytest.mark.parametrize("mode", ["success", "parent_exit", "tree", "sleep"])
def test_leased_run_releases_admission_only_after_exact_helper_exit(child, tmp_path: Path, mode: str) -> None:
    manager = OptionalRuntimeManager(tmp_path.resolve() / "app")
    manager._create_root()
    with manager.operation_lock() as lease:
        arguments: dict[str, Any] = dict(cwd=child[0].parent, result_path=child[1], operation_lease=lease,
                         cancelled=lambda: mode == "tree" and child[2].with_name("descendant.pid").exists(),
                         timeout_seconds=.7 if mode == "sleep" else 8)
        if mode == "tree":
            with pytest.raises(DomainProcessCancelled):
                run_managed_process(_argv(child, mode), **arguments)
        elif mode == "sleep":
            with pytest.raises(DomainProcessError, match="time limit"):
                run_managed_process(_argv(child, mode), **arguments)
        else:
            run_managed_process(_argv(child, mode), **arguments)
        record = json.loads((manager.root / EXECUTION_RECORD_NAME).read_text())
        assert record["state"] == "terminal" and record["tree_exited"] is True
        assert not psutil.pid_exists(record["helper"]["pid"])
        with pytest.raises(OptionalRuntimeError, match="in progress"):
            with manager.operation_lock():
                raise AssertionError("Host still holds primary lock")
    with manager.operation_lock():
        assert not (manager.root / EXECUTION_RECORD_NAME).exists()
    if mode != "sleep":
        _assert_gone(child, descendant=mode in {"tree", "parent_exit"})
    elif child[2].exists():
        _assert_gone(child)


def test_pre_spawn_record_quarantines_all_registry_mutations(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager._create_root()
    with manager.operation_lock() as lease:
        lease.prepare()  # Crash at this point: no child exists, but no proof exists either.
    before = (manager.root / EXECUTION_RECORD_NAME).read_bytes()
    for operation in (lambda: manager.install(archive), manager.remove, manager.cleanup_interrupted):
        with pytest.raises(OptionalRuntimeError, match="unconfirmed"):
            operation()
        assert (manager.root / EXECUTION_RECORD_NAME).read_bytes() == before
    with pytest.raises(OptionalRuntimeError, match="unconfirmed"):
        with manager.operation_lock():
            raise AssertionError("New execution was incorrectly admitted")


def test_hard_host_loss_cannot_admit_operation_while_helper_cleanup_is_paused(child, tmp_path: Path) -> None:
    # Isolated controller adopts/reaps Linux synthetic orphans. The host itself
    # is not a subreaper. macOS init and Windows kernel own orphan exit cleanup.
    source = textwrap.dedent('''
        import json, os, pathlib, signal, subprocess, sys, time
        sys.path.insert(0, sys.argv[1])
        import psutil
        from kuma_core.kuro import domain_process as process
        from kuma_core.kuro.domain_lease import EXECUTION_RECORD_NAME
        from kuma_core.kuro.optional_runtime import OptionalRuntimeManager, OptionalRuntimeError
        repo, app, script, work, result, marker, host_source = sys.argv[1:]
        manager = OptionalRuntimeManager(pathlib.Path(app))
        manager._create_root()
        marker = pathlib.Path(marker)
        record_path = manager.root / EXECUTION_RECORD_NAME
        host, helper = None, None
        helper_pid = None
        if sys.platform == 'linux':
            process._Subreaper.acquire()
        def wait_for(probe, seconds=12):
            deadline = time.monotonic() + seconds
            while not probe():
                assert time.monotonic() < deadline, 'Synthetic readiness/exit timed out'
                time.sleep(.01)
        try:
            host = subprocess.Popen([sys.executable, '-I', '-c', host_source,
                                     repo, app, script, work, result, str(marker)],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            wait_for(marker.with_name('descendant.pid').exists)
            record = json.loads(record_path.read_text())
            assert record['state'] == 'running'
            helper_pid = record['helper']['pid']
            helper = psutil.Process(helper_pid)
            helper.suspend()  # Deliberately expose the old unlocked cleanup gap.
            host.kill()
            assert host.wait(timeout=5) != 0
            for unused in range(5):
                try:
                    with manager.operation_lock():
                        raise AssertionError('Host death incorrectly admitted another operation')
                except OptionalRuntimeError:
                    pass
                assert json.loads(record_path.read_text())['state'] == 'running'
                time.sleep(.02)
            helper.resume()
            reaped = []
            def helper_done():
                if sys.platform == 'linux':
                    pid, status = os.waitpid(helper_pid, os.WNOHANG)
                    if pid:
                        reaped.append(status)
                    return bool(reaped)
                return not psutil.pid_exists(helper_pid)
            wait_for(helper_done)
            if reaped:
                assert os.waitstatus_to_exitcode(reaped[0]) == 0
            for path in (marker, marker.with_name('descendant.pid')):
                assert not psutil.pid_exists(int(path.read_text()))
            assert json.loads(record_path.read_text())['state'] == 'terminal'
            with manager.operation_lock():
                assert not record_path.exists()
            print(json.dumps({'host_loss_excluded_admission': True, 'tree_exited': True,
                              'exact_helper_exited_before_admission': True}))
        finally:
            if host is not None and host.poll() is None:
                host.kill(); host.wait(timeout=5)
            if helper is not None:
                try: helper.resume()
                except psutil.NoSuchProcess: pass
            pids = [helper_pid] if helper_pid else []
            for path in (marker, marker.with_name('descendant.pid')):
                if path.exists(): pids.append(int(path.read_text()))
            for pid in pids:
                try: psutil.Process(pid).kill()
                except psutil.NoSuchProcess: pass
            if sys.platform == 'linux':
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try: pid, status = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError: break
                    if not pid: time.sleep(.01)
                process._Subreaper.release()
            if host is not None and host.stderr is not None: host.stderr.close()
    ''')
    host_source = textwrap.dedent('''
        import pathlib, sys
        sys.path.insert(0, sys.argv[1])
        from kuma_core.kuro.domain_process import run_managed_process
        from kuma_core.kuro.optional_runtime import OptionalRuntimeManager
        repo, app, script, work, result, marker = sys.argv[1:]
        manager = OptionalRuntimeManager(pathlib.Path(app))
        with manager.operation_lock() as lease:
            run_managed_process([sys.executable, '-I', '-S', script, 'tree', result, marker],
                                cwd=pathlib.Path(work), result_path=pathlib.Path(result),
                                cancelled=lambda: False, operation_lease=lease)
        raise AssertionError('Host was expected to die')
    ''')
    completed = subprocess.run([sys.executable, "-I", "-c", source,
                                str(Path(__file__).resolve().parents[1]), str(tmp_path.resolve() / "app"),
                                str(child[0]), str(child[0].parent), str(child[1]), str(child[2]), host_source],
                               capture_output=True, text=True, timeout=35)
    assert completed.returncode == 0, completed.stderr
    assert all(json.loads(completed.stdout).values())
    _assert_gone(child, descendant=True)


@pytest.mark.skipif(os.name != "nt", reason="Atomic native JOB_LIST rejection requires Windows CI")
def test_windows_job_list_failure_has_no_create_then_assign_fallback(child, tmp_path, monkeypatch) -> None:
    import ctypes
    from kuma_core.kuro import domain_process as process
    real = process._windows_api()
    created: list[bool] = []

    class Api:
        def __getattr__(self, name):
            return getattr(real, name)

        def UpdateProcThreadAttribute(self, attributes, flags, attribute, *args):
            if attribute == 0x2000D:
                ctypes.set_last_error(87)
                return 0
            return real.UpdateProcThreadAttribute(attributes, flags, attribute, *args)

        def CreateProcessW(self, *args):
            created.append(True)
            raise AssertionError("CreateProcess must not run after failed atomic job attribute")

        def AssignProcessToJobObject(self, *args):
            raise AssertionError("Create-then-assign fallback is forbidden")

    monkeypatch.setattr(process, "_windows_api", Api)
    manager = OptionalRuntimeManager(tmp_path.resolve() / "app")
    manager._create_root()
    with manager.operation_lock() as lease:
        with pytest.raises(DomainProcessError, match="Cannot start"):
            run_managed_process(_argv(child, "success"), cwd=child[0].parent,
                                result_path=child[1], cancelled=lambda: False, operation_lease=lease)
    assert not created and not child[1].exists() and not child[2].exists()
    with manager.operation_lock():
        assert not (manager.root / EXECUTION_RECORD_NAME).exists()
