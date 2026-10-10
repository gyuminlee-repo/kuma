"""Lifecycle boundary for a verified, optional CPU-only domain executable.

The caller must hold its runtime operation lock and supply a trusted absolute
executable from the verified manifest. This is not an arbitrary-command API or
a security sandbox. POSIX runtimes must not daemonize/escape their session.
No ``preexec_fn`` or signal handlers are installed in the threaded sidecar.

Normal shutdown must cancel and WAIT for this function. Unknown termination
keeps this function, its private directory and the caller's lock alive, with a
bounded cleanup-pending notification. Windows atomically creates the suspended
runtime inside a kill-on-close Job Object, then resumes; descendants cannot
break away. A leased run has an external watchdog owning a second job handle.

POSIX uses a dedicated single-job helper: only that process becomes a Linux
subreaper. The shared sidecar's subreaper state is untouched. Its private stdin
lifetime pipe requests group termination/reaping on hard sidecar loss. The
runtime itself receives closed stdin, separate from this lifetime channel.
Managed jobs hand off a durable nonterminal execution record before spawning.
The POSIX helper retains the primary flock; the Windows watchdog holds a
separate admission guard. All new operations require terminal tree proof AND
exact helper exit, including after hard sidecar loss. Helper/combined loss
without proof leaves a fail-closed record; automatic recovery is not provided.
Real frozen runtime/helper crash and native platform evidence remain required
before production catalog activation. Flags request CPU-only execution; the
trusted runtime must honor --device cpu, including on Metal-capable systems.
Hard sidecar loss can leave private input/work directories behind. The helper
never recursively deletes a caller-supplied cwd; crash-leftover reclamation is
not established. Normal caller-owned TemporaryDirectory cleanup is preserved.

Result size is polled and checked after exit, not an OS-enforced disk quota.
The caller must still perform a stable bounded safe-read and validate the result.
"""
from __future__ import annotations

import ctypes
import json
import math
import os
from pathlib import Path
import selectors
import secrets
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from kuma_core.kuro.domain_lease import ExecutionLease, OperationLease


def _lease_module() -> Any:
    # The source helper is launched with -I. Load only adjacent trusted app
    # code, not a working-directory/PYTHONPATH module. Frozen minimal probes
    # bundle these same modules as top-level aliases.
    if __package__:
        from . import domain_lease
    else:
        if not getattr(sys, "frozen", False):
            own_directory = str(Path(__file__).resolve().parent)
            if own_directory not in sys.path:
                sys.path.insert(0, own_directory)
        import domain_lease
    return domain_lease


def _watchdog_module() -> Any:
    if __package__:
        from . import domain_watchdog
    else:
        if not getattr(sys, "frozen", False):
            directory = str(Path(__file__).resolve().parent)
            if directory not in sys.path:
                sys.path.insert(0, directory)
        import domain_watchdog
    return domain_watchdog

_POLL_SECONDS = 0.025
_TERM_GRACE_SECONDS = 0.25
_CLEANUP_NOTICE_SECONDS = 5.0
_CHUNK = 16 * 1024
_TAIL_LIMIT = 2048
_CONFIG_LIMIT = 64 * 1024
_PROTOCOL_LIMIT = 16 * 1024
_SUPERVISOR_FLAG = "--kuma-domain-supervisor"


class DomainProcessError(RuntimeError):
    """Execution failed, after the launched process tree has fully exited."""


class DomainProcessCancelled(DomainProcessError):
    """Cancellation acknowledged only after confirmed tree termination."""


class _Capture:
    def __init__(self, limit: int):
        self.limit = limit
        self.count = 0
        self.tail = b""

    def feed(self, data: bytes) -> None:
        # Saturate the counter too: indefinite cleanup never grows diagnostics.
        self.count = min(self.limit + 1, self.count + len(data))
        self.tail = (self.tail + data)[-_TAIL_LIMIT:]

    @property
    def exceeded(self) -> bool:
        return self.count > self.limit


class _Process(Protocol):
    def start(self) -> None: ...
    def poll(self) -> int | None: ...
    def drain(self, capture: _Capture) -> None: ...
    def tree_exited(self) -> bool: ...
    def stop(self, hard: bool) -> None: ...
    def close(self) -> None: ...


class _Subreaper:
    """Only used inside the dedicated, single-job POSIX helper process.

    Never enable this flag in the shared sidecar: orphan adoption is process-wide
    and cannot be undone just by restoring the flag. macOS uses launchd reaping.
    """
    _lock = threading.Lock()
    _users = 0
    _previous = 0
    _library: ctypes.CDLL | None = None

    @classmethod
    def acquire(cls) -> None:
        if sys.platform != "linux":
            return
        with cls._lock:
            if cls._users == 0:
                library = ctypes.CDLL(None, use_errno=True)
                library.prctl.argtypes = [ctypes.c_int]
                library.prctl.restype = ctypes.c_int
                previous = ctypes.c_int()
                if library.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:
                    raise OSError(ctypes.get_errno(), "Cannot inspect child subreaper")
                if library.prctl(36, 1, 0, 0, 0) != 0:
                    raise OSError(ctypes.get_errno(), "Cannot enable child subreaper")
                cls._previous, cls._library = previous.value, library
            cls._users += 1

    @classmethod
    def release(cls) -> None:
        if sys.platform != "linux":
            return
        with cls._lock:
            cls._users -= 1
            if cls._users == 0 and cls._library is not None:
                if cls._library.prctl(36, cls._previous, 0, 0, 0) != 0:
                    raise OSError(ctypes.get_errno(), "Cannot restore child subreaper")
                cls._library = None


class _PosixChild:
    def __init__(self, argv: list[str], cwd: Path, env: dict[str, str]):
        self.selector = selectors.DefaultSelector()
        self.process: subprocess.Popen[bytes] | None = None
        self.group_gone = False
        _Subreaper.acquire()
        try:
            self.process = subprocess.Popen(
                argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                shell=False, start_new_session=True, close_fds=True,
            )
        except BaseException:
            self.selector.close()
            _Subreaper.release()
            raise

    def start(self) -> None:
        assert self.process is not None
        for stream in (self.process.stdout, self.process.stderr):
            assert stream is not None
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ)

    def poll(self) -> int | None:
        assert self.process is not None
        return self.process.poll()

    def drain(self, capture: _Capture) -> None:
        # Bounded work per poll even when a descendant writes continuously.
        for key, _ in self.selector.select(0):
            try:
                data = os.read(key.fd, _CHUNK)
            except BlockingIOError:
                continue
            if data:
                capture.feed(data)
            else:
                self.selector.unregister(key.fileobj)

    def tree_exited(self) -> bool:
        assert self.process is not None
        # Reap root through Popen first, so group wait cannot consume its status.
        if self.process.poll() is None:
            return False
        if self.group_gone:
            return not self.selector.get_map()
        while True:
            try:
                pid, _ = os.waitpid(-self.process.pid, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                break
        try:
            os.killpg(self.process.pid, 0)
        except ProcessLookupError:
            # Inherited open pipes can expose a descendant outside the group.
            # Never claim it is dead, even if the trusted-runtime contract broke.
            self.group_gone = True
            return not self.selector.get_map()
        return False  # EPERM is propagated, never interpreted as absence.

    def stop(self, hard: bool) -> None:
        assert self.process is not None
        if self.group_gone:
            return
        try:
            os.killpg(self.process.pid, signal.SIGKILL if hard else signal.SIGTERM)
        except ProcessLookupError:
            pass

    def close(self) -> None:
        assert self.process is not None
        self.selector.close()
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()
        _Subreaper.release()


class _PosixSupervisor:
    """Private helper owns reaping; stdin EOF is the sidecar lifetime signal."""
    def __init__(self, argv: list[str], cwd: Path, env: dict[str, str], *,
                 timeout_seconds: float, output_limit: int, result_path: Path,
                 result_limit: int, callback: Callable[[str], None] | None,
                 lease: ExecutionLease | None = None):
        self.token = lease.token if lease is not None else secrets.token_hex(32)
        self.callback = callback
        self.terminal: dict | None = None
        self.problem: str | None = None
        self.protocol = bytearray()
        self.protocol_count = 0
        config = {"version": 1, "token": self.token, "argv": argv, "cwd": str(cwd),
                  "environment": env, "timeout_seconds": timeout_seconds,
                  "output_limit": output_limit, "result_path": str(result_path),
                  "result_limit": result_limit,
                  "lease": None if lease is None else lease.to_config()}
        self.outgoing = bytearray(json.dumps(config, ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n")
        if len(self.outgoing) > _CONFIG_LIMIT:
            raise DomainProcessError("Managed domain supervisor configuration exceeds its limit")
        if getattr(sys, "frozen", False):
            command = [sys.executable, _SUPERVISOR_FLAG, self.token]
        else:
            command = [sys.executable, "-I", str(Path(__file__).resolve()), _SUPERVISOR_FLAG, self.token]
        self.selector = selectors.DefaultSelector()
        try:
            self.process = subprocess.Popen(
                command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, bufsize=0, start_new_session=True, close_fds=True,
                pass_fds=() if lease is None else (lease.primary_fd,),
            )
        except BaseException:
            self.selector.close()
            raise

    def start(self) -> None:
        assert self.process.stdin is not None
        os.set_blocking(self.process.stdin.fileno(), False)
        for stream, name in ((self.process.stdout, "protocol"), (self.process.stderr, "diagnostic")):
            assert stream is not None
            os.set_blocking(stream.fileno(), False)
            self.selector.register(stream, selectors.EVENT_READ, name)
        self._flush()

    def _flush(self) -> None:
        if self.outgoing and self.process.stdin is not None and not self.process.stdin.closed:
            try:
                size = os.write(self.process.stdin.fileno(), self.outgoing)
            except BlockingIOError:
                return
            except BrokenPipeError:
                self.problem = "Supervisor closed its control channel"
                return
            del self.outgoing[:size]

    def _accept(self, raw: bytes) -> None:
        try:
            message = json.loads(raw)
            if (not isinstance(message, dict) or message.get("version") != 1
                    or message.get("token") != self.token):
                raise ValueError("Supervisor identity mismatch")
            kind = message.get("type")
            if kind == "stopping" and isinstance(message.get("message"), str):
                _notify(self.callback, message["message"])
            elif (kind == "complete" and message.get("tree_exited") is True
                  and message.get("outcome") in {"ok", "cancelled", "error"}
                  and isinstance(message.get("message"), str) and self.terminal is None):
                self.terminal = message
            else:
                raise ValueError("Invalid supervisor status")
        except (ValueError, TypeError):
            self.problem = "Invalid or mismatched supervisor status"
            self.stop(hard=False)

    def drain(self, capture: _Capture) -> None:
        self._flush()
        for key, _ in self.selector.select(0):
            try:
                data = os.read(key.fd, _CHUNK)
            except BlockingIOError:
                continue
            if not data:
                self.selector.unregister(key.fileobj)
                continue
            if key.data == "diagnostic":
                capture.feed(data)
                continue
            self.protocol_count = min(_PROTOCOL_LIMIT + 1, self.protocol_count + len(data))
            if self.protocol_count > _PROTOCOL_LIMIT:
                self.protocol.clear()
                self.problem = "Supervisor status exceeded its bounded protocol limit"
                self.stop(hard=False)
                continue
            self.protocol.extend(data)
            while b"\n" in self.protocol:
                raw, _, tail = self.protocol.partition(b"\n")
                self.protocol = bytearray(tail)
                self._accept(bytes(raw))

    def poll(self) -> int | None:
        code = self.process.poll()
        if code is None:
            return None
        if self.problem:
            raise DomainProcessError(self.problem)
        if self.terminal is None:
            if self.selector.get_map():
                # Exit and pipe readability race; drain the complete bounded
                # final message before deciding that the proof is missing.
                return None
            # The finally path keeps the lock: helper loss is not tree proof.
            raise DomainProcessError("Supervisor exited without confirmed process-tree cleanup")
        if code != 0:
            raise DomainProcessError("Supervisor exited unsuccessfully")
        if self.terminal["outcome"] == "cancelled":
            raise DomainProcessCancelled(self.terminal["message"][:512])
        if self.terminal["outcome"] == "error":
            raise DomainProcessError(self.terminal["message"][:512])
        return 0

    def tree_exited(self) -> bool:
        if self.process.poll() is None or self.terminal is None or self.selector.get_map():
            return False
        # Child's session/group was confirmed by the dedicated helper. Confirm
        # the helper itself and its own group too, before releasing the host lock.
        try:
            os.killpg(self.process.pid, 0)
        except ProcessLookupError:
            return True
        return False

    def stop(self, hard: bool) -> None:
        # Never kill the helper to implement timeout/cancel: it owns cleanup.
        # Closing this pipe also happens automatically on hard sidecar loss.
        self.outgoing.clear()
        if self.process.stdin is not None and not self.process.stdin.closed:
            self.process.stdin.close()

    def close(self) -> None:
        self.selector.close()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


# Fixed-width fields matter even on hosts where ctypes.c_ulong is 64 bits.
# Definitions stay importable on POSIX for ABI/layout and command-line tests.
_DWORD = ctypes.c_uint32
_BOOL = ctypes.c_int32
_HANDLE = ctypes.c_void_p
_SIZE_T = ctypes.c_size_t
_LPVOID = ctypes.c_void_p


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("length", _DWORD), ("descriptor", _LPVOID), ("inherit", _BOOL)]


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", _DWORD), ("reserved", ctypes.c_wchar_p),
        ("desktop", ctypes.c_wchar_p), ("title", ctypes.c_wchar_p),
        ("x", _DWORD), ("y", _DWORD), ("x_size", _DWORD), ("y_size", _DWORD),
        ("x_chars", _DWORD), ("y_chars", _DWORD), ("fill", _DWORD),
        ("flags", _DWORD), ("show", ctypes.c_uint16), ("reserved_size", ctypes.c_uint16),
        ("reserved_bytes", _LPVOID), ("stdin", _HANDLE), ("stdout", _HANDLE), ("stderr", _HANDLE),
    ]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("startup", _StartupInfo), ("attributes", _LPVOID)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [("process", _HANDLE), ("thread", _HANDLE), ("pid", _DWORD), ("tid", _DWORD)]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", _DWORD),
        ("min_working", _SIZE_T), ("max_working", _SIZE_T), ("active_limit", _DWORD),
        ("affinity", _SIZE_T), ("priority", _DWORD), ("scheduling", _DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits), ("io", _IoCounters), ("process_memory", _SIZE_T),
        ("job_memory", _SIZE_T), ("peak_process_memory", _SIZE_T), ("peak_job_memory", _SIZE_T),
    ]


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in (
        "user_time", "kernel_time", "period_user", "period_kernel")] + [
        (name, _DWORD) for name in ("page_faults", "total", "active", "terminated")]


def _windows_api():
    """Declare every used Win32 ABI; never truncate a 64-bit HANDLE."""
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CloseHandle": ([_HANDLE], _BOOL),
        "CreateJobObjectW": ([_LPVOID, ctypes.c_wchar_p], _HANDLE),
        "SetInformationJobObject": ([_HANDLE, ctypes.c_int, _LPVOID, _DWORD], _BOOL),
        "QueryInformationJobObject": ([_HANDLE, ctypes.c_int, _LPVOID, _DWORD, _LPVOID], _BOOL),
        "AssignProcessToJobObject": ([_HANDLE, _HANDLE], _BOOL),
        "IsProcessInJob": ([_HANDLE, _HANDLE, ctypes.POINTER(_BOOL)], _BOOL),
        "TerminateJobObject": ([_HANDLE, _DWORD], _BOOL),
        "TerminateProcess": ([_HANDLE, _DWORD], _BOOL),
        "CreatePipe": ([ctypes.POINTER(_HANDLE), ctypes.POINTER(_HANDLE), _LPVOID, _DWORD], _BOOL),
        "SetHandleInformation": ([_HANDLE, _DWORD, _DWORD], _BOOL),
        "PeekNamedPipe": ([_HANDLE, _LPVOID, _DWORD, _LPVOID, ctypes.POINTER(_DWORD), _LPVOID], _BOOL),
        "ReadFile": ([_HANDLE, _LPVOID, _DWORD, ctypes.POINTER(_DWORD), _LPVOID], _BOOL),
        "InitializeProcThreadAttributeList": ([_LPVOID, _DWORD, _DWORD, ctypes.POINTER(_SIZE_T)], _BOOL),
        "UpdateProcThreadAttribute": ([_LPVOID, _DWORD, _SIZE_T, _LPVOID, _SIZE_T, _LPVOID, _LPVOID], _BOOL),
        "DeleteProcThreadAttributeList": ([_LPVOID], None),
        "CreateProcessW": ([ctypes.c_wchar_p, ctypes.c_wchar_p, _LPVOID, _LPVOID, _BOOL,
                            _DWORD, _LPVOID, ctypes.c_wchar_p, _LPVOID, _LPVOID], _BOOL),
        "ResumeThread": ([_HANDLE], _DWORD),
        "WaitForSingleObject": ([_HANDLE, _DWORD], _DWORD),
        "GetExitCodeProcess": ([_HANDLE, ctypes.POINTER(_DWORD)], _BOOL),
        "GetWindowsDirectoryW": ([ctypes.c_wchar_p, _DWORD], _DWORD),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
    return api


def _win_check(ok: object) -> None:
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


class _WindowsProcess:
    def __init__(self, argv: list[str], cwd: Path, env: dict[str, str], *,
                 lease: ExecutionLease | None = None,
                 callback: Callable[[str], None] | None = None,
                 cancelled: Callable[[], bool] = lambda: False, timeout_seconds: float = 300):
        self.api = _windows_api()
        self.watchdog: Any = None
        self.handles: list[int] = []
        self.readers: list[int] = []
        self.info = _ProcessInformation()
        self.assigned = False
        self.job = self.api.CreateJobObjectW(None, None)
        _win_check(self.job)
        self.handles.append(self.job)
        attributes = None
        try:
            limits = _ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
            _win_check(self.api.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            if lease is not None:
                self.watchdog = _watchdog_module().WindowsLeaseWatchdog(self.job, lease, cwd, env, callback)
                self.watchdog.wait_ready(cancelled, min(30, timeout_seconds))
            security = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), None, 1)

            def pipe() -> tuple[int, int]:
                read, write = _HANDLE(), _HANDLE()
                _win_check(self.api.CreatePipe(ctypes.byref(read), ctypes.byref(write), ctypes.byref(security), 0))
                assert read.value is not None and write.value is not None
                self.handles.extend((read.value, write.value))
                return read.value, write.value

            stdin_read, stdin_write = pipe()
            stdout_read, stdout_write = pipe()
            stderr_read, stderr_write = pipe()
            self.readers = [stdout_read, stderr_read]
            for handle in (stdin_write, stdout_read, stderr_read):
                _win_check(self.api.SetHandleInformation(handle, 1, 0))
            inherited = (_HANDLE * 3)(stdin_read, stdout_write, stderr_write)
            size = _SIZE_T()
            self.api.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
            if not size.value:
                _win_check(False)
            storage = ctypes.create_string_buffer(size.value)
            _win_check(self.api.InitializeProcThreadAttributeList(storage, 2, 0, ctypes.byref(size)))
            attributes = ctypes.cast(storage, _LPVOID)
            _win_check(self.api.UpdateProcThreadAttribute(
                attributes, 0, 0x20002, inherited, ctypes.sizeof(inherited), None, None))
            job_list = (_HANDLE * 1)(self.job)
            # Windows10+/Server2016+: membership is atomic with creation. A
            # failed JOB_LIST attribute aborts; never fall back to create/assign.
            _win_check(self.api.UpdateProcThreadAttribute(
                attributes, 0, 0x2000D, job_list, ctypes.sizeof(job_list), None, None))
            startup = _StartupInfoEx()
            startup.startup.cb = ctypes.sizeof(startup)
            startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = inherited
            startup.attributes = attributes
            command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
            environment = ctypes.create_unicode_buffer(
                "\0".join(f"{key}={value}" for key, value in sorted(env.items(), key=lambda item: item[0].upper())) + "\0\0")
            # Application name is explicit (spaces cannot select another exe).
            # CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW |
            # EXTENDED_STARTUPINFO_PRESENT. Job assignment is atomic with creation.
            _win_check(self.api.CreateProcessW(
                argv[0], command, None, None, True, 0x08080404, environment,
                str(cwd), ctypes.byref(startup), ctypes.byref(self.info)))
            self.assigned = True
        except BaseException:
            # No runtime code has resumed. Still prove OS-level termination if
            # interrupted immediately after successful CreateProcessW.
            if self.info.process:
                while True:
                    try:
                        _win_check(self.api.TerminateJobObject(self.job, 1))
                        accounting = _Accounting()
                        _win_check(self.api.QueryInformationJobObject(
                            self.job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None))
                        if self.api.WaitForSingleObject(self.info.process, 0) == 0 and accounting.active == 0:
                            break
                    except BaseException:
                        pass
                    try:
                        time.sleep(_POLL_SECONDS)
                    except BaseException:
                        pass
            if self.watchdog is not None:
                self.watchdog.wait_stopped()
                self.watchdog.close()
            for handle in self.handles:
                self.api.CloseHandle(handle)
            for handle in (self.info.process, self.info.thread):
                if handle:
                    self.api.CloseHandle(handle)
            raise
        finally:
            if attributes is not None:
                self.api.DeleteProcThreadAttributeList(attributes)
        self.handles.extend((self.info.process, self.info.thread))
        # Closing every parent copy is essential for reliable EOF observation.
        for handle in (stdin_read, stdin_write, stdout_write, stderr_write):
            self.api.CloseHandle(handle)
            self.handles.remove(handle)

    def start(self) -> None:
        member = _BOOL()
        _win_check(self.api.IsProcessInJob(self.info.process, self.job, ctypes.byref(member)))
        if not member.value:
            self.assigned = False
            raise DomainProcessError("Runtime was not atomically assigned to its JobObject")
        if self.api.ResumeThread(self.info.thread) == 0xFFFFFFFF:
            _win_check(False)

    def poll(self) -> int | None:
        if self.watchdog is not None:
            watchdog_exit = self.watchdog.poll()
            if self.watchdog.problem or (watchdog_exit is not None and not self.watchdog.confirmed):
                raise DomainProcessError("Runtime lease watchdog exited without cleanup proof")
        state = self.api.WaitForSingleObject(self.info.process, 0)
        if state == 258:  # WAIT_TIMEOUT
            return None
        if state != 0:
            _win_check(False)
        code = _DWORD()
        _win_check(self.api.GetExitCodeProcess(self.info.process, ctypes.byref(code)))
        return code.value

    def drain(self, capture: _Capture) -> None:
        for handle in tuple(self.readers):
            available = _DWORD()
            if not self.api.PeekNamedPipe(handle, None, 0, None, ctypes.byref(available), None):
                if ctypes.get_last_error() == 109:  # ERROR_BROKEN_PIPE
                    self.readers.remove(handle)
                    continue
                _win_check(False)
            if available.value:
                data = ctypes.create_string_buffer(min(_CHUNK, available.value))
                size = _DWORD()
                _win_check(self.api.ReadFile(handle, data, len(data), ctypes.byref(size), None))
                capture.feed(data.raw[:size.value])

    def tree_exited(self) -> bool:
        if self.poll() is None:
            return False
        if self.assigned:
            accounting = _Accounting()
            _win_check(self.api.QueryInformationJobObject(
                self.job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None))
            if accounting.active:
                return False
        # An unassigned process was NEVER resumed, so it cannot have children.
        if self.readers:
            return False
        if self.watchdog is not None:
            self.watchdog.request_stop()
            return self.watchdog.exited_cleanly()
        return True

    def stop(self, hard: bool) -> None:
        if self.assigned:
            _win_check(self.api.TerminateJobObject(self.job, 1))
        elif self.api.WaitForSingleObject(self.info.process, 0) == 258:
            _win_check(self.api.TerminateProcess(self.info.process, 1))
        if self.watchdog is not None:
            self.watchdog.request_stop()

    def close(self) -> None:
        if self.watchdog is not None:
            self.watchdog.close()
        for handle in reversed(self.handles):
            self.api.CloseHandle(handle)
        self.handles.clear()


def _environment(private: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for name, leaf in {
        "PATH": "empty-path", "HOME": "home", "USERPROFILE": "home", "TMPDIR": "tmp",
        "TEMP": "tmp", "TMP": "tmp", "APPDATA": "config", "LOCALAPPDATA": "cache",
        "XDG_CACHE_HOME": "cache", "XDG_CONFIG_HOME": "config", "MPLCONFIGDIR": "matplotlib",
        "TORCH_HOME": "torch",
    }.items():
        path = private / leaf
        path.mkdir(mode=0o700, exist_ok=True)
        env[name] = str(path)
    env.update({
        "LANG": "C", "LC_ALL": "C", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1", "MPLBACKEND": "Agg",
        "CUDA_VISIBLE_DEVICES": "", "HIP_VISIBLE_DEVICES": "", "ROCR_VISIBLE_DEVICES": "",
    })
    if os.name == "nt":
        # Obtain OS location from the OS, not inherited loader/search variables.
        api = _windows_api()
        root = ctypes.create_unicode_buffer(32768)
        size = api.GetWindowsDirectoryW(root, len(root))
        if not 0 < size < len(root):
            _win_check(False)
        env.update({"SystemRoot": root.value, "WINDIR": root.value, "OS": "Windows_NT"})
    return env


def _check_result(path: Path, limit: int, *, required: bool) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise DomainProcessError("Managed domain runtime did not write a result") from None
        return
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, "st_file_attributes", 0) & 0x400):
        raise DomainProcessError("Managed domain result is not a single-link regular file")
    if info.st_size > limit:
        raise DomainProcessError("Managed domain result exceeded the size limit")


def _notify(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        try:
            callback(message[:512])
        except BaseException:
            # UI/reporting failures cannot unwind the lifecycle boundary.
            pass


def _stop_until_dead(process: _Process, capture: _Capture,
                     callback: Callable[[str], None] | None) -> None:
    """No finite timeout may release an operation lock around a live tree."""
    start = time.monotonic()
    next_signal = start
    pending_notified = False
    last_error = "termination still unconfirmed"
    while True:
        try:
            process.drain(capture)
        except BaseException as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
        try:
            if process.tree_exited():
                return
        except BaseException as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
        try:
            now = time.monotonic()
            if now >= next_signal:
                process.stop(hard=now - start >= _TERM_GRACE_SECONDS)
                next_signal = now + _TERM_GRACE_SECONDS
        except BaseException as exc:
            # Error text only; never append a growing list of failed attempts.
            last_error = f"{type(exc).__name__}: {str(exc)[:160]}"
        if not pending_notified and time.monotonic() - start >= _CLEANUP_NOTICE_SECONDS:
            pending_notified = True
            _notify(callback, "Cleanup pending; runtime remains locked until all processes exit. " + last_error)
        try:
            time.sleep(_POLL_SECONDS)
        except BaseException:
            pass  # A second interrupt must not abandon live children either.


def run_managed_process(
    argv: list[str], *, cwd: Path, cancelled: Callable[[], bool],
    timeout_seconds: float = 300, output_limit: int = 1048576,
    result_path: Path, result_limit: int = 8388608,
    on_stopping: Callable[[str], None] | None = None,
    operation_lease: OperationLease | None = None,
) -> None:
    """Run verified argv without a shell; return/raise only after tree cleanup.

    The private environment never inherits PYTHON/venv/loader variables. Output
    is drained into a constant-size tail; exceeding the combined byte allowance
    cancels execution. Polling the result is a soft growth watchdog, not a quota.
    Both callbacks are trusted internal, nonblocking functions (Event.is_set and
    a short status update); a callback must never wait for this invocation.
    """
    if (not argv or not all(isinstance(arg, str) and "\0" not in arg for arg in argv)
            or not Path(argv[0]).is_absolute()):
        raise DomainProcessError("Managed domain executable must be an absolute trusted path")
    if (not math.isfinite(timeout_seconds) or timeout_seconds <= 0
            or type(output_limit) is not int or output_limit <= 0
            or type(result_limit) is not int or result_limit <= 0):
        raise DomainProcessError("Invalid managed domain process limits")
    cwd = cwd.resolve(strict=True)
    if not cwd.is_dir() or result_path.parent.resolve(strict=True) != cwd:
        raise DomainProcessError("Managed domain result must be inside its private working directory")
    if os.path.lexists(result_path):
        raise DomainProcessError("Managed domain result path must be fresh")
    if cancelled():
        raise DomainProcessCancelled("Managed domain annotation cancelled")
    with tempfile.TemporaryDirectory(prefix="domain-private-", dir=cwd) as temporary:
        environment = _environment(Path(temporary))
        # This durable nonterminal record precedes EVERY helper/runtime spawn.
        # A startup crash leaves refusal, never an apparently empty registry.
        execution_lease = None if operation_lease is None else operation_lease.prepare()
        try:
            owned: _Process = (_WindowsProcess(argv, cwd, environment, lease=execution_lease,
                                               callback=on_stopping, cancelled=cancelled,
                                               timeout_seconds=timeout_seconds) if os.name == "nt" else
                               _PosixSupervisor(argv, cwd, environment, timeout_seconds=timeout_seconds,
                                                output_limit=output_limit, result_path=result_path,
                                                result_limit=result_limit, callback=on_stopping,
                                                lease=execution_lease))
        except Exception as exc:
            if cancelled():
                raise DomainProcessCancelled("Managed domain annotation cancelled before runtime launch") from exc
            raise DomainProcessError(f"Cannot start managed domain supervisor ({type(exc).__name__})") from exc
        _run_observed(owned, cancelled=cancelled, timeout_seconds=timeout_seconds,
                      output_limit=output_limit, result_path=result_path,
                      result_limit=result_limit, on_stopping=on_stopping)


def _run_observed(
    owned: _Process, *, cancelled: Callable[[], bool], timeout_seconds: float,
    output_limit: int, result_path: Path, result_limit: int,
    on_stopping: Callable[[str], None] | None,
) -> None:
    capture = _Capture(output_limit)
    failure: BaseException | None = None
    code: int | None = None
    try:
        owned.start()
        deadline = time.monotonic() + timeout_seconds
        while True:
            owned.drain(capture)
            if cancelled():
                raise DomainProcessCancelled("Managed domain annotation cancelled")
            if capture.exceeded:
                raise DomainProcessError("Managed domain runtime exceeded the output limit")
            _check_result(result_path, result_limit, required=False)
            code = owned.poll()
            if code is not None:
                break
            if time.monotonic() >= deadline:
                raise DomainProcessError("Managed domain runtime exceeded its time limit")
            time.sleep(_POLL_SECONDS)
    except BaseException as exc:
        failure = exc
    finally:
        _notify(on_stopping, "Stopping runtime and waiting for all processes to exit.")
        _stop_until_dead(owned, capture, on_stopping)
        owned.close()
    if failure is not None:
        if isinstance(failure, DomainProcessError):
            raise failure
        raise DomainProcessError(f"Managed domain runtime failed ({type(failure).__name__})") from failure
    if cancelled():
        raise DomainProcessCancelled("Managed domain annotation cancelled")
    if capture.exceeded:
        raise DomainProcessError("Managed domain runtime exceeded the output limit")
    if code != 0:
        raise DomainProcessError(f"Managed domain runtime exited unsuccessfully ({code})")
    _check_result(result_path, result_limit, required=True)


class _ParentLifetime:
    def __init__(self, fd: int):
        self.fd = fd
        self.closed = False
        self.signalled = False
        os.set_blocking(fd, False)

    def cancelled(self) -> bool:
        if self.closed or self.signalled:
            return True
        try:
            data = os.read(self.fd, 256)
        except BlockingIOError:
            return False
        # After the single initial config no further bytes are legitimate.
        # EOF and unexpected bytes both request safe cancellation.
        self.closed = True
        return True


def _read_supervisor_config(fd: int, token: str) -> dict:
    selector = selectors.DefaultSelector()
    selector.register(fd, selectors.EVENT_READ)
    os.set_blocking(fd, False)
    buffer = bytearray()
    deadline = time.monotonic() + 30
    try:
        while b"\n" not in buffer:
            if time.monotonic() >= deadline:
                raise DomainProcessError("Supervisor configuration was not received")
            if not selector.select(_POLL_SECONDS):
                continue
            chunk = os.read(fd, _CHUNK)
            if not chunk:
                raise DomainProcessCancelled("Parent exited before runtime launch")
            buffer.extend(chunk)
            if len(buffer) > _CONFIG_LIMIT:
                raise DomainProcessError("Supervisor configuration exceeded its limit")
    finally:
        selector.close()
    line, _, extra = buffer.partition(b"\n")
    if extra:
        raise DomainProcessError("Unexpected supervisor control bytes")
    try:
        config = json.loads(line)
        if (not isinstance(config, dict) or config.get("version") != 1 or config.get("token") != token
                or set(config) != {"version", "token", "argv", "cwd", "environment", "timeout_seconds",
                                   "output_limit", "result_path", "result_limit", "lease"}):
            raise ValueError("Supervisor configuration identity mismatch")
        argv, env = config["argv"], config["environment"]
        if (not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and "\0" not in arg for arg in argv)
                or not Path(argv[0]).is_absolute() or not isinstance(env, dict)
                or not all(isinstance(key, str) and isinstance(value, str) and "\0" not in key + value for key, value in env.items())
                or not Path(config["cwd"]).is_absolute() or not Path(config["result_path"]).is_absolute()
                or Path(config["result_path"]).parent != Path(config["cwd"])
                or not math.isfinite(config["timeout_seconds"]) or config["timeout_seconds"] <= 0
                or any(type(config[key]) is not int or config[key] <= 0 for key in ("output_limit", "result_limit"))):
            raise ValueError("Invalid supervisor configuration")
        return config
    except (ValueError, TypeError, KeyError) as exc:
        raise DomainProcessError("Invalid supervisor configuration") from exc


def supervisor_main(token: str) -> int:
    """Private early entrypoint for source or frozen POSIX helper execution."""
    if os.name == "nt" or len(token) != 64 or any(char not in "0123456789abcdef" for char in token):
        return 2
    output_fd = sys.stdout.fileno()
    os.set_blocking(output_fd, False)
    outgoing = bytearray()

    def flush_output() -> None:
        if not outgoing:
            return
        try:
            size = os.write(output_fd, outgoing)
        except BlockingIOError:
            return
        except BrokenPipeError:
            outgoing.clear()  # Parent vanished; child cleanup still completes.
            return
        del outgoing[:size]

    def emit(kind: str, **fields: object) -> None:
        message = {"version": 1, "token": token, "type": kind, **fields}
        raw = json.dumps(message, ensure_ascii=True, allow_nan=False).encode("ascii") + b"\n"
        if len(raw) > 2048:
            raise ValueError("Supervisor status exceeded its message limit")
        if len(outgoing) + len(raw) > _PROTOCOL_LIMIT:
            raise ValueError("Supervisor status queue exceeded its limit")
        outgoing.extend(raw)
        # Never block cleanup on a slow/stopped parent. Handle short writes
        # without assuming any particular platform's pipe capacity.
        flush_output()

    outcome, detail = "ok", ""
    held_lease = None
    try:
        config = _read_supervisor_config(sys.stdin.fileno(), token)
        lifetime = _ParentLifetime(sys.stdin.fileno())
        if config["lease"] is not None:
            try:
                held_lease = _lease_module().HelperLease.claim(config["lease"], expected_token=token)
            except Exception as exc:
                raise DomainProcessError("Cannot claim runtime execution lease") from exc

        def stop_signal(_signum: int, _frame: object) -> None:
            lifetime.signalled = True

        signal.signal(signal.SIGTERM, stop_signal)
        signal.signal(signal.SIGINT, stop_signal)
        if lifetime.cancelled():
            raise DomainProcessCancelled("Parent exited before runtime launch")
        try:
            child = _PosixChild(config["argv"], Path(config["cwd"]), config["environment"])
        except Exception as exc:
            raise DomainProcessError(f"Cannot launch managed domain child ({type(exc).__name__})") from exc
        _run_observed(child, cancelled=lifetime.cancelled, timeout_seconds=config["timeout_seconds"],
                      output_limit=config["output_limit"], result_path=Path(config["result_path"]),
                      result_limit=config["result_limit"],
                      on_stopping=lambda message: emit("stopping", message=message))
    except DomainProcessCancelled as exc:
        outcome, detail = "cancelled", str(exc)[:512]
    except DomainProcessError as exc:
        outcome, detail = "error", str(exc)[:512]
    if held_lease is not None:
        _complete_execution_lease(held_lease, lambda message: emit("stopping", message=message))
    # Only these known post-cleanup exceptions can reach a terminal proof. An
    # unexpected helper crash never emits it, and the parent retains its lock.
    emit("complete", outcome=outcome, message=detail, tree_exited=True)
    # Runtime cleanup is already confirmed. Keep the small terminal proof until
    # its reader drains it or disappears; never turn backpressure into success.
    while outgoing:
        flush_output()
        if outgoing:
            time.sleep(_POLL_SECONDS)
    if held_lease is not None:
        # Only close the inherited flock reference. LOCK_UN here would also
        # unlock the live parent's same open-file-description prematurely.
        held_lease.close()
    return 0


def _complete_execution_lease(held_lease: Any, callback: Callable[[str], None] | None) -> None:
    notified = False
    while True:
        try:
            held_lease.complete()
            return
        except BaseException:
            if not notified:
                notified = True
                _notify(callback, "Cleanup proof pending; runtime registry remains locked.")
            try:
                time.sleep(_POLL_SECONDS)
            except BaseException:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != _SUPERVISOR_FLAG:
        raise SystemExit(2)
    raise SystemExit(supervisor_main(sys.argv[2]))
