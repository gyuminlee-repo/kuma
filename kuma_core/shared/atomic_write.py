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

from contextlib import contextmanager
from collections.abc import Iterator
import codecs
import errno
import logging
import os
import stat
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
    # 12 hex digits keep the staging name short enough for paths near the
    # Windows MAX_PATH limit while staying unique per call.
    return path.with_name(f".{path.stem}.{uuid4().hex[:12]}{_TMP_SUFFIX}{path.suffix}")


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


# Filesystems that do not support chmod (some network shares and FUSE mounts)
# report one of these; the file still has the share's own permissions.
_CHMOD_UNSUPPORTED = {errno.EPERM, errno.ENOTSUP, errno.EOPNOTSUPP}


def _apply_permissions(fd: int, permissions: int, tmp_path: Path) -> None:
    """Restore the replaced file's mode, unless the filesystem refuses chmod."""
    try:
        os.fchmod(fd, permissions)
    except OSError as exc:
        if exc.errno not in _CHMOD_UNSUPPORTED:
            raise
        _logger.warning("Could not keep the previous permissions on %s: %s", tmp_path, exc)


def _private_opener(path: str, flags: int) -> int:
    """Stage for an existing target: owner-only until its own mode is applied.

    The file being replaced may be private, so its replacement must not be
    readable by others for the moment before ``fchmod`` gives it that mode.
    """
    return os.open(path, flags, 0o600)


def _umask_opener(path: str, flags: int) -> int:
    """Stage for a new target: the mode any file the user creates would get.

    The kernel applies the process umask at creation, so the published file is
    ``0o666 & ~umask`` without this module ever reading the umask. Reading it
    means ``os.umask`` setting and restoring it, and for that instant every
    other thread creates files under the wrong mask. Nothing is given up by not
    staging privately: the file is about to exist under that mode anyway.
    """
    return os.open(path, flags, 0o666)


def _existing_permissions(path: Path) -> int | None:
    """Preserve POSIX rwx bits of an existing regular target, not link modes."""
    if os.name != "posix":
        return None
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return stat.S_IMODE(info.st_mode) & 0o777 if stat.S_ISREG(info.st_mode) else None


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
    *path* (if any) is left untouched. A new file gets the mode the process
    umask gives any new file; an existing regular file keeps its POSIX rwx
    permissions. An existing *path* is always replaced.

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
        Exception: Whatever the write raised. The staging file is removed
            first in every case, including :class:`KeyboardInterrupt`, so a
            failed export never leaves a ``.tmp`` beside the target.
    """
    path = Path(path)
    codecs.lookup(encoding)  # an unknown encoding fails before any file exists
    tmp_path = _temp_path_for(path)
    permissions = _existing_permissions(path)
    opener = _umask_opener if permissions is None else _private_opener
    reserved = False
    try:
        with open(tmp_path, "x", encoding=encoding, newline=newline, opener=opener) as fh:
            reserved = True
            fh.write(content)
            fh.flush()
            if permissions is not None:
                _apply_permissions(fh.fileno(), permissions, tmp_path)
            if fsync:
                os.fsync(fh.fileno())
        _replace_with_retry(tmp_path, path)
    except BaseException:
        # Any failure, not only I/O: a TypeError from the content, a
        # ValueError from an encoder, or a KeyboardInterrupt mid-flush left
        # the staging file behind in the operator's export folder, where the
        # next person reads it as a half-written export. Leave the original
        # file intact; best-effort remove the partial temp file before
        # re-raising the original failure to the caller.
        if reserved:
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


@contextmanager
def atomic_output_path(path: Path) -> Iterator[Path]:
    """Stage an external writer's output beside its target and publish on success.

    The caller must validate the staged artifact before leaving the context.
    A conversion, validation, flush, or rename failure leaves the target intact.
    """
    path = Path(path)
    tmp_path = _temp_path_for(path)
    permissions = _existing_permissions(path)
    opener = _umask_opener if permissions is None else _private_opener
    reserved = False
    try:
        # Reserve the stage under a per-call name, never a predictable shared one.
        with open(tmp_path, "xb", opener=opener):
            reserved = True
        yield tmp_path
        with open(tmp_path, "r+b") as fh:
            if permissions is not None:
                _apply_permissions(fh.fileno(), permissions, tmp_path)
            os.fsync(fh.fileno())
        _replace_with_retry(tmp_path, path)
        fsync_directory(path.parent)
    finally:
        if reserved:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError as exc:
                _logger.warning("Could not remove staged output %s: %s", tmp_path, exc)


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


__all__ = ["atomic_write_text", "atomic_output_path", "fsync_directory"]
