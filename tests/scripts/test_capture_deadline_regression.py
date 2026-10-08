import importlib.util
import os
import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="Synthetic executable peer uses a POSIX shebang")


@pytest.mark.parametrize("name", ["gen_real_capture_data", "gen_mame_capture_data"])
@pytest.mark.parametrize("mode", ["silent", "reply", "eof", "silent_close"])
def test_capture_pipe_deadline(tmp_path: Path, name: str, mode: str) -> None:
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    peer = tmp_path / "peer"
    peer.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, time\n"
        f"mode = {mode!r}\n"
        "for line in sys.stdin:\n"
        "    req = json.loads(line)\n"
        "    if mode in ('silent', 'silent_close'): time.sleep(30)\n"
        "    if mode == 'eof': break\n"
        "    print(json.dumps({'method': 'progress', 'params': {}}), flush=True)\n"
        "    print(json.dumps({'id': req['id'], 'result': {'ok': True}}), flush=True)\n"
        "    if req['method'] == 'shutdown': break\n",
        encoding="utf-8",
    )
    peer.chmod(0o755)
    client = module.Sidecar(peer)
    watchdog = threading.Timer(2.0, client._proc.kill)
    watchdog.start()
    started = time.monotonic()
    try:
        if mode == "silent":
            with pytest.raises(TimeoutError):
                client.call("ping", {}, timeout_s=0.1)
            assert time.monotonic() - started < 1.0
        elif mode == "silent_close":
            client.close(timeout_s=0.1)
            assert time.monotonic() - started < 1.0
            assert client._proc.poll() is not None
            assert not client._io._reader.is_alive()
            assert client._proc.stdout.closed
        elif mode == "eof":
            with pytest.raises(RuntimeError, match="closed"):
                client.call("ping", {}, timeout_s=1.0)
        else:
            assert client.call("ping", {}, timeout_s=1.0) == {"ok": True}
            client.close()
            assert client._proc.poll() == 0
    finally:
        watchdog.cancel()
        watchdog.join()
        if client._proc.poll() is None:
            client._proc.kill()
        client._proc.wait(timeout=5)
        for stream in (client._proc.stdin, client._proc.stdout):
            if stream is not None:
                stream.close()
