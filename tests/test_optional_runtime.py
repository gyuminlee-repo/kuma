"""Synthetic storage fixtures only: these bytes are not a runnable ML runtime."""
from __future__ import annotations

import hashlib
import io
import os
import stat
import struct
import tarfile
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from kuma_core.kuro import optional_runtime as runtime

PLATFORM = "linux-x86_64"
FILES = {"bin/merizo-cpu": b"synthetic executable identity; never execute\x00\x01",
         "models/weights.bin": b"synthetic non-model fixture\x02\x03",
         "NOTICE.txt": b"Test data only; not a third-party distribution.\n"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_bytes(entries: list[tuple[str | zipfile.ZipInfo, bytes]] | None = None) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in entries if entries is not None else FILES.items():
            archive.writestr(name, contents)
    return out.getvalue()


def artifact_for(raw: bytes) -> runtime.RuntimeArtifact:
    return runtime.RuntimeArtifact(
        "merizo", "fixture-1", PLATFORM, sha(raw), len(raw),
        tuple(runtime.RuntimeFile(name, sha(data), len(data), name.startswith("bin/"))
              for name, data in FILES.items()), "bin/merizo-cpu")


def setup_runtime(tmp_path: Path, raw: bytes | None = None) -> tuple[
        runtime.OptionalRuntimeManager, Path, runtime.RuntimeArtifact]:
    tmp_path = tmp_path.resolve()  # macOS /var and /tmp may be trusted OS aliases.
    raw = archive_bytes() if raw is None else raw
    archive = tmp_path / "runtime.zip"
    archive.write_bytes(raw)
    artifact = artifact_for(raw)
    manager = runtime.OptionalRuntimeManager(
        tmp_path / "app-data", catalog={("merizo", PLATFORM): artifact}, platform_key=PLATFORM)
    return manager, archive, artifact


def installed_target(manager: runtime.OptionalRuntimeManager) -> Path:
    status = manager.status()
    assert status.state == "installed"
    assert status.executable_path is not None
    return Path(status.executable_path).parent.parent


def test_production_catalog_stays_empty_and_license_blocked(tmp_path: Path) -> None:
    assert not runtime.PRODUCTION_CATALOG
    manager = runtime.OptionalRuntimeManager(tmp_path / "unused", platform_key=PLATFORM)
    assert manager.status().state == manager.verify().state == "licensing_blocked"
    with pytest.raises(runtime.OptionalRuntimeError, match="licensing"):
        manager.install(tmp_path / "does-not-exist.zip")
    with pytest.raises(runtime.OptionalRuntimeError, match="licensing"):
        manager.remove()
    assert not (tmp_path / "unused").exists()


def test_install_verify_remove_exact_synthetic_payload(tmp_path: Path) -> None:
    manager, archive, artifact = setup_runtime(tmp_path)
    assert manager.status().state == "missing"
    assert not manager.root.exists()
    result = manager.install(archive)
    assert result.state == "installed"
    assert result.version == artifact.version
    target = installed_target(manager)
    for name, data in FILES.items():
        assert (target / name).read_bytes() == data
    assert manager.verify().state == "installed"
    assert not list(manager.root.glob(".stage-*"))
    assert manager.install(archive) == manager.status()  # No implicit update.
    assert manager.remove().state == "missing"
    assert archive.exists()
    assert manager.root.is_dir()
    assert manager.remove().state == "missing"


@pytest.mark.parametrize("changed", ["hash", "size"])
def test_archive_is_pinned_before_creating_any_runtime_files(tmp_path: Path, changed: str) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    raw = archive.read_bytes()
    archive.write_bytes(raw + b"extra" if changed == "size" else bytes([raw[0] ^ 1]) + raw[1:])
    with pytest.raises(runtime.OptionalRuntimeError, match="archive.*(size|SHA-256)"):
        manager.install(archive)
    assert not manager.root.exists()


@pytest.mark.parametrize("bad_name", ["../outside", "/absolute", "C:/evil", "a/../../evil",
                                        "a\\evil", "a//evil", "a/./evil", "NUL.txt",
                                        "a./evil", "evil ", "a/evil\x00suffix", "évil"])
def test_archive_rejects_unsafe_paths(tmp_path: Path, bad_name: str) -> None:
    entries: list[tuple[str | zipfile.ZipInfo, bytes]] = list(FILES.items())
    entries.append((bad_name, b"bad"))
    manager, archive, _ = setup_runtime(tmp_path, archive_bytes(entries))
    with pytest.raises(runtime.OptionalRuntimeError):
        manager.install(archive)
    assert not manager.root.exists()
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("kind", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK])
def test_archive_rejects_links_and_special_files(tmp_path: Path, kind: int) -> None:
    info = zipfile.ZipInfo("bin/merizo-cpu")
    info.create_system = 3
    info.external_attr = (kind | 0o755) << 16
    entries: list[tuple[str | zipfile.ZipInfo, bytes]] = [(info, FILES[info.filename])]
    entries.extend((name, data) for name, data in FILES.items() if name != info.filename)
    manager, archive, _ = setup_runtime(tmp_path, archive_bytes(entries))
    with pytest.raises(runtime.OptionalRuntimeError, match="links|unsupported"):
        manager.install(archive)
    assert not manager.root.exists()


def test_tar_hardlink_archive_is_not_an_accepted_format(tmp_path: Path) -> None:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        info = tarfile.TarInfo("bin/merizo-cpu")
        info.type = tarfile.LNKTYPE
        info.linkname = "../../outside"
        archive.addfile(info)
    manager, path, _ = setup_runtime(tmp_path, out.getvalue())
    with pytest.raises(runtime.OptionalRuntimeError, match="standard ZIP"):
        manager.install(path)


@pytest.mark.parametrize("kind", ["extra", "missing", "duplicate", "case_alias", "wrong_size", "extra_dir"])
def test_archive_requires_exact_file_manifest(tmp_path: Path, kind: str) -> None:
    entries: list[tuple[str | zipfile.ZipInfo, bytes]] = list(FILES.items())
    if kind == "extra":
        entries.append(("unlisted.txt", b"extra"))
    elif kind == "missing":
        entries.pop()
    elif kind == "duplicate":
        entries.append(entries[0])
    elif kind == "case_alias":
        entries.append(("BIN/MERIZO-CPU", FILES["bin/merizo-cpu"]))
    elif kind == "wrong_size":
        entries[0] = ("bin/merizo-cpu", b"different")
    else:
        entries.append(("unlisted/", b""))
    if kind == "duplicate":
        with pytest.warns(UserWarning, match="Duplicate"):
            raw = archive_bytes(entries)
    else:
        raw = archive_bytes(entries)
    manager, archive, _ = setup_runtime(tmp_path, raw)
    with pytest.raises(runtime.OptionalRuntimeError):
        manager.install(archive)
    assert not manager.root.exists()


def test_declared_directories_are_allowed(tmp_path: Path) -> None:
    entries: list[tuple[str | zipfile.ZipInfo, bytes]] = [("bin/", b""), ("models/", b"")]
    entries.extend(FILES.items())
    manager, archive, _ = setup_runtime(tmp_path, archive_bytes(entries))
    assert manager.install(archive).state == "installed"


def test_per_file_hash_mismatch_cleans_stage_and_never_promotes(tmp_path: Path) -> None:
    entries: list[tuple[str | zipfile.ZipInfo, bytes]] = list(FILES.items())
    entries[0] = ("bin/merizo-cpu", b"x" * len(FILES["bin/merizo-cpu"]))
    manager, archive, _ = setup_runtime(tmp_path, archive_bytes(entries))
    with pytest.raises(runtime.OptionalRuntimeError, match="SHA-256"):
        manager.install(archive)
    assert manager.status().state == "missing"
    assert not list(manager.root.glob(".stage-*"))


@pytest.mark.parametrize("change", ["file", "missing", "extra_file", "extra_dir", "receipt", "permission"])
def test_verify_rechecks_every_file_and_exact_tree(tmp_path: Path, change: str) -> None:
    if change == "permission" and os.name == "nt":
        pytest.skip("POSIX executable permissions are not available on Windows")
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    target = installed_target(manager)
    if change == "file":
        (target / "bin/merizo-cpu").write_bytes(b"x" * len(FILES["bin/merizo-cpu"]))
    elif change == "missing":
        (target / "NOTICE.txt").unlink()
    elif change == "extra_file":
        (target / "unlisted.dll").write_bytes(b"not approved")
    elif change == "extra_dir":
        (target / "unlisted").mkdir()
    elif change == "receipt":
        (target / ".kuma-runtime.json").write_text("{}")
    else:
        (target / "bin/merizo-cpu").chmod(0o600)
    result = manager.verify()
    assert result.state == "corrupt"
    assert result.executable_path is None
    with pytest.raises(runtime.OptionalRuntimeError, match="corrupt"):
        manager.install(archive)


def test_remove_corrupt_payload_only_with_exact_ownership(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    target = installed_target(manager)
    (target / "models/weights.bin").write_bytes(b"corrupt")
    unrelated = manager.root / "user-stuff"
    unrelated.mkdir()
    (unrelated / "keep").write_text("keep")
    assert manager.remove().state == "missing"
    assert (unrelated / "keep").read_text() == "keep"


def test_remove_refuses_unknown_ownership(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    target = installed_target(manager)
    (target / ".kuma-runtime.json").unlink()
    with pytest.raises((runtime.OptionalRuntimeError, OSError)):
        manager.remove()
    assert target.exists()


def make_symlink(source: Path, destination: Path, *, is_dir: bool = False) -> None:
    try:
        destination.symlink_to(source, target_is_directory=is_dir)
    except OSError:
        pytest.skip("This host does not permit test symlinks")


@pytest.mark.parametrize("place", ["app_data", "root", "target", "member", "receipt"])
def test_symlink_boundaries_never_follow_or_remove_outside(tmp_path: Path, place: str) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_bytes(b"must survive")
    if place == "app_data":
        make_symlink(outside, manager.app_data_root, is_dir=True)
    elif place == "root":
        manager.app_data_root.mkdir()
        make_symlink(outside, manager.root, is_dir=True)
    else:
        manager.install(archive)
        target = installed_target(manager)
        if place == "target":
            target.rename(outside / "saved-runtime")
            make_symlink(outside / "saved-runtime", target, is_dir=True)
        else:
            path = target / ("NOTICE.txt" if place == "member" else ".kuma-runtime.json")
            path.unlink()
            make_symlink(sentinel, path)
    assert manager.status().state == "corrupt"
    with pytest.raises((runtime.OptionalRuntimeError, OSError)):
        manager.remove()
    assert sentinel.read_bytes() == b"must survive"


def test_hardlinked_member_is_corrupt_and_removal_is_refused(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    target = installed_target(manager)
    outside = tmp_path / "outside"
    outside.write_bytes(FILES["NOTICE.txt"])
    member = target / "NOTICE.txt"
    member.unlink()
    os.link(outside, member)
    assert manager.status().state == "corrupt"
    with pytest.raises(runtime.OptionalRuntimeError, match="hard link"):
        manager.remove()
    assert outside.read_bytes() == FILES["NOTICE.txt"]


def test_unmarked_existing_root_is_not_adopted(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager.root.mkdir(parents=True)
    assert manager.status().state == "corrupt"
    with pytest.raises(runtime.OptionalRuntimeError):
        manager.install(archive)
    assert list(manager.root.iterdir()) == []


def test_cancellation_before_install_creates_nothing(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    with pytest.raises(runtime.RuntimeCancelled):
        manager.install(archive, cancelled=lambda: True)
    assert not manager.root.exists()


def test_cancellation_during_install_cleans_unpromoted_stage(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)

    def cancelled() -> bool:
        return manager.root.exists() and bool(list(manager.root.glob(".stage-*/payload/bin/*")))

    with pytest.raises(runtime.RuntimeCancelled):
        manager.install(archive, cancelled=cancelled)
    assert manager.status().state == "missing"
    assert not list(manager.root.glob(".stage-*"))


def test_cancellation_does_not_remove_existing_runtime(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    with pytest.raises(runtime.RuntimeCancelled):
        manager.remove(cancelled=lambda: True)
    assert manager.status().state == "installed"


def test_failed_atomic_promotion_leaves_no_partial_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, archive, _ = setup_runtime(tmp_path)

    def fail_rename(self: Path, target: Path) -> None:
        raise OSError("synthetic interrupted promotion")

    monkeypatch.setattr(Path, "rename", fail_rename)
    with pytest.raises(runtime.OptionalRuntimeError, match="interrupted promotion"):
        manager.install(archive)
    assert manager.status().state == "missing"
    assert not list(manager.root.glob(".stage-*"))


def test_interrupted_stage_cleanup_is_narrow_and_preserves_installed_runtime(tmp_path: Path) -> None:
    manager, archive, artifact = setup_runtime(tmp_path)
    manager.install(archive)
    prefix = manager._stage_prefix(artifact)
    interrupted = manager.root / f"{prefix}abc12345"
    (interrupted / "payload").mkdir(parents=True)
    (interrupted / "payload" / "partial").write_bytes(b"unfinished")
    unrelated = manager.root / ".stage-unrecognized-abc12345"
    unrelated.mkdir()
    assert manager.cleanup_interrupted() == 1
    assert not interrupted.exists()
    assert unrelated.exists()
    assert manager.status().state == "installed"
    assert manager.cleanup_interrupted() == 0


def test_interrupted_stage_symlink_is_never_followed(tmp_path: Path) -> None:
    manager, archive, artifact = setup_runtime(tmp_path)
    manager.install(archive)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    stage = manager.root / f"{manager._stage_prefix(artifact)}abc12345"
    make_symlink(outside, stage, is_dir=True)
    with pytest.raises(runtime.OptionalRuntimeError):
        manager.cleanup_interrupted()
    assert (outside / "keep").read_text() == "keep"


@pytest.mark.parametrize("change", ["sha", "size", "count", "total", "path", "executable", "collision", "key"])
def test_invalid_catalog_entries_are_rejected(tmp_path: Path, change: str) -> None:
    artifact = artifact_for(archive_bytes())
    if change == "sha":
        artifact = replace(artifact, archive_sha256="unpinned")
    elif change == "size":
        artifact = replace(artifact, archive_size=runtime.MAX_ARCHIVE_BYTES + 1)
    elif change == "count":
        artifact = replace(artifact, files=artifact.files * runtime.MAX_FILES)
    elif change == "total":
        artifact = replace(artifact, files=(replace(artifact.files[0], size=runtime.MAX_FILE_BYTES + 1),))
    elif change == "path":
        artifact = replace(artifact, files=(replace(artifact.files[0], path="../evil"),))
    elif change == "executable":
        artifact = replace(artifact, executable_path="missing")
    elif change == "collision":
        artifact = replace(artifact, files=artifact.files + (runtime.RuntimeFile("bin", sha(b""), 0),))
    key = ("wrong" if change == "key" else "merizo", PLATFORM)
    with pytest.raises(runtime.OptionalRuntimeError):
        runtime.OptionalRuntimeManager(tmp_path, catalog={key: artifact}, platform_key=PLATFORM)


def test_catalog_snapshot_cannot_change_after_manager_construction(tmp_path: Path) -> None:
    artifact = artifact_for(archive_bytes())
    catalog = {("merizo", PLATFORM): artifact}
    manager = runtime.OptionalRuntimeManager(tmp_path, catalog=catalog, platform_key=PLATFORM)
    catalog.clear()
    assert manager.status().state == "missing"


@pytest.mark.parametrize("change", ["comment", "extra", "zip64", "member_count", "central_size"])
def test_zip_preflight_bounds_metadata_before_parsing(tmp_path: Path, change: str) -> None:
    if change == "extra":
        info = zipfile.ZipInfo("bin/merizo-cpu")
        info.extra = b"\x0d\x00\x04\x00link"  # Reject Unix extension/link metadata.
        entries: list[tuple[str | zipfile.ZipInfo, bytes]] = [(info, FILES[info.filename])]
        entries.extend((n, d) for n, d in FILES.items() if n != info.filename)
        raw = archive_bytes(entries)
    else:
        raw_data = bytearray(archive_bytes())
        eocd = raw_data.rfind(b"PK\x05\x06")
        if change == "comment":
            struct.pack_into("<H", raw_data, eocd + 20, 1)
            raw_data.extend(b"x")
        elif change == "zip64":
            struct.pack_into("<I", raw_data, eocd + 12, 0xFFFFFFFF)
        elif change == "member_count":
            struct.pack_into("<2H", raw_data, eocd + 8, runtime.MAX_MEMBERS + 1, runtime.MAX_MEMBERS + 1)
        else:
            struct.pack_into("<I", raw_data, eocd + 12, 1)
        raw = bytes(raw_data)
    manager, archive, _ = setup_runtime(tmp_path, raw)
    with pytest.raises(runtime.OptionalRuntimeError):
        manager.install(archive)
    assert not manager.root.exists()


def test_unsupported_platform_cannot_borrow_other_platform_artifact(tmp_path: Path) -> None:
    artifact = artifact_for(archive_bytes())
    manager = runtime.OptionalRuntimeManager(tmp_path, catalog={("merizo", PLATFORM): artifact},
                                             platform_key="unknown-platform")
    assert manager.status().state == "unsupported_platform"


@pytest.mark.parametrize("action", ["install", "remove", "cleanup"])
def test_separate_managers_cannot_mutate_during_install(tmp_path: Path, action: str) -> None:
    manager, archive, artifact = setup_runtime(tmp_path)
    other = runtime.OptionalRuntimeManager(manager.app_data_root,
        catalog={("merizo", PLATFORM): artifact}, platform_key=PLATFORM)
    checked = False

    def check_race() -> bool:
        nonlocal checked
        if not checked and manager.root.exists() and list(manager.root.glob(".stage-*/payload")):
            checked = True
            with pytest.raises(runtime.OptionalRuntimeError, match="operation is in progress"):
                if action == "install":
                    other.install(archive)
                elif action == "remove":
                    other.remove()
                else:
                    other.cleanup_interrupted()
        return False

    assert manager.install(archive, cancelled=check_race).state == "installed"
    assert checked
    assert other.status().state == "installed"


def test_operation_lock_protects_runtime_job_until_released(tmp_path: Path) -> None:
    manager, archive, artifact = setup_runtime(tmp_path)
    manager.install(archive)
    other = runtime.OptionalRuntimeManager(manager.app_data_root,
        catalog={("merizo", PLATFORM): artifact}, platform_key=PLATFORM)
    with manager.operation_lock():
        assert manager.verify().state == "installed"
        with pytest.raises(runtime.OptionalRuntimeError, match="operation is in progress"):
            other.remove()
    assert other.remove().state == "missing"
    assert other.install(archive).state == "installed"


def test_failed_install_releases_operation_lock(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)

    def stop_after_stage_created() -> bool:
        return manager.root.exists() and bool(list(manager.root.glob(".stage-*")))

    with pytest.raises(runtime.RuntimeCancelled):
        manager.install(archive, cancelled=stop_after_stage_created)
    assert manager.install(archive).state == "installed"


def test_existing_operation_lock_symlink_is_rejected(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    lock = manager.root / ".kuma-operation.lock"
    lock.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"keep")
    make_symlink(outside, lock)
    with pytest.raises((OSError, runtime.OptionalRuntimeError)):
        manager.remove()
    assert outside.read_bytes() == b"keep"


def test_supported_empty_catalog_reports_licensing_not_platform_error(tmp_path: Path) -> None:
    for platform_key in runtime.PLATFORMS:
        manager = runtime.OptionalRuntimeManager(tmp_path, platform_key=platform_key)
        assert manager.status().state == "licensing_blocked"
    for platform_key in ("linux-arm64", "macos-x86_64", "windows-arm64"):
        manager = runtime.OptionalRuntimeManager(tmp_path, platform_key=platform_key)
        assert manager.status().state == "unsupported_platform"


def test_appearing_target_is_not_overwritten(tmp_path: Path) -> None:
    manager, archive, artifact = setup_runtime(tmp_path)
    appeared = False

    def create_conflicting_target() -> bool:
        nonlocal appeared
        if not appeared and manager.root.exists() and list(manager.root.glob(".stage-*/payload/.kuma-runtime.json")):
            appeared = True
            target = manager._target(artifact)
            target.mkdir()
            (target / "keep").write_bytes(b"not ours")
        return False

    with pytest.raises(runtime.OptionalRuntimeError, match="appeared"):
        manager.install(archive, cancelled=create_conflicting_target)
    assert (manager._target(artifact) / "keep").read_bytes() == b"not ours"
    assert not list(manager.root.glob(".stage-*"))


def test_cancelled_verification_is_not_reported_as_corruption(tmp_path: Path) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    with pytest.raises(runtime.RuntimeCancelled):
        manager.verify(cancelled=lambda: True)
    assert manager.status().state == "installed"


def test_interrupted_removal_can_be_cleaned_on_next_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    original_remove = runtime._remove_tree

    def interrupted_delete(path: Path) -> None:
        raise OSError("synthetic interruption after removal commit")

    monkeypatch.setattr(runtime, "_remove_tree", interrupted_delete)
    with pytest.raises(OSError, match="interruption"):
        manager.remove()
    assert manager.status().state == "missing"
    assert len(list(manager.root.glob(".stage-*"))) == 1
    monkeypatch.setattr(runtime, "_remove_tree", original_remove)
    assert manager.cleanup_interrupted() == 1
    assert not list(manager.root.glob(".stage-*"))
