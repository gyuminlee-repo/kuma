"""Process-lifecycle machinery both sidecar dispatchers run.

The KURO and MAME dispatchers carried byte-identical copies of the memory
monitor and the clean-exit helper, and near-identical copies of the parent
watchdog. Keeping two copies means a fix lands on one sidecar and not the
other, which is one of the two defect families this repository's audit kept
finding.

What stays in each dispatcher is what genuinely differs: the method registry,
the error-code mapping, and the stdin loop's log strings.

The memory decision is a pure function rather than a step inside the thread.
The notification it produces crosses three layers (here, the Rust forwarder,
then `src/store/appStore.ts`), and nothing could reach it to check its shape
while it lived inside a `while True` behind a 30-second sleep.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from typing import Any, Callable, Protocol

_logger = logging.getLogger(__name__)

#: Seconds between RSS samples. Long enough not to matter, short enough that a
#: run climbing towards the block threshold is reported before it gets there.
MEMORY_CHECK_INTERVAL = 30

#: How long the watchdog waits between checks that the parent is still alive.
_WATCHDOG_INTERVAL = 5

#: Windows ``OpenProcess`` access right for waiting on a handle.
_SYNCHRONIZE = 0x00100000


class _Sender(Protocol):
    # Positional-only, so a caller whose writer names the parameter something
    # else still satisfies this. Both sidecars call theirs `obj`.
    def __call__(self, message: dict[str, Any], /) -> None: ...


def build_memory_warning(
    ratio: float | None,
    rss_bytes: int,
    *,
    warn_threshold: float,
    block_threshold: float,
) -> dict[str, Any] | None:
    """Return the progress notification for this sample, or None to stay quiet.

    Three outcomes, kept apart because two of them used to be one:

    - ``ratio is None``: the system total could not be read, so no threshold
      applies. None is returned and the caller reports that the guard is off.
      Before ``memory_usage_ratio`` grew this case it returned 0.0, which is
      below both thresholds, so an unreadable total silenced the warning and
      the block for the life of the process with nothing to say so.
    - below ``warn_threshold``: nothing to report.
    - at or above it: a notification, at "block" level once
      ``block_threshold`` is reached.

    ``method="progress"`` because that is what the Rust sidecar forwards to
    ``sidecar://progress``; ``type="memory_warning"`` is how the frontend tells
    this apart from stage progress.
    """
    if ratio is None:
        return None
    if ratio < warn_threshold:
        return None
    return {
        "jsonrpc": "2.0",
        "method": "progress",
        "params": {
            "type": "memory_warning",
            "ratio": round(ratio, 4),
            "rss_mb": round(rss_bytes / (1024 * 1024), 1),
            "level": "block" if ratio >= block_threshold else "warn",
        },
    }


def start_memory_monitor(
    send: _Sender, *, interval: int = MEMORY_CHECK_INTERVAL
) -> None:
    """Sample RSS on a daemon thread and emit a warning when it climbs.

    Daemon so it never holds the process open, and so it does not block the
    stdin loop.

    Args:
        send: Writes one JSON-RPC message. Passed in rather than imported
            because each sidecar owns its own stdout writer.
        interval: Seconds between samples.
    """
    try:
        from kuma_core.shared.memory_monitor import (
            BLOCK_THRESHOLD,
            WARN_THRESHOLD,
            get_self_rss_bytes,
            memory_usage_ratio,
        )
    except ImportError:
        _logger.warning("memory_monitor unavailable, skipping RSS monitoring")
        return

    # Latched so an unreadable total is reported once rather than every
    # interval for the life of the process.
    reported_unmeasurable = False

    def _check() -> None:
        nonlocal reported_unmeasurable
        while True:
            time.sleep(interval)
            try:
                ratio = memory_usage_ratio()
                if ratio is None:
                    if not reported_unmeasurable:
                        reported_unmeasurable = True
                        _logger.warning(
                            "memory monitor cannot read the system total; "
                            "RSS thresholds are not being enforced"
                        )
                    continue
                message = build_memory_warning(
                    ratio,
                    get_self_rss_bytes(),
                    warn_threshold=WARN_THRESHOLD,
                    block_threshold=BLOCK_THRESHOLD,
                )
                if message is not None:
                    send(message)
            except Exception:
                # Monitoring is advisory: a failed sample must not take down
                # the sidecar that is doing the actual work. Logged rather
                # than swallowed, at debug because a broken pipe here is the
                # ordinary shape of shutdown.
                _logger.debug("memory monitor check failed", exc_info=True)

    threading.Thread(target=_check, daemon=True).start()


def exit_after_shutdown() -> None:
    """Flush what can be flushed, then leave without running atexit handlers.

    ``os._exit`` rather than ``sys.exit`` because the shutdown RPC has already
    been answered and an interpreter teardown could block on a non-daemon
    thread.

    The flushes are best-effort. The parent may have closed the pipe already,
    which is the ordinary case when it is the one shutting us down, and there
    is nowhere left to report that to.
    """
    logging.shutdown()
    for name, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
        try:
            stream.flush()
        except BrokenPipeError:
            _logger.debug("%s closed before shutdown flush", name)
    os._exit(0)


def start_parent_watchdog(*, interval: int = _WATCHDOG_INTERVAL) -> None:
    """Exit when the parent process goes away.

    Without this a sidecar outlives the app that spawned it. Windows is the
    reason it exists: there is no orphan reparenting to notice, so the process
    would sit holding its memory indefinitely.
    """
    ppid = os.getppid()
    if ppid <= 1:
        # Already reparented to init, so there is no parent left to watch.
        return

    def _check_posix() -> None:
        while True:
            time.sleep(interval)
            try:
                os.kill(ppid, 0)
            except ProcessLookupError:
                _logger.info("Parent process %d died, exiting", ppid)
                os._exit(0)
            except PermissionError:
                # Signal 0 was refused, which means the process is there and
                # owned by another user. That is the parent alive, so this is
                # a successful check rather than a failure to handle.
                _logger.debug("Parent process %d alive, not signallable", ppid)

    def _check_windows() -> None:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        parent_handle = kernel32.OpenProcess(_SYNCHRONIZE, False, ppid)
        if not parent_handle:
            _logger.debug("Could not open parent %d, watchdog not started", ppid)
            return
        while True:
            time.sleep(interval)
            if kernel32.WaitForSingleObject(ctypes.c_void_p(parent_handle), 0) == 0:
                _logger.info("Parent process %d died, exiting", ppid)
                kernel32.CloseHandle(ctypes.c_void_p(parent_handle))
                os._exit(0)

    target: Callable[[], None] = (
        _check_windows if sys.platform == "win32" else _check_posix
    )
    threading.Thread(target=target, daemon=True).start()


__all__ = [
    "MEMORY_CHECK_INTERVAL",
    "build_memory_warning",
    "exit_after_shutdown",
    "start_memory_monitor",
    "start_parent_watchdog",
]
