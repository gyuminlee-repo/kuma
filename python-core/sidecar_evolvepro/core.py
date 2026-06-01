"""Shared state and stdout writer for the EVOLVEpro sidecar.

Ports evolvepro-gui/python-core/sidecar/core.py. Adds the sys.path bootstrap
(mirroring sidecar_kuro/core.py) so ``kuma_core.*`` imports resolve from any
working directory, whether run directly, under PyInstaller, or from tests.
"""
from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Ensure the project root is importable so `kuma_core.*` resolves regardless of
# cwd (PyInstaller frozen build, direct invocation, tests).
_SCRIPT_DIR = Path(__file__).parent.parent.resolve()  # python-core/
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@dataclass
class SidecarState:
    evolvepro_runs: dict[str, Any] = field(default_factory=dict)


_state = SidecarState()
_state_lock = threading.Lock()

_send_lock = threading.Lock()


def _send(payload: dict) -> None:
    """Write a JSON object to stdout (one line). Thread-safe."""
    with _send_lock:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()
