"""Phase wall-time instrumentation for the MAME step2 (analyze/demux) pipeline.

Purpose
-------
Answer "which phase is what share of the total?" from a real run, without
changing any pipeline output.  The instrumentation is always on; it only adds
``time.perf_counter()`` pairs at *phase* granularity (per chunk, per well, per
call), never per read.

Two sinks
---------
1. ``logging``, at the end of each :meth:`PhaseTimer.session` a single INFO
   block lists every phase key with its seconds and its share of that session's
   wall time.
2. Optional JSON, when ``KUMA_MAME_TIMING_JSON`` names a path, each session
   also appends one JSON object per line (JSONL) to that file.  Sub-processes
   inherit the variable and append their own records, tagged with ``pid``, so a
   ProcessPool run leaves one record per worker plus the parent's.

Wall vs. summed time
--------------------
A session's ``wall_s`` is elapsed wall-clock time in the *reporting* process.
Phase keys suffixed ``_sum`` are summed across worker threads of that process
and can therefore exceed ``wall_s``; their percentage is share-of-wall, not a
partition.  Work done inside a ProcessPool worker is never folded into the
parent's phase keys: the parent measures only its own wall time for that
region (keys suffixed ``_parallel_wall``), and each worker emits its own
session record.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterable, Iterator, TypeVar

log = logging.getLogger(__name__)

_ENV_JSON_PATH = "KUMA_MAME_TIMING_JSON"

T = TypeVar("T")


class PhaseTimer:
    """Thread-safe accumulator of per-phase wall seconds.

    Accumulation is global to the process; :meth:`session` reports the *delta*
    accumulated inside its ``with`` block, so repeated calls of an instrumented
    function each report their own numbers.
    """

    __slots__ = ("_lock", "_seconds", "_counts")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seconds: dict[str, float] = {}
        self._counts: dict[str, int] = {}

    def add(self, name: str, seconds: float) -> None:
        with self._lock:
            self._seconds[name] = self._seconds.get(name, 0.0) + seconds
            self._counts[name] = self._counts.get(name, 0) + 1

    def snapshot(self) -> tuple[dict[str, float], dict[str, int]]:
        with self._lock:
            return dict(self._seconds), dict(self._counts)

    def reset(self) -> None:
        with self._lock:
            self._seconds.clear()
            self._counts.clear()

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Accumulate the wall time of the wrapped block under *name*."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.add(name, time.perf_counter() - t0)

    def begin(self) -> tuple[float, dict[str, float], dict[str, int]]:
        """Open a measurement window; pass the result to :meth:`end`."""
        base_s, base_c = self.snapshot()
        return time.perf_counter(), base_s, base_c

    def end(
        self,
        scope: str,
        baseline: tuple[float, dict[str, float], dict[str, int]],
        **extra: Any,
    ) -> None:
        """Close a :meth:`begin` window and report the phases inside it."""
        t0, base_s, base_c = baseline
        wall = time.perf_counter() - t0
        now_s, now_c = self.snapshot()
        phases = {
            k: v - base_s.get(k, 0.0)
            for k, v in now_s.items()
            if v - base_s.get(k, 0.0) > 0.0
        }
        counts = {k: now_c.get(k, 0) - base_c.get(k, 0) for k in phases}
        _report(scope, wall, phases, counts, extra)

    @contextmanager
    def session(self, scope: str, **extra: Any) -> Iterator[None]:
        """Measure a whole stage and report the phases accumulated inside it."""
        baseline = self.begin()
        try:
            yield
        finally:
            self.end(scope, baseline, **extra)


def _report(
    scope: str,
    wall: float,
    phases: dict[str, float],
    counts: dict[str, int],
    extra: dict[str, Any],
) -> None:
    ordered = sorted(phases.items(), key=lambda kv: kv[1], reverse=True)
    lines = [f"[perf] {scope}: wall {wall:.3f}s"]
    for name, seconds in ordered:
        pct = (seconds / wall * 100.0) if wall > 0 else 0.0
        lines.append(
            f"[perf]   {name:<34} {seconds:9.3f}s  {pct:5.1f}%  (n={counts.get(name, 0)})"
        )
    accounted = sum(
        s for k, s in phases.items() if not (k.endswith("_sum") or "." in k)
    )
    if wall > 0:
        lines.append(
            f"[perf]   {'(unattributed)':<34} {wall - accounted:9.3f}s  "
            f"{(wall - accounted) / wall * 100.0:5.1f}%"
        )
    log.info("\n".join(lines))

    path = os.environ.get(_ENV_JSON_PATH, "").strip()
    if not path:
        return
    record = {
        "scope": scope,
        "pid": os.getpid(),
        "timestamp": time.time(),
        "wall_s": wall,
        "phases_s": {k: round(v, 6) for k, v in ordered},
        "phase_counts": counts,
        **extra,
    }
    try:
        # One short append per session; O_APPEND makes concurrent worker writes
        # interleave at record granularity rather than corrupt each other.
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception as exc:  # noqa: BLE001 - instrumentation must never fail a run
        log.debug("timing JSON dump to %s failed: %s", path, exc)


def timed_iter(it: Iterable[T], name: str, timer: "PhaseTimer | None" = None) -> Iterator[T]:
    """Yield from *it*, charging only the time spent producing each item.

    Used for chunked generators so the producing cost (FASTQ read + parse) is
    separated from the consuming cost, with one timer pair per chunk.
    """
    tm = timer or TIMER
    iterator = iter(it)
    while True:
        t0 = time.perf_counter()
        try:
            item = next(iterator)
        except StopIteration:
            tm.add(name, time.perf_counter() - t0)
            return
        tm.add(name, time.perf_counter() - t0)
        yield item


#: Process-global timer used by the MAME pipeline.
TIMER = PhaseTimer()

__all__ = ["PhaseTimer", "TIMER", "timed_iter"]
