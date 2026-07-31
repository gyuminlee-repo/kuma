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


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    fsync: bool = True,
) -> Path:
    """Write *content* to *path* atomically via a sibling temp file + os.replace.

    The data is written to ``<path><_TMP_SUFFIX>`` in the same directory,
    flushed and (by default) fsync'd, then renamed over *path*. If the write
    fails, the temp file is removed and the original *path* (if any) is left
    untouched.

    Args:
        path: Destination path. Its parent directory must already exist.
        content: Text to write.
        encoding: Text encoding, default ``"utf-8"``.
        fsync: When True (default), fsync the temp file before the rename so
            the contents survive a machine crash / power loss. Pass False
            **only** for intermediate artifacts that a re-run can regenerate
            (crash-recoverable scratch output). The rename stays atomic either
            way, so a reader never sees a partial file; what is given up is
            durability across an OS-level crash, where the file may come back
            empty or stale. Never pass False for a lone final deliverable, a
            stage marker, or anything a resume path treats as authoritative.
            The one exception is a *batch* of files whose durability point is
            deferred to a single :func:`fsync_directory` call over their shared
            parent once the batch is complete; see that function.

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
            if fsync:
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


def fsync_directory(path: Path) -> bool:
    """Best-effort fsync of the directory *path* itself.

    :func:`atomic_write_text` fsyncs the temp file but never the parent
    directory, so the ``os.replace`` that publishes the final name is not
    durable on its own. Calling this once after a batch of writes commits all
    of those renames together, which is what lets the per-file fsync be dropped
    for the members of the batch: on ext4 (``data=ordered``, the mount default)
    the metadata commit forces the newly allocated data blocks out first, so
    after this call the batch is "absent or complete" rather than "present but
    empty".

    Best-effort by design. Directory file descriptors do not exist on Windows,
    and network/pass-through filesystems (9p, drvfs) may reject the fsync; in
    both cases durability was never actually available and the caller should
    not fail because of it.

    Args:
        path: Directory to fsync.

    Returns:
        True if the directory was fsync'd, False if the platform or filesystem
        refused (logged at debug level).
    """
    if os.name != "posix":
        return False
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError as exc:
        _logger.debug("Could not open %s for directory fsync: %s", path, exc)
        return False
    try:
        os.fsync(fd)
    except OSError as exc:
        _logger.debug("Directory fsync of %s not supported: %s", path, exc)
        return False
    finally:
        os.close(fd)
    return True


__all__ = ["atomic_write_text", "fsync_directory"]
