"""Acquire bounded official CPython provider/source candidate bytes for CI audit.

A matching version is NOT a matching installation. The builder rehashes these
archives and maps actual installed/frozen inputs to their member bytes; anything
unmatched stays unresolved. Discovery is pinned to the python-versions manifest
commit observed by this run, not retrospectively attributed to earlier runs.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import platform
import re
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from scripts.merizo_runtime_archive.common import digest, read_regular, strict_json, write_json
from scripts.merizo_runtime_archive.inputs import safe_member

MAX_METADATA = 8 * 1024 * 1024
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_MEMBERS = 30000
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
ACQUISITION_SECONDS = 300
NETWORK_OPERATION_SECONDS = 15
NETWORK_CHUNK_BYTES = 64 * 1024
METADATA_ROOT = 'https://api.github.com/repos/actions/python-versions/'
OFFICIAL_HOSTS = {'api.github.com', 'raw.githubusercontent.com', 'github.com',
                  'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
                  'codeload.github.com', 'www.python.org'}


class _AcquisitionDeadlineExceeded(TimeoutError):
    pass


class _MetadataRedirectRejected(ValueError):
    pass


class _MetadataSizeExceeded(ValueError):
    pass


def _remaining(deadline: float | None) -> float:
    remaining = NETWORK_OPERATION_SECONDS if deadline is None else deadline - time.monotonic()
    if remaining <= 0:
        raise _AcquisitionDeadlineExceeded('CPython acquisition deadline exceeded')
    return min(NETWORK_OPERATION_SECONDS, remaining)


def _validated_token(github_token: str | None) -> str:
    if not github_token:
        raise ValueError('CPython metadata acquisition requires the CI GitHub token')
    if not isinstance(github_token, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,4096}', github_token):
        raise ValueError('Invalid CI GitHub metadata token')
    return github_token


def _validated_tag(tag: str) -> str:
    # An individual, unencoded ref name, never a path, query or traversal.
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', tag):
        raise ValueError('Invalid Python provider release tag')
    return tag


def _validate_metadata_url(url: str) -> None:
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'api.github.com'
                or parsed.hostname != 'api.github.com' or parsed.port is not None
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment
                or url != 'https://api.github.com' + parsed.path):
            raise ValueError
        if not url.startswith(METADATA_ROOT):
            raise ValueError
        relative = url[len(METADATA_ROOT):]
        if relative == 'commits/main':
            return
        for prefix in ('releases/tags/', 'commits/'):
            if relative.startswith(prefix):
                _validated_tag(relative[len(prefix):])
                return
    except (TypeError, ValueError, UnicodeError):
        pass
    raise ValueError('Unapproved CPython metadata endpoint')


class _NoMetadataRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Raising here happens before urllib constructs or follows the target.
        # Do not include the URL, headers or request in the exception.
        raise _MetadataRedirectRejected('CPython metadata redirects are forbidden')


def fetch_metadata(url: str, *, github_token: str | None, deadline: float | None = None) -> bytes:
    """Authenticate only these fixed public GitHub metadata GET endpoints.

    Never use this helper for raw files, release binaries or Python.org. The
    explicit token remains in this process; no environment lookup or subprocess.
    Every error leaving the request boundary is static, with at most an integer
    HTTP status, because transport exceptions can echo Authorization headers.
    """
    _validate_metadata_url(url)  # Must precede even constructing Authorization.
    token = _validated_token(github_token)
    try:
        request = urllib.request.Request(url, method='GET', headers={
            'User-Agent': 'KUMA-internal-CPython-audit/1',
            'Accept': 'application/vnd.github+json',
        })
        # Defense in depth: urllib must not propagate this header on a redirect,
        # even though our redirect handler rejects before following any target.
        request.add_unredirected_header('Authorization', 'Bearer ' + token)
        opener = urllib.request.build_opener(_NoMetadataRedirects())
        with opener.open(request, timeout=_remaining(deadline)) as response:
            if response.url != url:
                raise _MetadataRedirectRejected
            chunks, size = [], 0
            while True:
                _remaining(deadline)
                # read1 performs at most one underlying read, so a slow trickle
                # cannot keep a read(limit) loop running past every budget check.
                block = response.read1(NETWORK_CHUNK_BYTES)
                _remaining(deadline)
                if not block:
                    break
                size += len(block)
                if size > MAX_METADATA:
                    raise _MetadataSizeExceeded
                chunks.append(block)
        return b''.join(chunks)
    except urllib.error.HTTPError as exc:
        status = exc.code
        detail = f' (HTTP {status})' if type(status) is int and 100 <= status <= 599 else ''
        raise ValueError('CPython metadata request failed' + detail) from None
    except _MetadataRedirectRejected:
        raise ValueError('CPython metadata redirects are forbidden') from None
    except _MetadataSizeExceeded:
        raise ValueError('CPython metadata exceeds predeclared byte bound') from None
    except _AcquisitionDeadlineExceeded:
        raise _AcquisitionDeadlineExceeded('CPython acquisition deadline exceeded') from None
    except Exception:
        raise ValueError('CPython metadata request failed') from None


def fetch(url: str, limit: int, destination: Path | None = None, *, deadline: float | None = None):
    """Fetch public artifact bytes without any authentication capability."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in OFFICIAL_HOSTS or parsed.username or parsed.password:
        raise ValueError('Unapproved CPython/provider origin')
    request = urllib.request.Request(url, headers={'User-Agent': 'KUMA-internal-CPython-audit/1',
                                                   'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=_remaining(deadline)) as response:
        final = urllib.parse.urlsplit(response.url)
        if final.scheme != 'https' or final.hostname not in OFFICIAL_HOSTS:
            raise ValueError('Unapproved CPython artifact redirect')
        size, chunks = 0, []
        outgoing = None if destination is None else destination.open('xb')
        try:
            while True:
                _remaining(deadline)
                block = response.read1(NETWORK_CHUNK_BYTES)
                _remaining(deadline)
                if not block:
                    break
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


def archive_inventory(path: Path, *, deadline: float | None = None) -> list[dict]:
    _remaining(deadline)
    entries, seen, total = [], set(), 0
    def add(name, size, stream=None, alias=None):
        nonlocal total
        _remaining(deadline)
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
                    _remaining(deadline)
                    checksum.update(block)
            row['sha256'] = checksum.hexdigest()
        else:
            row['alias'] = alias
        entries.append(row)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                _remaining(deadline)
                if member.is_dir():
                    continue
                if member.flag_bits & 1 or (member.external_attr >> 16) & 0o170000 not in {0, 0o100000}:
                    raise ValueError('Unsupported Python ZIP member')
                add(member.filename, member.file_size, archive.open(member))
    else:
        with tarfile.open(path, 'r|*') as archive:
            for member in archive:
                _remaining(deadline)
                if member.isdir():
                    continue
                if member.isfile():
                    add(member.name, member.size, archive.extractfile(member))
                elif member.issym() or member.islnk():
                    add(member.name, 0, alias=member.linkname)
                else:
                    raise ValueError('Unsupported Python tar member')
    _remaining(deadline)
    return entries


def acquire(output: Path, payload: Path, *, runner_platform_version: str | None = None,
            github_token: str | None = None):
    # Cooperative total budget plus short per-operation network timeouts. The CI
    # step's ten-minute timeout remains the hard cross-platform wall-clock bound
    # for DNS/header setup and local filesystem operations; no child watchdog is
    # claimed for this deliberately in-process authenticated acquisition.
    deadline = time.monotonic() + ACQUISITION_SECONDS
    _validated_token(github_token)
    if payload.exists():
        raise ValueError('Use a fresh CPython-origin payload directory')
    payload.mkdir(parents=True, exist_ok=False)
    commit_info = strict_json(fetch_metadata(METADATA_ROOT + 'commits/main',
                                             github_token=github_token, deadline=deadline))
    manifest_commit = commit_info['sha']
    if not re.fullmatch('[0-9a-f]{40}', manifest_commit):
        raise ValueError('Unpinned official provider manifest')
    manifest_url = f'https://raw.githubusercontent.com/actions/python-versions/{manifest_commit}/versions-manifest.json'
    manifest_bytes = fetch(manifest_url, MAX_METADATA, deadline=deadline)
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
    tag, filename = _validated_tag(parts[5]), urllib.parse.unquote(parts[6])
    safe_member(filename)
    binary = payload / filename
    fetch(url, MAX_ARCHIVE, binary, deadline=deadline)
    members = archive_inventory(binary, deadline=deadline)
    release_metadata = strict_json(fetch_metadata(METADATA_ROOT + 'releases/tags/' + tag,
                                                  github_token=github_token, deadline=deadline))
    matching = [item for item in release_metadata['assets'] if item['name'] == filename]
    if len(matching) != 1 or matching[0]['size'] != binary.stat().st_size:
        raise ValueError('Provider release asset metadata does not match bytes')
    expected_digest = matching[0].get('digest')
    if expected_digest and expected_digest != 'sha256:' + digest(binary):
        raise ValueError('Provider asset digest mismatch')
    # A tag must resolve to a concrete provider build-recipe commit. No main fallback.
    provider_commit = strict_json(fetch_metadata(METADATA_ROOT + 'commits/' + tag,
                                                 github_token=github_token, deadline=deadline))['sha']
    if not re.fullmatch('[0-9a-f]{40}', provider_commit):
        raise ValueError('Provider build recipe commit cannot be identified')
    recipe_url = f'https://github.com/actions/python-versions/archive/{provider_commit}.tar.gz'
    recipe = payload / 'provider-build-recipe.tar.gz'
    fetch(recipe_url, MAX_ARCHIVE, recipe, deadline=deadline)
    source_url = f'https://www.python.org/ftp/python/{version}/Python-{version}.tar.xz'
    source = payload / f'Python-{version}.tar.xz'
    fetch(source_url, MAX_ARCHIVE, source, deadline=deadline)
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
    _remaining(deadline)
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
