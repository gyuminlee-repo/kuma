"""Shared newline-delimited JSON-RPC client for the frozen sidecar smoke tests.

``frozen_kuro_smoke.py`` and ``frozen_mame_smoke.py`` both need the same
transport: spawn the frozen binary, write one JSON object per line to stdin,
read one JSON object per line from stdout, match responses by ``id``, skip
notifications, and turn stdout EOF into a hard failure instead of a hang.
Two copies drifted apart and the MAME copy silently lost the ``saw_ready``
diagnostic, which is the single most valuable signal these scripts produce.
One copy lives here.

Why this is shared while the synthetic fixtures are NOT:
``frozen_mame_smoke.py`` deliberately mirrors the fixture constants from
``tests/mame/test_combinatorial_demux.py`` rather than importing them, so a
change to the pytest fixtures cannot silently change what CI asserts about a
release binary. That argument is about *test data*. It does not extend to the
RPC transport, which has no assertions in it and whose duplication was pure
drift risk. The fixture mirroring stays as it is.

Frozen-binary note: only the *sidecar under test* is a PyInstaller binary.
Both smoke scripts are invoked as ``python python-core/scripts/frozen_*.py``
from the repo checkout (``.github/workflows/build.yml:239`` and ``:243``), so
this module is imported by ordinary CPython from the script directory and
needs no PyInstaller hidden-import or bundling change.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


def rpc_request(id_: int, method: str, params: dict[str, Any]) -> str:
    """Serialise one JSON-RPC 2.0 request as a single line (no trailing newline)."""
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params})


# ---------------------------------------------------------------------------
# Cross-platform sidecar I/O: daemon reader thread + queue
#
# queue.Queue avoids select() (broken on Windows named-pipe handles) and
# signal.alarm() (Unix-only). The reader thread blocks on proc.stdout and
# pushes each decoded JSON object into the queue; EOF pushes the None sentinel,
# which is what turns "ready then died" into a hard failure instead of a hang.
# ---------------------------------------------------------------------------


class SidecarIO:
    """Drive a frozen sidecar over newline-delimited JSON-RPC 2.0."""

    def __init__(
        self,
        binary: Path,
        stderr_path: Path,
        env: dict[str, str] | None = None,
    ) -> None:
        self._stderr_fh = open(stderr_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_fh,
            text=True,
            bufsize=1,
            env=env,
        )
        # Set when the sidecar emits its ``ready`` notification. ``ready`` is
        # sent BEFORE the heavy imports, so "saw_ready and then EOF" is the
        # v0.13.17 import-crash shape and is distinguishable from "never
        # started at all".
        self.saw_ready = False
        self._q: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        try:
            # readline() loop (not `for line in stdout`) so a response is not
            # held in the iterator read-ahead buffer until more output arrives.
            while True:
                raw_line = self.proc.stdout.readline()
                if not raw_line:  # EOF
                    break
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    obj = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    print(f"[reader] JSONDecodeError on line {raw_line!r}: {exc}",
                          file=sys.stderr)
                    continue
                self._q.put(obj)
        finally:
            self._q.put(None)  # sentinel: reader done (EOF or exception)

    def send(self, payload: str) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(payload + "\n")
        self.proc.stdin.flush()

    def recv(self, req_id: int, timeout: float) -> dict[str, Any]:
        """Block until a response with matching id arrives, skipping notifications.

        Raises TimeoutError on timeout; raises RuntimeError on process EOF.
        """
        t0 = time.monotonic()
        while True:
            remaining = timeout - (time.monotonic() - t0)
            if remaining <= 0:
                raise TimeoutError(f"No response for id={req_id} within {timeout}s")
            try:
                obj = self._q.get(timeout=min(remaining, 1.0))
            except queue.Empty:
                continue
            if obj is None:
                raise RuntimeError(
                    f"sidecar stdout closed before responding to id={req_id} "
                    f"(ready notification seen: {self.saw_ready}) - "
                    f"the process died without answering, the v0.13.17 import-crash shape"
                )
            # Skip JSON-RPC notifications (ready, progress, etc.)
            if "method" in obj:
                if obj.get("method") == "ready":
                    self.saw_ready = True
                continue
            if obj.get("id") == req_id:
                return obj
            print(f"[recv] skipping unexpected id={obj.get('id')!r} while waiting for {req_id}",
                  file=sys.stderr)

    def close(self, timeout: float = 10.0) -> int:
        """Close stdin, wait for process exit; kill if stuck. Returns exit code."""
        if self.proc.stdin:
            try:
                self.proc.stdin.close()
            except OSError as exc:
                print(f"[close] stdin close error (ignored): {exc}", file=sys.stderr)
        try:
            rc = self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            rc = self.proc.wait()
        self._stderr_fh.flush()
        self._stderr_fh.close()
        return rc


__all__ = ["SidecarIO", "rpc_request"]
