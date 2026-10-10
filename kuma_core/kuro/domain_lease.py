"""Fail-closed admission for optional runtime execution across host crashes.

Only the trusted registry constructs these objects, while holding its primary
operation lock. A prepared record is durable BEFORE any helper/runtime spawn.
The dedicated helper inherits that same POSIX flock description; closing a copy
must never explicitly unlock it. On Windows a helper-owned execution guard and
the nonterminal record cover primary-lock release after a host crash.

A terminal record is an attestation by the lifecycle helper that its ENTIRE child
tree has exited. Call ``complete`` only after that proof, including failed starts
known to have launched no child. Admission additionally requires that exact
helper PID/creation identity to have exited, closing the close-before-exit gap.
Unknown, corrupt and nonterminal state requires operator investigation; neither
PID death nor a timeout permits deleting it. This module is not crash recovery,
a process-tree terminator, or a security boundary against another same-user
process deliberately rewriting the app-owned registry.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any

import psutil

EXECUTION_RECORD_NAME = ".kuma-execution.json"
EXECUTION_GUARD_NAME = ".kuma-execution.lock"
MAX_RECORD_BYTES = 4096
_PRIMARY_LOCK_NAME = ".kuma-operation.lock"
_TOKEN = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_KEYS = {"version", "root_dev", "root_ino", "token", "state", "helper", "tree_exited"}
_CONFIG_KEYS = {"version", "root", "root_dev", "root_ino", "token", "primary_fd", "record_dev", "record_ino"}


class RuntimeLeaseError(ValueError):
    """Execution admission is busy, unsafe, or lacks a complete cleanup proof."""


def _is_link(info: os.stat_result) -> bool:
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0) & 0x400))


def _identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


def _snapshot(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (*_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _root_identity(root: Path) -> tuple[int, int]:
    if not root.is_absolute() or ".." in root.parts:
        raise RuntimeLeaseError("Execution lease root must be a canonical absolute directory")
    try:
        for component in reversed((root, *root.parents)):
            info = component.lstat()
            if _is_link(info) or not stat.S_ISDIR(info.st_mode):
                raise RuntimeLeaseError("Unsafe execution lease directory")
        return _identity(root.lstat())
    except OSError as exc:
        raise RuntimeLeaseError("Cannot verify execution lease directory") from exc


def _check_root(root: Path, expected: tuple[int, int]) -> None:
    if _root_identity(root) != expected:
        raise RuntimeLeaseError("Execution lease directory identity changed")


def _regular(info: os.stat_result, limit: int) -> None:
    if (_is_link(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or not 0 <= info.st_size <= limit):
        raise RuntimeLeaseError("Execution lease must be a bounded single-link regular file")


def _check_named(path: Path, fd: int, limit: int) -> os.stat_result:
    actual, named = os.fstat(fd), path.lstat()
    _regular(actual, limit)
    _regular(named, limit)
    if _snapshot(actual) != _snapshot(named):
        raise RuntimeLeaseError("Execution lease file identity changed")
    return actual


def _primary(root: Path, fd: int) -> None:
    if type(fd) is not int or fd < 0:
        raise RuntimeLeaseError("Missing inherited primary execution lock")
    try:
        _check_named(root / _PRIMARY_LOCK_NAME, fd, 1)
    except OSError as exc:
        raise RuntimeLeaseError("Cannot verify primary execution lock") from exc


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeLeaseError("Duplicate execution lease fields")
        result[key] = value
    return result


def _valid_identity(value: Any) -> bool:
    if (not isinstance(value, dict) or set(value) != {"pid", "created"}
            or type(value["pid"]) is not int or not 0 < value["pid"] <= 0xFFFFFFFF
            or type(value["created"]) not in {int, float}):
        return False
    try:
        return math.isfinite(value["created"]) and value["created"] > 0
    except OverflowError:
        return False


def _validate(record: Any, root_id: tuple[int, int]) -> dict[str, Any]:
    if (not isinstance(record, dict) or set(record) != _RECORD_KEYS
            or type(record["version"]) is not int or record["version"] != 1
            or any(type(record[key]) is not int or record[key] < 0 for key in ("root_dev", "root_ino"))
            or (record["root_dev"], record["root_ino"]) != root_id
            or not isinstance(record["token"], str) or not _TOKEN.fullmatch(record["token"])
            or type(record["tree_exited"]) is not bool):
        raise RuntimeLeaseError("Invalid execution lease record")
    state, helper, exited = record["state"], record["helper"], record["tree_exited"]
    if not ((state == "prepared" and helper is None and not exited)
            or (state == "running" and _valid_identity(helper) and not exited)
            or (state == "terminal" and _valid_identity(helper) and exited)):
        raise RuntimeLeaseError("Invalid execution lease cleanup proof")
    return record


def _read_record(root: Path, root_id: tuple[int, int]) -> tuple[dict[str, Any], os.stat_result] | None:
    _check_root(root, root_id)
    path = root / EXECUTION_RECORD_NAME
    fd: int | None = None
    try:
        try:
            before = path.lstat()
        except FileNotFoundError:
            return None
        _regular(before, MAX_RECORD_BYTES)
        # NONBLOCK also protects against a regular file being swapped for a FIFO.
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        actual = _check_named(path, fd, MAX_RECORD_BYTES)
        if _snapshot(before) != _snapshot(actual):
            raise RuntimeLeaseError("Execution lease changed while opening")
        raw = bytearray()
        while len(raw) <= MAX_RECORD_BYTES:
            chunk = os.read(fd, MAX_RECORD_BYTES + 1 - len(raw))
            if not chunk:
                break
            raw.extend(chunk)
        after = _check_named(path, fd, MAX_RECORD_BYTES)
        if _snapshot(actual) != _snapshot(after) or len(raw) != actual.st_size:
            raise RuntimeLeaseError("Execution lease changed while reading")
        record = json.loads(raw, object_pairs_hook=_no_duplicates)
        _check_root(root, root_id)
        return _validate(record, root_id), after
    except (OSError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        if isinstance(exc, RuntimeLeaseError):
            raise
        raise RuntimeLeaseError("Cannot verify execution lease record") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _sync_root(root: Path) -> None:
    if os.name != "nt":
        fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write_record(root: Path, root_id: tuple[int, int], record: dict[str, Any],
                  previous: os.stat_result | None) -> os.stat_result:
    _validate(record, root_id)
    raw = (json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")
    if len(raw) > MAX_RECORD_BYTES:
        raise RuntimeLeaseError("Execution lease exceeds its size limit")
    _check_root(root, root_id)
    path = root / EXECUTION_RECORD_NAME
    temporary = root / (".kuma-execution-" + secrets.token_hex(16) + ".tmp")
    fd: int | None = None
    created: os.stat_result | None = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0), 0o600)
        created = os.fstat(fd)
        view = memoryview(raw)
        while view:
            count = os.write(fd, view)
            if count <= 0:
                raise RuntimeLeaseError("Cannot write execution lease record")
            view = view[count:]
        os.fsync(fd)
        current = _check_named(temporary, fd, MAX_RECORD_BYTES)
        _check_root(root, root_id)
        if previous is None:
            if os.path.lexists(path):
                raise RuntimeLeaseError("Execution lease already exists")
        else:
            named = path.lstat()
            _regular(named, MAX_RECORD_BYTES)
            if _snapshot(named) != _snapshot(previous):
                raise RuntimeLeaseError("Execution lease changed before update")
        # Close before rename for native Windows. No runtime exists before the
        # first publish; a crash leaving a temporary file grants no admission.
        os.close(fd)
        fd = None
        os.replace(temporary, path)
        _sync_root(root)
        named = path.lstat()
        _regular(named, MAX_RECORD_BYTES)
        # Rename may change ctime, but must retain the exact published inode.
        if _identity(named) != _identity(current) or named.st_size != len(raw):
            raise RuntimeLeaseError("Execution lease changed during publication")
        _check_root(root, root_id)
        return named
    except OSError as exc:
        raise RuntimeLeaseError("Cannot persist execution lease record") from exc
    finally:
        if fd is not None:
            os.close(fd)
        # Remove only our exact temporary regular file; never sweep crash state.
        try:
            leftover = temporary.lstat()
            if created is not None and _identity(leftover) == _identity(created):
                _regular(leftover, MAX_RECORD_BYTES)
                temporary.unlink()
        except FileNotFoundError:
            pass


class _Guard:
    def __init__(self, root: Path, root_id: tuple[int, int]):
        self.fd = -1
        self.root, self.root_id = root, root_id
        self.path = root / EXECUTION_GUARD_NAME
        _check_root(root, root_id)
        try:
            if os.path.lexists(self.path):
                _regular(self.path.lstat(), 1)
            self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                              | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0), 0o600)
            actual = _check_named(self.path, self.fd, 1)
            if os.name == "nt":
                import msvcrt
                if actual.st_size == 0:
                    os.write(self.fd, b"0")
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.file_id = _identity(_check_named(self.path, self.fd, 1))
            _check_root(root, root_id)
        except (OSError, RuntimeLeaseError) as exc:
            self.close()
            raise RuntimeLeaseError("Runtime execution guard is busy or unsafe") from exc

    def check(self) -> None:
        _check_root(self.root, self.root_id)
        try:
            if self.fd < 0 or _identity(_check_named(self.path, self.fd, 1)) != self.file_id:
                raise RuntimeLeaseError("Runtime execution guard identity changed")
        except OSError as exc:
            raise RuntimeLeaseError("Cannot verify runtime execution guard") from exc

    def close(self) -> None:
        if self.fd >= 0:
            fd, self.fd = self.fd, -1
            os.close(fd)  # Closing, rather than explicitly unlocking, is essential.


def _helper_identity() -> dict[str, Any]:
    try:
        result = {"pid": os.getpid(), "created": psutil.Process().create_time()}
    except (psutil.Error, OSError, ValueError, OverflowError) as exc:
        raise RuntimeLeaseError("Cannot establish helper creation identity") from exc
    if not _valid_identity(result):
        raise RuntimeLeaseError("Invalid helper creation identity")
    return result


def _helper_exited(identity: dict[str, Any]) -> bool:
    try:
        # A fresh object avoids cached is_running/PID-reuse decisions. A reused
        # PID with a different creation identity proves our helper has exited.
        return psutil.Process(identity["pid"]).create_time() != identity["created"]
    except psutil.NoSuchProcess:
        return True
    except (psutil.Error, OSError, ValueError, OverflowError) as exc:
        raise RuntimeLeaseError("Cannot establish exact helper exit") from exc


def check_execution_admission(root: Path) -> None:
    """Check/consume proof under the caller-held registry primary lock.

    Missing state permits admission only with a free execution guard. A terminal
    record is consumed only after exact helper exit; every uncertainty fails
    closed, without deleting or repairing evidence.
    """
    root_id = _root_identity(root)
    guard = _Guard(root, root_id)
    try:
        saved = _read_record(root, root_id)
        if saved is None:
            guard.check()
            return
        record, before = saved
        if record["state"] != "terminal":
            raise RuntimeLeaseError("Runtime execution cleanup is unconfirmed; admission refused")
        if not _helper_exited(record["helper"]):
            raise RuntimeLeaseError("Runtime execution helper has not exited; admission refused")
        guard.check()
        path = root / EXECUTION_RECORD_NAME
        named = path.lstat()
        _regular(named, MAX_RECORD_BYTES)
        if _snapshot(named) != _snapshot(before):
            raise RuntimeLeaseError("Execution lease changed before consumption")
        path.unlink()
        _sync_root(root)
    except OSError as exc:
        raise RuntimeLeaseError("Cannot consume execution cleanup proof") from exc
    finally:
        guard.close()


class ExecutionLease:
    """Trusted, single execution handoff; never constructed from RPC input."""
    def __init__(self, root: Path, root_id: tuple[int, int], token: str, primary_fd: int,
                 record: os.stat_result):
        self.root, self.root_id = root, root_id
        self.token, self.primary_fd = token, primary_fd
        self.record_id = _identity(record)

    def to_config(self) -> dict[str, Any]:
        return {"version": 1, "root": str(self.root), "root_dev": self.root_id[0],
                "root_ino": self.root_id[1], "token": self.token,
                "primary_fd": None if os.name == "nt" else self.primary_fd,
                "record_dev": self.record_id[0], "record_ino": self.record_id[1]}


class OperationLease:
    """Borrow a caller-held primary lock; preparation never spawns anything."""
    def __init__(self, root: Path, primary_fd: int):
        self.root, self.primary_fd = root, primary_fd
        self.root_id = _root_identity(root)
        _primary(root, primary_fd)
        self.prepared = False

    def prepare(self) -> ExecutionLease:
        if self.prepared:
            raise RuntimeLeaseError("Operation execution lease was already prepared")
        _check_root(self.root, self.root_id)
        _primary(self.root, self.primary_fd)
        check_execution_admission(self.root)
        token = secrets.token_hex(32)
        record = {"version": 1, "root_dev": self.root_id[0], "root_ino": self.root_id[1],
                  "token": token, "state": "prepared", "helper": None, "tree_exited": False}
        info = _write_record(self.root, self.root_id, record, None)
        self.prepared = True
        return ExecutionLease(self.root, self.root_id, token, self.primary_fd, info)


class HelperLease:
    """Dedicated helper's execution guard and borrowed POSIX flock descriptor."""
    def __init__(self, root: Path, root_id: tuple[int, int], token: str,
                 primary_fd: int | None, guard: _Guard, helper: dict[str, Any],
                 record: os.stat_result):
        self.root, self.root_id, self.token = root, root_id, token
        self.primary_fd, self.guard, self.helper = primary_fd, guard, helper
        self.record = record
        self.completed = False
        self.closed = False

    @classmethod
    def claim(cls, payload: dict[str, Any], expected_token: str) -> HelperLease:
        if (not isinstance(payload, dict) or set(payload) != _CONFIG_KEYS
                or type(payload.get("version")) is not int or payload["version"] != 1
                or not isinstance(expected_token, str) or not _TOKEN.fullmatch(expected_token)
                or payload.get("token") != expected_token
                or not isinstance(payload.get("root"), str) or "\0" in payload["root"]
                or any(type(payload[key]) is not int or payload[key] < 0
                       for key in ("root_dev", "root_ino", "record_dev", "record_ino"))):
            raise RuntimeLeaseError("Invalid helper execution lease configuration")
        root = Path(payload["root"])
        root_id = (payload["root_dev"], payload["root_ino"])
        _check_root(root, root_id)
        primary_fd = payload["primary_fd"]
        if os.name == "nt":
            if primary_fd is not None:
                raise RuntimeLeaseError("Windows helper must own a separate execution guard")
        else:
            _primary(root, primary_fd)
        guard = _Guard(root, root_id)
        try:
            saved = _read_record(root, root_id)
            if saved is None:
                raise RuntimeLeaseError("Prepared execution lease is missing")
            record, before = saved
            if (record["state"] != "prepared" or record["token"] != expected_token
                    or _identity(before) != (payload["record_dev"], payload["record_ino"])):
                raise RuntimeLeaseError("Prepared execution lease identity mismatch")
            helper = _helper_identity()
            record.update(state="running", helper=helper)
            info = _write_record(root, root_id, record, before)
            return cls(root, root_id, expected_token, primary_fd, guard, helper, info)
        except BaseException:
            guard.close()
            raise

    def complete(self) -> None:
        """Attest complete child-tree exit; only the lifecycle helper may call.

        This is not a request to kill anything. An uncertain/failed cleanup must
        leave the running record untouched, even if the helper is about to die.
        """
        if self.closed or self.completed or _helper_identity() != self.helper:
            raise RuntimeLeaseError("Execution lease is closed, completed, or owned by another helper")
        self.guard.check()
        if self.primary_fd is not None:
            _primary(self.root, self.primary_fd)
        saved = _read_record(self.root, self.root_id)
        if saved is None:
            raise RuntimeLeaseError("Running execution lease is missing")
        record, before = saved
        if (record["state"] != "running" or record["token"] != self.token
                or record["helper"] != self.helper or _snapshot(before) != _snapshot(self.record)):
            raise RuntimeLeaseError("Running execution lease identity mismatch")
        record.update(state="terminal", tree_exited=True)
        self.record = _write_record(self.root, self.root_id, record, before)
        self.completed = True

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.guard.close()
        finally:
            if self.primary_fd is not None:
                fd, self.primary_fd = self.primary_fd, None
                os.close(fd)  # NEVER LOCK_UN: the host may still own this flock.
