"""Synthetic contracts for the exact managed Darwin Python-copy exception.

These tests never enumerate native images or load a model. They establish the
copy/declaration/receipt bindings, not actual macOS runtime evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.merizo_runtime_archive import python_framework_copy as python_copy
from scripts.merizo_runtime_archive import runtime_origin as origin
from scripts.merizo_runtime_archive.common import canonical
from scripts.merizo_windows_smoke import runtime_origins as shared


@pytest.fixture(autouse=True)
def no_native_enumeration(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Synthetic Python-copy tests must not enumerate native images')
    for name in ('darwin_native_images', 'linux_native_paths', 'windows_loaded_native_paths'):
        monkeypatch.setattr(shared, name, forbidden)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def image(path, index=0):
    return shared.DarwinImage(index, str(path), 4096 + 8 * index,
        shared.MH_MAGIC_64, shared.CPU_TYPE_ARM64, 2, shared.MH_DYLIB, 0, False)


def original_package(tmp_path):
    root = (tmp_path / 'installed').resolve()
    framework = root / python_copy.FRAMEWORK
    framework.parent.mkdir(parents=True)
    framework.write_bytes(b'synthetic Python framework bytes\n')
    framework.chmod(0o755)
    (root / python_copy.FLAT).symlink_to('Python.framework/Versions/3.11/Python')
    return root


@pytest.fixture
def installed(tmp_path):
    root = original_package(tmp_path)
    declaration = python_copy.create_declaration(root)
    flat = root / python_copy.FLAT
    flat.unlink()
    flat.write_bytes((root / python_copy.FRAMEWORK).read_bytes())
    flat.chmod(0o755)
    executable = root / 'kuma-merizo'
    executable.write_bytes(b'synthetic executable\n')
    executable.chmod(0o755)
    rows = [{'path': name, 'sha256': sha((root / name).read_bytes()),
             'size': (root / name).stat().st_size, 'executable': name != python_copy.DECLARATION_NAME}
            for name in (python_copy.FLAT, python_copy.FRAMEWORK,
                         python_copy.DECLARATION_NAME, 'kuma-merizo')]
    artifact = {'engine': 'merizo', 'version': 'synthetic-python-copy-v1',
        'platform': 'macos-arm64', 'archive_sha256': 'a' * 64,
        'archive_size': 1000, 'files': rows, 'executable_path': 'kuma-merizo'}
    (root / '.kuma-runtime.json').write_bytes(python_copy.receipt_bytes(artifact))
    records = [{**row, 'original_path': python_copy.FRAMEWORK if row['path'] == python_copy.FLAT else row['path'],
                'aliases': [python_copy.ALIAS] if row['path'] == python_copy.FLAT else []}
               for row in rows]
    return SimpleNamespace(root=root, internal=root / '_internal', declaration=declaration,
        artifact=artifact, records=records, executable_sha256=sha(executable.read_bytes()),
        native={'bundled': [str(flat)]}, images=(image(flat),))


def live(value):
    return python_copy.live_proof(value.root, value.internal, value.executable_sha256,
                                  value.native, value.images)


def replay_inputs(value):
    return {'artifact': value.artifact, 'executable_sha256': value.executable_sha256,
            'native': {'bundled': [python_copy.FLAT], 'required': {'python': python_copy.FLAT}},
            'images': [{'image_index': 0, 'kind': 'bundled', 'path': python_copy.FLAT,
                        'resolved_path': python_copy.FLAT}]}


def rewrite_declaration(value, change):
    declaration = {**value.declaration, **change}
    (value.root / python_copy.DECLARATION_NAME).write_bytes(canonical(declaration) + b'\n')
    return declaration


def test_original_symlink_is_declared_before_normalization(tmp_path):
    root = original_package(tmp_path)
    value = python_copy.create_declaration(root)
    assert value == {'schema': python_copy.DECLARATION_SCHEMA, 'flat_path': python_copy.FLAT,
                     'framework_path': python_copy.FRAMEWORK, 'original_alias': python_copy.ALIAS,
                     'sha256': sha((root / python_copy.FRAMEWORK).read_bytes()),
                     'size': (root / python_copy.FRAMEWORK).stat().st_size}
    assert (root / python_copy.FLAT).is_symlink()
    assert (root / python_copy.DECLARATION_NAME).read_bytes() == canonical(value) + b'\n'


def test_exact_normalized_pair_has_bound_build_live_and_offline_proofs(installed, monkeypatch):
    value = installed
    normalized = python_copy.check_normalized(value.declaration, value.records, value.artifact)
    proof, artifact = live(value)
    assert artifact == value.artifact
    assert normalized == {'declaration_sha256': sha(canonical(value.declaration) + b'\n'),
        'copy_sha256': value.declaration['sha256'], 'copy_bytes': value.declaration['size'],
        'original_alias': python_copy.ALIAS, 'archive_sha256': value.artifact['archive_sha256'],
        'executable_sha256': value.executable_sha256}
    assert proof == {'schema': python_copy.PROOF_SCHEMA, 'declaration': value.declaration,
        'declaration_sha256': normalized['declaration_sha256'],
        'receipt_sha256': sha(python_copy.receipt_bytes(value.artifact)),
        'archive_sha256': value.artifact['archive_sha256'],
        'executable_sha256': value.executable_sha256, 'loaded_path': python_copy.FLAT,
        'loaded_image_index': 0}
    assert not (value.root / python_copy.FLAT).is_symlink()
    assert (value.root / python_copy.FLAT).stat().st_ino != (value.root / python_copy.FRAMEWORK).stat().st_ino
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline proof replay must not inspect or enumerate host native images')
    monkeypatch.setattr(Path, 'resolve', forbidden)
    monkeypatch.setattr(shared, 'darwin_native_images', forbidden)
    python_copy.validate_proof(proof, **replay_inputs(value))


def test_shared_policy_still_raises_typed_missing_python_without_role_exception(installed):
    value = installed
    paths = [value.root / python_copy.FLAT, value.internal / 'libtorch_cpu.dylib',
             value.internal / 'libc10.dylib']
    for path in paths[1:]:
        path.write_bytes(b'synthetic native library')
    images = tuple(image(path, index) for index, path in enumerate(paths))
    with pytest.raises(shared.MissingNativeRolesError) as caught:
        shared.validate_posix_native_paths([str(path) for path in paths], value.internal,
                                           'Darwin', darwin_images=images)
    assert isinstance(caught.value, ValueError)
    assert caught.value.missing == frozenset({'python'})
    assert caught.value.validated == {'bundled': sorted(str(path) for path in paths),
        'posix_system': [], 'required_bundled': {'torch_cpu': str(paths[1]), 'c10': str(paths[2])}}
    assert shared.runtime_role(value.root / python_copy.FLAT, 'Darwin') is None
    assert shared.runtime_role(value.root / python_copy.FRAMEWORK, 'Darwin') == 'python'


@pytest.mark.parametrize('variant', ['regular', 'absolute', 'equivalent-relative', 'other-version', 'external'])
def test_declaration_requires_original_exact_symlink(tmp_path, variant):
    root = original_package(tmp_path)
    flat = root / python_copy.FLAT
    flat.unlink()
    if variant == 'regular':
        flat.write_bytes((root / python_copy.FRAMEWORK).read_bytes())
    else:
        targets = {'absolute': str(root / python_copy.FRAMEWORK),
            'equivalent-relative': './Python.framework/Versions/3.11/Python',
            'other-version': 'Python.framework/Versions/3.12/Python',
            'external': str(tmp_path / 'external' / 'Python')}
        flat.symlink_to(targets[variant])
    with pytest.raises(ValueError, match='exact original'):
        python_copy.create_declaration(root)
    assert not (root / python_copy.DECLARATION_NAME).exists()


@pytest.mark.parametrize('variant', ['file', 'directory', 'dangling-symlink'])
def test_declaration_destination_must_be_fresh(tmp_path, variant):
    root = original_package(tmp_path)
    destination = root / python_copy.DECLARATION_NAME
    if variant == 'file':
        destination.write_bytes(b'stale declaration')
    elif variant == 'directory':
        destination.mkdir()
    else:
        destination.symlink_to('missing-declaration')
    with pytest.raises(ValueError, match='stale'):
        python_copy.create_declaration(root)
    if variant == 'file':
        assert destination.read_bytes() == b'stale declaration'
    elif variant == 'directory':
        assert destination.is_dir()
    else:
        assert destination.is_symlink()


@pytest.mark.parametrize('variant', ['symlink', 'hardlink', 'empty', 'oversized'])
def test_original_framework_must_be_bounded_plain_single_link_file(tmp_path, monkeypatch, variant):
    root = original_package(tmp_path)
    framework = root / python_copy.FRAMEWORK
    if variant in {'symlink', 'hardlink'}:
        other = root / 'other-Python'
        other.write_bytes(framework.read_bytes())
        framework.unlink()
        if variant == 'symlink':
            framework.symlink_to(other)
        else:
            framework.hardlink_to(other)
    elif variant == 'empty':
        framework.write_bytes(b'')
    else:
        monkeypatch.setattr(python_copy, 'MAX_PYTHON_BYTES', framework.stat().st_size - 1)
    with pytest.raises(ValueError):
        python_copy.create_declaration(root)
    assert not (root / python_copy.DECLARATION_NAME).exists()


@pytest.mark.parametrize('field,replacement', [
    ('schema', 'unknown'), ('flat_path', '_internal/Other/Python'),
    ('framework_path', '_internal/Python.framework/Versions/3.12/Python'),
    ('original_alias', '_internal/Python -> external/Python'), ('sha256', 'A' * 64),
    ('sha256', 'a' * 63), ('sha256', 3), ('size', True), ('size', 0),
    ('size', python_copy.MAX_PYTHON_BYTES + 1), ('size', '32')])
def test_declaration_schema_is_exact(installed, field, replacement):
    with pytest.raises(ValueError):
        python_copy.declaration({**installed.declaration, field: replacement})


@pytest.mark.parametrize('variant', ['extra', 'missing', 'list'])
def test_declaration_rejects_changed_shape(installed, variant):
    value = copy.deepcopy(installed.declaration)
    if variant == 'extra':
        value['untrusted'] = True
    elif variant == 'missing':
        value.pop('original_alias')
    else:
        value = [value]
    with pytest.raises(ValueError):
        python_copy.declaration(value)


@pytest.mark.parametrize('name', [python_copy.FLAT, python_copy.FRAMEWORK])
@pytest.mark.parametrize('field,replacement', [
    ('original_path', '_internal/Elsewhere/Python'), ('sha256', 'b' * 64),
    ('size', 1), ('executable', False), ('aliases', ['unrelated alias']),
    ('path', '_internal/Other/Python')])
def test_normalized_records_preserve_exact_original_relation(installed, name, field, replacement):
    records = copy.deepcopy(installed.records)
    next(row for row in records if row['path'] == name)[field] = replacement
    with pytest.raises(ValueError):
        python_copy.check_normalized(installed.declaration, records, installed.artifact)


@pytest.mark.parametrize('variant', ['duplicate', 'missing-flat', 'missing-framework', 'no-flat-alias'])
def test_normalized_inventory_rejects_missing_or_duplicate_pair(installed, variant):
    records = copy.deepcopy(installed.records)
    if variant == 'duplicate':
        records.append(copy.deepcopy(records[0]))
    elif variant == 'no-flat-alias':
        records[0]['aliases'] = []
    else:
        name = python_copy.FLAT if variant == 'missing-flat' else python_copy.FRAMEWORK
        records = [row for row in records if row['path'] != name]
    with pytest.raises(ValueError):
        python_copy.check_normalized(installed.declaration, records, installed.artifact)


@pytest.mark.parametrize('changed', [(python_copy.FLAT,), (python_copy.FRAMEWORK,),
    (python_copy.FLAT, python_copy.FRAMEWORK)])
def test_loaded_bytes_must_match_original_receipt_even_if_both_copies_change(installed, changed):
    for name in changed:
        original = (installed.root / name).read_bytes()
        (installed.root / name).write_bytes(b'x' * len(original))
    with pytest.raises(ValueError, match='differs from verified artifact'):
        live(installed)


def test_changing_both_copies_and_declaration_cannot_replace_original_receipt(installed):
    raw = b'changed Python bytes, equal to each other'
    for name in (python_copy.FLAT, python_copy.FRAMEWORK):
        (installed.root / name).write_bytes(raw)
    rewrite_declaration(installed, {'sha256': sha(raw), 'size': len(raw)})
    with pytest.raises(ValueError, match='external artifact'):
        live(installed)


@pytest.mark.parametrize('name,limit', [(python_copy.DECLARATION_NAME, python_copy.MAX_DECLARATION_BYTES),
                                      ('.kuma-runtime.json', python_copy.MAX_RECEIPT_BYTES)])
@pytest.mark.parametrize('variant', ['missing', 'malformed', 'duplicate-key', 'noncanonical', 'oversized'])
def test_live_metadata_is_present_strict_canonical_and_bounded(installed, name, limit, variant):
    path = installed.root / name
    raw = path.read_bytes()
    if variant == 'missing':
        path.unlink()
    elif variant == 'malformed':
        path.write_bytes(b'{not json')
    elif variant == 'duplicate-key':
        path.write_bytes(b'{"schema":"duplicate",' + raw[1:])
    elif variant == 'noncanonical':
        path.write_bytes(json.dumps(json.loads(raw), indent=2).encode() + b'\n')
    else:
        path.write_bytes(b' ' * (limit + 1))
    with pytest.raises((ValueError, OSError)):
        live(installed)


@pytest.mark.parametrize('variant', ['wrong-schema', 'missing-schema', 'extra-field',
                                   'wrong-platform', 'boolean-archive-size', 'duplicate-member'])
def test_live_receipt_rejects_invalid_managed_artifact(installed, variant):
    path = installed.root / '.kuma-runtime.json'
    value = json.loads(path.read_bytes())
    if variant == 'wrong-schema':
        value['schema'] = 'unknown'
    elif variant == 'missing-schema':
        value.pop('schema')
    elif variant == 'extra-field':
        value['untrusted'] = True
    elif variant == 'wrong-platform':
        value['platform'] = 'linux-x86_64'
    elif variant == 'boolean-archive-size':
        value['archive_size'] = True
    else:
        value['files'].append(copy.deepcopy(value['files'][0]))
    path.write_bytes(canonical(value) + b'\n')
    with pytest.raises(ValueError):
        live(installed)


@pytest.mark.parametrize('change', [{'sha256': 'b' * 64}, {'size': 1},
    {'flat_path': '_internal/Other/Python'},
    {'framework_path': '_internal/Python.framework/Versions/3.12/Python'}])
def test_live_declaration_rejects_stale_claims_and_wrong_paths(installed, change):
    rewrite_declaration(installed, change)
    with pytest.raises(ValueError):
        live(installed)


@pytest.mark.parametrize('variant', ['wrong-internal', 'no-native-flat', 'same-basename-native',
    'missing-original-row', 'same-basename-image', 'wrong-index', 'duplicate-loaded-row'])
def test_live_proof_requires_exact_native_path_and_original_indexed_row(installed, tmp_path, variant):
    value = installed
    external = tmp_path / 'external' / 'Python'
    external.parent.mkdir()
    external.write_bytes((value.root / python_copy.FLAT).read_bytes())
    if variant == 'wrong-internal':
        value.internal = value.root / 'other'
    elif variant == 'no-native-flat':
        value.native = {'bundled': []}
    elif variant == 'same-basename-native':
        value.native = {'bundled': [str(external)]}
    elif variant == 'missing-original-row':
        value.images = (image(value.root / python_copy.FRAMEWORK),)
    elif variant == 'same-basename-image':
        value.images = (image(external),)
    elif variant == 'wrong-index':
        value.images = (image(value.root / python_copy.FLAT, 1),)
    else:
        value.images += (image(value.root / python_copy.FLAT, 1),)
    with pytest.raises(ValueError):
        live(value)


@pytest.mark.parametrize('location', ['internal', 'external'])
def test_live_proof_rejects_alias_spelling_for_original_loaded_row(installed, tmp_path, location):
    base = installed.internal if location == 'internal' else tmp_path
    alias = base / 'alias-Python'
    alias.symlink_to(installed.root / python_copy.FLAT)
    installed.images = (image(alias),)
    with pytest.raises(ValueError, match='original exact loaded'):
        live(installed)


@pytest.mark.parametrize('name', [python_copy.FLAT, python_copy.FRAMEWORK,
                                python_copy.DECLARATION_NAME, '.kuma-runtime.json'])
@pytest.mark.parametrize('variant', ['symlink', 'hardlink', 'reparse', 'changed-open-identity',
                                   'changed-during-read', 'replaced-during-read'])
def test_live_inputs_require_stable_plain_single_link_files(installed, monkeypatch, name, variant):
    target = installed.root / name
    if variant in {'symlink', 'hardlink'}:
        other = installed.root / ('saved-' + target.name)
        other.write_bytes(target.read_bytes())
        target.unlink()
        if variant == 'symlink':
            target.symlink_to(other)
        else:
            target.hardlink_to(other)
    elif variant == 'reparse':
        real_lstat = Path.lstat
        def reparse_lstat(path):
            info = real_lstat(path)
            if path == target:
                return SimpleNamespace(st_mode=info.st_mode, st_nlink=info.st_nlink,
                    st_file_attributes=0x400, st_size=info.st_size)
            return info
        monkeypatch.setattr(Path, 'lstat', reparse_lstat)
    else:
        expected = target.stat()
        real_fstat = origin.os.fstat
        calls = 0
        def unstable_fstat(fd):
            nonlocal calls
            info = real_fstat(fd)
            if (info.st_dev, info.st_ino) != (expected.st_dev, expected.st_ino):
                return info
            calls += 1
            if variant == 'changed-open-identity' and calls == 1:
                return SimpleNamespace(st_dev=info.st_dev, st_ino=info.st_ino + 1)
            if variant == 'changed-during-read' and calls == 2:
                return SimpleNamespace(st_size=info.st_size, st_mtime_ns=info.st_mtime_ns + 1,
                                       st_ctime_ns=info.st_ctime_ns)
            if variant == 'replaced-during-read' and calls == 2:
                contents = target.read_bytes()
                target.rename(installed.root / ('replaced-' + target.name))
                target.write_bytes(contents)
            return info
        monkeypatch.setattr(origin.os, 'fstat', unstable_fstat)
    with pytest.raises(ValueError):
        live(installed)


@pytest.mark.parametrize('parent', ['_internal', '_internal/Python.framework/Versions'])
def test_live_python_copy_parent_reparse_points_are_rejected(installed, monkeypatch, parent):
    target = installed.root / parent
    real_lstat = Path.lstat
    def reparse_lstat(path):
        info = real_lstat(path)
        if path == target:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info
    monkeypatch.setattr(Path, 'lstat', reparse_lstat)
    with pytest.raises(ValueError, match='parent is not plain'):
        live(installed)


def test_live_framework_parent_symlink_is_rejected(installed):
    original = installed.internal / 'Python.framework'
    moved = installed.root / 'moved-framework'
    original.rename(moved)
    original.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError, match='exact and canonical'):
        live(installed)


@pytest.mark.parametrize('variant', ['schema', 'missing-field', 'extra-field', 'declaration',
    'declaration-hash', 'receipt-hash', 'archive-hash', 'executable-hash', 'loaded-path',
    'negative-index', 'out-of-range-index', 'boolean-index'])
def test_replay_rejects_stale_or_malformed_proof(installed, variant):
    proof, _ = live(installed)
    changes = {'schema': ('schema', 'unknown'), 'declaration-hash': ('declaration_sha256', 'b' * 64),
        'receipt-hash': ('receipt_sha256', 'b' * 64), 'archive-hash': ('archive_sha256', 'b' * 64),
        'executable-hash': ('executable_sha256', 'b' * 64), 'loaded-path': ('loaded_path', python_copy.FRAMEWORK),
        'negative-index': ('loaded_image_index', -1), 'out-of-range-index': ('loaded_image_index', 1),
        'boolean-index': ('loaded_image_index', False)}
    if variant == 'missing-field':
        proof.pop('receipt_sha256')
    elif variant == 'extra-field':
        proof['untrusted'] = True
    elif variant == 'declaration':
        proof['declaration'] = {**proof['declaration'], 'sha256': 'b' * 64}
    else:
        key, replacement = changes[variant]
        proof[key] = replacement
    with pytest.raises(ValueError):
        python_copy.validate_proof(proof, **replay_inputs(installed))


@pytest.mark.parametrize('variant', ['image-path', 'resolved-path', 'image-kind', 'image-index',
                                   'missing-images', 'missing-native', 'wrong-role', 'wrong-executable'])
def test_replay_requires_matching_loaded_image_native_row_and_executable(installed, variant):
    proof, _ = live(installed)
    kwargs = replay_inputs(installed)
    changes = {'image-path': ('path', python_copy.FRAMEWORK),
               'resolved-path': ('resolved_path', '_internal/Other/Python'),
               'image-kind': ('kind', 'system'), 'image-index': ('image_index', 1)}
    if variant in changes:
        key, replacement = changes[variant]
        kwargs['images'][0][key] = replacement
    elif variant == 'missing-images':
        kwargs['images'] = []
    elif variant == 'missing-native':
        kwargs['native']['bundled'] = []
    elif variant == 'wrong-role':
        kwargs['native']['required']['python'] = python_copy.FRAMEWORK
    else:
        kwargs['executable_sha256'] = 'b' * 64
    with pytest.raises(ValueError):
        python_copy.validate_proof(proof, **kwargs)


@pytest.mark.parametrize('variant', ['archive-hash', 'archive-size', 'version', 'engine', 'platform',
    'executable-path', 'duplicate-member', 'casefold-duplicate', 'missing-declaration',
    'missing-flat', 'missing-framework', 'missing-executable', 'flat-hash', 'framework-size',
    'framework-not-executable', 'declaration-hash', 'declaration-executable', 'executable-hash',
    'extra-field', 'bad-row-path', 'row-extra-field', 'row-boolean-size', 'row-invalid-hash'])
def test_replay_requires_original_external_artifact(installed, variant):
    proof, _ = live(installed)
    kwargs = replay_inputs(installed)
    artifact = kwargs['artifact'] = copy.deepcopy(installed.artifact)
    changes = {'archive-hash': ('archive_sha256', 'b' * 64), 'archive-size': ('archive_size', 1001),
        'version': ('version', 'different-v2'), 'engine': ('engine', 'other'),
        'platform': ('platform', 'linux-x86_64'), 'executable-path': ('executable_path', 'other')}
    rows = {row['path']: row for row in artifact['files']}
    if variant in changes:
        key, replacement = changes[variant]
        artifact[key] = replacement
    elif variant in {'duplicate-member', 'casefold-duplicate'}:
        row = copy.deepcopy(artifact['files'][0])
        if variant == 'casefold-duplicate':
            row['path'] = row['path'].upper()
        artifact['files'].append(row)
    elif variant.startswith('missing-'):
        names = {'missing-declaration': python_copy.DECLARATION_NAME, 'missing-flat': python_copy.FLAT,
                 'missing-framework': python_copy.FRAMEWORK, 'missing-executable': 'kuma-merizo'}
        artifact['files'] = [row for row in artifact['files'] if row['path'] != names[variant]]
    elif variant == 'extra-field':
        artifact['untrusted'] = True
    else:
        edits = {'flat-hash': (python_copy.FLAT, 'sha256', 'b' * 64),
            'framework-size': (python_copy.FRAMEWORK, 'size', 1),
            'framework-not-executable': (python_copy.FRAMEWORK, 'executable', False),
            'declaration-hash': (python_copy.DECLARATION_NAME, 'sha256', 'b' * 64),
            'declaration-executable': (python_copy.DECLARATION_NAME, 'executable', True),
            'executable-hash': ('kuma-merizo', 'sha256', 'b' * 64),
            'bad-row-path': (python_copy.FLAT, 'path', '_internal/../Python'),
            'row-extra-field': (python_copy.FLAT, 'untrusted', True),
            'row-boolean-size': (python_copy.FLAT, 'size', True),
            'row-invalid-hash': (python_copy.FLAT, 'sha256', 'A' * 64)}
        name, key, replacement = edits[variant]
        rows[name][key] = replacement
    with pytest.raises(ValueError):
        python_copy.validate_proof(proof, **kwargs)


def test_self_consistent_local_replacement_is_not_external_artifact_authority(installed):
    original = copy.deepcopy(installed.artifact)
    raw = b'locally substituted Python framework'
    for name in (python_copy.FLAT, python_copy.FRAMEWORK):
        (installed.root / name).write_bytes(raw)
    rewrite_declaration(installed, {'sha256': sha(raw), 'size': len(raw)})
    for row in installed.artifact['files']:
        contents = (installed.root / row['path']).read_bytes()
        row.update(sha256=sha(contents), size=len(contents))
    (installed.root / '.kuma-runtime.json').write_bytes(python_copy.receipt_bytes(installed.artifact))
    # A local receipt is deliberately not an independent trust root. Replay
    # must use the manager/exporter's separate trusted artifact, not this copy.
    proof, claimed_artifact = live(installed)
    assert claimed_artifact != original
    kwargs = replay_inputs(installed)
    kwargs['artifact'] = original
    with pytest.raises(ValueError, match='external artifact'):
        python_copy.validate_proof(proof, **kwargs)


def test_real_registry_dataclass_serialization_matches_exact_receipt(installed):
    from dataclasses import asdict
    from kuma_core.kuro.optional_runtime import RuntimeArtifact, RuntimeFile, _receipt
    from scripts.merizo_runtime_archive.common import strict_json
    value = installed.artifact
    artifact = RuntimeArtifact(**{**value, 'files': tuple(RuntimeFile(**row) for row in value['files'])})
    assert isinstance(asdict(artifact)['files'], tuple)
    # Both build and service export pass through JSON at this strict schema boundary.
    normalized = strict_json(canonical(asdict(artifact)))
    assert isinstance(normalized['files'], list)
    assert python_copy.receipt_bytes(normalized) == _receipt(artifact)
    assert python_copy.check_normalized(installed.declaration, installed.records, normalized)


@pytest.mark.parametrize('field,replacement', [('path', 'OTHER.json'), ('sha256', 'b' * 64),
    ('size', 1), ('executable', True), ('original_path', 'OTHER.json'), ('aliases', ['unrelated'])])
def test_normalized_declaration_row_matches_artifact_and_original_inventory(installed, field, replacement):
    records = copy.deepcopy(installed.records)
    next(row for row in records if row['path'] == python_copy.DECLARATION_NAME)[field] = replacement
    with pytest.raises(ValueError):
        python_copy.check_normalized(installed.declaration, records, installed.artifact)
