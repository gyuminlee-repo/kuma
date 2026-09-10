"""Shared helpers for the round-2/round-3-1 A/A'/B/C benchmark extension.

Generalises 260812_MAME_regression/scripts/mame_common.py: the worktree
(code variant) and the guard mark are read from environment variables
instead of being hardcoded, so the same module works for the arm-A
(samtools-ab-baseline, origin/main-equivalent) and arm-A' (rounds-ab,
a9a71227) code checkouts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

KUMA_WT = Path(os.environ["KUMA_WT"])
GUARD_MARK = os.environ["GUARD_MARK"]
sys.path.insert(0, str(KUMA_WT))

import kuma_core.mame.ingest.run_pipeline as _rp  # noqa: E402

if GUARD_MARK not in _rp.__file__.replace("\\", "/"):
    raise SystemExit(
        f"ABORT: expected code not loaded. mark={GUARD_MARK} "
        f"run_pipeline.__file__={_rp.__file__}"
    )


def log_open(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8", buffering=1)
