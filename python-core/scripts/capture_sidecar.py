from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from scripts.smoke_sidecar_io import SidecarIO, rpc_request


class Sidecar:
    def __init__(self, binary: Path) -> None:
        self._io = SidecarIO(binary, Path(os.devnull))
        self._proc = self._io.proc
        self._next_id = 0

    def call(self, method: str, params: dict, timeout_s: float = 900.0) -> dict:
        self._next_id += 1
        self._io.send(rpc_request(self._next_id, method, params))
        message = self._io.recv(self._next_id, timeout_s)
        if "error" in message:
            raise RuntimeError(f"{method}: {json.dumps(message['error'], ensure_ascii=False)}")
        return message["result"]

    def close(self, timeout_s: float = 10.0) -> None:
        try:
            self.call("shutdown", {}, timeout_s=timeout_s)
        except (TimeoutError, RuntimeError, OSError) as exc:
            print(f"[capture] shutdown acknowledgement unavailable: {exc}", file=sys.stderr)
        finally:
            self._io.close(timeout=timeout_s)
