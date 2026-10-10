"""Test-only stdlib frozen IPC/lifecycle entry. Never a scientific runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

if not getattr(sys, "frozen", False):
    repository = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repository))
    # Import the actual stdlib module without scientific kuro/__init__.py.
    # Frozen builds use the same explicit --paths source root.
    sys.path.insert(0, str(repository / "kuma_core" / "kuro"))

import domain_process  # type: ignore[import-not-found]

# The private protocol must precede every public output and RPC initialization.
if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "--kuma-domain-supervisor":
    raise SystemExit(domain_process.supervisor_main(sys.argv[2]))

from kuma_core.shared.sidecar import JsonRpcWriter, loads_rpc_request
from kuma_core.shared.windows_rpc import BoundedUtf8LineReader, RpcLineError, windows_stdin_reader


def command(*arguments: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *arguments]
    return [sys.executable, "-I", "-S", str(Path(__file__).resolve()), *arguments]


def identity() -> dict:
    return {"frozen": bool(getattr(sys, "frozen", False)),
            "executable": str(Path(sys.executable).resolve()), "pid": os.getpid()}


def ipc() -> int:
    writer = JsonRpcWriter()
    reader = (windows_stdin_reader(sys.stdin.fileno()) if os.name == "nt" else
              BoundedUtf8LineReader(lambda: os.read(sys.stdin.fileno(), 16 * 1024)))
    workers: list[threading.Thread] = []
    while True:
        try:
            line = reader.readline()
            if not line:
                break
            request = loads_rpc_request(line)
        except (RpcLineError, json.JSONDecodeError) as exc:
            writer.error(None, -32700, str(exc))
            continue
        if not isinstance(request, dict):
            writer.error(None, -32600, "object required")
            continue
        request_id = request.get("id")
        method = request.get("method")
        text = request.get("params", {}).get("text", "")
        if method == "delay":
            def reply(identifier=request_id, value=text):
                time.sleep(0.2)
                writer.ok(identifier, {"text": value, **identity()})
            thread = threading.Thread(target=reply, daemon=True)
            workers.append(thread)
            thread.start()
        elif method == "echo":
            writer.ok(request_id, {"text": text, **identity()})
        elif method == "shutdown":
            for thread in workers:
                thread.join(3)
            writer.ok(request_id, {"ok": True})
            return 0
        else:
            writer.error(request_id, -32601, "unknown fixture method")
    return 0


def child(mode: str, work: Path) -> int:
    work = work.resolve(strict=True)
    if os.name != "nt" and mode != "success":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    marker = work / ("descendant.pid" if mode == "descendant" else "root.pid")
    staged = marker.with_suffix(".writing")
    staged.write_text(str(os.getpid()), encoding="ascii")
    staged.replace(marker)
    if mode == "success":
        (work / "result.json").write_text('{"fixture":true}', encoding="ascii")
        return 0
    if mode == "tree":
        subprocess.Popen(command("--child", "descendant", str(work)), close_fds=True)
    elif mode not in {"descendant", "sleep"}:
        return 2
    while True:
        time.sleep(0.05)


def managed_host(mode: str, work: Path, timeout: float) -> int:
    if mode not in {"cancel", "timeout", "hard_loss", "success"} or not 0.5 <= timeout <= 60:
        return 2
    writer = JsonRpcWriter()
    cancel = threading.Event()
    done = threading.Event()
    result: dict = {}
    work = work.resolve(strict=True)
    started = time.monotonic()

    def run() -> None:
        try:
            domain_process.run_managed_process(
                command("--child", "success" if mode == "success" else
                        "sleep" if mode == "timeout" else "tree", str(work)),
                cwd=work, cancelled=cancel.is_set, result_path=work / "result.json",
                timeout_seconds=timeout if mode == "timeout" else max(30.0, timeout),
                output_limit=65536, result_limit=4096,
            )
            result.update(outcome="ok")
        except domain_process.DomainProcessCancelled as exc:
            result.update(outcome="cancelled", message=str(exc)[:512])
        except domain_process.DomainProcessError as exc:
            result.update(outcome="error", message=str(exc)[:512])
        except Exception as exc:
            result.update(outcome="unexpected", message=f"{type(exc).__name__}: {exc}"[:512])
        finally:
            done.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    markers = [work / "root.pid"]
    if mode in {"cancel", "hard_loss"}:
        markers.append(work / "descendant.pid")
    deadline = time.monotonic() + 60
    while not all(path.exists() and path.stat().st_size for path in markers):
        if done.is_set() or time.monotonic() >= deadline:
            writer.send({"event": "failed_before_ready", "reason": "startup_did_not_reach_pid_marker",
                         **result, **identity()})
            return 1
        time.sleep(0.01)
    pids = [int(path.read_text(encoding="ascii")) for path in markers]
    writer.send({"event": "ready", "child_pids": pids, **identity()})
    if mode in {"cancel", "hard_loss"}:
        action = sys.stdin.readline().strip()
        if mode == "hard_loss" and action == "crash":
            # Abrupt host death: no finally/context/atexit cleanup executes.
            os._exit(91)
        if action != "cancel":
            cancel.set()
            raise ValueError("Unexpected fixture control command")
        cancel.set()
    if not done.wait(timeout + 20):
        writer.send({"event": "cleanup_pending", **identity()})
        return 1
    thread.join()
    writer.send({"event": "finished", **result, "elapsed_seconds": time.monotonic() - started,
                 "private_directory_removed": not list(work.glob("domain-private-*")), **identity()})
    return 0


def main() -> int:
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if sys.argv[1:] == ["--ipc"]:
        return ipc()
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        return child(sys.argv[2], Path(sys.argv[3]))
    if len(sys.argv) == 5 and sys.argv[1] == "--managed-host":
        return managed_host(sys.argv[2], Path(sys.argv[3]), float(sys.argv[4]))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
