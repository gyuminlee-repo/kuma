"""Windows-only external JobObject/registry lease lifetime watchdog.

The watchdog is NOT a member of the runtime job. The host waits for a token-
bound READY after lease claim, before atomically creating the suspended runtime
in that job. EOF kills and queries the entire job before terminal lease proof.
An unexplained watchdog exit never permits admission: its nonterminal record
remains fail-closed. No stale-record repair or arbitrary command API lives here.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import queue
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kuma_core.kuro.domain_lease import ExecutionLease

WATCHDOG_FLAG = "--kuma-domain-watchdog"
_LIMIT = 8192
_POLL = .025
_DWORD = ctypes.c_uint32
_HANDLE = ctypes.c_void_p
_BOOL = ctypes.c_int32


def _lease_module() -> Any:
    if __package__:
        from . import domain_lease
    else:
        if not getattr(sys, "frozen", False):
            directory = str(Path(__file__).resolve().parent)
            if directory not in sys.path:
                sys.path.insert(0, directory)
        import domain_lease
    return domain_lease


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")] + [
        (name, _DWORD) for name in ("faults", "total", "active", "terminated")]


def _api() -> Any:
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "GetCurrentProcess": ([], _HANDLE),
        "DuplicateHandle": ([_HANDLE, _HANDLE, _HANDLE, ctypes.POINTER(_HANDLE), _DWORD, _BOOL, _DWORD], _BOOL),
        "CloseHandle": ([_HANDLE], _BOOL),
        "WaitForSingleObject": ([_HANDLE, _DWORD], _DWORD),
        "IsProcessInJob": ([_HANDLE, _HANDLE, ctypes.POINTER(_BOOL)], _BOOL),
        "PeekNamedPipe": ([_HANDLE, ctypes.c_void_p, _DWORD, ctypes.c_void_p,
                           ctypes.POINTER(_DWORD), ctypes.c_void_p], _BOOL),
        "TerminateJobObject": ([_HANDLE, _DWORD], _BOOL),
        "QueryInformationJobObject": ([_HANDLE, ctypes.c_int, ctypes.c_void_p, _DWORD, ctypes.c_void_p], _BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
    return api


def _check(ok: object) -> None:
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def _read_pipe(api: Any, fd: int) -> bytes | None:
    """None means no bytes yet; b'' means EOF. Works on native Python 3.11."""
    import msvcrt
    available = _DWORD()
    handle = msvcrt.get_osfhandle(fd)
    if not api.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
        if ctypes.get_last_error() == 109:  # ERROR_BROKEN_PIPE
            return b""
        _check(False)
    if not available.value:
        return None
    return os.read(fd, min(available.value, _LIMIT))


def _notify(callback: Callable[[str], None] | None, text: str) -> None:
    if callback is not None:
        try:
            callback(text[:512])
        except BaseException:
            pass


def _read_config(path: Path) -> dict[str, Any]:
    before = path.lstat()
    if (not path.is_absolute() or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or getattr(before, "st_file_attributes", 0) & 0x400 or not 0 < before.st_size <= _LIMIT):
        raise ValueError("Invalid watchdog lease configuration")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as stream:
        actual = os.fstat(stream.fileno())
        if ((actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns)
                != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                or not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1):
            raise ValueError("Watchdog configuration changed while opening")
        raw = stream.read(_LIMIT + 1)
        after, named = os.fstat(stream.fileno()), path.lstat()
        for checked in (after, named):
            if ((checked.st_dev, checked.st_ino, checked.st_size, checked.st_mtime_ns, checked.st_ctime_ns)
                    != (actual.st_dev, actual.st_ino, actual.st_size, actual.st_mtime_ns, actual.st_ctime_ns)):
                raise ValueError("Watchdog configuration changed while reading")
    if len(raw) != actual.st_size or len(raw) > _LIMIT:
        raise ValueError("Watchdog configuration exceeds its limit")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Invalid watchdog lease configuration")
    return result


class _StatusWriter:
    """At most four small messages; stalled stdout never blocks tree cleanup."""
    def __init__(self, token: str, fd: int):
        self.token, self.fd = token, fd
        self.queue: queue.Queue[bytes | None] = queue.Queue(maxsize=4)
        self.finished = threading.Event()
        self.failed = False
        self.reader_gone = False
        self.thread = threading.Thread(target=self._write, name="domain-lease-status", daemon=True)
        self.thread.start()

    def send(self, kind: str, **fields: object) -> None:
        raw = json.dumps({"version": 1, "token": self.token, "type": kind, **fields},
                         ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"
        if len(raw) > 2048:
            raise ValueError("Watchdog status exceeded its limit")
        self.queue.put_nowait(raw)

    def _write(self) -> None:
        try:
            while True:
                raw = self.queue.get()
                if raw is None:
                    return
                if self.reader_gone:
                    continue
                view = memoryview(raw)
                while view:
                    try:
                        count = os.write(self.fd, view)
                    except BrokenPipeError:
                        self.reader_gone = True
                        break
                    if count <= 0:
                        raise OSError("Watchdog status pipe made no progress")
                    view = view[count:]
        except BaseException:
            self.failed = True
        finally:
            self.finished.set()

    def finish(self) -> None:
        self.queue.put(None)
        self.finished.wait()  # Child tree already exited; lease still retained.
        if self.failed:
            raise OSError("Watchdog status transport failed")


class WindowsLeaseWatchdog:
    """Parent-side lifetime/ready/proof transport; owns no runtime processes."""
    def __init__(self, job_handle: int, lease: ExecutionLease, cwd: Path,
                 env: dict[str, str], callback: Callable[[str], None] | None):
        if os.name != "nt":
            raise RuntimeError("Windows lease watchdog requires native Windows")
        self.api = _api()
        self.lease, self.token, self.callback = lease, lease.token, callback
        self.ready = False
        self.confirmed = False
        self.problem: str | None = None
        self.buffer = bytearray()
        self.count = 0
        self.eof: set[str] = set()
        self.capture = bytearray()
        config = json.dumps(lease.to_config(), ensure_ascii=True, allow_nan=False).encode("ascii")
        if len(config) > _LIMIT:
            raise ValueError("Watchdog lease configuration exceeds its limit")
        fd, filename = tempfile.mkstemp(prefix="domain-lease-", suffix=".json", dir=cwd)
        self.config_path = Path(filename)
        with os.fdopen(fd, "wb") as stream:
            stream.write(config)
            stream.flush()
            os.fsync(stream.fileno())
        duplicated = _HANDLE()
        parent_handle = _HANDLE()
        current = self.api.GetCurrentProcess()
        try:
            _check(self.api.DuplicateHandle(current, job_handle, current, ctypes.byref(duplicated), 0, True, 2))
            # The real process handle pins identity and proves that a hard
            # host exit has finished before an empty job is called terminal.
            _check(self.api.DuplicateHandle(current, current, current, ctypes.byref(parent_handle),
                                            0x00100000, True, 0))  # SYNCHRONIZE only
            assert duplicated.value is not None and parent_handle.value is not None
            if getattr(sys, "frozen", False):
                command = [sys.executable, WATCHDOG_FLAG, self.token, str(duplicated.value), str(parent_handle.value), str(self.config_path)]
            else:
                command = [sys.executable, "-I", str(Path(__file__).resolve()),
                           WATCHDOG_FLAG, self.token, str(duplicated.value), str(parent_handle.value), str(self.config_path)]
            startup = subprocess.STARTUPINFO()
            startup.lpAttributeList = {"handle_list": [duplicated.value, parent_handle.value]}
            self.process = subprocess.Popen(
                command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, bufsize=0, close_fds=True, startupinfo=startup,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except BaseException:
            self.config_path.unlink(missing_ok=True)
            raise
        finally:
            for handle in (duplicated, parent_handle):
                if handle.value is not None:
                    self.api.CloseHandle(handle)

    def _accept(self, raw: bytes) -> None:
        message = json.loads(raw)
        if (not isinstance(message, dict) or message.get("version") != 1
                or message.get("token") != self.token):
            raise ValueError("Watchdog status identity mismatch")
        if message.get("type") == "ready" and not self.ready:
            helper = message.get("helper")
            expected = {"token": self.token, "root_dev": self.lease.root_id[0], "root_ino": self.lease.root_id[1]}
            if (message.get("lease") != expected or not isinstance(helper, dict)
                    or helper.get("pid") != self.process.pid
                    or _lease_module().psutil.Process(self.process.pid).create_time() != helper.get("created")):
                raise ValueError("Watchdog lease ownership was not established")
            self.ready = True
        elif message.get("type") == "stopping" and isinstance(message.get("message"), str):
            _notify(self.callback, message["message"])
        elif (message.get("type") == "complete" and self.ready and not self.confirmed
              and message.get("tree_exited") is True and message.get("lease_terminal") is True):
            self.confirmed = True
        else:
            raise ValueError("Invalid watchdog status")

    def poll(self) -> int | None:
        for name, stream in (("stdout", self.process.stdout), ("stderr", self.process.stderr)):
            if name in self.eof or stream is None:
                continue
            data = _read_pipe(self.api, stream.fileno())
            if data is None:
                continue
            if not data:
                self.eof.add(name)
                if name == "stdout" and self.buffer:
                    self.problem = "Watchdog closed with incomplete status"
                    self.request_stop()
                continue
            if name == "stderr":
                self.capture = (self.capture + data)[-2048:]
                continue
            self.count = min(_LIMIT + 1, self.count + len(data))
            if self.count > _LIMIT:
                self.problem = "Watchdog status exceeded its limit"
                self.buffer.clear()
                self.request_stop()
                continue
            self.buffer.extend(data)
            while b"\n" in self.buffer:
                line, _, tail = self.buffer.partition(b"\n")
                self.buffer = bytearray(tail)
                try:
                    self._accept(bytes(line))
                except Exception:
                    self.problem = "Invalid watchdog lease status"
                    self.request_stop()
        return self.process.poll()

    def wait_ready(self, cancelled: Callable[[], bool], timeout_seconds: float) -> None:
        deadline = time.monotonic() + timeout_seconds
        while True:
            code = self.poll()
            if self.problem or code is not None:
                raise RuntimeError(self.problem or "Watchdog exited before runtime launch")
            if self.ready:
                return
            if cancelled():
                raise RuntimeError("Cancelled before watchdog lease readiness")
            if time.monotonic() >= deadline:
                raise RuntimeError("Watchdog lease readiness exceeded its time limit")
            time.sleep(_POLL)

    def request_stop(self) -> None:
        if self.process.stdin is not None and not self.process.stdin.closed:
            # Only called when host-side runtime creation has returned or has
            # not started. EOF without this byte is a hard-loss path instead.
            try:
                self.process.stdin.write(b"S")
            except OSError:
                pass
            self.process.stdin.close()

    def exited_cleanly(self) -> bool:
        code = self.poll()
        return (not self.problem and not self.buffer and self.confirmed
                and code == 0 and self.eof == {"stdout", "stderr"})

    def wait_stopped(self) -> None:
        self.request_stop()
        start = time.monotonic()
        notified = False
        while True:
            try:
                if self.exited_cleanly():
                    return
            except BaseException:
                pass
            if not notified and time.monotonic() - start >= 5:
                notified = True
                _notify(self.callback, "Cleanup pending; runtime lease watchdog has not confirmed exit.")
            try:
                time.sleep(_POLL)
            except BaseException:
                pass

    def close(self) -> None:
        if not self.exited_cleanly():
            raise RuntimeError("Cannot release unconfirmed watchdog lease")
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()
        self.config_path.unlink(missing_ok=True)


def _wait_lifetime(api: Any, fd: int) -> tuple[bool, bool]:
    """Return (launch-finished, valid) only after EOF or invalid bounded bytes."""
    control = b""
    while True:
        incoming = _read_pipe(api, fd)
        if incoming == b"":
            return control == b"S", True
        if incoming is not None:
            if control or incoming != b"S":
                return False, False  # Duplicate, oversized or unknown marker.
            control = incoming
        time.sleep(_POLL)


def watchdog_main(token: str, job_handle: int, parent_handle: int, config_path: Path) -> int:
    if (os.name != "nt" or len(token) != 64 or any(char not in "0123456789abcdef" for char in token)
            or type(job_handle) is not int or job_handle <= 0
            or type(parent_handle) is not int or parent_handle <= 0):
        return 2
    api = _api()
    member = _BOOL()
    _check(api.IsProcessInJob(api.GetCurrentProcess(), job_handle, ctypes.byref(member)))
    if member.value:
        return 2  # The cleanup owner must never be in the job it terminates.
    # Claim cannot be skipped: a prepared record already exists before spawn.
    held = _lease_module().HelperLease.claim(_read_config(config_path), expected_token=token)
    writer = _StatusWriter(token, sys.stdout.fileno())
    writer.send("ready", helper=held.helper,
                lease={"token": token, "root_dev": held.root_id[0], "root_ino": held.root_id[1]})
    launch_finished, valid_control = _wait_lifetime(api, sys.stdin.fileno())
    notified = False
    while True:
        try:
            # Establish "no more creators" BEFORE the final termination and
            # accounting query. Checking parent exit after an empty query could
            # miss a process created between that query and the host's death.
            host_exited = api.WaitForSingleObject(parent_handle, 0) == 0
            _check(api.TerminateJobObject(job_handle, 1))
            accounting = _Accounting()
            _check(api.QueryInformationJobObject(job_handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None))
            # EOF can race an in-flight CreateProcess. No runtime creation
            # remains possible after the exact host handle is signaled. The
            # normal marker is sent only after host-side creation has ended.
            if accounting.active == 0 and (launch_finished or host_exited or not valid_control):
                break
        except BaseException:
            if not notified:
                notified = True
                writer.send("stopping", message="Cleanup pending; runtime JobObject exit is unconfirmed.")
        time.sleep(_POLL)
    if not valid_control:
        # No terminal record or status on malformed control, even if the job
        # was just emptied. Later admission stays quarantined. A live host
        # observes missing proof and retains its primary lock too.
        api.CloseHandle(job_handle)
        api.CloseHandle(parent_handle)
        held.close()
        return 2
    proof_notified = False
    while True:
        try:
            held.complete()
            break
        except BaseException:
            if not proof_notified:
                proof_notified = True
                writer.send("stopping", message="Cleanup proof pending; runtime execution guard remains held.")
            time.sleep(_POLL)
    writer.send("complete", tree_exited=True, lease_terminal=True)
    writer.finish()
    api.CloseHandle(job_handle)
    api.CloseHandle(parent_handle)
    held.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 6 or sys.argv[1] != WATCHDOG_FLAG:
        raise SystemExit(2)
    raise SystemExit(watchdog_main(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), Path(sys.argv[5])))
