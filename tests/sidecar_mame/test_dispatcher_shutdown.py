"""Tests for the §22 graceful shutdown RPC in the mame sidecar dispatcher.

Subprocess tests keep stdin OPEN to verify that the dispatcher exits due to the
shutdown RPC, not due to stdin closing. If the break-on-shutdown logic were
removed, proc.wait() would block indefinitely (stdin never closes).
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"
if str(_SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_DIR))

from sidecar_mame.dispatcher import dispatch  # noqa: E402


# ---------------------------------------------------------------------------
# In-process dispatch: verify shutdown ack response structure
# ---------------------------------------------------------------------------


def _dispatch_capture(request: dict) -> dict:
    """Call dispatch() in-process and capture the JSON response."""
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        dispatch(request)
    finally:
        sys.stdout = old_stdout

    for line in buf.getvalue().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == request.get("id") and ("result" in msg or "error" in msg):
            return msg
    raise AssertionError(f"no response captured; stdout={buf.getvalue()!r}")


class TestMameShutdownRpcResponse:
    def test_shutdown_returns_ack(self):
        resp = _dispatch_capture(
            {"jsonrpc": "2.0", "id": 99, "method": "shutdown", "params": {}}
        )
        assert "result" in resp, f"expected result, got: {resp}"
        assert resp["result"]["ok"] is True
        assert resp["result"]["message"] == "shutdown_acked"

    def test_shutdown_ack_has_jsonrpc_envelope(self):
        resp = _dispatch_capture(
            {"jsonrpc": "2.0", "id": 100, "method": "shutdown", "params": {}}
        )
        assert resp.get("jsonrpc") == "2.0"
        assert resp.get("id") == 100

    def test_shutdown_not_in_async_methods(self):
        from sidecar_mame.dispatcher import _ASYNC_METHODS
        assert "shutdown" not in _ASYNC_METHODS, (
            "shutdown must run on the main thread, not a worker thread"
        )


# ---------------------------------------------------------------------------
# Subprocess: verify the dispatcher process exits due to the shutdown RPC.
# stdin is kept OPEN — if the feature were absent, proc.wait() would block.
# ---------------------------------------------------------------------------


def _spawn_mame_dispatcher() -> subprocess.Popen:
    """Spawn a mame dispatcher subprocess with stdin/stdout pipes."""
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(_SIDECAR_DIR)!r}); "
                "from sidecar_mame.dispatcher import main; "
                "main()"
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _shutdown_dispatcher(request_id: int) -> int:
    """Wait for ready, drain both pipes, and bound shutdown independently."""
    proc = _spawn_mame_dispatcher()
    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None
    stdout_pipe = proc.stdout
    stderr_pipe = proc.stderr
    ready = threading.Event()
    ack = threading.Event()
    stdout: list[str] = []
    stderr: list[str] = []

    def collect_stdout() -> None:
        for line in stdout_pipe:
            stdout.append(line)
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("method") == "ready":
                ready.set()
            if msg.get("id") == request_id and msg.get("result", {}).get("ok") is True:
                ack.set()

    def collect_stderr() -> None:
        stderr.extend(stderr_pipe)

    readers = [
        threading.Thread(target=collect_stdout, daemon=True),
        threading.Thread(target=collect_stderr, daemon=True),
    ]
    for reader in readers:
        reader.start()
    failure = ""
    exit_code = None
    try:
        if not ready.wait(timeout=30):
            failure = "Dispatcher did not emit ready within 30s"
        else:
            proc.stdin.write(json.dumps({
                "jsonrpc": "2.0", "id": request_id, "method": "shutdown", "params": {},
            }) + "\n")
            proc.stdin.flush()
            # stdin stays open: only the shutdown RPC may drive this exit.
            try:
                exit_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                failure = "Dispatcher did not exit within 5s after ready + shutdown"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)
        proc.stdin.close()
        proc.stdout.close()
        proc.stderr.close()

    diagnostics = f"stdout={''.join(stdout)!r}\nstderr={''.join(stderr)!r}"
    assert not failure, f"{failure}\n{diagnostics}"
    assert all(not reader.is_alive() for reader in readers), diagnostics
    assert ack.is_set(), f"Expected shutdown ack before exit\n{diagnostics}"
    assert exit_code == 0, f"Expected clean exit (0), got {exit_code}\n{diagnostics}"
    return exit_code


class TestMameShutdownProcessExit:
    def test_shutdown_rpc_causes_process_exit_within_5s(self):
        """Dispatcher exits after shutdown RPC while stdin remains open."""
        assert _shutdown_dispatcher(1) == 0

    def test_dispatcher_exits_cleanly_not_via_sigkill(self):
        """Exit code 0 (clean), not negative (signal-killed)."""
        assert _shutdown_dispatcher(2) == 0
