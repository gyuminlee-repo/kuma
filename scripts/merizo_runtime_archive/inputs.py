"""Freeze candidate official wheel bytes before an offline, hashed CI install.

A fresh pip --dry-run --ignore-installed --only-binary=:all: --report report.json
resolves candidates. This module downloads only those exact official artifacts,
checks report SHA-256 and wheel RECORD, and writes a lock. These are unreviewed
candidate pins, never provenance attributed to an earlier run or a release lock.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
from pathlib import Path, PurePosixPath
import re
import urllib.parse
import urllib.request
import zipfile

from scripts.merizo_runtime_archive.common import digest, read_regular, strict_json, write_json

MAX_WHEELS = 128
MAX_WHEEL_BYTES = 1024 * 1024 * 1024
MAX_WHEELHOUSE_BYTES = 2 * 1024 * 1024 * 1024
MAX_WHEEL_MEMBERS = 100000
MAX_RECORD_BYTES = 16 * 1024 * 1024
OFFICIAL_HOSTS = {'files.pythonhosted.org', 'download.pytorch.org'}
# Exact links on https://download.pytorch.org/whl/cpu/torch/ (2026-10-10).
# Do not broadly admit all artifacts on a newly observed CDN host.
R2_CPU_PATHS = {'/whl/cpu/torch-2.0.1+cpu-cp311-cp311-linux_x86_64.whl',
                '/whl/cpu/torch-2.0.1+cpu-cp311-cp311-win_amd64.whl'}


def official_wheel_url(parsed) -> bool:
    return (parsed.hostname in OFFICIAL_HOSTS or
            (parsed.hostname == 'download-r2.pytorch.org' and
             urllib.parse.unquote(parsed.path) in R2_CPU_PATHS))


def canonical_name(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def safe_member(name: str) -> str:
    if (not name or '\\' in name or ':' in name or name.startswith('/') or '\x00' in name
            or any(part in {'', '.', '..'} for part in name.split('/'))):
        raise ValueError('Unsafe wheel member')
    return name


def wheel_members(path: Path) -> list[dict]:
    """Hash every wheel member and independently verify all RECORD assertions."""
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if not 1 <= len(infos) <= MAX_WHEEL_MEMBERS:
            raise ValueError('Wheel member count exceeds bound')
        names = [safe_member(info.filename) for info in infos]
        if len(set(names)) != len(names) or sum(info.file_size for info in infos) > 4 * MAX_WHEEL_BYTES:
            raise ValueError('Duplicate or oversized wheel contents')
        records = [name for name in names if name.endswith('.dist-info/RECORD')]
        if len(records) != 1:
            raise ValueError('Expected one wheel RECORD')
        if archive.getinfo(records[0]).file_size > MAX_RECORD_BYTES:
            raise ValueError('Wheel RECORD exceeds explicit metadata byte bound')
        rows = list(csv.reader(io.StringIO(archive.read(records[0]).decode('utf-8'))))
        declarations = {}
        for row in rows:
            if len(row) != 3 or row[0] in declarations:
                raise ValueError('Invalid wheel RECORD rows')
            declarations[safe_member(row[0])] = row[1:]
        if set(declarations) != set(names):
            raise ValueError('Wheel RECORD does not inventory every file')
        output = []
        for info in infos:
            # Wheel-only links are refused, not attributed by pathname guesses.
            mode = info.external_attr >> 16
            if mode & 0o170000 not in {0, 0o100000} or info.flag_bits & 1:
                raise ValueError('Wheel contains links/special/encrypted members')
            checksum = hashlib.sha256()
            with archive.open(info) as stream:
                while block := stream.read(1024 * 1024):
                    checksum.update(block)
            encoded, size = declarations[info.filename]
            if info.filename == records[0]:
                if encoded or size:
                    raise ValueError('RECORD must not recursively hash itself')
            else:
                expected = 'sha256=' + base64.urlsafe_b64encode(checksum.digest()).decode().rstrip('=')
                if encoded != expected or size != str(info.file_size):
                    raise ValueError('Wheel RECORD hash/size mismatch')
            output.append({'member': info.filename, 'sha256': checksum.hexdigest(), 'size': info.file_size})
        return output


def freeze(reports: list[Path], wheelhouse: Path, output: Path, requirements: Path) -> dict:
    if wheelhouse.exists():
        raise ValueError('Use a fresh candidate wheelhouse')
    candidates = {}
    for report in reports:
        data = strict_json(read_regular(report, 8 * 1024 * 1024))
        if data.get('version') != '1' or not isinstance(data.get('install'), list):
            raise ValueError('Require a pip v1 installation report')
        for item in data['install']:
            metadata = item['metadata']
            name = canonical_name(metadata['name'])
            version = metadata['version']
            download = item['download_info']
            url = download['url']
            parsed = urllib.parse.urlsplit(url)
            filename = urllib.parse.unquote(PurePosixPath(parsed.path).name)
            checksum = download['archive_info']['hashes']['sha256']
            if (parsed.scheme != 'https' or not official_wheel_url(parsed) or parsed.username
                    or parsed.password or parsed.port not in {None, 443} or parsed.query or parsed.fragment
                    or not filename.endswith('.whl') or '/' in filename or '\\' in filename
                    or not re.fullmatch('[0-9a-f]{64}', checksum)
                    or not re.fullmatch('[a-z0-9-]+', name) or not re.fullmatch('[A-Za-z0-9.+!_-]+', version)):
                raise ValueError('Candidate is not an exact allowed official wheel')
            record = {'name': name, 'version': version, 'filename': filename, 'url': url,
                      'sha256': checksum, 'requested': bool(item.get('requested')),
                      'source_correspondence': 'unreviewed_wheel_metadata_and_vendor_notices'}
            if name in candidates and candidates[name] != record:
                raise ValueError('Conflicting candidate reports')
            candidates[name] = record
    if not 1 <= len(candidates) <= MAX_WHEELS:
        raise ValueError('Candidate wheel count exceeds bound')
    filenames = [record['filename'] for record in candidates.values()]
    if len(set(filenames)) != len(filenames):
        raise ValueError('Duplicate wheel filenames')
    wheelhouse.mkdir(parents=True, exist_ok=False)
    total = 0
    for record in candidates.values():
        destination = wheelhouse / record['filename']
        request = urllib.request.Request(record['url'], headers={'User-Agent': 'KUMA-internal-runtime-audit/1'})
        with urllib.request.urlopen(request, timeout=120) as response, destination.open('xb') as stream:
            final = urllib.parse.urlsplit(response.url)
            if final.scheme != 'https' or not official_wheel_url(final):
                raise ValueError('Official wheel redirected to an unapproved origin')
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                total += len(block)
                if size > MAX_WHEEL_BYTES or total > MAX_WHEELHOUSE_BYTES:
                    raise ValueError('Wheel download exceeds declared bounds')
                stream.write(block)
        if digest(destination) != record['sha256']:
            raise ValueError('Downloaded wheel differs from resolution SHA-256')
        record['size'] = size
        record['wheel_tags'] = record['filename'][:-4].rsplit('-', 3)[-3:]
        record['member_count'] = len(wheel_members(destination))
    lock = {'schema': 'kuma-merizo-input-lock-v1', 'status': 'candidate_inputs_unreviewed',
            'report_sha256': [digest(report) for report in reports],
            'wheels': sorted(candidates.values(), key=lambda item: item['name'])}
    write_json(output, lock)
    requirements.write_text(''.join(f"{item['name']}=={item['version']} --hash=sha256:{item['sha256']}\n"
        for item in lock['wheels']), encoding='ascii')
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', action='append', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--requirements-lock', type=Path, required=True)
    args = parser.parse_args()
    freeze(args.report, args.wheelhouse, args.output, args.requirements_lock)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
