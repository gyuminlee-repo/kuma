import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PING = '{"jsonrpc":"2.0","id":2,"method":"ping"}'
SHUTDOWN = '{"jsonrpc":"2.0","id":3,"method":"shutdown"}'


def run_sidecar(kind: str, first_line: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "python-core" / f"sidecar_main_{kind}.py")],
        input=f"{first_line}\n{PING}\n{SHUTDOWN}\n",
        text=True,
        capture_output=True,
        cwd=ROOT,
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize("kind", ["kuro", "mame"])
@pytest.mark.parametrize(
    "first_line,code",
    [
        ("{", -32700),
        ("null", -32600),
        ("[]", -32600),
        ('"ping"', -32600),
        ("42", -32600),
        ("true", -32600),
        ("{}", -32600),
        ('{"id":1,"method":[]}', -32600),
        ('{"id":1,"method":{}}', -32600),
        ('{"id":1,"method":null}', -32600),
        ('{"id":1,"method":7}', -32600),
        ('{"id":1,"method":false}', -32600),
        ('{"jsonrpc":"2.0","id":1,"method":"unknown"}', -32601),
    ],
)
def test_error_then_ping_survives_invalid_input(
    kind: str, first_line: str, code: int
) -> None:
    # Given a real sidecar, when an invalid line precedes ping and shutdown.
    result = run_sidecar(kind, first_line)

    # Then the error is framed correctly and neither later request is lost.
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert replies[0] == {"jsonrpc": "2.0", "method": "ready", "params": {}}
    responses = [reply for reply in replies if "id" in reply]
    assert len(responses) == 3, replies
    error, pong, ack = responses
    assert error["jsonrpc"] == "2.0"
    assert error["id"] == (1 if code == -32601 else None)
    assert error["error"]["code"] == code
    assert isinstance(error["error"]["message"], str)
    assert "result" not in error
    assert pong == {"jsonrpc": "2.0", "id": 2, "result": {"ok": True}}
    assert ack == {
        "jsonrpc": "2.0", "id": 3,
        "result": {"ok": True, "message": "shutdown_acked"},
    }


@pytest.mark.parametrize("kind", ["kuro", "mame"])
def test_idless_ping_preserves_existing_response(kind: str) -> None:
    # Given the existing id-less request behavior, when ping has no id.
    result = run_sidecar(kind, '{"jsonrpc":"2.0","method":"ping"}')

    # Then preserve the legacy null-id reply and the ready notification.
    assert result.returncode == 0, result.stderr
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert replies[0] == {"jsonrpc": "2.0", "method": "ready", "params": {}}
    assert replies[1] == {"jsonrpc": "2.0", "id": None, "result": {"ok": True}}


@pytest.mark.parametrize("kind", ["kuro", "mame"])
@pytest.mark.parametrize("with_id", [True, False])
def test_shutdown_exits_with_stdin_open(kind: str, with_id: bool) -> None:
    # Given a real process with an open input pipe.
    with subprocess.Popen(
        [sys.executable, str(ROOT / "python-core" / f"sidecar_main_{kind}.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=ROOT,
    ) as proc:
        assert proc.stdin is not None
        assert proc.stdout is not None
        assert proc.stderr is not None
        try:
            # When shutdown is requested without closing stdin.
            request = SHUTDOWN if with_id else '{"jsonrpc":"2.0","method":"shutdown"}'
            proc.stdin.write(request + "\n")
            proc.stdin.flush()
            proc.wait(timeout=30)
            # Then shutdown itself terminates the process after flushing its ack.
            assert proc.returncode == 0, proc.stderr.read()
            replies = [json.loads(line) for line in proc.stdout.read().splitlines()]
            assert replies[-1] == {
                "jsonrpc": "2.0", "id": 3 if with_id else None,
                "result": {"ok": True, "message": "shutdown_acked"},
            }
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
