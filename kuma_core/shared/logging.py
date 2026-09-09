"""Shared logger factory writing to ~/.kuma/logs/."""
from __future__ import annotations

import logging
import sys

from .config_paths import kuma_logs_dir


def get_logger(name: str, *, stream: bool = True) -> logging.Logger:
    logs_dir = kuma_logs_dir()
    logger = logging.getLogger(name)
    logs_ready = False

    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        logs_ready = True
    except OSError:
        logs_ready = False

    # Avoid duplicate handlers on re-entry.
    has_file = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    if logs_ready and not has_file:
        try:
            # encoding/errors are pinned because the default is the locale
            # codec: on a Korean Windows install that is cp949, which cannot
            # encode characters such as U+2014 and makes emit() raise
            # UnicodeEncodeError. logging then prints "--- Logging error ---"
            # plus a traceback into the log, burying the real failure.
            fh = logging.FileHandler(
                logs_dir / f"{name}.log", encoding="utf-8", errors="replace"
            )
        except OSError:
            fh = None
        if fh is not None:
            fh.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            )
            logger.addHandler(fh)

    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in logger.handlers
    )
    if stream and not has_stream:
        # StreamHandler takes no encoding argument, so relax the error
        # handler on the stream itself. Only errors= is changed: the console
        # encoding stays as-is so existing Korean output is unaffected.
        reconfigure = getattr(sys.stderr, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="backslashreplace")
            except (ValueError, OSError):
                pass
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(sh)

    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)

    return logger
