"""Bounded, offline storage for a future KUMA-managed optional CPU runtime.

There is deliberately no production artifact: redistribution/licensing has not
been cleared. A catalog is trusted application code, never RPC/user input. This
module cannot download, import, or execute a runtime. ``installed`` means exact
catalog bytes and executable permissions were verified, not that inference or
platform execution has been tested. Future distributable ZIPs must be normalized
regular-files-only packages; an arbitrary PyInstaller onedir (which may contain
symlinks) is not a compatible archive. Actual packaged file counts and all three
platforms still need validation before a catalog entry may be published.

Mutations use an OS-backed nonblocking exclusive lock. Runtime jobs must hold
``operation_lock()`` from verification until process completion too. Cleanup is
for startup, not automatic deletion of an active installation's staging files.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import struct
import tempfile
import zipfile
import zlib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import BinaryIO, Literal

if __package__:
    from .domain_lease import OperationLease, RuntimeLeaseError, check_execution_admission
else:
    # Minimal frozen lifecycle probe bundles these exact modules as aliases.
    from domain_lease import OperationLease, RuntimeLeaseError, check_execution_admission

MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_FILE_BYTES = 1024 * 1024 * 1024
MAX_INSTALLED_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILES = 2048
MAX_MEMBERS = MAX_FILES * 2
MAX_PATH_BYTES = 240
MAX_PATH_DEPTH = 16
CHUNK_BYTES = 1024 * 1024
ENGINE = "merizo"
PLATFORMS = frozenset({"linux-x86_64", "macos-arm64", "windows-x86_64"})
_ROOT_NAME = "optional-runtimes"
_ROOT_MARKER = ".kuma-optional-runtimes.json"
_ROOT_BYTES = b'{"owner":"kuma","schema":"optional-runtime-root-v1"}\n'
_RECEIPT = ".kuma-runtime.json"
_LOCK_FILE = ".kuma-operation.lock"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}\Z")
_RESERVED = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?\Z", re.I)
CancelCheck = Callable[[], bool] | None
RuntimeState = Literal["installed", "missing", "corrupt", "licensing_blocked", "unsupported_platform"]


class OptionalRuntimeError(ValueError):
    """Unsafe, unsupported, unavailable, or corrupt optional runtime storage."""


class RuntimeCancelled(OptionalRuntimeError):
    """The caller cancelled before the atomic installation/removal commit."""


@dataclass(frozen=True)
class RuntimeFile:
    path: str
    sha256: str
    size: int
    executable: bool = False


@dataclass(frozen=True)
class RuntimeArtifact:
    engine: str
    version: str
    platform: str
    archive_sha256: str
    archive_size: int
    files: tuple[RuntimeFile, ...]
    executable_path: str


@dataclass(frozen=True)
class RuntimeStatus:
    state: RuntimeState
    engine: str
    platform: str
    version: str | None
    message: str
    executable_path: str | None = None


# Never fill this from disk, an environment variable, a request, or an archive.
# A reviewed release must supply pinned artifacts and the license/notice bundle.
PRODUCTION_CATALOG: Mapping[tuple[str, str], RuntimeArtifact] = MappingProxyType({})


def current_platform_key() -> str:
    system = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(
        platform.system(), "unsupported")
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{arch}"


def _cancel(cancelled: CancelCheck) -> None:
    if cancelled is not None and cancelled():
        raise RuntimeCancelled("Optional runtime operation cancelled")


def _safe_name(name: str) -> str:
    # ASCII intentionally excludes Unicode/case normalization aliases across OSes.
    if (not isinstance(name, str) or not name or not name.isascii()
            or len(name.encode("ascii")) > MAX_PATH_BYTES or "\\" in name
            or ":" in name or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        raise OptionalRuntimeError("Unsafe runtime member path")
    parts = name.split("/")
    if (len(parts) > MAX_PATH_DEPTH or any(
            not part or part in {".", ".."} or part.endswith((".", " "))
            or _RESERVED.fullmatch(part) or any(c in part for c in '<>"|?*')
            for part in parts)):
        raise OptionalRuntimeError("Unsafe runtime member path")
    return name


def _manifest_dirs(artifact: RuntimeArtifact) -> set[str]:
    return {"/".join(f.path.split("/")[:i]) for f in artifact.files
            for i in range(1, len(f.path.split("/")))}


def _validate_artifact(artifact: RuntimeArtifact) -> None:
    if (artifact.engine != ENGINE or not _TOKEN.fullmatch(artifact.version)
            or artifact.platform not in PLATFORMS or not _HASH.fullmatch(artifact.archive_sha256)
            or type(artifact.archive_size) is not int
            or not 1 <= artifact.archive_size <= MAX_ARCHIVE_BYTES
            or not isinstance(artifact.files, tuple) or not 1 <= len(artifact.files) <= MAX_FILES):
        raise OptionalRuntimeError("Invalid trusted optional runtime catalog entry")
    names: set[str] = set()
    total = 0
    for member in artifact.files:
        name = _safe_name(member.path)
        if (name.casefold() in names or name.casefold() == _RECEIPT.casefold()
                or not _HASH.fullmatch(member.sha256) or type(member.size) is not int
                or not 0 <= member.size <= MAX_FILE_BYTES or type(member.executable) is not bool):
            raise OptionalRuntimeError("Invalid or duplicate runtime manifest member")
        names.add(name.casefold())
        total += member.size
    dirs = _manifest_dirs(artifact)
    if (total > MAX_INSTALLED_BYTES or names & {d.casefold() for d in dirs}
            or _RECEIPT.casefold() in {d.casefold() for d in dirs}
            or len({d.casefold() for d in dirs}) != len(dirs)
            or len(dirs) + len(names) > MAX_MEMBERS):
        raise OptionalRuntimeError("Runtime manifest exceeds bounds or aliases a path")
    executable = next((f for f in artifact.files if f.path == artifact.executable_path), None)
    if executable is None or not executable.executable or executable.size == 0:
        raise OptionalRuntimeError("Catalog executable identity is missing")


def _receipt(artifact: RuntimeArtifact) -> bytes:
    return (json.dumps({"schema": "kuma-optional-runtime-v1", **asdict(artifact)},
                       sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _is_link(info: os.stat_result) -> bool:
    return (stat.S_ISLNK(info.st_mode)
            or bool(getattr(info, "st_file_attributes", 0)
                    & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))


def _directory_chain(path: Path, *, allow_missing: bool = False) -> None:
    """Refuse symlinks/junctions, including ancestors of the app-owned root."""
    for component in reversed((path, *path.parents)):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if allow_missing:
                return
            raise
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise OptionalRuntimeError("Runtime directory is not a real directory")


def _open_regular(path: Path) -> BinaryIO:
    before = path.lstat()
    if _is_link(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise OptionalRuntimeError("Runtime files must be regular files, without links")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    try:
        actual = os.fstat(fd)
        if ((before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino)
                or not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1):
            raise OptionalRuntimeError("Runtime file changed during verification")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _read_exact(path: Path, expected: bytes) -> None:
    with _open_regular(path) as handle:
        if handle.read(len(expected) + 1) != expected:
            raise OptionalRuntimeError("Runtime ownership metadata is missing or corrupt")


def _hash_handle(handle: BinaryIO, size: int, cancelled: CancelCheck) -> str:
    digest = hashlib.sha256()
    left = size
    while left:
        _cancel(cancelled)
        data = handle.read(min(CHUNK_BYTES, left))
        if not data:
            raise OptionalRuntimeError("Runtime file is shorter than its manifest")
        digest.update(data)
        left -= len(data)
    if handle.read(1):
        raise OptionalRuntimeError("Runtime file exceeds its manifest size")
    _cancel(cancelled)
    return digest.hexdigest()


def _tree(root: Path, cancelled: CancelCheck = None) -> tuple[set[str], set[str]]:
    _directory_chain(root)
    files: set[str] = set()
    dirs: set[str] = set()
    pending = [root]
    device = root.lstat().st_dev
    while pending:
        _cancel(cancelled)
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                _cancel(cancelled)
                info = entry.stat(follow_symlinks=False)
                # Preserve cached reparse flags: even no-follow stat may resolve
                # non-name-surrogate reparse points on Windows. Other entries
                # need fresh stat because the Windows cache zeros dev/nlink.
                if not _is_link(info):
                    info = os.stat(entry.path, follow_symlinks=False)
                name = Path(entry.path).relative_to(root).as_posix()
                if (_is_link(info) or info.st_dev != device
                        or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
                    raise OptionalRuntimeError("Runtime tree contains a link, mount, or special file")
                if stat.S_ISDIR(info.st_mode):
                    dirs.add(name)
                    pending.append(Path(entry.path))
                else:
                    if info.st_nlink != 1:
                        raise OptionalRuntimeError("Runtime tree contains a hard link")
                    files.add(name)
                if len(files) + len(dirs) > MAX_MEMBERS + 8:
                    raise OptionalRuntimeError("Runtime tree exceeds member count limit")
                if len(Path(name).parts) > MAX_PATH_DEPTH + 2:
                    raise OptionalRuntimeError("Runtime tree exceeds path depth limit")
    return files, dirs


def _remove_tree(root: Path) -> None:
    # Never recursively remove a link, junction, mount, or an unbounded tree.
    _tree(root)
    shutil.rmtree(root)


def _preflight_zip(handle: BinaryIO, archive_size: int) -> None:
    """Bound central-directory allocation before ZipFile parses untrusted bytes."""
    handle.seek(max(0, archive_size - 65557))
    tail = handle.read(65557)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or offset + 22 > len(tail):
        raise OptionalRuntimeError("Runtime archive must be a standard ZIP")
    disk, start_disk, disk_count, count, directory_size, directory_offset, comment = struct.unpack_from(
        "<4H2IH", tail, offset + 4)
    absolute_offset = max(0, archive_size - 65557) + offset
    if (disk or start_disk or disk_count != count or not 1 <= count <= MAX_MEMBERS
            or comment or offset + 22 != len(tail)
            or directory_size > MAX_MEMBERS * (46 + MAX_PATH_BYTES)
            or directory_offset + directory_size != absolute_offset):
        raise OptionalRuntimeError("Unsupported or oversized runtime ZIP directory")
    handle.seek(directory_offset)
    for _ in range(count):
        header = handle.read(46)
        if len(header) != 46 or header[:4] != b"PK\x01\x02":
            raise OptionalRuntimeError("Inconsistent runtime ZIP directory")
        name_size, extra_size, comment_size = struct.unpack_from("<3H", header, 28)
        if not 1 <= name_size <= MAX_PATH_BYTES or extra_size or comment_size:
            raise OptionalRuntimeError("ZIP names, extra fields, or comments are unsupported")
        handle.seek(name_size, os.SEEK_CUR)
    if handle.tell() != absolute_offset:
        raise OptionalRuntimeError("Runtime ZIP directory size does not match member count")
    handle.seek(0)


class OptionalRuntimeManager:
    """A single fixed version per engine/platform, with no auto-update behavior.

    ``app_data_root`` must be a trusted canonical app-data directory, not a project
    path or request parameter. Symlink/junction ancestors are deliberately refused;
    the host must canonicalize its trusted app-data root before construction.
    A nondefault catalog is only for trusted application
    construction/testing. No operation executes the catalog executable.
    """

    def __init__(self, app_data_root: str | Path, *,
                 catalog: Mapping[tuple[str, str], RuntimeArtifact] | None = None,
                 platform_key: str | None = None) -> None:
        self.app_data_root = Path(os.path.abspath(app_data_root))
        self.root = self.app_data_root / _ROOT_NAME
        self.platform_key = platform_key or current_platform_key()
        copied = dict(PRODUCTION_CATALOG if catalog is None else catalog)
        for key, artifact in copied.items():
            _validate_artifact(artifact)
            if key != (artifact.engine, artifact.platform):
                raise OptionalRuntimeError("Catalog key differs from runtime identity")
        self._catalog = MappingProxyType(copied)

    def _artifact(self, engine: str) -> RuntimeArtifact:
        if engine != ENGINE:
            raise OptionalRuntimeError("Unsupported optional runtime engine")
        if self.platform_key not in PLATFORMS:
            raise OptionalRuntimeError("Unsupported optional runtime platform")
        artifact = self._catalog.get((engine, self.platform_key))
        if artifact is None:
            raise OptionalRuntimeError("Optional runtime licensing/redistribution is not cleared; "
                                       "no approved artifact is available for this platform")
        return artifact

    def _target(self, artifact: RuntimeArtifact) -> Path:
        return self.root / f"{artifact.engine}-{artifact.version}-{artifact.platform}"

    def _stage_prefix(self, artifact: RuntimeArtifact) -> str:
        identity = hashlib.sha256(_receipt(artifact)).hexdigest()
        return f".stage-{identity}-"

    def _check_root(self) -> None:
        _directory_chain(self.root)
        _read_exact(self.root / _ROOT_MARKER, _ROOT_BYTES)

    @contextmanager
    def operation_lock(self) -> Iterator[OperationLease]:
        """Exclude other installs/removals/cleanups and cooperating runtime jobs.

        Non-reentrant and nonblocking, including between manager instances.
        A runtime helper also retains an execution lease and bounded proof
        record, so host termination does not authorize concurrent mutation.
        Never delete either lock file or an unproved execution record.
        The app-owned root must already exist (a verified installation does).
        """
        self._check_root()
        path = self.root / _LOCK_FILE
        fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_BINARY", 0), 0o600)
        locked = False
        try:
            actual = os.fstat(fd)
            named = path.lstat()
            if (_is_link(named) or not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1
                    or (named.st_dev, named.st_ino) != (actual.st_dev, actual.st_ino)
                    or actual.st_size > 1):
                raise OptionalRuntimeError("Unsafe optional runtime operation lock")
            if os.name == "nt":
                import msvcrt
                if actual.st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    raise OptionalRuntimeError("Another optional runtime operation is in progress") from exc
            else:
                import fcntl
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    raise OptionalRuntimeError("Another optional runtime operation is in progress") from exc
            locked = True
            self._check_root()
            try:
                check_execution_admission(self.root)
            except RuntimeLeaseError as exc:
                raise OptionalRuntimeError(str(exc)) from exc
            yield OperationLease(self.root, fd)
        finally:
            try:
                if locked:
                    if os.name == "nt":
                        import msvcrt
                        os.lseek(fd, 0, os.SEEK_SET)
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                    # POSIX inherited descriptors share one flock. Explicit
                    # LOCK_UN would also unlock the helper's borrowed lease.
                    # Close only; the last owner releases the shared lock.
            finally:
                os.close(fd)

    def _create_root(self) -> None:
        # Do not adopt an existing, unmarked directory or follow an ancestor link.
        _directory_chain(self.app_data_root, allow_missing=True)
        self.app_data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _directory_chain(self.app_data_root)
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            self._check_root()
        else:
            try:
                with (self.root / _ROOT_MARKER).open("xb") as handle:
                    handle.write(_ROOT_BYTES)
                    handle.flush()
                    os.fsync(handle.fileno())
            except BaseException:
                # Preserve evidence if root creation itself was interrupted.
                raise
        self._check_root()

    def _verify_tree(self, target: Path, artifact: RuntimeArtifact,
                     cancelled: CancelCheck = None) -> None:
        files, dirs = _tree(target, cancelled)
        if (files != {f.path for f in artifact.files} | {_RECEIPT}
                or dirs != _manifest_dirs(artifact)):
            raise OptionalRuntimeError("Runtime tree does not exactly match its manifest")
        _read_exact(target / _RECEIPT, _receipt(artifact))
        for member in artifact.files:
            _cancel(cancelled)
            path = target / member.path
            with _open_regular(path) as handle:
                info = os.fstat(handle.fileno())
                if info.st_size != member.size or _hash_handle(handle, member.size, cancelled) != member.sha256:
                    raise OptionalRuntimeError("Runtime file SHA-256 or size differs from catalog")
                if os.name != "nt":
                    mode = stat.S_IMODE(info.st_mode)
                    expected = 0o700 if member.executable else 0o600
                    if mode != expected:
                        raise OptionalRuntimeError("Runtime executable permissions differ from catalog")

    def status(self, engine: str = ENGINE, *, cancelled: CancelCheck = None) -> RuntimeStatus:
        _cancel(cancelled)
        if engine != ENGINE:
            raise OptionalRuntimeError("Unsupported optional runtime engine")
        if self.platform_key not in PLATFORMS:
            return RuntimeStatus("unsupported_platform", engine, self.platform_key, None,
                                 "Optional runtime installation is not supported on this platform.")
        artifact = self._catalog.get((engine, self.platform_key))
        if artifact is None:
            return RuntimeStatus("licensing_blocked", engine, self.platform_key, None,
                                 "Licensing/redistribution is not cleared; no approved runtime "
                                 "artifact is available for this platform.")
        try:
            # lexists notices dangling symlinks instead of misreporting missing.
            if not os.path.lexists(self.root):
                _directory_chain(self.app_data_root, allow_missing=True)
                return RuntimeStatus("missing", engine, self.platform_key, artifact.version,
                                     "The optional runtime is not installed.")
            self._check_root()
            target = self._target(artifact)
            if not os.path.lexists(target):
                return RuntimeStatus("missing", engine, self.platform_key, artifact.version,
                                     "The optional runtime is not installed.")
            self._verify_tree(target, artifact, cancelled)
        except RuntimeCancelled:
            raise
        except (OSError, OptionalRuntimeError) as exc:
            return RuntimeStatus("corrupt", engine, self.platform_key, artifact.version, str(exc))
        return RuntimeStatus("installed", engine, self.platform_key, artifact.version,
                             "The installed runtime matches the trusted catalog.",
                             str(target / artifact.executable_path))

    def verify(self, engine: str = ENGINE, *, cancelled: CancelCheck = None) -> RuntimeStatus:
        """Verify bytes afresh; no cached success or executable launch is used."""
        return self.status(engine, cancelled=cancelled)

    def install(self, archive_path: str | Path, *, engine: str = ENGINE,
                cancelled: CancelCheck = None) -> RuntimeStatus:
        artifact = self._artifact(engine)  # Fail closed before reading the archive.
        _cancel(cancelled)
        existing = self.status(engine, cancelled=cancelled)
        if existing.state == "installed":
            return existing
        if existing.state == "corrupt":
            raise OptionalRuntimeError("Remove the corrupt app-owned runtime before reinstalling")
        try:
            with _open_regular(Path(archive_path)) as handle:
                if os.fstat(handle.fileno()).st_size != artifact.archive_size:
                    raise OptionalRuntimeError("Runtime archive size differs from catalog")
                if _hash_handle(handle, artifact.archive_size, cancelled) != artifact.archive_sha256:
                    raise OptionalRuntimeError("Runtime archive SHA-256 differs from catalog")
                _preflight_zip(handle, artifact.archive_size)
                with zipfile.ZipFile(handle) as archive:
                    members = self._check_archive(archive, artifact)
                    _cancel(cancelled)
                    self._create_root()
                    with self.operation_lock():
                        existing = self.status(engine, cancelled=cancelled)
                        if existing.state == "installed":
                            return existing
                        if existing.state != "missing":
                            raise OptionalRuntimeError("Runtime changed during installation")
                        self._extract_and_promote(archive, members, artifact, cancelled)
                        return self.status(engine)
        except RuntimeCancelled:
            raise
        except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, zlib.error) as exc:
            raise OptionalRuntimeError(f"Cannot install optional runtime: {exc}") from exc

    def _extract_and_promote(self, archive: zipfile.ZipFile,
                             members: dict[str, zipfile.ZipInfo], artifact: RuntimeArtifact,
                             cancelled: CancelCheck) -> None:
        stage = Path(tempfile.mkdtemp(prefix=self._stage_prefix(artifact), dir=self.root))
        try:
            payload = stage / "payload"
            payload.mkdir(mode=0o700)
            for member in artifact.files:
                _cancel(cancelled)
                destination = payload / member.path
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                digest = hashlib.sha256()
                with archive.open(members[member.path]) as source, destination.open("xb") as output:
                    left = member.size
                    while left:
                        _cancel(cancelled)
                        data = source.read(min(CHUNK_BYTES, left))
                        if not data:
                            raise OptionalRuntimeError("Truncated runtime archive member")
                        output.write(data)
                        digest.update(data)
                        left -= len(data)
                    if source.read(1) or digest.hexdigest() != member.sha256:
                        raise OptionalRuntimeError("Runtime member SHA-256 or size differs from catalog")
                    output.flush()
                    os.fsync(output.fileno())
                destination.chmod(0o700 if member.executable else 0o600)
            with (payload / _RECEIPT).open("xb") as receipt:
                receipt.write(_receipt(artifact))
                receipt.flush()
                os.fsync(receipt.fileno())
            self._verify_tree(payload, artifact, cancelled)
            _cancel(cancelled)
            self._check_root()
            target = self._target(artifact)
            if os.path.lexists(target):
                raise OptionalRuntimeError("Runtime target appeared during installation")
            # Stage and destination share a filesystem. No existing runtime is
            # replaced, and cancelled work never becomes the target.
            payload.rename(target)
        finally:
            if os.path.lexists(stage):
                _remove_tree(stage)

    def _check_archive(self, archive: zipfile.ZipFile,
                       artifact: RuntimeArtifact) -> dict[str, zipfile.ZipInfo]:
        expected = {f.path: f for f in artifact.files}
        expected_dirs = _manifest_dirs(artifact)
        found: dict[str, zipfile.ZipInfo] = {}
        seen: set[str] = set()
        infos = archive.infolist()
        if not 1 <= len(infos) <= MAX_MEMBERS:
            raise OptionalRuntimeError("Runtime archive exceeds member count limit")
        for info in infos:
            name = _safe_name(info.orig_filename[:-1] if info.is_dir() else info.orig_filename)
            if name.casefold() in seen:
                raise OptionalRuntimeError("Duplicate runtime archive member")
            seen.add(name.casefold())
            mode = info.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if (kind not in ({0, stat.S_IFDIR} if info.is_dir() else {0, stat.S_IFREG})
                    or mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX)
                    or info.extra or info.comment or info.flag_bits & 1
                    or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}):
                raise OptionalRuntimeError("Runtime archive contains links or unsupported member metadata")
            if info.is_dir():
                if name not in expected_dirs or info.file_size:
                    raise OptionalRuntimeError("Unexpected runtime archive directory")
            else:
                if name not in expected or info.file_size != expected[name].size:
                    raise OptionalRuntimeError("Runtime archive differs from exact manifest")
                found[name] = info
        if found.keys() != expected.keys():
            raise OptionalRuntimeError("Runtime archive is missing a manifest member")
        return found

    def cleanup_interrupted(self, *, engine: str = ENGINE) -> int:
        """Remove only reserved stages for this pinned artifact, while no job runs."""
        artifact = self._artifact(engine)
        _directory_chain(self.app_data_root, allow_missing=True)
        if not os.path.lexists(self.root):
            return 0
        with self.operation_lock():
            self._check_root()
            prefix = self._stage_prefix(artifact)
            count = 0
            with os.scandir(self.root) as entries:
                for entry in entries:
                    # mkdtemp uses an eight-character lowercase/digit/underscore suffix.
                    if re.fullmatch(re.escape(prefix) + r"[a-z0-9_]{8}", entry.name):
                        _remove_tree(Path(entry.path))
                        count += 1
            return count

    def remove(self, *, engine: str = ENGINE, cancelled: CancelCheck = None) -> RuntimeStatus:
        artifact = self._artifact(engine)
        _cancel(cancelled)
        _directory_chain(self.app_data_root, allow_missing=True)
        if not os.path.lexists(self.root):
            return self.status(engine)
        with self.operation_lock():
            self._check_root()
            target = self._target(artifact)
            if not os.path.lexists(target):
                return self.status(engine)
            _directory_chain(target)
            # A corrupt payload may be removed, but ownership cannot be inferred from
            # a directory's name alone. Never delete arbitrary user-selected paths.
            _read_exact(target / _RECEIPT, _receipt(artifact))
            _tree(target, cancelled)
            _cancel(cancelled)
            stage = Path(tempfile.mkdtemp(prefix=self._stage_prefix(artifact), dir=self.root))
            try:
                target.rename(stage / "payload")
                # Removal is committed by rename. Complete deletion after this point
                # even if cancellation is requested; startup can recover interruption.
                _remove_tree(stage)
            except BaseException:
                if stage.exists() and not any(stage.iterdir()):
                    stage.rmdir()
                raise
            return self.status(engine)
