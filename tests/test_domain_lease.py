"""Synthetic admission leases only; no optional executable or model is used.

Native Windows/macOS runs remain required. Mocked unsafe metadata and identity
errors establish fail-closed branches, not native platform lifecycle evidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

import psutil
import pytest

from kuma_core.kuro import domain_lease as lease


@contextmanager
def primary(root: Path) -> Iterator[int]:
    fd = os.open(root / ".kuma-operation.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.name == "nt":
            import msvcrt
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield fd
    finally:
        os.close(fd)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path.resolve()


def read_record(root: Path) -> dict[str, Any]:
    return json.loads((root / lease.EXECUTION_RECORD_NAME).read_text(encoding="ascii"))


def write_record(root: Path, record: dict[str, Any]) -> None:
    (root / lease.EXECUTION_RECORD_NAME).write_text(json.dumps(record), encoding="ascii")


def borrowed_config(execution: lease.ExecutionLease) -> dict[str, Any]:
    config = execution.to_config()
    if os.name != "nt":
        config["primary_fd"] = os.dup(execution.primary_fd)
    return config


def test_prepared_record_is_bounded_durable_and_refuses_admission(root: Path) -> None:
    with primary(root) as fd:
        operation = lease.OperationLease(root, fd)
        execution = operation.prepare()
        record = read_record(root)
        assert record == {"version": 1, "root_dev": root.stat().st_dev, "root_ino": root.stat().st_ino,
                          "token": execution.token, "state": "prepared", "helper": None, "tree_exited": False}
        info = (root / lease.EXECUTION_RECORD_NAME).stat()
        assert info.st_nlink == 1 and info.st_size <= lease.MAX_RECORD_BYTES
        assert execution.primary_fd == fd
        config = execution.to_config()
        assert (config["record_dev"], config["record_ino"]) == (info.st_dev, info.st_ino)
        assert config["primary_fd"] == (None if os.name == "nt" else fd)
        with pytest.raises(lease.RuntimeLeaseError, match="already prepared"):
            operation.prepare()
        with pytest.raises(lease.RuntimeLeaseError, match="unconfirmed"):
            lease.check_execution_admission(root)
    # Merely releasing the primary lock is never a prepared-record recovery.
    with primary(root):
        with pytest.raises(lease.RuntimeLeaseError, match="unconfirmed"):
            lease.check_execution_admission(root)
    assert read_record(root) == record


def test_missing_record_requires_free_guard(root: Path) -> None:
    with primary(root):
        lease.check_execution_admission(root)
        guard = lease._Guard(root, lease._root_identity(root))
        try:
            with pytest.raises(lease.RuntimeLeaseError, match="guard"):
                lease.check_execution_admission(root)
        finally:
            guard.close()
        lease.check_execution_admission(root)
    assert not (root / lease.EXECUTION_RECORD_NAME).exists()


def test_running_and_terminal_records_preserve_exact_helper_identity(root: Path) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        helper = lease.HelperLease.claim(borrowed_config(execution), execution.token)
        try:
            running = read_record(root)
            assert running["state"] == "running" and running["tree_exited"] is False
            assert running["helper"] == {"pid": os.getpid(), "created": psutil.Process().create_time()}
            helper.complete()
            terminal = read_record(root)
            assert terminal["state"] == "terminal" and terminal["tree_exited"] is True
            assert terminal["helper"] == running["helper"]
            with pytest.raises(lease.RuntimeLeaseError, match="guard"):
                lease.check_execution_admission(root)
            with pytest.raises(lease.RuntimeLeaseError, match="completed"):
                helper.complete()
        finally:
            helper.close()
            helper.close()
        with pytest.raises(lease.RuntimeLeaseError, match="helper has not exited"):
            lease.check_execution_admission(root)
        assert read_record(root) == terminal
        with pytest.raises(lease.RuntimeLeaseError, match="closed"):
            helper.complete()


def test_dead_helper_cannot_recover_nonterminal_record(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        helper = lease.HelperLease.claim(borrowed_config(execution), execution.token)
        helper.close()
        record = read_record(root)
        record["helper"]["pid"] = 99999999
        write_record(root, record)

        def must_not_check_pid(_identity: dict[str, Any]) -> bool:
            raise AssertionError("PID liveness must not recover a nonterminal record")

        monkeypatch.setattr(lease, "_helper_exited", must_not_check_pid)
        with pytest.raises(lease.RuntimeLeaseError, match="unconfirmed"):
            lease.check_execution_admission(root)
        assert read_record(root) == record


@pytest.mark.parametrize("exited", [False, True])
def test_terminal_consumption_requires_exact_identity_exit(
    root: Path, monkeypatch: pytest.MonkeyPatch, exited: bool,
) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        helper = lease.HelperLease.claim(borrowed_config(execution), execution.token)
        helper.complete()
        helper.close()
        record = read_record(root)

        def check(identity: dict[str, Any]) -> bool:
            assert identity == record["helper"]
            return exited

        monkeypatch.setattr(lease, "_helper_exited", check)
        if exited:
            lease.check_execution_admission(root)
            assert not (root / lease.EXECUTION_RECORD_NAME).exists()
            assert lease.OperationLease(root, fd).prepare().token != execution.token
        else:
            with pytest.raises(lease.RuntimeLeaseError, match="helper has not exited"):
                lease.check_execution_admission(root)
            assert read_record(root) == record


@pytest.mark.parametrize("change", [
    {"state": "running"}, {"state": "terminal", "tree_exited": True},
    {"state": "prepared", "tree_exited": True}, {"tree_exited": 1},
    {"version": True}, {"version": 2}, {"token": "bad"}, {"root_dev": -1},
    {"root_ino": True}, {"helper": {"pid": True, "created": 123.0}},
    {"state": "terminal", "tree_exited": True, "helper": {"pid": 12, "created": float("nan")}},
    {"state": "terminal", "tree_exited": True, "helper": {"pid": 12, "created": float("inf")}},
    {"unexpected": "field"},
])
def test_invalid_records_are_never_consumed(root: Path, change: dict[str, Any]) -> None:
    with primary(root) as fd:
        lease.OperationLease(root, fd).prepare()
        record = read_record(root)
        record.update(change)
        write_record(root, record)
        raw = (root / lease.EXECUTION_RECORD_NAME).read_bytes()
        with pytest.raises(lease.RuntimeLeaseError):
            lease.check_execution_admission(root)
        assert (root / lease.EXECUTION_RECORD_NAME).read_bytes() == raw


@pytest.mark.parametrize("raw", [b"", b"[", b"null", b"[]", b"{}", b"\xff",
                                  b'{"version":1,"version":1}', b"x" * (lease.MAX_RECORD_BYTES + 1),
                                  b"[" * 2000 + b"]" * 2000])
def test_corrupt_bounded_records_are_never_removed(root: Path, raw: bytes) -> None:
    path = root / lease.EXECUTION_RECORD_NAME
    path.write_bytes(raw)
    with primary(root):
        with pytest.raises(lease.RuntimeLeaseError):
            lease.check_execution_admission(root)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("filename", [lease.EXECUTION_RECORD_NAME, lease.EXECUTION_GUARD_NAME])
@pytest.mark.parametrize("kind", ["hardlink", "directory", "oversized", "symlink", "fifo"])
def test_unsafe_record_or_guard_is_refused_without_touching_target(
    root: Path, filename: str, kind: str,
) -> None:
    path, target = root / filename, root / "unrelated"
    target.write_bytes(b"preserve me")
    if kind == "hardlink":
        os.link(target, path)
    elif kind == "directory":
        path.mkdir()
    elif kind == "oversized":
        path.write_bytes(b"x" * (lease.MAX_RECORD_BYTES + 1))
    elif kind == "symlink":
        try:
            path.symlink_to(target)
        except OSError:
            pytest.skip("Native symlink privilege is unavailable")
    else:
        if os.name == "nt":
            pytest.skip("POSIX FIFO fixture")
        os.mkfifo(path)
    with primary(root):
        with pytest.raises(lease.RuntimeLeaseError):
            lease.check_execution_admission(root)
    assert os.path.lexists(path)
    assert target.read_bytes() == b"preserve me"


@pytest.mark.parametrize("field,value", [
    ("version", True), ("version", 2), ("token", "0" * 64), ("root_dev", -1),
    ("root_ino", True), ("record_dev", -1), ("record_ino", -1), ("root", "relative"),
    ("root", "\0"), ("primary_fd", -1), ("extra", True),
])
def test_claim_rejects_invalid_internal_handoff(root: Path, field: str, value: Any) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        config = execution.to_config()
        config[field] = value
        before = (root / lease.EXECUTION_RECORD_NAME).read_bytes()
        with pytest.raises(lease.RuntimeLeaseError):
            lease.HelperLease.claim(config, execution.token)
        assert (root / lease.EXECUTION_RECORD_NAME).read_bytes() == before
        os.fstat(fd)  # A rejected handoff must not close the caller's descriptor.


def test_claim_rejects_replaced_prepared_file(root: Path) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        replacement = root / "replacement"
        replacement.write_bytes((root / lease.EXECUTION_RECORD_NAME).read_bytes())
        replacement.replace(root / lease.EXECUTION_RECORD_NAME)
        with pytest.raises(lease.RuntimeLeaseError, match="identity mismatch"):
            lease.HelperLease.claim(execution.to_config(), execution.token)


def test_completion_rejects_record_tampering(root: Path) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        helper = lease.HelperLease.claim(borrowed_config(execution), execution.token)
        try:
            record = read_record(root)
            record["token"] = "0" * 64
            write_record(root, record)
            with pytest.raises(lease.RuntimeLeaseError, match="identity mismatch"):
                helper.complete()
            assert read_record(root) == record
        finally:
            helper.close()


def test_atomic_publication_failure_preserves_prepared_record(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        before = (root / lease.EXECUTION_RECORD_NAME).read_bytes()

        def fail_replace(_source: Path, _target: Path) -> None:
            raise OSError("Synthetic atomic publication failure")

        monkeypatch.setattr(lease.os, "replace", fail_replace)
        with pytest.raises(lease.RuntimeLeaseError, match="persist"):
            lease.HelperLease.claim(execution.to_config(), execution.token)
        assert (root / lease.EXECUTION_RECORD_NAME).read_bytes() == before
        assert not list(root.glob(".kuma-execution-*.tmp"))
        with pytest.raises(lease.RuntimeLeaseError, match="unconfirmed"):
            lease.check_execution_admission(root)


def test_creation_identity_query_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    identity = {"pid": os.getpid(), "created": psutil.Process().create_time()}
    assert lease._helper_exited(identity) is False
    assert lease._helper_exited({**identity, "created": identity["created"] - 1}) is True

    def denied(_pid: int | None = None) -> None:
        raise psutil.AccessDenied(identity["pid"])

    monkeypatch.setattr(lease.psutil, "Process", denied)
    with pytest.raises(lease.RuntimeLeaseError, match="exact helper exit"):
        lease._helper_exited(identity)
    with pytest.raises(lease.RuntimeLeaseError, match="creation identity"):
        lease._helper_identity()


@pytest.fixture
def helper_script(root: Path) -> Path:
    script = root / "synthetic lease helper.py"
    script.write_text(textwrap.dedent('''
        import importlib.util, json, os, sys
        spec = importlib.util.spec_from_file_location("synthetic_lease", sys.argv[1])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        config = json.loads(sys.stdin.buffer.readline())
        helper = module.HelperLease.claim(config, config["token"])
        sys.stdout.buffer.write(b"claimed\\n"); sys.stdout.buffer.flush()
        if sys.argv[2] == "terminal":
            helper.complete()
            sys.stdout.buffer.write(b"terminal\\n"); sys.stdout.buffer.flush()
            sys.stdin.buffer.read(1)
            helper.close()
            sys.stdout.buffer.write(b"closed\\n"); sys.stdout.buffer.flush()
        sys.stdin.buffer.read(1)
        helper.close()
    '''), encoding="utf-8")
    return script


@contextmanager
def running_helper(execution: lease.ExecutionLease, script: Path, mode: str) -> Iterator[subprocess.Popen[bytes]]:
    child = subprocess.Popen([sys.executable, "-I", str(script), str(Path(lease.__file__).resolve()), mode],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             cwd=script.parent, close_fds=True,
                             pass_fds=(execution.primary_fd,) if os.name != "nt" else ())
    assert child.stdin is not None and child.stdout is not None
    try:
        child.stdin.write(json.dumps(execution.to_config()).encode("ascii") + b"\n")
        child.stdin.flush()
        assert child.stdout.readline() == b"claimed\n"
        yield child
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None:
                stream.close()


def test_real_helper_terminal_guard_and_close_before_exit_window(root: Path, helper_script: Path) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        with running_helper(execution, helper_script, "terminal") as child:
            assert child.stdin is not None and child.stdout is not None
            assert child.stdout.readline() == b"terminal\n"
            record = read_record(root)
            assert record["helper"] == {"pid": child.pid, "created": psutil.Process(child.pid).create_time()}
            with pytest.raises(lease.RuntimeLeaseError, match="guard"):
                lease.check_execution_admission(root)
            child.stdin.write(b"c")
            child.stdin.flush()
            assert child.stdout.readline() == b"closed\n"
            with pytest.raises(lease.RuntimeLeaseError, match="helper has not exited"):
                lease.check_execution_admission(root)
            child.stdin.write(b"e")
            child.stdin.flush()
            assert child.wait(timeout=5) == 0
            lease.check_execution_admission(root)
            assert not (root / lease.EXECUTION_RECORD_NAME).exists()


def test_real_helper_crash_leaves_running_record_blocked(root: Path, helper_script: Path) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        with running_helper(execution, helper_script, "running") as child:
            before = (root / lease.EXECUTION_RECORD_NAME).read_bytes()
            child.kill()
            child.wait(timeout=5)
            with pytest.raises(lease.RuntimeLeaseError, match="unconfirmed"):
                lease.check_execution_admission(root)
            assert (root / lease.EXECUTION_RECORD_NAME).read_bytes() == before


@pytest.mark.skipif(os.name == "nt", reason="POSIX inherited open-file-description semantics")
def test_helper_close_never_unlocks_hosts_shared_flock(root: Path, helper_script: Path) -> None:
    import fcntl
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        with running_helper(execution, helper_script, "terminal") as child:
            assert child.stdin is not None and child.stdout is not None
            assert child.stdout.readline() == b"terminal\n"
            child.stdin.write(b"c")
            child.stdin.flush()
            assert child.stdout.readline() == b"closed\n"
            contender = os.open(root / ".kuma-operation.lock", os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(contender)


@pytest.mark.skipif(os.name == "nt", reason="POSIX inherited open-file-description semantics")
def test_helper_retains_primary_flock_after_host_closes_last_copy(root: Path, helper_script: Path) -> None:
    import fcntl
    fd = os.open(root / ".kuma-operation.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        execution = lease.OperationLease(root, fd).prepare()
        with running_helper(execution, helper_script, "running") as child:
            os.close(fd)
            fd = -1
            contender = os.open(root / ".kuma-operation.lock", os.O_RDWR)
            try:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                child.kill()
                child.wait(timeout=5)
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with pytest.raises(lease.RuntimeLeaseError, match="unconfirmed"):
                    lease.check_execution_admission(root)
            finally:
                os.close(contender)
    finally:
        if fd >= 0:
            os.close(fd)


def test_root_replacement_is_not_adopted(root: Path) -> None:
    managed = root / "managed"
    managed.mkdir()
    with primary(managed) as fd:
        operation = lease.OperationLease(managed, fd)
    # Windows denies renaming a directory containing the open primary handle.
    # Release/reopen the same old lock only in this fixture, preserving the
    # captured root identity and testing stale-directory refusal on every OS.
    managed.rename(root / "original")
    managed.mkdir()
    with primary(root / "original") as original_fd:
        operation.primary_fd = original_fd
        with pytest.raises(lease.RuntimeLeaseError, match="directory identity"):
            operation.prepare()
    assert not (managed / lease.EXECUTION_RECORD_NAME).exists()
    assert not (root / "original" / lease.EXECUTION_RECORD_NAME).exists()


def test_primary_lock_file_replacement_refuses_prepare(root: Path) -> None:
    with primary(root) as fd:
        operation = lease.OperationLease(root, fd)
        replacement = root / "replacement"
        replacement.write_bytes(b"")
        # Native Windows may refuse replacing an open lock, which is safe too.
        try:
            replacement.replace(root / ".kuma-operation.lock")
        except PermissionError:
            pytest.skip("OS prevents replacement of the opened lock")
        with pytest.raises(lease.RuntimeLeaseError):
            operation.prepare()
    assert not (root / lease.EXECUTION_RECORD_NAME).exists()


def test_ancestor_symlink_is_rejected(root: Path) -> None:
    actual = root / "actual"
    actual.mkdir()
    alias = root / "alias"
    try:
        alias.symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip("Native symlink privilege is unavailable")
    (actual / "managed").mkdir()
    with pytest.raises(lease.RuntimeLeaseError, match="directory"):
        lease.check_execution_admission(alias / "managed")
    assert not list((actual / "managed").iterdir())


def test_windows_reparse_metadata_is_refused_on_regular_file(root: Path) -> None:
    path = root / "fixture"
    path.write_bytes(b"x")
    info = path.stat()
    reparse = cast(os.stat_result, SimpleNamespace(
        st_mode=info.st_mode, st_nlink=info.st_nlink, st_size=info.st_size,
        st_file_attributes=0x400))
    with pytest.raises(lease.RuntimeLeaseError, match="single-link regular"):
        lease._regular(reparse, lease.MAX_RECORD_BYTES)


def test_short_writes_still_publish_whole_record(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_write = os.write

    def short_write(fd: int, data: Any) -> int:
        return original_write(fd, data[:7])

    with primary(root) as fd:
        monkeypatch.setattr(lease.os, "write", short_write)
        execution = lease.OperationLease(root, fd).prepare()
        assert read_record(root)["token"] == execution.token
        assert not list(root.glob(".kuma-execution-*.tmp"))


def test_terminal_identity_uncertainty_preserves_proof(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with primary(root) as fd:
        execution = lease.OperationLease(root, fd).prepare()
        helper = lease.HelperLease.claim(borrowed_config(execution), execution.token)
        helper.complete()
        helper.close()
        before = (root / lease.EXECUTION_RECORD_NAME).read_bytes()

        def unknown(_pid: int | None = None) -> None:
            raise psutil.AccessDenied()

        monkeypatch.setattr(lease.psutil, "Process", unknown)
        with pytest.raises(lease.RuntimeLeaseError, match="exact helper exit"):
            lease.check_execution_admission(root)
        assert (root / lease.EXECUTION_RECORD_NAME).read_bytes() == before
