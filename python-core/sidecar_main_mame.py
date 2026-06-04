"""MAME sidecar entry point.

JSON-RPC 2.0 over stdin/stdout (newline-delimited JSON).

The host no longer gates RPC dispatch on the ready notification (see
`src-tauri/src/sidecar.rs::ensure_spawned`); requests are written to stdin
immediately and the OS pipe queues them until the python main loop drains.
The ready emit here is kept as a diagnostic boundary marker only.
"""

import json
import sys
from pathlib import Path

# Ensure python-core/ is on sys.path so ``sidecar_mame`` is importable
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
    import multiprocessing

    # Must run before any ProcessPool spawn so frozen Windows children do not
    # re-run the RPC loop or emit a second ready notification.
    multiprocessing.freeze_support()
    _emit_ready_now()
    from sidecar_mame.dispatcher import main  # noqa: E402
    main(emit_ready=False)
