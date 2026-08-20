"""Atomic text-file writes for kuma output paths.

An interrupted ``open(path, "w")`` leaves a truncated file that still
"exists" on disk, which downstream consumers may treat as valid output.
Writing to a sibling staging file and then calling :func:`os.replace`
makes the final swap atomic on the same filesystem: a reader sees either
the previous file or the fully-written new file, never a partial one.

The staging name carries a per-call token, so the guarantee holds against a
second writer of the same target and not only against interruption. On Windows
the publishing rename itself can refuse while a competing writer holds the
destination, so it is retried a bounded number of times.

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
import time
from pathlib import Path
from uuid import uuid4

_logger = logging.getLogger(__name__)

_TMP_SUFFIX = ".tmp"

# Windows only. Three attempts over 10 + 20 ms covers the publish window a
# competing writer holds; beyond that the error is not a race.
_REPLACE_RETRY_ATTEMPTS = 3
_REPLACE_RETRY_INITIAL_DELAY = 0.01


def _temp_path_for(path: Path) -> Path:
    """Return a temp path unique to this call, in *path*'s own directory.

    Deriving the temp name from the target alone gives every writer of that
    target the same string, so a second writer truncates the first writer's
    temp file and the first writer's rename then takes it away. Measured with
    two threads on one target, that raised ``FileNotFoundError`` out of
    ``os.replace`` in 18 of 20 rounds, on a path the caller never named.

    The token makes the staging file private to one call. Same directory, so
    ``os.replace`` stays a rename rather than a cross-device copy. Leading dot
    and the suffix kept last so the shape matches the per-call staging name
    ``_publish_artifact_bundle`` already uses.
    """
    return path.with_name(f".{path.stem}.{uuid4().hex}{_TMP_SUFFIX}{path.suffix}")


def _replace_with_retry(tmp_path: Path, path: Path) -> None:
    """``os.replace`` with a bounded retry for the Windows sharing violation.

    On POSIX the rename is unconditional and this is a single call. On Windows
    it is ``MoveFileEx``, which fails with ``PermissionError`` ("Access is
    denied") when another handle to the destination is open, including the
    brief window while a second writer is publishing over the same target.
    Measured on the Windows CI leg, two threads on one path hit it even with
    per-call staging names, so the token alone does not make the primitive
    concurrent there.

    The retry is bounded and re-raises the original error, so a genuine
    permission problem still surfaces rather than being spun on.
    """
    if os.name != "nt":
        os.replace(tmp_path, path)
        return
    delay = _REPLACE_RETRY_INITIAL_DELAY
    for _ in range(_REPLACE_RETRY_ATTEMPTS - 1):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            time.sleep(delay)
            delay *= 2
    os.replace(tmp_path, path)


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    fsync: bool = True,
    newline: str | None = None,
) -> Path:
    """Write *content* to *path* atomically via a sibling temp file + os.replace.

    The data is written to a staging file unique to this call, in the same
    directory as *path*, flushed and (by default) fsync'd, then renamed over
    *path*. If the write fails, the staging file is removed and the original
    *path* (if any) is left untouched.

    Two concurrent calls on one target both publish; which of the two wins is
    whichever renames last. What no longer happens is one of them failing with
    a missing-file error on a path the caller never named.

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
        newline: Passed straight to :func:`open`. Default None keeps the
            platform translation, which turns ``"\\n"`` into ``"\\r\\n"`` on
            Windows. Pass ``""`` when the bytes on disk are the contract
            rather than the text, as they are for a ``shasum -c`` checksum
            line, where a CR before the filename makes the checker read a
            different name than the one written.

    Returns:
        The resolved absolute path that was written.

    Raises:
        OSError: On any I/O failure (the temp file is cleaned up first).
    """
    path = Path(path)
    tmp_path = _temp_path_for(path)
    try:
        with open(tmp_path, "w", encoding=encoding, newline=newline) as fh:
            fh.write(content)
            fh.flush()
            if fsync:
                os.fsync(fh.fileno())
        _replace_with_retry(tmp_path, path)
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
