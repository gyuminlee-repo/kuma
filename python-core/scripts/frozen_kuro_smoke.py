#!/usr/bin/env python3
"""Frozen KURO sidecar smoke test.

Launches the frozen (PyInstaller) KURO sidecar binary and drives it over
newline-delimited JSON-RPC 2.0 to prove the process is actually usable, not
merely present on disk.

Motivation (v0.13.17 incident): ``sidecar_main_kuro.py`` emits the ``ready``
notification BEFORE triggering the heavy imports (numpy / pandas / biopython).
A crash inside those imports (e.g. a non-UTF-8 Windows locale) therefore looks
like "ready, then silence" and every subsequent RPC fails with
"Sidecar process exited". CI only checked that the binary file existed, so the
broken build shipped. This script detects that shape via two independent
checks:

  1. RPC liveness: ``ping`` and ``load_fasta`` must return real responses. A
     ready-then-die sidecar hits EOF on stdout and fails here.
  2. stderr marker: ``KURO sidecar started`` is logged by
     ``sidecar_kuro/dispatcher.py:main()`` AFTER the heavy imports complete.
     Its absence means the import stage never finished.

Usage:
    python frozen_kuro_smoke.py <path-to-frozen-kuro-sidecar> [fixture.gb]

Exit codes:
    0 = PASS
    1 = FAIL (with diagnostic output, including captured sidecar stderr)
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

# Repo root = <repo>/python-core/scripts/frozen_kuro_smoke.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FIXTURE = _REPO_ROOT / "fixtures" / "pSHCE-dmpR.gb"

# Timeouts (seconds). Generous: a cold --onefile launch on a Windows CI runner
# with AV scanning can take 10-20s before the main loop drains stdin.
_PING_TIMEOUT = 90.0
_LOAD_FASTA_TIMEOUT = 120.0
_SHUTDOWN_TIMEOUT = 15.0

_STARTED_MARKER = "KURO sidecar started"


def _rpc(id_: int, method: str, params: dict[str, Any]) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params})


class _SidecarDead(Exception):
    """Internal: stop driving RPCs once the sidecar is known to be gone."""


# ---------------------------------------------------------------------------
# Cross-platform sidecar I/O: daemon reader thread + queue
#
# queue.Queue avoids select() (broken on Windows named-pipe handles) and
# signal.alarm() (Unix-only). The reader thread blocks on proc.stdout and
# pushes each decoded JSON object into the queue; EOF pushes the None sentinel,
# which is what turns "ready then died" into a hard failure instead of a hang.
# ---------------------------------------------------------------------------

class SidecarIO:

    def __init__(self, binary: Path, stderr_path: Path) -> None:
        self._stderr_fh = open(stderr_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self._stderr_fh,
            text=True,
            bufsize=1,
        )
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


# ---------------------------------------------------------------------------
# Main smoke test
# ---------------------------------------------------------------------------

def run_smoke(binary: Path, fixture: Path) -> None:
    workdir = Path(tempfile.mkdtemp(prefix="kuro_smoke_"))
    stderr_path = workdir / "sidecar_stderr.txt"
    sio: SidecarIO | None = None
    failures: list[str] = []

    try:
        sio = SidecarIO(binary, stderr_path)

        # --- ping ---
        print("[1/3] ping ...")
        sio.send(_rpc(1, "ping", {}))
        try:
            ping_resp = sio.recv(1, timeout=_PING_TIMEOUT)
            if "error" in ping_resp:
                failures.append(f"ping RPC error: {ping_resp['error']}")
            elif ping_resp.get("result", {}).get("ok") is not True:
                failures.append(f"ping: ok is not True - got {ping_resp!r}")
            else:
                print("      ping OK")
        except (TimeoutError, RuntimeError) as exc:
            failures.append(f"ping failed: {exc}")
            # The sidecar is dead or wedged. Writing further requests would only
            # raise BrokenPipeError and bury the real diagnostic, so stop here.
            raise _SidecarDead from exc

        # --- load_fasta (real repo fixture: exercises biopython + parsing) ---
        print(f"[2/3] load_fasta ({fixture.name}) ...")
        sio.send(_rpc(2, "load_fasta", {"filepath": str(fixture)}))
        try:
            load_resp = sio.recv(2, timeout=_LOAD_FASTA_TIMEOUT)
            if "error" in load_resp:
                failures.append(f"load_fasta RPC error: {load_resp['error']}")
            else:
                load_result = load_resp.get("result", {})
                seq_length = load_result.get("seq_length")
                genes = load_result.get("genes")
                if not isinstance(seq_length, int) or seq_length <= 0:
                    failures.append(
                        f"load_fasta: seq_length={seq_length!r}, expected a positive int"
                    )
                elif not isinstance(genes, list):
                    failures.append(
                        f"load_fasta: genes is not a list - got {type(genes).__name__!r}"
                    )
                elif not genes:
                    failures.append(
                        f"load_fasta: genes is empty, expected >= 1 annotated gene "
                        f"from {fixture.name}"
                    )
                else:
                    print(f"      load_fasta OK - seq_length={seq_length}, "
                          f"genes={len(genes)} ({[g.get('gene') for g in genes[:5]]})")
        except (TimeoutError, RuntimeError) as exc:
            failures.append(f"load_fasta failed: {exc}")

        # --- shutdown ---
        print("[3/3] shutdown ...")
        sio.send(_rpc(3, "shutdown", {}))
        try:
            sio.recv(3, timeout=_SHUTDOWN_TIMEOUT)
            print("      shutdown ack received")
        except (TimeoutError, RuntimeError) as exc:
            # Ack may not arrive before EOF; process exit is the criterion.
            print(f"      shutdown ack not received ({exc}); waiting for process exit")

        rc = sio.close(timeout=_SHUTDOWN_TIMEOUT)
        print(f"      sidecar exit code: {rc}")
        sio = None

    except _SidecarDead:
        print("      sidecar is gone; skipping remaining RPCs")
    except OSError as exc:
        failures.append(f"OS error driving sidecar: {exc}")
    finally:
        if sio is not None:
            sio.close(timeout=5.0)
            sio = None

    # --- stderr analysis (after the process is dead so the buffer is flushed) ---
    print("\n[stderr analysis]")
    stderr_lines: list[str] = []
    if stderr_path.exists():
        stderr_lines = stderr_path.read_text(encoding="utf-8", errors="replace").splitlines()

    started_count = sum(1 for line in stderr_lines if _STARTED_MARKER in line)
    print(f"      '{_STARTED_MARKER}' occurrences in stderr: {started_count}")

    if started_count == 0:
        # main() logs this only after the heavy imports succeed, so a missing
        # marker pins the failure to the import stage even when stdout looks fine.
        failures.append(
            f"import check: '{_STARTED_MARKER}' not found in stderr - the dispatcher "
            f"main loop never started, so the heavy imports crashed (v0.13.17 shape)"
        )
    else:
        print("      import check OK: dispatcher main loop reached")

    # --- Final report ---
    print()
    if failures:
        print("=" * 60)
        print("FROZEN KURO SMOKE: FAIL")
        print("=" * 60)
        for i, msg in enumerate(failures, 1):
            print(f"  [{i}] {msg}")
        print()
        print("--- sidecar stderr (last 40 lines) ---")
        if stderr_lines:
            for line in stderr_lines[-40:]:
                print(f"  {line}")
        else:
            print("  (empty)")
        sys.exit(1)
    else:
        print("=" * 60)
        print("FROZEN KURO SMOKE: PASS")
        print("=" * 60)
        sys.exit(0)


def main() -> None:
    if len(sys.argv) not in (2, 3):
        print(f"Usage: {sys.argv[0]} <path-to-frozen-kuro-sidecar> [fixture.gb]")
        sys.exit(1)

    binary = Path(sys.argv[1])
    if not binary.exists():
        print(f"FAIL: sidecar binary not found: {binary}")
        sys.exit(1)
    if not os.access(binary, os.X_OK):
        print(f"FAIL: sidecar binary is not executable: {binary}")
        sys.exit(1)

    fixture = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else _DEFAULT_FIXTURE
    if not fixture.exists():
        print(f"FAIL: fixture not found: {fixture}")
        sys.exit(1)

    print("Frozen KURO sidecar smoke test")
    print(f"Binary: {binary}")
    print(f"Fixture: {fixture}")
    print(f"Platform: {sys.platform}")
    print()

    run_smoke(binary, fixture)


if __name__ == "__main__":
    main()
