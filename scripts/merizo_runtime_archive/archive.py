"""Normalize an internal onedir into the existing registry's regular-file ZIP.

The returned manifest is a build candidate for tests. Never load it into the
production catalog or treat a user's manifest as a trust decision.
"""
from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import shutil
import stat
import zipfile

from kuma_core.kuro.optional_runtime import (
    RuntimeArtifact, RuntimeFile, MAX_FILES, MAX_MEMBERS, MAX_INSTALLED_BYTES,
    MAX_FILE_BYTES, MAX_ARCHIVE_BYTES, _safe_name, _validate_artifact,
)
from scripts.merizo_runtime_archive.common import digest, write_json


def inventory(package: Path, executable: str) -> list[dict]:
    root = package.resolve(strict=True)
    if not root.is_dir() or package.is_symlink():
        raise ValueError('Package must be a real directory')
    _safe_name(executable)
    records = []
    total = entries = 0
    names = {}
    def walk(path: Path, logical: str, ancestors: tuple[Path, ...], aliases: tuple[str, ...]):
        nonlocal total, entries
        entries += 1
        if entries > MAX_MEMBERS:
            raise ValueError('Expanded bundle exceeds registry member bound')
        _safe_name(logical)
        folded = logical.casefold()
        if folded in names:
            raise ValueError('Case-fold path collision in expanded bundle')
        names[folded] = logical
        info = path.lstat()
        if getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Windows reparse points/junctions are not supported')
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError('Bundle alias escapes the original package')
        edges = aliases
        if stat.S_ISLNK(info.st_mode):
            edges += (logical + ' -> ' + resolved.relative_to(root).as_posix(),)
            info = resolved.stat()
        if stat.S_ISDIR(info.st_mode):
            if resolved in ancestors:
                raise ValueError('Bundle directory alias cycle')
            for child in sorted(resolved.iterdir(), key=lambda item: item.name):
                walk(child, logical + '/' + child.name, (*ancestors, resolved), edges)
        elif stat.S_ISREG(info.st_mode):
            total += info.st_size
            if len(records) >= MAX_FILES or total > MAX_INSTALLED_BYTES or info.st_size > MAX_FILE_BYTES:
                raise ValueError('Normalized bundle exceeds existing registry byte/file bound')
            records.append({'path': logical, 'source_path': str(resolved),
                            'original_path': resolved.relative_to(root).as_posix(),
                            'sha256': digest(resolved), 'size': info.st_size,
                            'executable': logical == executable or bool(info.st_mode & 0o111),
                            'aliases': list(edges)})
        else:
            raise ValueError('Bundle contains a nonregular file')
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        walk(child, child.name, (root,), ())
    return sorted(records, key=lambda record: record['path'])


def artifact_from_records(records, *, version, platform, executable, archive_sha256, archive_size):
    artifact = RuntimeArtifact('merizo', version, platform, archive_sha256, archive_size,
        tuple(RuntimeFile(**{key: row[key] for key in ('path', 'sha256', 'size', 'executable')})
              for row in records), executable)
    _validate_artifact(artifact)
    return artifact


def normalize_archive(package: Path, output: Path, *, version: str, platform: str,
                      executable: str) -> tuple[RuntimeArtifact, list[dict]]:
    """output is fresh and disjoint; failures remove only our created output."""
    source = package.resolve(strict=True)
    destination = output.resolve()
    if source.is_relative_to(destination) or destination.is_relative_to(source) or output.exists():
        raise ValueError('Archive output must be fresh and disjoint from package')
    records = inventory(package, executable)
    artifact_from_records(records, version=version, platform=platform, executable=executable,
                          archive_sha256='0' * 64, archive_size=1)  # Bounds only, never published.
    output.mkdir(parents=True, exist_ok=False)
    try:
        stage, archive_path = output / 'normalized', output / 'runtime.zip'
        stage.mkdir()
        for row in records:
            target = stage / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(row['source_path'], target)
            target.chmod(0o700 if row['executable'] else 0o600)
            if target.stat().st_size != row['size'] or digest(target) != row['sha256']:
                raise ValueError('Source changed during bundle normalization')
        with zipfile.ZipFile(archive_path, 'x', compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=False) as archive:
            for row in records:
                info = zipfile.ZipInfo(row['path'], (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | (0o700 if row['executable'] else 0o600)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                with archive.open(info, 'w') as outgoing, (stage / row['path']).open('rb') as incoming:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
                    raise ValueError('Compressed archive exceeds registry byte bound')
        artifact = artifact_from_records(records, version=version, platform=platform, executable=executable,
            archive_sha256=digest(archive_path), archive_size=archive_path.stat().st_size)
        write_json(output / 'candidate-manifest.json', asdict(artifact))
        return artifact, records
    except BaseException:
        shutil.rmtree(output)
        raise
