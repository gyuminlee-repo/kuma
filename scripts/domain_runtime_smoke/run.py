"""JSON-only test-only probe for source or caller-built frozen onedir helper.

The caller owns the supplied binary/build tree. This driver never builds,
installs, downloads, or executes scientific inference. It removes its temporary
fixture data on success/failure; retained reports contain bounded JSON only.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import psutil
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from ctypes import wintypes

ENTRY = Path(__file__).with_name("entry.py").resolve()
MAX_CAPTURE = 64 * 1024


def pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True  # Permission failure is not proof of termination.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE only.
    if not handle:
        if ctypes.get_last_error() == 87:  # Invalid PID.
            return False
        raise OSError(ctypes.get_last_error(), "Cannot verify fixture process")
    try:
        status = kernel.WaitForSingleObject(handle, 0)
        if status not in {0, 258}:
            raise OSError("Cannot inspect fixture process exit")
        return status == 258
    finally:
        kernel.CloseHandle(handle)


def wait_until(predicate: Callable[[], bool], seconds: float, message: str) -> None:
    deadline = time.monotonic() + seconds
    while not predicate():
        if time.monotonic() >= deadline:
            raise TimeoutError(message)
        time.sleep(0.025)


class Process:
    def __init__(self, command: list[str], cwd: Path):
        self.process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, shell=False,
            start_new_session=os.name != "nt")
        self.messages: queue.Queue[dict | Exception] = queue.Queue(maxsize=32)
        self.stderr = bytearray()
        self.stdout_bytes = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.errors = threading.Thread(target=self._stderr, daemon=True)
        self.reader.start()
        self.errors.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        try:
            while True:
                raw = self.process.stdout.readline(MAX_CAPTURE + 1)
                if not raw:
                    return
                self.stdout_bytes += len(raw)
                if self.stdout_bytes > MAX_CAPTURE:
                    raise ValueError("Fixture protocol exceeded its byte bound")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("Fixture protocol must be a JSON object")
                self.messages.put_nowait(value)
        except Exception as exc:
            try:
                self.messages.put_nowait(exc)
            except queue.Full:
                pass

    def _stderr(self) -> None:
        assert self.process.stderr is not None
        while True:
            raw = self.process.stderr.read(1024)
            if not raw:
                return
            self.stderr.extend(raw)
            del self.stderr[:-2048]

    def send(self, raw: bytes) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(raw)
        self.process.stdin.flush()

    def receive(self, timeout: float = 20) -> dict:
        try:
            value = self.messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("Fixture response timed out; " + self.stderr.decode("utf-8", "replace")) from exc
        if isinstance(value, Exception):
            raise value
        return value

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=10)
        self.reader.join(2)
        self.errors.join(2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()


def request(identifier: int, method: str, text: str = "") -> bytes:
    return (json.dumps({"jsonrpc": "2.0", "id": identifier, "method": method,
                       "params": {"text": text}}, ensure_ascii=False) + "\n").encode()


def run_probe(binary: Path | None, *, timeout_seconds: float | None = None) -> dict:
    frozen = binary is not None
    if binary is not None:
        binary = binary.resolve(strict=True)
        command = [str(binary)]
    else:
        command = [sys.executable, "-I", str(ENTRY)]
    timeout = timeout_seconds if timeout_seconds is not None else (30.0 if frozen else 2.0)
    if not 0.5 <= timeout <= 60:
        raise ValueError("Fixture timeout must be between 0.5 and 60 seconds")
    report: dict = {"schema": "kuma-domain-contract-smoke-v1", "status": "failed",
                    "mode": "frozen_onedir" if frozen else "source", "platform": sys.platform,
                    "scope": "synthetic_ipc_and_process_lifecycle_only", "checks": {},
                    "not_verified": ["full GUI/product bundle", "Merizo inference or biological accuracy",
                                     "runtime redistribution rights", "hard supervisor-helper loss"]}
    temporary = tempfile.TemporaryDirectory(prefix="kuma domain contract ")
    root = Path(temporary.name).resolve()
    active: Process | None = None
    seen_pids: list[int] = []
    suspended_helper = None
    def admission(work: Path) -> bool:
        check = subprocess.run(command + ["--admission", str(work)], cwd=root,
            stdin=subprocess.DEVNULL, capture_output=True, timeout=15, shell=False)
        if check.returncode or len(check.stdout) > 4096:
            raise AssertionError("Registry admission probe failed")
        value = json.loads(check.stdout)
        if set(value) != {"admitted"} or type(value["admitted"]) is not bool:
            raise AssertionError("Invalid registry admission response")
        return value["admitted"]
    try:
        active = Process(command + ["--ipc"], root)
        active.send(request(1, "delay", "한국어"))
        first = active.receive()
        value = first.get("result", {})
        if (first.get("id") != 1 or value.get("text") != "한국어"
                or value.get("frozen") is not frozen):
            raise AssertionError("Delayed IPC response or frozen identity mismatch")
        executable = Path(value["executable"]).resolve()
        if executable != (binary if frozen else Path(sys.executable).resolve()):
            raise AssertionError("Probe executable origin mismatch")
        report["executable"] = str(executable)
        report["checks"]["delayed_reply_before_next_input"] = True
        report["checks"]["actual_frozen_identity"] = frozen
        second = request(2, "echo", "韓-日本")
        split = second.index("韓".encode()) + 1
        active.send(second[:split])
        time.sleep(0.03)
        active.send(second[split:] + request(3, "echo", "three"))
        replies = {item["id"]: item["result"] for item in (active.receive(), active.receive())}
        if replies[2]["text"] != "韓-日本" or replies[3]["text"] != "three":
            raise AssertionError("Fragmented UTF-8 or multiple-frame IPC failed")
        report["checks"]["fragmented_utf8_and_multiple_frames"] = True
        active.send(request(4, "shutdown"))
        if active.receive().get("result", {}).get("ok") is not True:
            raise AssertionError("IPC shutdown failed")
        if active.process.wait(timeout=10) != 0:
            raise AssertionError("IPC helper did not exit cleanly")
        active.close()
        active = None
        for mode in ("success", "cancel", "timeout", "hard_loss"):
            work = root / mode
            work.mkdir()
            active = Process(command + ["--managed-host", mode, str(work), str(timeout)], root)
            ready = active.receive(timeout=max(60, timeout + 10))
            if ready.get("event") != "ready" or ready.get("frozen") is not frozen:
                raise AssertionError(f"{mode}: startup readiness was not established (not a cleanup assertion): {ready}")
            pids = ready["child_pids"]
            if not isinstance(pids, list) or not pids or any(type(pid) is not int or pid <= 1 for pid in pids):
                raise AssertionError("Invalid fixture process identities")
            seen_pids.extend(pids)
            if mode in {"cancel", "hard_loss"} and not all(pid_alive(pid) for pid in pids):
                raise AssertionError("Fixture process exited before cancellation/crash")
            helper = ready["helper"]
            if not isinstance(helper, dict) or type(helper.get("pid")) is not int or type(helper.get("created")) not in (int, float):
                raise AssertionError("Missing exact helper identity")
            if mode == "hard_loss":
                suspended_helper = psutil.Process(helper["pid"])
                if suspended_helper.create_time() != helper["created"]:
                    raise AssertionError("Helper creation identity changed")
                suspended_helper.suspend()
                active.send(b"crash\n")
                if active.process.wait(timeout=10) != 91:
                    raise AssertionError("Abrupt host exit was not established")
                if admission(work):
                    raise AssertionError("Registry admitted a new operation before helper cleanup")
                suspended_helper.resume()
                suspended_helper = None
            else:
                if mode == "cancel":
                    active.send(b"cancel\n")
                final = active.receive(timeout=timeout + 25)
                expected = {"success": "ok", "cancel": "cancelled", "timeout": "error"}[mode]
                if final.get("event") != "finished" or final.get("outcome") != expected:
                    raise AssertionError(f"{mode}: unexpected lifecycle outcome: {final}")
                if mode == "timeout" and not any(word in final.get("message", "").lower() for word in ("timed out", "timeout", "time limit")):
                    raise AssertionError("Timeout did not produce the bounded-timeout error")
                if final.get("private_directory_removed") is not True:
                    raise AssertionError("Normal lifecycle left a private environment directory")
                if active.process.wait(timeout=10) != 0:
                    raise AssertionError("Managed fixture host did not exit cleanly")
            wait_until(lambda: all(not pid_alive(pid) for pid in pids), 15,
                       f"{mode}: child/descendant termination was not confirmed")
            def helper_exited():
                try:
                    return psutil.Process(helper["pid"]).create_time() != helper["created"]
                except psutil.NoSuchProcess:
                    return True
            wait_until(helper_exited, 15, "Exact lifecycle helper did not exit")
            if not admission(work):
                raise AssertionError("Terminal proof plus helper exit did not restore registry admission")
            report["checks"][mode] = {"passed": True, "helper_exit_verified": True,
                                      "registry_admitted_after_cleanup": True, "child_count": len(pids),
                                      "termination_verified": True}
            if mode == "hard_loss":
                report["checks"][mode]["method"] = "host_os_exit_without_cleanup"
                report["checks"][mode]["registry_refused_during_suspended_helper_cleanup"] = True
                report["checks"][mode]["crash_leftover_files_removed_by_driver"] = True
            active.close()
            active = None
        report["status"] = "passed"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"[:4000]
    finally:
        if suspended_helper is not None:
            try:
                suspended_helper.resume()
            except psutil.NoSuchProcess:
                pass
            except psutil.Error as exc:
                report["status"] = "failed"
                report["cleanup_error"] = f"Cannot resume fixture helper: {type(exc).__name__}"
        if active is not None:
            try:
                active.close()
            except Exception as exc:
                report["status"] = "failed"
                report["cleanup_error"] = f"{type(exc).__name__}: {exc}"[:1000]
        # Failed readiness/response assertions may precede normal PID capture.
        # Consult only the fixed names created by our own fixture processes.
        for mode in ("success", "cancel", "timeout", "hard_loss"):
            for name in ("root.pid", "descendant.pid"):
                marker = root / mode / name
                try:
                    raw = marker.read_bytes()
                    if len(raw) > 32:
                        raise ValueError("Oversized fixture PID marker")
                    pid = int(raw)
                    if pid <= 1:
                        raise ValueError("Invalid fixture PID marker")
                    if pid not in seen_pids:
                        seen_pids.append(pid)
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    report["status"] = "failed"
                    report["cleanup_error"] = f"{type(exc).__name__}: {exc}"[:1000]
        try:
            wait_until(lambda: all(not pid_alive(pid) for pid in seen_pids), 15,
                       "Fixture processes remain after host cleanup")
        except Exception as exc:
            report["status"] = "failed"
            report["cleanup_error"] = f"{type(exc).__name__}: {exc}"[:1000]
        try:
            temporary.cleanup()
            report["temporary_files_removed"] = not root.exists()
        except Exception as exc:
            report["status"] = "failed"
            report["cleanup_error"] = f"{type(exc).__name__}: {exc}"[:1000]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float)
    args = parser.parse_args()
    try:
        report = run_probe(args.binary, timeout_seconds=args.timeout_seconds)
    except Exception as exc:
        report = {"schema": "kuma-domain-contract-smoke-v1", "status": "failed",
                  "error": f"{type(exc).__name__}: {exc}"[:2000]}
    raw = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(raw, encoding="utf-8")
    sys.stdout.write(raw)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
