"""Byte-derived source/wheel/installed-file provenance, with explicit unknowns.

Ownership and source correspondence are distinct. Wheel RECORD establishes the
former; its package name/license never clears every native object in the latter.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import sys
import sysconfig
import urllib.parse
import zipfile

from kuma_core.kuro.domain_merizo import MERIZO_COMMIT, MERIZO_WEIGHTS_SHA256
from scripts.merizo_runtime_archive.common import (
    MAX_SOURCE_BYTES, MAX_SOURCE_FILES, canonical, digest, read_regular, strict_json,
)
from scripts.merizo_runtime_archive.inputs import (canonical_name, safe_member, wheel_members,
    official_wheel_url, MAX_WHEEL_BYTES, MAX_WHEELHOUSE_BYTES)

LICENSE_SHA256 = '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
MAX_LEGAL_BYTES = 4 * 1024 * 1024
MAX_INSTALLED_FILES = 100000


def git(source: Path, *arguments: str) -> bytes:
    result = subprocess.run(['git', '-C', str(source), *arguments], check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if len(result.stdout) > 2 * 1024 * 1024:
        raise ValueError('Source git inventory exceeds bound')
    return result.stdout


def verify_source(source: Path) -> dict:
    if source.is_symlink() or git(source, 'rev-parse', 'HEAD').decode().strip() != MERIZO_COMMIT:
        raise ValueError('Require the exact official Merizo commit')
    for options in (('--others', '--exclude-standard'), ('--others', '--ignored', '--exclude-standard')):
        if git(source, 'ls-files', *options).strip():
            raise ValueError('Untracked or ignored upstream input is forbidden')
    files, total = [], 0
    for raw in git(source, 'ls-tree', '-rz', '--full-tree', 'HEAD').split(b'\0'):
        if not raw:
            continue
        fields, name_bytes = raw.split(b'\t', 1)
        mode, kind, blob = fields.decode('ascii').split(' ')
        name = safe_member(name_bytes.decode('utf-8'))
        path = source / name
        if mode not in {'100644', '100755'} or kind != 'blob' or not path.is_file() or path.is_symlink():
            raise ValueError('Unsupported tracked upstream file')
        size = path.stat().st_size
        total += size
        if len(files) >= MAX_SOURCE_FILES or total > MAX_SOURCE_BYTES:
            raise ValueError('Upstream tree exceeds declared bounds')
        sha1, sha256 = hashlib.sha1(), hashlib.sha256()
        sha1.update(f'blob {size}\0'.encode('ascii'))
        with path.open('rb') as stream:
            while block := stream.read(1024 * 1024):
                sha1.update(block)
                sha256.update(block)
        if sha1.hexdigest() != blob:
            raise ValueError('Upstream bytes differ from pinned git blob')
        files.append({'path': name, 'mode': mode, 'blob': blob, 'sha256': sha256.hexdigest(), 'size': size})
    index = {item['path']: item for item in files}
    if index.get('LICENSE', {}).get('sha256') != LICENSE_SHA256:
        raise ValueError('Pinned root GPLv3 text differs')
    for name, expected in MERIZO_WEIGHTS_SHA256.items():
        if index.get('weights/' + name, {}).get('sha256') != expected:
            raise ValueError('Pinned model bytes differ')
    return {'schema': 'kuma-merizo-source-v1', 'repository': 'https://github.com/psipred/Merizo',
            'commit': MERIZO_COMMIT, 'tree': git(source, 'rev-parse', 'HEAD^{tree}').decode().strip(),
            'files': files, 'python_files': {item['path']: item['sha256'] for item in files
                                            if item['path'].endswith('.py')},
            'weights_sha256': MERIZO_WEIGHTS_SHA256, 'root_license_sha256': LICENSE_SHA256}


def _wheel_destination(member: str) -> tuple[str, str]:
    parts = member.split('/')
    if len(parts) > 2 and parts[0].endswith('.data'):
        if parts[1] in {'purelib', 'platlib'}:
            return 'site', '/'.join(parts[2:])
        if parts[1] == 'scripts':
            return 'scripts', '/'.join(parts[2:])
        # Real installation-scheme mapping is required for this uncommon case.
        raise ValueError('Unimplemented wheel .data installation scheme')
    return 'site', member


def installed_provenance(lock_path: Path, wheelhouse: Path) -> dict:
    lock = strict_json(read_regular(lock_path, 8 * 1024 * 1024))
    if lock.get('schema') != 'kuma-merizo-input-lock-v1' or not 1 <= len(lock.get('wheels', [])) <= 128:
        raise ValueError('Invalid pre-install input lock')
    wheels = lock['wheels']
    expected = {item['name']: item['version'] for item in wheels}
    distributions = list(importlib.metadata.distributions())
    installed = {canonical_name(dist.metadata['Name']): dist for dist in distributions}
    if len(installed) != len(distributions) or len(expected) != len(wheels):
        raise ValueError('Duplicate installed distribution or lock identity')
    if set(installed) != set(expected) or any(installed[name].version != version for name, version in expected.items()):
        raise ValueError('Installed distribution closure differs from pre-install lock')
    ownership, components, legal, unresolved = {}, [], [], []
    if sum(wheel['size'] for wheel in wheels) > MAX_WHEELHOUSE_BYTES:
        raise ValueError('Wheel lock total exceeds acquisition bound')
    for wheel in wheels:
        parsed = urllib.parse.urlsplit(wheel['url'])
        filename = wheel['filename']
        if (parsed.scheme != 'https' or not official_wheel_url(parsed) or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in {None, 443}
                or '/' in filename or '\\' in filename or not filename.endswith('.whl')
                or urllib.parse.unquote(Path(parsed.path).name) != filename
                or not 0 < wheel['size'] <= MAX_WHEEL_BYTES):
            raise ValueError('Wheel lock origin/path/size is not an approved candidate')
        path = wheelhouse / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size != wheel['size'] or digest(path) != wheel['sha256']:
            raise ValueError('Original wheel bytes differ from pre-install lock')
        members = wheel_members(path)
        distribution = installed[wheel['name']]
        installed_files = list(distribution.files or ())
        if not installed_files:
            raise ValueError('Installed package has no RECORD')
        rows = {}
        for member in members:
            scheme, relative = _wheel_destination(member['member'])
            actual = (Path(sysconfig.get_path('scripts')) / relative if scheme == 'scripts'
                      else Path(str(distribution.locate_file(relative)))).resolve()
            rows[str(actual)] = member
        for entry in installed_files:
            actual = Path(str(distribution.locate_file(entry))).resolve()
            if not actual.is_relative_to(Path(sys.prefix).resolve()) or not actual.is_file():
                raise ValueError('Installed RECORD path escapes isolated environment or is missing')
            if len(ownership) >= MAX_INSTALLED_FILES:
                raise ValueError('Installed ownership inventory exceeds bound')
            checksum, size = digest(actual), actual.stat().st_size
            if entry.hash is not None:
                if entry.hash.mode != 'sha256' or entry.hash.value != base64.urlsafe_b64encode(bytes.fromhex(checksum)).decode().rstrip('='):
                    raise ValueError('Installed RECORD digest differs from actual bytes')
            if entry.size is not None and entry.size != size:
                raise ValueError('Installed RECORD size differs from actual bytes')
            original = rows.pop(str(actual), None)
            record = {'path': str(actual), 'sha256': checksum, 'size': size, 'owner': wheel['name'],
                      'wheel_sha256': wheel['sha256'], 'installed_record_path': str(entry)}
            if original:
                record['wheel_member'] = original['member']
                record['wheel_member_sha256'] = original['sha256']
                if checksum == original['sha256']:
                    record['mapping'] = 'exact_wheel_member'
                elif original['member'].endswith('.dist-info/RECORD'):
                    record['mapping'] = 'pip_rewritten_RECORD'
                else:
                    record['mapping'] = 'unexplained_installer_transform'
                    unresolved.append({'kind': 'installed_transform', 'path': str(actual), 'owner': wheel['name']})
            else:
                record['mapping'] = 'installer_generated'
                if actual.suffix == '.pyc':
                    try:
                        py = Path(importlib.util.source_from_cache(str(actual)))
                        record['compilation_source_sha256'] = digest(py)
                        record['compilation_abi'] = sys.implementation.cache_tag
                    except (ValueError, OSError):
                        unresolved.append({'kind': 'unmapped_bytecode', 'path': str(actual)})
                elif actual.name not in {'INSTALLER', 'REQUESTED', 'direct_url.json'}:
                    record['generator'] = 'pip_entry_script_or_metadata_review_required'
            if str(actual) in ownership:
                raise ValueError('Installed file has ambiguous wheel owners')
            ownership[str(actual)] = record
        if rows:
            raise ValueError('Not every original wheel member maps to installed RECORD')
        metadata = distribution.metadata
        licenses = metadata.get_all('License-Expression') or metadata.get_all('License') or []
        component = {'id': wheel['name'], 'version': distribution.version,
                     'wheel': wheel, 'declared_license': licenses[0] if licenses else None,
                     'project_urls': metadata.get_all('Project-URL') or [],
                     'source_correspondence': 'requires_review_of_exact_source_and_vendor_build_recipe'}
        components.append(component)
        with zipfile.ZipFile(path) as archive:
            for row in members:
                basename = Path(row['member']).name.upper()
                if (basename.startswith(('LICENSE', 'COPYING', 'NOTICE', 'AUTHORS'))
                        or '/licenses/' in row['member'].lower()):
                    if row['size'] > MAX_LEGAL_BYTES:
                        raise ValueError('Original legal text exceeds complete-evidence bound')
                    raw = archive.read(row['member'])
                    legal.append({'component': wheel['name'], 'member': row['member'],
                                  'sha256': row['sha256'], 'text': raw.decode('utf-8-sig')})
        if not any(item['component'] == wheel['name'] for item in legal):
            unresolved.append({'kind': 'missing_original_legal_text', 'component': wheel['name']})
    return {'lock': lock, 'components': components, 'installed_files': list(ownership.values()),
            'legal_texts': legal, 'unresolved': unresolved}


def map_build_inputs(toc: dict, provenance: dict, source: Path, source_identity: dict,
                     recipe_root: Path, cpython_origin: dict | None = None) -> dict:
    owners = {item['path']: item for item in provenance['installed_files']}
    upstream = {str((source / item['path']).resolve()): item for item in source_identity['files']}
    mappings, unresolved = [], list(provenance['unresolved'])
    recipe_root = recipe_root.resolve()
    python_members = {}
    if cpython_origin is not None:
        for member in cpython_origin['binary_archive']['members']:
            if member.get('sha256'):
                python_members.setdefault(member['sha256'], []).append(member['member'])
    for stage, rows in toc.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            raw = row.get('source')
            if not raw:
                continue
            path = Path(raw).resolve()
            mapping = {**row, 'stage': stage}
            owner = owners.get(str(path))
            if owner and owner['sha256'] == row.get('sha256'):
                mapping.update(owner=owner['owner'], wheel_member=owner.get('wheel_member'),
                               wheel_sha256=owner['wheel_sha256'], ownership='verified_installed_RECORD')
            elif str(path) in upstream and upstream[str(path)]['sha256'] == row.get('sha256'):
                mapping.update(owner='Merizo', ownership='verified_git_blob',
                               git_blob=upstream[str(path)]['blob'], commit=MERIZO_COMMIT)
            elif path.is_relative_to(recipe_root):
                mapping.update(owner='KUMA-adapter', ownership='build_recipe_file_hash')
            elif cpython_origin is not None and row.get('sha256') in python_members:
                mapping.update(owner='CPython-provider-archive', ownership='exact_provider_archive_member_bytes',
                               provider_archive_sha256=cpython_origin['binary_archive']['sha256'],
                               provider_members=python_members[row['sha256']])
            elif path.is_relative_to(Path(sys.base_prefix).resolve()):
                mapping.update(owner='CPython-installation', ownership='actual_installed_bytes_origin_unresolved')
                unresolved.append({'kind': 'cpython_installer_member_correspondence', 'path': str(path)})
            else:
                mapping.update(owner=None, ownership='unresolved')
                unresolved.append({'kind': 'unowned_build_input', 'path': str(path), 'stage': stage})
            if row.get('typecode') in {'BINARY', 'EXTENSION'}:
                mapping['native_constituents'] = 'requires_exact_vendor_source_build_and_terms_review'
                unresolved.append({'kind': 'native_constituents', 'path': str(path)})
            mappings.append(mapping)
    return {'edges': mappings, 'unresolved': unresolved,
            'cpython': {'version': platform.python_version(), 'abi': sys.implementation.cache_tag,
                        'executable_sha256': digest(Path(sys.executable)),
                        'source_release': f'https://www.python.org/ftp/python/{platform.python_version()}/',
                        'origin_evidence': cpython_origin,
                        'correspondence': 'per_input_exact_member_hash_matches_above; unmatched_inputs_remain_unresolved'}}
