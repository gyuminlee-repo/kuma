"""Exact Darwin framework-copy role proof within a verified managed installation.

The local receipt is not an independent trust root. The manager verifies its
canonical trusted-catalog bytes under the held lease before launch; export and
replay require that external artifact again, rather than trusting these claims.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat

from scripts.merizo_runtime_archive.common import canonical, strict_json, write_json

DECLARATION_NAME = 'PYTHON_ORIGIN.json'
FLAT = '_internal/Python'
FRAMEWORK = '_internal/Python.framework/Versions/3.11/Python'
ALIAS = FLAT + ' -> ' + FRAMEWORK
DECLARATION_SCHEMA = 'kuma-darwin-python-copy-declaration-v1'
PROOF_SCHEMA = 'kuma-darwin-python-copy-proof-v1'
MAX_DECLARATION_BYTES = 4096
MAX_RECEIPT_BYTES = 1024 * 1024
MAX_PYTHON_BYTES = 64 * 1024 * 1024
_HASH = re.compile('[0-9a-f]{64}\\Z')
_RESERVED = re.compile(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?\Z', re.I)


def _read(path: Path, limit: int) -> bytes:
    # Reuse the existing bounded stable single-link reader; import lazily to
    # keep this shared build/runtime helper free of an initialization cycle.
    from scripts.merizo_runtime_archive.runtime_origin import read_stable
    return read_stable(path, limit)


def _plain(path: Path, root: Path) -> None:
    if not path.is_relative_to(root) or path.resolve(strict=True) != path:
        raise ValueError('Python-copy path is not exact and canonical')
    for parent in (path.parent, *path.parent.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Python-copy parent is not plain')
        if parent == root:
            break


def declaration(value):
    if (not isinstance(value, dict) or set(value) != {'schema', 'flat_path', 'framework_path', 'original_alias', 'sha256', 'size'}
            or value['schema'] != DECLARATION_SCHEMA or value['flat_path'] != FLAT
            or value['framework_path'] != FRAMEWORK or value['original_alias'] != ALIAS
            or not isinstance(value['sha256'], str) or not _HASH.fullmatch(value['sha256'])
            or type(value['size']) is not int or not 1 <= value['size'] <= MAX_PYTHON_BYTES):
        raise ValueError('Invalid exact Python-copy declaration')
    return value


def create_declaration(package: Path) -> dict:
    """Build only: require the original exact PyInstaller symlink first."""
    root = package.resolve(strict=True)
    flat, framework = root / FLAT, root / FRAMEWORK
    if not stat.S_ISLNK(flat.lstat().st_mode) or os.readlink(flat) != 'Python.framework/Versions/3.11/Python':
        raise ValueError('Expected exact original Python framework symlink')
    _plain(framework, root)
    if flat.resolve(strict=True) != framework:
        raise ValueError('Original Python symlink resolves elsewhere')
    raw = _read(framework, MAX_PYTHON_BYTES)
    value = declaration({'schema': DECLARATION_SCHEMA, 'flat_path': FLAT, 'framework_path': FRAMEWORK,
                         'original_alias': ALIAS, 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)})
    output = root / DECLARATION_NAME
    if output.exists() or output.is_symlink():
        raise ValueError('Python-copy declaration destination is stale')
    write_json(output, value, MAX_DECLARATION_BYTES)
    return value


def _member_name(value):
    # Same cross-platform member spelling constraints as the registry. Spaces
    # inside a name are legitimate (the pinned setuptools wheel includes one).
    return (isinstance(value, str) and 1 <= len(value) <= 240 and value.isascii()
            and not any(c in value for c in '\\:<>"|?*')
            and not any(ord(c) < 32 or ord(c) == 127 for c in value)
            and len(value.split('/')) <= 16
            and all(part not in {'', '.', '..'} and not part.endswith(('.', ' '))
                    and not _RESERVED.fullmatch(part) for part in value.split('/')))


def artifact_rows(artifact):
    keys = {'engine', 'version', 'platform', 'archive_sha256', 'archive_size', 'files', 'executable_path'}
    if (not isinstance(artifact, dict) or set(artifact) != keys or artifact['engine'] != 'merizo'
            or artifact['platform'] != 'macos-arm64' or artifact['executable_path'] != 'kuma-merizo'
            or not isinstance(artifact['version'], str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', artifact['version'])
            or not isinstance(artifact['archive_sha256'], str) or not _HASH.fullmatch(artifact['archive_sha256'])
            or type(artifact['archive_size']) is not int or not 1 <= artifact['archive_size'] <= 1024**3
            or not isinstance(artifact['files'], list) or not 1 <= len(artifact['files']) <= 2048):
        raise ValueError('Invalid managed Python-copy artifact')
    rows, folded, total = {}, set(), 0
    for row in artifact['files']:
        if (not isinstance(row, dict) or set(row) != {'path', 'sha256', 'size', 'executable'}
                or not _member_name(row['path'])
                or row['path'].casefold() in folded or row['path'] == '.kuma-runtime.json'
                or not isinstance(row['sha256'], str) or not _HASH.fullmatch(row['sha256'])
                or type(row['size']) is not int or not 0 <= row['size'] <= 1024**3
                or type(row['executable']) is not bool):
            raise ValueError('Invalid managed Python-copy file row')
        rows[row['path']] = row
        folded.add(row['path'].casefold())
        total += row['size']
    if total > 2 * 1024**3:
        raise ValueError('Managed Python-copy artifact exceeds installed limit')
    return rows


def receipt_bytes(artifact) -> bytes:
    artifact_rows(artifact)
    raw = canonical({'schema': 'kuma-optional-runtime-v1', **artifact}) + b'\n'
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ValueError('Managed Python-copy receipt exceeds bound')
    return raw


def _matching_rows(value, artifact, executable_sha256):
    value = declaration(value)
    rows = artifact_rows(artifact)
    for name in (FLAT, FRAMEWORK):
        if rows.get(name) != {'path': name, 'sha256': value['sha256'], 'size': value['size'], 'executable': True}:
            raise ValueError('Python-copy bytes do not match the external artifact')
    raw = canonical(value) + b'\n'
    if rows.get(DECLARATION_NAME) != {'path': DECLARATION_NAME, 'sha256': hashlib.sha256(raw).hexdigest(),
                                     'size': len(raw), 'executable': False}:
        raise ValueError('Python-copy declaration is not an artifact member')
    executable = rows.get('kuma-merizo')
    if executable is None or not executable['executable'] or executable['size'] <= 0 or executable['sha256'] != executable_sha256:
        raise ValueError('Python-copy executable differs from the artifact')
    return rows


def check_normalized(value, records, artifact) -> dict:
    """Build only: match original alias records to final normalized file rows."""
    values = {row['path']: row for row in records}
    if len(values) != len(records):
        raise ValueError('Duplicate normalized Python-copy inventory')
    executable = next(row for row in artifact['files'] if row['path'] == 'kuma-merizo')
    expected = _matching_rows(value, artifact, executable['sha256'])
    declared_row = values.get(DECLARATION_NAME, {})
    if (any(declared_row.get(key) != item for key, item in expected[DECLARATION_NAME].items())
            or declared_row.get('original_path') != DECLARATION_NAME or declared_row.get('aliases') != []):
        raise ValueError('Normalized declaration differs from its artifact row')
    for name in (FLAT, FRAMEWORK):
        row = values.get(name, {})
        if (row.get('original_path') != FRAMEWORK or row.get('sha256') != value['sha256']
                or row.get('size') != value['size'] or row.get('executable') is not True
                or row.get('aliases') != ([ALIAS] if name == FLAT else [])):
            raise ValueError('Normalized Python-copy relation differs')
    return {'declaration_sha256': hashlib.sha256(canonical(value) + b'\n').hexdigest(),
            'copy_sha256': value['sha256'], 'copy_bytes': value['size'], 'original_alias': ALIAS,
            'archive_sha256': artifact['archive_sha256'], 'executable_sha256': executable['sha256']}


def live_proof(root: Path, internal: Path, executable_sha256: str, native, images):
    """Called only after all ordinary native policies pass except Python role."""
    if internal != root / '_internal' or str(root / FLAT) not in native['bundled']:
        raise ValueError('Exact loaded Python-copy path is absent')
    indices = [i for i, row in enumerate(images) if row.image_index == i and row.path == str(root / FLAT) and Path(row.path).resolve() == root / FLAT]
    if len(indices) != 1:
        raise ValueError('Python-copy proof requires the original exact loaded dyld row')
    receipt = _read(root / '.kuma-runtime.json', MAX_RECEIPT_BYTES)
    parsed = strict_json(receipt)
    if not isinstance(parsed, dict) or parsed.get('schema') != 'kuma-optional-runtime-v1':
        raise ValueError('Missing managed runtime receipt')
    artifact = {key: value for key, value in parsed.items() if key != 'schema'}
    if receipt != receipt_bytes(artifact):
        raise ValueError('Runtime receipt is not the exact canonical artifact')
    declaration_path = root / DECLARATION_NAME
    _plain(declaration_path, root)
    raw = _read(declaration_path, MAX_DECLARATION_BYTES)
    value = declaration(strict_json(raw))
    if raw != canonical(value) + b'\n':
        raise ValueError('Python-copy declaration is not canonical')
    _matching_rows(value, artifact, executable_sha256)
    for name in (FLAT, FRAMEWORK):
        path = root / name
        _plain(path, root)
        payload = _read(path, MAX_PYTHON_BYTES)
        if len(payload) != value['size'] or hashlib.sha256(payload).hexdigest() != value['sha256']:
            raise ValueError('Loaded Python copy or counterpart differs from verified artifact')
    return {'schema': PROOF_SCHEMA, 'declaration': value,
            'declaration_sha256': hashlib.sha256(raw).hexdigest(),
            'receipt_sha256': hashlib.sha256(receipt).hexdigest(), 'archive_sha256': artifact['archive_sha256'],
            'executable_sha256': executable_sha256, 'loaded_path': FLAT, 'loaded_image_index': indices[0]}, artifact


def validate_proof(proof, *, artifact, executable_sha256, native, images):
    keys = {'schema', 'declaration', 'declaration_sha256', 'receipt_sha256', 'archive_sha256',
            'executable_sha256', 'loaded_path', 'loaded_image_index'}
    if not isinstance(proof, dict) or set(proof) != keys or proof['schema'] != PROOF_SCHEMA:
        raise ValueError('Invalid Python-copy role proof')
    _matching_rows(proof['declaration'], artifact, executable_sha256)
    index = proof['loaded_image_index']
    if (proof['declaration_sha256'] != hashlib.sha256(canonical(proof['declaration']) + b'\n').hexdigest()
            or proof['receipt_sha256'] != hashlib.sha256(receipt_bytes(artifact)).hexdigest()
            or proof['archive_sha256'] != artifact['archive_sha256'] or proof['executable_sha256'] != executable_sha256
            or proof['loaded_path'] != FLAT or type(index) is not int or not 0 <= index < len(images)
            or images[index]['path'] != FLAT or images[index]['resolved_path'] != FLAT
            or images[index]['kind'] != 'bundled' or images[index]['image_index'] != index
            or FLAT not in native['bundled'] or native['required'].get('python') != FLAT):
        raise ValueError('Python-copy role proof is not bound to the artifact and loaded image')
