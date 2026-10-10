"""Harmless synthetic processes only; native Windows runs in the next CI gate.

No runtime archive, weights, installs, network, or biological inference is used.
Linux passing does not establish the Win32 lifecycle or hard-parent-loss gate.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import threading
import time
from collections.abc import Callable

import psutil
import pytest

from kuma_core.kuro import domain_process as process
from kuma_core.kuro.domain_process import DomainProcessCancelled, DomainProcessError, run_managed_process


@pytest.fixture
def child(tmp_path: Path) -> tuple[Path, Path, Path]:
    work = tmp_path / "private work with spaces"
    work.mkdir()
    script = work / "synthetic child with spaces.py"
    script.write_text(textwrap.dedent('''
        import json, os, signal, subprocess, sys, time
        from pathlib import Path
        mode, result, marker = sys.argv[1:4]
        result, marker = Path(result), Path(marker)
        def mark_ready(path):
            temporary = path.with_name(path.name + ".ready")
            temporary.write_text(str(os.getpid()))
            temporary.replace(path)
        if mode == "descendant":
            if os.name != "nt":
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
            mark_ready(marker)
            while True:
                time.sleep(.05)
        mark_ready(marker)
        if mode in {"tree", "parent_exit", "nonzero_tree"}:
            descendant = marker.with_name("descendant.pid")
            subprocess.Popen([sys.executable, "-I", "-S", __file__, "descendant",
                              str(result), str(descendant)])
            while not descendant.exists():
                time.sleep(.01)
            if mode == "parent_exit":
                result.write_text('{"ok": true}')
                os._exit(0)
            if mode == "nonzero_tree":
                os._exit(7)
        if mode in {"sleep", "tree"}:
            while True:
                time.sleep(.05)
        elif mode == "output":
            while True:
                os.write(1, b"x" * 16384)
                os.write(2, b"y" * 16384)
        elif mode == "oversize":
            result.write_bytes(b"x" * 8192)
            time.sleep(30)
        elif mode == "late_output":
            os.write(1, b"x" * 8192)
            result.write_text('{"ok": true}')
        elif mode == "fifo":
            os.mkfifo(result)
            time.sleep(30)
        elif mode == "symlink":
            result.symlink_to(marker)
            time.sleep(30)
        elif mode == "hardlink":
            os.link(marker, result)
            time.sleep(30)
        elif mode == "env":
            result.write_text(json.dumps(dict(os.environ)))
        elif mode == "arguments":
            result.write_text(json.dumps(sys.argv[4:]))
        elif mode == "nonzero":
            sys.exit(13)
        elif mode == "missing":
            pass
        else:
            result.write_text('{"ok": true}')
    '''), encoding="utf-8")
    return script, work / "result.json", work / "root.pid"


def _argv(child: tuple[Path, Path, Path], mode: str) -> list[str]:
    script, result, marker = child
    return [sys.executable, "-I", "-S", str(script), mode, str(result), str(marker)]


def _run(child: tuple[Path, Path, Path], mode: str, *,
         cancelled: Callable[[], bool] = lambda: False,
         timeout: float = 5, output_limit: int = 1024 * 1024,
         result_limit: int = 8 * 1024 * 1024,
         on_stopping: Callable[[str], None] | None = None) -> None:
    script, result, _ = child
    run_managed_process(_argv(child, mode), cwd=script.parent, cancelled=cancelled,
                        timeout_seconds=timeout, output_limit=output_limit,
                        result_path=result, result_limit=result_limit, on_stopping=on_stopping)


def _wait_for(predicate: Callable[[], bool], seconds: float = 5) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= deadline:
            pytest.fail("Synthetic process did not reach the expected state")
        time.sleep(.01)


def _assert_gone(child: tuple[Path, Path, Path], *, descendant: bool = False) -> None:
    marker = child[2]
    markers = [marker, marker.with_name("descendant.pid")] if descendant else [marker]
    for path in markers:
        pid = int(path.read_text())
        assert not psutil.pid_exists(pid), f"Synthetic PID {pid} was not fully reaped"


def test_success_and_private_working_directory_cleanup(child: tuple[Path, Path, Path]) -> None:
    _run(child, "success")
    assert json.loads(child[1].read_text()) == {"ok": True}
    _assert_gone(child)
    assert not list(child[0].parent.glob("domain-private-*"))


def test_argument_boundaries_spaces_quotes_and_shell_metacharacters(child: tuple[Path, Path, Path]) -> None:
    arguments = ["", "space here", 'a"b', "trailing\\", "slashes\\\\\"quote", "; touch not-a-command", "$(echo nope)"]
    run_managed_process(_argv(child, "arguments") + arguments, cwd=child[0].parent,
                        cancelled=lambda: False, result_path=child[1])
    assert json.loads(child[1].read_text()) == arguments
    assert not (child[0].parent / "not-a-command").exists()
    _assert_gone(child)


def test_environment_is_private_cpu_only_and_does_not_inherit_loaders(
    child: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = ["PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH",
               "DYLD_INSERT_LIBRARIES", "VIRTUAL_ENV", "CONDA_PREFIX", "_PYI_APPLICATION_HOME_DIR",
               "PYINSTALLER_RESET_ENVIRONMENT", "KUMA_PRIVATE_SENTINEL"]
    for name in blocked:
        monkeypatch.setenv(name, "must-not-inherit")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1")
    _run(child, "env")
    env = json.loads(child[1].read_text())
    assert all(name not in env for name in blocked)
    assert env["CUDA_VISIBLE_DEVICES"] == env["HIP_VISIBLE_DEVICES"] == env["ROCR_VISIBLE_DEVICES"] == ""
    assert env["OMP_NUM_THREADS"] == env["MKL_NUM_THREADS"] == env["OPENBLAS_NUM_THREADS"] == "1"
    for name in ["PATH", "HOME", "TMP", "TEMP", "TMPDIR", "TORCH_HOME", "MPLCONFIGDIR"]:
        assert Path(env[name]).is_relative_to(child[0].parent)
        assert not Path(env[name]).exists()  # Private environment removed AFTER exit.


@pytest.mark.parametrize("mode,match", [
    ("missing", "did not write a result"),
    ("nonzero", "exited unsuccessfully"),
    ("nonzero_tree", "exited unsuccessfully"),
    ("output", "output limit"),
    ("late_output", "output limit"),
    ("oversize", "size limit"),
])
def test_failure_paths_reap_before_raising(child: tuple[Path, Path, Path], mode: str, match: str) -> None:
    with pytest.raises(DomainProcessError, match=match):
        _run(child, mode, output_limit=4096, result_limit=4096)
    _assert_gone(child, descendant=mode == "nonzero_tree")


@pytest.mark.parametrize("mode", ["fifo", "symlink", "hardlink"])
@pytest.mark.skipif(os.name == "nt", reason="POSIX special-file fixtures; Win32 reparse bit checked separately")
def test_special_result_is_rejected_without_blocking(child: tuple[Path, Path, Path], mode: str) -> None:
    with pytest.raises(DomainProcessError, match="regular file"):
        _run(child, mode)
    _assert_gone(child)


def test_timeout_reaps_owned_root_without_assuming_fixture_startup(
    child: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned_pids: list[int] = []
    if os.name == "nt":
        windows_start = process._WindowsProcess.start

        def record_windows(self: process._WindowsProcess) -> None:
            owned_pids.append(self.info.pid)
            windows_start(self)

        monkeypatch.setattr(process._WindowsProcess, "start", record_windows)
    else:
        posix_start = process._PosixSupervisor.start

        def record_posix(self: process._PosixSupervisor) -> None:
            owned_pids.append(self.process.pid)
            posix_start(self)

        monkeypatch.setattr(process._PosixSupervisor, "start", record_posix)
    with pytest.raises(DomainProcessError, match="time limit"):
        _run(child, "tree", timeout=.7)
    assert len(owned_pids) == 1 and not psutil.pid_exists(owned_pids[0])
    # Timeout includes startup and may legitimately fire before fixture code.
    # Reap every runtime PID that started, without pretending a descendant was
    # observed. The separate cancellation case explicitly waits for its ready
    # marker before testing stubborn-descendant termination.
    for marker in (child[2], child[2].with_name("descendant.pid")):
        if marker.exists():
            assert not psutil.pid_exists(int(marker.read_text()))


def test_parent_exits_first_with_inherited_pipes_and_stubborn_descendant(child: tuple[Path, Path, Path]) -> None:
    _run(child, "parent_exit")
    _assert_gone(child, descendant=True)


def test_cancellation_kills_tree_without_touching_unrelated_process(child: tuple[Path, Path, Path]) -> None:
    outsider = subprocess.Popen([sys.executable, "-I", "-S", "-c", "import time; time.sleep(30)"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    descendant = child[2].with_name("descendant.pid")
    try:
        with pytest.raises(DomainProcessCancelled):
            _run(child, "tree", cancelled=descendant.exists)
        _assert_gone(child, descendant=True)
        assert outsider.poll() is None
    finally:
        outsider.kill()
        outsider.wait(timeout=5)


def test_prelaunch_cancel_creates_no_process(child: tuple[Path, Path, Path]) -> None:
    with pytest.raises(DomainProcessCancelled):
        _run(child, "success", cancelled=lambda: True)
    assert not child[2].exists()


def test_stale_result_is_never_reused(child: tuple[Path, Path, Path]) -> None:
    child[1].write_text('{"old": true}')
    with pytest.raises(DomainProcessError, match="fresh"):
        _run(child, "success")
    assert not child[2].exists()


def test_callback_failure_cannot_abandon_process(child: tuple[Path, Path, Path]) -> None:
    def failing_callback(_text: str) -> None:
        raise RuntimeError("Synthetic notification failure")

    with pytest.raises(DomainProcessCancelled):
        _run(child, "sleep", cancelled=child[2].exists, on_stopping=failing_callback)
    _assert_gone(child)


def test_cancellation_probe_failure_still_cleans_up(child: tuple[Path, Path, Path]) -> None:
    def failing_probe() -> bool:
        if child[2].exists():
            raise ValueError("Synthetic cancellation callback failure")
        return False

    with pytest.raises(DomainProcessError, match="ValueError"):
        _run(child, "sleep", cancelled=failing_probe)
    _assert_gone(child)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission-error negative control")
def test_unknown_cleanup_keeps_caller_lock_and_never_reports_cancelled(
    child: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_available = threading.Event()
    pending = threading.Event()
    operation_lock = threading.Lock()
    outcomes: list[BaseException] = []
    notifications: list[str] = []
    actual_probe = process._PosixSupervisor.tree_exited

    def uncertain_probe(self: process._PosixSupervisor) -> bool:
        if not evidence_available.is_set():
            raise PermissionError("Synthetic probe denied")
        return actual_probe(self)

    def callback(message: str) -> None:
        notifications.append(message)
        if "Cleanup pending" in message:
            pending.set()

    def worker() -> None:
        try:
            with operation_lock:
                _run(child, "sleep", cancelled=child[2].exists, on_stopping=callback)
        except BaseException as exc:
            outcomes.append(exc)

    monkeypatch.setattr(process._PosixSupervisor, "tree_exited", uncertain_probe)
    monkeypatch.setattr(process, "_CLEANUP_NOTICE_SECONDS", .1)
    thread = threading.Thread(target=worker)
    thread.start()
    try:
        assert pending.wait(5)
        assert thread.is_alive() and operation_lock.locked()
        assert not outcomes
        assert 2 <= len(notifications) <= 4
        assert all(len(message) <= 512 for message in notifications)
    finally:
        evidence_available.set()
        thread.join(5)
    assert not thread.is_alive() and not operation_lock.locked()
    assert len(outcomes) == 1 and isinstance(outcomes[0], DomainProcessCancelled)
    _assert_gone(child)


@pytest.mark.skipif(os.name == "nt", reason="POSIX subreaper and group isolation")
def test_concurrent_managed_trees_do_not_steal_exit_statuses(tmp_path: Path) -> None:
    barrier = threading.Barrier(3)
    failures: list[BaseException] = []

    def worker(number: int) -> None:
        work = tmp_path / str(number)
        work.mkdir()
        result = work / "result.json"
        barrier.wait()
        try:
            run_managed_process([sys.executable, "-I", "-S", "-c",
                                 "import time,pathlib,sys;time.sleep(.15);pathlib.Path(sys.argv[1]).write_text('{}')",
                                 str(result)], cwd=work, cancelled=lambda: False, result_path=result)
        except BaseException as exc:
            failures.append(exc)

    threads = [threading.Thread(target=worker, args=(number,)) for number in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(5)
        assert not thread.is_alive()
    assert not failures
    if sys.platform == "linux":
        assert process._Subreaper._users == 0


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_limits_rejected_before_spawn(child: tuple[Path, Path, Path], timeout: float) -> None:
    with pytest.raises(DomainProcessError, match="limits"):
        _run(child, "success", timeout=timeout)
    assert not child[2].exists()


def test_capture_is_bounded_even_during_indefinite_cleanup() -> None:
    capture = process._Capture(50)
    for _ in range(1000):
        capture.feed(b"x" * 8192)
    assert capture.count == 51
    assert len(capture.tail) == process._TAIL_LIMIT


@pytest.mark.parametrize("change", [{"token": "0" * 64}, {"tree_exited": False},
                                   {"outcome": "running"}, {"version": 2}])
def test_supervisor_does_not_accept_unbound_or_unconfirmed_terminal_status(
    monkeypatch: pytest.MonkeyPatch, change: dict,
) -> None:
    supervisor = object.__new__(process._PosixSupervisor)
    supervisor.token = "1" * 64
    supervisor.terminal = None
    supervisor.problem = None
    supervisor.callback = None
    stops: list[bool] = []
    monkeypatch.setattr(supervisor, "stop", lambda hard: stops.append(hard))
    message = {"version": 1, "token": supervisor.token, "type": "complete",
               "tree_exited": True, "outcome": "ok", "message": "", **change}
    supervisor._accept(json.dumps(message).encode("ascii"))
    assert supervisor.terminal is None
    assert supervisor.problem == "Invalid or mismatched supervisor status"
    assert stops == [False]


@pytest.mark.skipif(os.name == "nt", reason="POSIX helper nonblocking status pipe")
def test_helper_status_survives_backpressure_and_partial_writes(tmp_path: Path) -> None:
    token = "2" * 64
    source = textwrap.dedent('''
        import os, runpy, sys
        m = runpy.run_path(sys.argv[1])
        real_write, attempts = os.write, 0
        def partial_write(fd, data):
            global attempts
            if fd == sys.stdout.fileno():
                attempts += 1
                if attempts <= 2:
                    raise BlockingIOError('Synthetic pipe backpressure')
                data = data[:64]
            return real_write(fd, data)
        os.write = partial_write
        raise SystemExit(m['supervisor_main'](sys.argv[2]))
    ''')
    # Invalid config proves no child was launched, while still exercising the
    # real bounded terminal transport through injected EAGAIN and short writes.
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", source, str(Path(process.__file__).resolve()), token],
        input=b"{}\n", stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
        cwd=tmp_path,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    report = json.loads(completed.stdout)
    assert report["token"] == token and report["type"] == "complete"
    assert report["tree_exited"] is True and report["outcome"] == "error"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux isolated subreaper/lifetime-pipe probes")
@pytest.mark.parametrize("scenario", ["host_loss", "unrelated_orphan"])
def test_posix_helper_isolates_reaping_and_survives_hard_host_loss(
    child: tuple[Path, Path, Path], scenario: str,
) -> None:
    # The outer test controller is itself a separate process and reaps every
    # synthetic orphan, even on container PID 1 implementations that do not.
    # The tested host starts WITHOUT subreaper status and must never enable it.
    host_source = textwrap.dedent('''
        import ctypes, json, os, pathlib, runpy, subprocess, sys, threading, time
        module, script, work, result, marker, scenario, controller = sys.argv[1:]
        work, result, marker = pathlib.Path(work), pathlib.Path(result), pathlib.Path(marker)
        m = runpy.run_path(module)
        library = ctypes.CDLL(None)
        library.prctl.argtypes = [ctypes.c_int]
        library.prctl.restype = ctypes.c_int
        def flag():
            value = ctypes.c_int()
            assert library.prctl(37, ctypes.byref(value), 0, 0, 0) == 0
            return value.value
        before = flag()
        original = m['_PosixSupervisor'].start
        def record_helper(self):
            (work / 'supervisor.pid').write_text(str(self.process.pid))
            original(self)
        m['_PosixSupervisor'].start = record_helper
        cancelled = threading.Event()
        failures = []
        def job():
            try:
                m['run_managed_process'](
                    [sys.executable, '-I', '-S', script, 'tree', str(result), str(marker)],
                    cwd=work, result_path=result, cancelled=cancelled.is_set)
            except m['DomainProcessCancelled']:
                pass
            except BaseException as exc:
                failures.append(str(exc))
        if scenario == 'host_loss':
            job()
            raise AssertionError('Host should have been killed by the controller')
        thread = threading.Thread(target=job)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not marker.with_name('descendant.pid').exists():
                assert time.monotonic() < deadline
                time.sleep(.01)
            orphan = work / 'unrelated.pid'
            grandchild = 'import os,pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(30)'
            parent_code = 'import subprocess,sys;subprocess.Popen([sys.executable,"-I","-S","-c",sys.argv[1],sys.argv[2]])'
            outsider = subprocess.Popen([sys.executable, '-I', '-S', '-c', parent_code, grandchild, str(orphan)])
            outsider.wait(timeout=5)
            while not orphan.exists():
                assert time.monotonic() < deadline
                time.sleep(.01)
            orphan_pid = int(orphan.read_text())
            status = pathlib.Path('/proc') / str(orphan_pid) / 'stat'
            ppid = int(status.read_text().rsplit(')', 1)[1].split()[1])
            during = flag()
        finally:
            cancelled.set()
            thread.join(10)
        assert not thread.is_alive() and not failures, failures
        after = flag()
        assert before == during == after == 0, (before, during, after)
        assert ppid == int(controller), (ppid, controller)
        (work / 'isolation.json').write_text(json.dumps({'host_flag_unchanged': True, 'unrelated_not_adopted': True}))
    ''')
    controller_source = textwrap.dedent('''
        import json, os, pathlib, runpy, signal, subprocess, sys, time
        module, script, work, result, marker, scenario, host_source = sys.argv[1:]
        work, result, marker = pathlib.Path(work), pathlib.Path(result), pathlib.Path(marker)
        m = runpy.run_path(module)
        m['_Subreaper'].acquire()  # Dedicated test controller only, never tested host.
        host = None
        def wait_for(predicate, seconds=8):
            deadline = time.monotonic() + seconds
            while not predicate():
                assert time.monotonic() < deadline, 'Synthetic state timed out'
                time.sleep(.01)
        try:
            host = subprocess.Popen([sys.executable, '-I', '-S', '-c', host_source,
                                     module, script, str(work), str(result), str(marker), scenario, str(os.getpid())])
            if scenario == 'host_loss':
                wait_for(marker.with_name('descendant.pid').exists)
                helper = int((work / 'supervisor.pid').read_text())
                host.kill()
                host.wait(timeout=5)
                reaped = []
                def helper_done():
                    pid, status = os.waitpid(helper, os.WNOHANG)
                    if pid:
                        reaped.append((pid, status))
                    return bool(reaped)
                wait_for(helper_done)
                assert os.waitstatus_to_exitcode(reaped[0][1]) == 0
                for path in (marker, marker.with_name('descendant.pid')):
                    pid = int(path.read_text())
                    assert not (pathlib.Path('/proc') / str(pid)).exists(), pid
                print(json.dumps({'hard_host_loss_cleaned_tree': True, 'helper_reaped': True}))
            else:
                assert host.wait(timeout=12) == 0
                report = json.loads((work / 'isolation.json').read_text())
                print(json.dumps(report))
        finally:
            if host is not None and host.poll() is None:
                host.kill()
                host.wait(timeout=5)
            for path in (marker, marker.with_name('descendant.pid'), work / 'supervisor.pid', work / 'unrelated.pid'):
                if path.exists():
                    try:
                        os.kill(int(path.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    pid, _ = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if not pid:
                    time.sleep(.01)
            m['_Subreaper'].release()
    ''')
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", controller_source,
         str(Path(process.__file__).resolve()), str(child[0]), str(child[0].parent),
         str(child[1]), str(child[2]), scenario, host_source],
        capture_output=True, text=True, timeout=25,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report and all(value is True for value in report.values())
    _assert_gone(child, descendant=True)


def test_win32_structures_have_explicit_pointer_width_and_fixed_integer_fields() -> None:
    assert ctypes.sizeof(process._DWORD) == 4
    assert ctypes.sizeof(process._BOOL) == 4
    assert ctypes.sizeof(process._HANDLE) == ctypes.sizeof(ctypes.c_void_p)
    assert ctypes.sizeof(process._Accounting) == 48
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(process._StartupInfo) == 104
        assert ctypes.sizeof(process._StartupInfoEx) == 112
        assert ctypes.sizeof(process._ProcessInformation) == 24
        assert ctypes.sizeof(process._ExtendedLimits) == 144


@pytest.mark.skipif(os.name != "nt", reason="Actual Win32 job assignment failure requires native Windows CI")
def test_windows_assignment_failure_never_resumes_child(
    child: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_assignment(self: process._WindowsProcess) -> None:
        raise OSError("Synthetic assignment failure while child is suspended")

    monkeypatch.setattr(process._WindowsProcess, "start", refuse_assignment)
    with pytest.raises(DomainProcessError, match="OSError"):
        _run(child, "success")
    assert not child[2].exists() and not child[1].exists()


@pytest.mark.skipif(os.name != "nt", reason="Actual suspended Win32 launch requires native Windows CI")
def test_windows_job_owns_child_before_resume(child: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    actual_start = process._WindowsProcess.start
    observed: list[bool] = []

    def inspect_suspended(self: process._WindowsProcess) -> None:
        time.sleep(.1)
        assert not child[2].exists()
        assert self.poll() is None
        actual_start(self)
        observed.append(self.assigned)

    monkeypatch.setattr(process._WindowsProcess, "start", inspect_suspended)
    _run(child, "success")
    assert observed == [True]
    _assert_gone(child)


@pytest.mark.skipif(os.name != "nt", reason="Actual Win32 assigned-but-suspended cleanup requires native Windows CI")
def test_windows_failure_after_assignment_kills_suspended_process(
    child: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse_resume(self: process._WindowsProcess) -> None:
        process._win_check(self.api.AssignProcessToJobObject(self.job, self.info.process))
        self.assigned = True
        raise OSError("Synthetic resume failure")

    monkeypatch.setattr(process._WindowsProcess, "start", refuse_resume)
    with pytest.raises(DomainProcessError, match="OSError"):
        _run(child, "success")
    assert not child[2].exists() and not child[1].exists()


@pytest.mark.skipif(os.name != "nt", reason="Actual JobObject kill-on-close requires native Windows CI")
def test_windows_hard_supervisor_loss_closes_job_and_kills_tree(child: tuple[Path, Path, Path]) -> None:
    # Separate host: os._exit/TerminateProcess closes its non-inherited job
    # handle. Run source directly to avoid depending on package import hooks.
    module_path = Path(process.__file__).resolve()
    supervisor_source = (
        "import pathlib,runpy,sys; "
        "m=runpy.run_path(sys.argv[1]); "
        "m['run_managed_process'](sys.argv[4:],cwd=pathlib.Path(sys.argv[2]),"
        "result_path=pathlib.Path(sys.argv[3]),cancelled=lambda:False)"
    )
    supervisor = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", supervisor_source,
         str(module_path), str(child[0].parent), str(child[1]), *_argv(child, "tree")],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    descendant = child[2].with_name("descendant.pid")
    try:
        _wait_for(descendant.exists)
        supervisor.kill()
        supervisor.wait(timeout=5)
        pids = [int(marker.read_text()) for marker in (child[2], descendant)]
        _wait_for(lambda: all(not psutil.pid_exists(pid) for pid in pids))
        _assert_gone(child, descendant=True)
    finally:
        if supervisor.poll() is None:
            supervisor.kill()
            supervisor.wait(timeout=5)
        # The failure path cannot leave harmless synthetic children behind.
        for marker in (child[2], descendant):
            if marker.exists():
                try:
                    psutil.Process(int(marker.read_text())).kill()
                except psutil.NoSuchProcess:
                    pass
