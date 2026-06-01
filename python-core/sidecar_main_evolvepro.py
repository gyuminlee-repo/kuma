"""JSON-RPC 2.0 entry point for the EVOLVEpro sidecar.

Communicates via stdin/stdout with the Tauri host using newline-delimited JSON.

Mirrors sidecar_main_kuro.py: emit the ready notification before the heavy
imports (pydantic, kuma_core) run so the host's READY_TIMEOUT budget is
decoupled from import latency. The host does not gate RPC dispatch on ready
(see src-tauri/src/sidecar.rs); ready is an informational boundary marker.
"""

import json
import sys
from pathlib import Path

# Ensure python-core/ is on sys.path so `sidecar_evolvepro` is importable
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
    from sidecar_evolvepro.dispatcher import main  # noqa: E402

    main(emit_ready=False)
