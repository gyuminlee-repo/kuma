"""JSON-RPC 2.0 dispatcher for KURO sidecar.

Communicates via stdin/stdout with the Tauri host.
Protocol: one JSON object per line (newline-delimited JSON).

This file is the thin entry point only.
All logic lives in the sidecar/ package.
"""

import sys
from pathlib import Path

# Ensure python-core/ is on sys.path so `sidecar` package is importable
# regardless of cwd (PyInstaller frozen build, direct invocation, tests).
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from sidecar_kuro.dispatcher import main  # noqa: E402

if __name__ == "__main__":
    main()
