"""One malformed request line must not end the sidecar session.

Both stdin loops answer :class:`json.JSONDecodeError` with a ``-32700`` parse
error and catch nothing else. ``json`` does not raise only that type: a number
literal longer than the interpreter integer-string limit raises a plain
``ValueError``, and a deeply nested payload raises ``RecursionError``. Measured
before the fix, either one unwound out of ``main`` and the process exited with
code 1, leaving that request unanswered and every later request on the session
lost.

A unit test that :func:`loads_rpc_request` raises the right type is necessary
but does not show that the process survives, so this file spawns the real
dispatcher the way ``test_dispatcher_shutdown.py`` does and asks it a question
after the bad line. Each case sends a control request first: if the control is
unanswered the harness is broken and the case proves nothing, so a dead process
can never read as a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"

# Above the 4300-digit interpreter limit for integer string conversion, which
# is where the plain ValueError comes from.
_HUGE_INT_LINE = (
    '{"jsonrpc":"2.0","id":2,"method":"ping","params":{"n":' + "9" * 4400 + "}}"
)
# Well above the depth at which the C scanner gives up. Measured on this
# machine (Python 3.12) the boundary sits between 5000 and 10000; 100000 is far
# enough past it that a different interpreter build cannot land under it.
_DEEP_LINE = '{"params":' + "[" * 100000 + "]" * 100000 + "}"


def _spawn(module: str) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(_SIDECAR_DIR)!r}); "
                f"from {module}.dispatcher import main; "
                "main(emit_ready=False)"
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def _ping(req_id: int) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": req_id, "method": "ping", "params": {}}
    )


def _replies(stdout: str) -> dict:
    """Map request id to reply. Notifications (no id) are ignored."""
    out = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and ("result" in msg or "error" in msg):
            out[msg.get("id")] = msg
    return out


@pytest.mark.parametrize("module", ["sidecar_kuro", "sidecar_mame"])
def test_a_malformed_line_does_not_end_the_session(module: str) -> None:
    """Send a control, two unparseable lines, and a control after each.

    The two loops are byte-identical from ``line = sys.stdin.readline()`` to
    ``dispatch(request)``; they differ only in a docstring and two log strings.
    Both are spawned here anyway, because this repo has shipped a fix to one
    copy of a duplicated loop and not the other.
    """
    proc = _spawn(module)
    try:
        payload = "\n".join(
            [_ping(1), _HUGE_INT_LINE, _ping(3), _DEEP_LINE, _ping(5)]
        ) + "\n"
        stdout, stderr = proc.communicate(input=payload, timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    replies = _replies(stdout)

    # The control. Without it a process that died on line 1 would look the same
    # as one that answered nothing for an unrelated reason.
    assert 1 in replies, (
        f"{module}: the control request before the malformed lines was not "
        f"answered, so this case measured nothing. stderr={stderr[-400:]!r}"
    )
    assert replies[1].get("result") == {"ok": True}

    for req_id, after in ((3, "the over-long integer literal"), (5, "the deeply nested payload")):
        assert req_id in replies, (
            f"{module}: no reply to the request sent after {after}; the "
            f"session ended on one malformed line. "
            f"exit={proc.returncode} stderr={stderr[-400:]!r}"
        )
        assert replies[req_id].get("result") == {"ok": True}

    # Closing stdin is the only thing that should end this process, so a clean
    # exit is part of the claim.
    assert proc.returncode == 0, (
        f"{module}: expected a clean exit after stdin closed, got "
        f"{proc.returncode}. stderr={stderr[-400:]!r}"
    )


@pytest.mark.parametrize("module", ["sidecar_kuro", "sidecar_mame"])
def test_the_malformed_lines_are_answered_with_a_parse_error(module: str) -> None:
    """Refusing the line is not enough; the caller has to be told.

    Both loops reply ``-32700`` with a null id, because an unparseable line has
    no id to quote back.
    """
    proc = _spawn(module)
    try:
        payload = "\n".join([_ping(1), _HUGE_INT_LINE]) + "\n"
        stdout, stderr = proc.communicate(input=payload, timeout=60)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    replies = _replies(stdout)
    assert 1 in replies, (
        f"{module}: control unanswered, this case measured nothing. "
        f"stderr={stderr[-400:]!r}"
    )
    assert None in replies, (
        f"{module}: the malformed line drew no parse error at all. "
        f"exit={proc.returncode} stderr={stderr[-400:]!r}"
    )
    error = replies[None]["error"]
    assert error["code"] == -32700, error
    assert "Parse error" in error["message"], error
