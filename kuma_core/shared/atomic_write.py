"""Atomic text-file writes for kuma output paths.

An interrupted ``open(path, "w")`` leaves a truncated file that still
"exists" on disk, which downstream consumers may treat as valid output.
Writing to a sibling ``<path>.tmp`` and then calling :func:`os.replace`
makes the final swap atomic on the same filesystem: a reader sees either
the previous file or the fully-written new file, never a partial one.

The temp file is always a sibling of the target (same directory, same
filesystem) so ``os.replace`` is a real atomic rename rather than a
cross-device copy.

Usage::

    from kuma_core.shared.atomic_write import atomic_write_text

    atomic_write_text(path, content)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

_logger = logging.getLogger(__name__)

_TMP_SUFFIX = ".tmp"


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> Path:
    """Write *content* to *path* atomically via a sibling temp file + os.replace.

    The data is written to ``<path><_TMP_SUFFIX>`` in the same directory,
    flushed and fsync'd, then renamed over *path*. If the write fails, the
    temp file is removed and the original *path* (if any) is left untouched.

    Args:
        path: Destination path. Its parent directory must already exist.
        content: Text to write.
        encoding: Text encoding, default ``"utf-8"``.

    Returns:
        The resolved absolute path that was written.

    Raises:
        OSError: On any I/O failure (the temp file is cleaned up first).
    """
    path = Path(path)
    tmp_path = path.with_name(path.name + _TMP_SUFFIX)
    try:
        with open(tmp_path, "w", encoding=encoding) as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except OSError:
        # Leave the original file intact; best-effort remove the partial temp
        # file before re-raising the original failure to the caller.
        try:
            tmp_path.unlink()
        except OSError as cleanup_exc:
            _logger.warning(
                "Could not remove temp file %s after failed atomic write: %s",
                tmp_path,
                cleanup_exc,
            )
        raise
    return path.resolve()


__all__ = ["atomic_write_text"]
