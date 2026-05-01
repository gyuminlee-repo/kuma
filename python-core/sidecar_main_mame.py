"""MAME sidecar entry point.

JSON-RPC 2.0 over stdin/stdout (newline-delimited JSON).

Same cold-start trick as KURO: emit the ready notification before importing
the dispatcher so the host does not hit READY_TIMEOUT while heavy imports
finish on Windows + AV first launches.
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
    _emit_ready_now()
    from sidecar_mame.dispatcher import main  # noqa: E402
    main(emit_ready=False)
