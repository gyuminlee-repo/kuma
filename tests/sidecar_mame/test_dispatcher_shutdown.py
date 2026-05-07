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
import time
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
                "main(emit_ready=False)"
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


class TestMameShutdownProcessExit:
    def test_shutdown_rpc_causes_process_exit_within_5s(self):
        """Dispatcher exits after shutdown RPC while stdin remains open."""
        proc = _spawn_mame_dispatcher()
        try:
            shutdown_msg = json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "shutdown", "params": {}}
            ) + "\n"
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(shutdown_msg)
            proc.stdin.flush()
            # stdin is intentionally NOT closed — exit must come from shutdown handler

            # Read ack from stdout
            deadline = time.monotonic() + 5.0
            ack_received = False
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.strip())
                    if msg.get("id") == 1 and "result" in msg:
                        ack_received = True
                        break
                except json.JSONDecodeError:
                    pass

            # Process must exit with stdin open — proves shutdown handler drove the exit
            exit_code = proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        assert ack_received, "Expected shutdown ack before process exit"
        assert exit_code == 0, f"Expected exit code 0, got {exit_code}"

    def test_dispatcher_exits_cleanly_not_via_sigkill(self):
        """Exit code 0 (clean), not negative (signal-killed)."""
        proc = _spawn_mame_dispatcher()
        try:
            msg = json.dumps(
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}}
            ) + "\n"
            assert proc.stdin is not None
            proc.stdin.write(msg)
            proc.stdin.flush()
            # stdin NOT closed
            exit_code = proc.wait(timeout=5)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        assert exit_code == 0, (
            f"Expected clean exit (0), got {exit_code}. "
            "Negative codes indicate signal-based termination."
        )
