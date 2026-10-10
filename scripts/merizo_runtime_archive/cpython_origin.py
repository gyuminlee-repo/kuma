"""Acquire bounded official CPython provider/source candidate bytes for CI audit.

A matching version is NOT a matching installation. The builder rehashes these
archives and maps actual installed/frozen inputs to their member bytes; anything
unmatched stays unresolved. Discovery is pinned to the python-versions manifest
commit observed by this run, not retrospectively attributed to earlier runs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import tarfile
import urllib.parse
import urllib.request
import zipfile

from scripts.merizo_runtime_archive.common import digest, read_regular, strict_json, write_json
from scripts.merizo_runtime_archive.inputs import safe_member

MAX_METADATA = 8 * 1024 * 1024
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_MEMBERS = 30000
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
OFFICIAL_HOSTS = {'api.github.com', 'raw.githubusercontent.com', 'github.com',
                  'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
                  'codeload.github.com', 'www.python.org'}


def fetch(url: str, limit: int, destination: Path | None = None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in OFFICIAL_HOSTS or parsed.username or parsed.password:
        raise ValueError('Unapproved CPython/provider origin')
    request = urllib.request.Request(url, headers={'User-Agent': 'KUMA-internal-CPython-audit/1',
                                                   'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        final = urllib.parse.urlsplit(response.url)
        if final.scheme != 'https' or final.hostname not in OFFICIAL_HOSTS:
            raise ValueError('Unapproved CPython artifact redirect')
        size, chunks = 0, []
        outgoing = None if destination is None else destination.open('xb')
        try:
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > limit:
                    raise ValueError('CPython acquisition exceeds predeclared byte bound')
                if outgoing is None:
                    chunks.append(block)
                else:
                    outgoing.write(block)
        finally:
            if outgoing is not None:
                outgoing.close()
    return b''.join(chunks) if destination is None else b''


def archive_inventory(path: Path) -> list[dict]:
    entries, seen, total = [], set(), 0
    def add(name, size, stream=None, alias=None):
        nonlocal total
        name = name.removeprefix('./').rstrip('/')
        if not name:
            return
        safe_member(name)
        if name in seen or len(entries) >= MAX_MEMBERS:
            raise ValueError('Duplicate or oversized CPython archive inventory')
        seen.add(name)
        total += size
        if total > MAX_EXPANDED or size > MAX_ARCHIVE:
            raise ValueError('CPython archive expanded bytes exceed bounds')
        row = {'member': name, 'size': size}
        if stream is not None:
            checksum = hashlib.sha256()
            with stream:
                while block := stream.read(1024 * 1024):
                    checksum.update(block)
            row['sha256'] = checksum.hexdigest()
        else:
            row['alias'] = alias
        entries.append(row)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                if member.flag_bits & 1 or (member.external_attr >> 16) & 0o170000 not in {0, 0o100000}:
                    raise ValueError('Unsupported Python ZIP member')
                add(member.filename, member.file_size, archive.open(member))
    else:
        with tarfile.open(path, 'r|*') as archive:
            for member in archive:
                if member.isdir():
                    continue
                if member.isfile():
                    add(member.name, member.size, archive.extractfile(member))
                elif member.issym() or member.islnk():
                    add(member.name, 0, alias=member.linkname)
                else:
                    raise ValueError('Unsupported Python tar member')
    return entries


def acquire(output: Path, payload: Path, *, runner_platform_version: str | None = None):
    if payload.exists():
        raise ValueError('Use a fresh CPython-origin payload directory')
    payload.mkdir(parents=True, exist_ok=False)
    commit_info = strict_json(fetch('https://api.github.com/repos/actions/python-versions/commits/main', MAX_METADATA))
    manifest_commit = commit_info['sha']
    if not re.fullmatch('[0-9a-f]{40}', manifest_commit):
        raise ValueError('Unpinned official provider manifest')
    manifest_url = f'https://raw.githubusercontent.com/actions/python-versions/{manifest_commit}/versions-manifest.json'
    manifest_bytes = fetch(manifest_url, MAX_METADATA)
    releases = strict_json(manifest_bytes)
    version = platform.python_version()
    system = {'Linux': 'linux', 'Windows': 'win32', 'Darwin': 'darwin'}.get(platform.system())
    architecture = {'AMD64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64'}.get(platform.machine())
    options = [file for release in releases if release.get('version') == version
               for file in release.get('files', []) if file.get('platform') == system and file.get('arch') == architecture
               and (runner_platform_version is None or file.get('platform_version') in {None, runner_platform_version})]
    if len(options) != 1:
        raise ValueError('Cannot uniquely identify official candidate Python asset for this runner')
    asset = options[0]
    url = asset['download_url']
    parsed = urllib.parse.urlsplit(url)
    parts = parsed.path.split('/')
    if parsed.hostname != 'github.com' or parts[1:5] != ['actions', 'python-versions', 'releases', 'download'] or len(parts) != 7:
        raise ValueError('Unexpected Python provider asset URL')
    tag, filename = parts[5], urllib.parse.unquote(parts[6])
    safe_member(filename)
    binary = payload / filename
    fetch(url, MAX_ARCHIVE, binary)
    members = archive_inventory(binary)
    release_metadata = strict_json(fetch('https://api.github.com/repos/actions/python-versions/releases/tags/' +
                                        urllib.parse.quote(tag, safe=''), MAX_METADATA))
    matching = [item for item in release_metadata['assets'] if item['name'] == filename]
    if len(matching) != 1 or matching[0]['size'] != binary.stat().st_size:
        raise ValueError('Provider release asset metadata does not match bytes')
    expected_digest = matching[0].get('digest')
    if expected_digest and expected_digest != 'sha256:' + digest(binary):
        raise ValueError('Provider asset digest mismatch')
    # A tag must resolve to a concrete provider build-recipe commit. No main fallback.
    provider_commit = strict_json(fetch('https://api.github.com/repos/actions/python-versions/commits/' +
                                       urllib.parse.quote(tag, safe=''), MAX_METADATA))['sha']
    if not re.fullmatch('[0-9a-f]{40}', provider_commit):
        raise ValueError('Provider build recipe commit cannot be identified')
    recipe_url = f'https://github.com/actions/python-versions/archive/{provider_commit}.tar.gz'
    recipe = payload / 'provider-build-recipe.tar.gz'
    fetch(recipe_url, MAX_ARCHIVE, recipe)
    source_url = f'https://www.python.org/ftp/python/{version}/Python-{version}.tar.xz'
    source = payload / f'Python-{version}.tar.xz'
    fetch(source_url, MAX_ARCHIVE, source)
    record = {'schema': 'kuma-cpython-origin-v1', 'status': 'candidate_bytes_unreviewed',
        'python_version': version, 'manifest_commit': manifest_commit,
        'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'manifest_url': manifest_url,
        'binary_archive': {'url': url, 'path': str(binary.resolve()), 'sha256': digest(binary),
                           'size': binary.stat().st_size, 'provider_digest': expected_digest, 'members': members},
        'provider_build_recipe': {'url': recipe_url, 'commit': provider_commit, 'path': str(recipe.resolve()),
                                  'sha256': digest(recipe), 'size': recipe.stat().st_size},
        'source_archive': {'url': source_url, 'path': str(source.resolve()), 'sha256': digest(source),
                           'size': source.stat().st_size},
        'installation_match': 'must_compare_actual_file_hashes; version_and_toolcache_path_are_not_identity',
        'native_constituents': 'provider recipes retained; component source and patches still require review'}
    write_json(output, record)
    return record


def verify(record: dict) -> dict:
    if record.get('schema') != 'kuma-cpython-origin-v1':
        raise ValueError('Unexpected CPython origin schema')
    for key in ('binary_archive', 'source_archive', 'provider_build_recipe'):
        item = record[key]
        path = Path(item['path'])
        if not path.is_file() or path.is_symlink() or path.stat().st_size != item['size'] or digest(path) != item['sha256']:
            raise ValueError('CPython/provider bytes differ from acquisition record')
    if archive_inventory(Path(record['binary_archive']['path'])) != record['binary_archive']['members']:
        raise ValueError('CPython member correspondence differs from original archive')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--payload-directory', type=Path, required=True)
    parser.add_argument('--runner-platform-version')
    args = parser.parse_args()
    acquire(args.output, args.payload_directory, runner_platform_version=args.runner_platform_version)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
