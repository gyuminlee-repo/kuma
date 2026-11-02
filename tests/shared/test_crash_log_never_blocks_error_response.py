"""A crash log that cannot be written must not swallow the RPC error reply.

Both sidecars log a handler failure before answering it. The log path used to
be built (directory created) outside the guarded writer, so an unwritable
config directory raised out of the ``except`` branch and the client got no
response at all. The writer promises "never raises"; the path has to be inside
that promise too.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _refuse_mkdir(self: Path, *args: object, **kwargs: object) -> None:
    raise PermissionError(f"read-only config directory: {self}")


@pytest.mark.parametrize("package", ["sidecar_mame", "sidecar_kuro"])
def test_the_error_reply_is_sent_when_the_log_directory_is_unwritable(
    package: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dispatcher = importlib.import_module(f"{package}.dispatcher")
    assert dispatcher.__file__ is not None
    assert str(Path(dispatcher.__file__).resolve()).startswith(
        str(Path(__file__).resolve().parents[2])
    ), "dispatcher imported from outside this checkout"

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setattr(Path, "mkdir", _refuse_mkdir)
    sent: list[tuple] = []
    monkeypatch.setattr(
        dispatcher, "_error", lambda req_id, code, msg: sent.append((req_id, code, msg))
    )

    def handler(_params: dict) -> dict:
        raise ValueError("bad request")

    dispatcher._dispatch_handler(7, "some.method", handler, {})

    assert sent == [(7, -32602, "bad request")]
