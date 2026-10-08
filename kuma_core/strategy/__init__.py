"""Strategy package for KUMA combinatorial switching signals.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §12-A
Phase 6 Task 6.1 — signal computation only.
Classifier logic (advisory/auto decision) is v0.3+.
"""

from kuma_core.strategy.classify import (
    classify,
    compute_signals,
    Decision,
    Signals,
    RoundState,
)

__all__ = [
    "classify",
    "compute_signals",
    "Decision",
    "Signals",
    "RoundState",
]
