"""JSON-RPC 2.0 dispatcher for KURO sidecar.

Communicates via stdin/stdout with the Tauri host.
Protocol: one JSON object per line (newline-delimited JSON).

The dispatcher package transitively imports numpy / pandas / biopython, which
on a cold PyInstaller --onefile launch (Windows + AV) can cost 10-20 seconds
before any code in the package runs. The host enforces a ready timeout, so we
emit the ready notification as the very first thing — before importing the
dispatcher — and let the host enqueue requests on stdin while the heavy
imports finish in the background.
"""

import json
import sys
from pathlib import Path

# Ensure python-core/ is on sys.path so `sidecar_kuro` package is importable
# regardless of cwd (PyInstaller frozen build, direct invocation, tests).
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _emit_ready_now() -> None:
    """Send the ready notification before any heavy import runs."""
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    payload = json.dumps({"jsonrpc": "2.0", "method": "ready", "params": {}})
    sys.stdout.write(payload + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    _emit_ready_now()
    # Heavy imports happen below; the host already saw ready, so the
    # READY_TIMEOUT budget is effectively decoupled from import time.
    from sidecar_kuro.dispatcher import main  # noqa: E402
    main(emit_ready=False)
