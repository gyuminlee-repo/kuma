"""Offline public-fixture export/replay tests, never real execution evidence.

Labels and origin records below are deliberately synthetic test data. Passing
these tests establishes strict serialization and binding checks, not model
execution, loaded-library provenance, AF3 prediction quality, or accuracy.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from kuma_core.kuro.domain_merizo import (
    MERIZO_CODE_FINGERPRINT,
    MERIZO_COMMIT,
    MERIZO_NOTICE_POLICY,
    MERIZO_NOTICE_SOURCE_SHA256,
    MERIZO_WEIGHTS_SHA256,
    domain_input_manifest,
    expected_ca_coordinates,
)
from scripts.merizo_runtime_archive import execution_evidence as evidence
from scripts.merizo_runtime_archive import public_fixture, runtime_origin
from scripts.merizo_runtime_archive.common import canonical, strict_json


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'tests/data/domain_annotation/1ubq.pdb'
IDENTITIES = {
    'archive_sha256': 'a' * 64,
    'executable_sha256': 'b' * 64,
    'source_identity_sha256': 'c' * 64,
    'build_revision': 'd' * 40,
}
FIXTURE_IDS = ('public_1ubq', 'synthetic_af3_public_geometry')
EXPECTED_FILENAMES = {
    'public_1ubq': 'archive-public-1ubq-execution.json',
    'synthetic_af3_public_geometry': 'archive-synthetic-af3-execution.json',
}


@pytest.fixture(scope='module')
def public_inputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp('execution-public-fixtures')
    _, synthetic, recipe = public_fixture.create_af3_fixture(PUBLIC, directory / 'fixture.zip')
    return {
        'public_1ubq': public_fixture.public_prepared(PUBLIC),
        'synthetic_af3_public_geometry': synthetic,
        'recipe': recipe,
    }


def mock_result(prepared):
    """Valid interchange with invented, discontinuous labels; no inference."""
    nres = len(prepared.sequence)
    labels = [42 if i % 3 == 0 else 7 if i % 3 == 1 else 0 for i in range(nres)]
    return {
        'schema': 'kuma-merizo-result-v1', 'tool_commit': MERIZO_COMMIT,
        'weights_sha256': dict(MERIZO_WEIGHTS_SHA256),
        'input': domain_input_manifest(prepared),
        'process': {'status': 'ok', 'exit_code': 0, 'warnings': []},
        'features': {
            'nres': nres, 'sequence': prepared.sequence,
            'residue_numbers': list(range(1, nres + 1)),
            'ca_coordinates': [list(xyz) for xyz in expected_ca_coordinates(prepared)],
        },
        'prediction': {
            'nres': nres, 'ndom': 2, 'labels': labels,
            'residue_numbers': list(range(1, nres + 1)),
            'confidence': 0.91, 'time_sec': 0.2,
        },
    }


def mock_notices():
    return {
        'basis': {
            'policy_id': MERIZO_NOTICE_POLICY, 'source_member': 'pyparsing/util.py',
            'source_sha256': MERIZO_NOTICE_SOURCE_SHA256,
            'code_fingerprint_schema': MERIZO_CODE_FINGERPRINT,
            'python_abi': 'cpython-311',
            'code_fingerprints': {'461': '1' * 64, '472': '2' * 64},
        },
        'count': 11,
        'counts': {'pyparsing_parse_string_alias': 5, 'pyparsing_reset_cache_alias': 5,
                   'pyparsing_enable_packrat_alias': 1},
    }


def mock_origins(prepared):
    """Schema-valid Linux mock, explicitly not an observed process inventory."""
    required = {'python': '_internal/libpython3.11.so.1.0',
                'torch_cpu': '_internal/torch/lib/libtorch_cpu.so',
                'c10': '_internal/torch/lib/libc10.so'}
    return {
        'schema': 'kuma-merizo-installed-origins-v1', 'platform': 'Linux',
        'module_families': ['torch', 'model', 'predict'],
        'executable_sha256': IDENTITIES['executable_sha256'],
        'input_binding_sha256': prepared.binding_sha256,
        'source_identity_sha256': IDENTITIES['source_identity_sha256'],
        'snapshots': [{
            'phase': phase, 'mechanism': 'proc_self_maps_executable_files',
            'contract': 'linux_loaded_origins_v1',
            'modules': {'torch': 'torch/__init__.pyc', 'predict': 'predict.pyc',
                        'model.network': 'model/network.pyc',
                        'model.utils.features': 'model/utils/features.pyc'},
            'native': {'bundled': list(required.values()),
                       'system_path_basis': 'absolute_posix_os_roots',
                       'system': ['/usr/lib/x86_64-linux-gnu/libc.so.6'],
                       'required': dict(required)},
            'images': [],
            'environment': {
                'empty_search_path': True, 'private_home_cache_temp': True,
                'no_python_environment': True, 'bundle_loader_paths': True,
                'gpu_hidden': True, 'single_thread_environment': True,
            },
        } for phase in ('before_weights', 'after_inference')],
    }


def original_result_bytes(prepared):
    # Preserve CRLF, leading/trailing whitespace and pretty-printing exactly.
    return ('\t \r\n' + json.dumps(mock_result(prepared), indent=2).replace('\n', '\r\n')
            + '\r\n \t\n').encode('utf-8')


def write_inputs(directory, prepared, *, result=None, origins=None):
    result_path, origin_path = directory / 'result.json', directory / 'origins.json'
    result_path.write_bytes(original_result_bytes(prepared) if result is None else result)
    origin_path.write_bytes(canonical(mock_origins(prepared) if origins is None else origins) + b'\n')
    return result_path, origin_path


def export(directory, result, origins, public_inputs, fixture_id, **overrides):
    kwargs = {'prepared': public_inputs[fixture_id], 'fixture_id': fixture_id, 'fixture': PUBLIC,
              'recipe': public_inputs['recipe'], **IDENTITIES, **overrides}
    return evidence.export_execution(directory, result, origins, **kwargs)


def exported(tmp_path, public_inputs, fixture_id='synthetic_af3_public_geometry'):
    result, origins = write_inputs(tmp_path, public_inputs[fixture_id])
    metadata = export(tmp_path, result, origins, public_inputs, fixture_id)
    path = tmp_path / metadata['filename']
    return path, strict_json(path.read_bytes()), result, origins


def write_evidence(path, value):
    path.write_bytes(canonical(value) + b'\n')


@pytest.mark.parametrize('fixture_id', FIXTURE_IDS)
def test_exact_public_result_bytes_export_and_independent_replay(tmp_path, public_inputs, fixture_id):
    prepared = public_inputs[fixture_id]
    raw = original_result_bytes(prepared)
    result, origins = write_inputs(tmp_path, prepared)
    assert runtime_origin.validate_origins(mock_origins(prepared),
        executable_sha256=IDENTITIES['executable_sha256'], binding_sha256=prepared.binding_sha256,
        source_identity_sha256=IDENTITIES['source_identity_sha256']) == mock_origins(prepared)
    metadata = export(tmp_path, result, origins, public_inputs, fixture_id)
    assert evidence.FILENAMES == EXPECTED_FILENAMES
    assert metadata['filename'] == EXPECTED_FILENAMES[fixture_id]
    path = tmp_path / metadata['filename']
    serialized = path.read_bytes()
    value = strict_json(serialized)
    assert serialized == canonical(value) + b'\n'
    assert metadata == {
        'filename': path.name, 'sha256': hashlib.sha256(serialized).hexdigest(),
        'bytes': len(serialized), 'result_sha256': hashlib.sha256(raw).hexdigest(),
        'result_bytes': len(raw), 'input_binding_sha256': prepared.binding_sha256,
        'origin_phases': ['before_weights', 'after_inference'],
    }
    assert value['result_text'].encode('utf-8') == raw
    assert value['result_sha256'] != hashlib.sha256(canonical(mock_result(prepared))).hexdigest()
    assert value['result_bytes'] == len(raw)
    assert value['fixture_recipe'] == public_inputs['recipe']
    assert value['origins'] == mock_origins(prepared)
    assert evidence.MAX_EXECUTION_BYTES == 1024 * 1024
    assert evidence.MAX_PUBLIC_RESULT_BYTES == 256 * 1024
    assert runtime_origin.MAX_ORIGIN_BYTES == 512 * 1024
    assert len(serialized) <= evidence.MAX_EXECUTION_BYTES
    result.unlink()
    origins.unlink()
    annotation = evidence.replay_execution(path, PUBLIC, **IDENTITIES)
    assert annotation.total_residues == 76
    assert len(annotation.domains) == 2
    assert annotation.unassigned_positions == tuple(range(3, 77, 3))
    assert annotation.domains[1].source_residues[3] == prepared.residues[10]
    assert 'provenance_unverified' in annotation.interpretation
    # A new interpreter must regenerate fixture/recipe and decode only. Model
    # imports are explicitly blocked, and the original two inputs are gone.
    script = """
import importlib.abc, json, sys
from pathlib import Path
class NoModel(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'predict', 'model'}:
            raise AssertionError('Offline replay attempted model import')
sys.meta_path.insert(0, NoModel())
from scripts.merizo_runtime_archive.execution_evidence import replay_execution
result = replay_execution(Path(sys.argv[1]), Path(sys.argv[2]), **json.loads(sys.argv[3]))
assert result.total_residues == 76 and len(result.domains) == 2
print('offline replay passed')
"""
    completed = subprocess.run([sys.executable, '-c', script, str(path), str(PUBLIC),
                                json.dumps(IDENTITIES)], cwd=ROOT, text=True,
                               capture_output=True, check=False, timeout=60,
                               env={**os.environ, 'PYTHONPATH': str(ROOT)})
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == 'offline replay passed'


@pytest.mark.parametrize('fixture_id', FIXTURE_IDS)
def test_strict_optional_compatibility_notices_survive_export(tmp_path, public_inputs, fixture_id):
    prepared = public_inputs[fixture_id]
    value = mock_result(prepared)
    value['process']['compatibility_notices'] = mock_notices()
    raw = canonical(value) + b'\n'
    result, origins = write_inputs(tmp_path, prepared, result=raw)
    metadata = export(tmp_path, result, origins, public_inputs, fixture_id)
    path = tmp_path / metadata['filename']
    assert strict_json(path.read_bytes())['result_text'].encode() == raw
    assert evidence.replay_execution(path, PUBLIC, **IDENTITIES).total_residues == 76


@pytest.mark.parametrize('section', [None, 'input', 'weights_sha256', 'process', 'features',
                                   'prediction', 'residue', 'notices', 'notice_basis', 'notice_counts'])
def test_result_extra_fields_cannot_be_exported(tmp_path, public_inputs, section):
    prepared = public_inputs['public_1ubq']
    value = mock_result(prepared)
    if section == 'residue':
        target = value['input']['residues'][0]
    elif section in {'notices', 'notice_basis', 'notice_counts'}:
        value['process']['compatibility_notices'] = mock_notices()
        target = value['process']['compatibility_notices']
        if section != 'notices':
            target = target['basis' if section == 'notice_basis' else 'counts']
    else:
        target = value if section is None else value[section]
    target['private_unapproved_data'] = 'must never be copied to evidence'
    result, origins = write_inputs(tmp_path, prepared, result=canonical(value))
    with pytest.raises(ValueError):
        export(tmp_path, result, origins, public_inputs, 'public_1ubq')
    assert not (tmp_path / EXPECTED_FILENAMES['public_1ubq']).exists()


@pytest.mark.parametrize(('section', 'field', 'bad'), [
    ('process', 'exit_code', False), ('process', 'warnings', ['private warning']),
    ('features', 'nres', True), ('prediction', 'nres', True), ('prediction', 'ndom', True),
    ('prediction', 'labels', [True] * 76), ('prediction', 'confidence', True),
    ('prediction', 'time_sec', True), ('features', 'residue_numbers', [True] + list(range(2, 77))),
    ('prediction', 'residue_numbers', [True] + list(range(2, 77))),
])
def test_boolean_counts_and_malformed_results_fail_closed(tmp_path, public_inputs, section, field, bad):
    prepared = public_inputs['public_1ubq']
    value = mock_result(prepared)
    value[section][field] = bad
    result, origins = write_inputs(tmp_path, prepared, result=canonical(value))
    with pytest.raises(ValueError):
        export(tmp_path, result, origins, public_inputs, 'public_1ubq')
    assert not (tmp_path / EXPECTED_FILENAMES['public_1ubq']).exists()


@pytest.mark.parametrize('location', ['count', 'counts', 'basis', 'fingerprints'])
def test_malformed_compatibility_notices_reject(tmp_path, public_inputs, location):
    prepared = public_inputs['public_1ubq']
    value, notice = mock_result(prepared), mock_notices()
    if location == 'count':
        notice['count'] = True
    elif location == 'counts':
        notice['counts']['pyparsing_enable_packrat_alias'] = True
    elif location == 'basis':
        notice['basis']['source_sha256'] = '0' * 64
    else:
        notice['basis']['code_fingerprints']['private'] = '3' * 64
    value['process']['compatibility_notices'] = notice
    result, origins = write_inputs(tmp_path, prepared, result=canonical(value))
    with pytest.raises(ValueError):
        export(tmp_path, result, origins, public_inputs, 'public_1ubq')


@pytest.mark.parametrize('bad_json', ['duplicate_root', 'duplicate_nested', 'NaN', 'Infinity',
                                  '-Infinity', 'overflow', 'bom', 'invalid_utf8', 'array_root'])
def test_invalid_json_cannot_be_exported(tmp_path, public_inputs, bad_json):
    prepared = public_inputs['public_1ubq']
    raw = canonical(mock_result(prepared))
    if bad_json == 'duplicate_root':
        raw = b'{"schema":"kuma-merizo-result-v1",' + raw[1:]
    elif bad_json == 'duplicate_nested':
        raw = raw.replace(b'"ndom":2', b'"ndom":2,"ndom":2')
    elif bad_json in {'NaN', 'Infinity', '-Infinity', 'overflow'}:
        raw = raw.replace(b'"confidence":0.91', b'"confidence":' +
                          ('1e999' if bad_json == 'overflow' else bad_json).encode())
    elif bad_json == 'bom':
        raw = b'\xef\xbb\xbf' + raw
    elif bad_json == 'invalid_utf8':
        raw += b'\xff'
    else:
        raw = b'[]'
    result, origins = write_inputs(tmp_path, prepared, result=raw)
    with pytest.raises(ValueError):
        export(tmp_path, result, origins, public_inputs, 'public_1ubq')


@pytest.mark.parametrize('field', ['archive_sha256', 'executable_sha256', 'source_identity_sha256',
                                 'build_revision', 'input_binding_sha256', 'fixture'])
def test_replay_rejects_wrong_execution_binding(tmp_path, public_inputs, field):
    path, value, _, _ = exported(tmp_path, public_inputs)
    value[field] = ('0' * 40 if field == 'build_revision' else
                    'public_1ubq' if field == 'fixture' else '0' * 64)
    write_evidence(path, value)
    with pytest.raises(ValueError):
        evidence.replay_execution(path, PUBLIC, **IDENTITIES)


@pytest.mark.parametrize('field', tuple(IDENTITIES))
def test_replay_rejects_wrong_independent_expected_identity(tmp_path, public_inputs, field):
    path, _, _, _ = exported(tmp_path, public_inputs)
    wrong = {**IDENTITIES, field: '0' * (40 if field == 'build_revision' else 64)}
    with pytest.raises(ValueError):
        evidence.replay_execution(path, PUBLIC, **wrong)


@pytest.mark.parametrize('field', ['public_source_sha256', 'generator_source_sha256', 'bundle_sha256',
                                 'source_sha256', 'binding_sha256', 'public_binding_sha256',
                                 'confidence_member_sha256', 'normalized_sha256', 'zip', 'atom_count',
                                 'residue_count', 'source_residues', 'private_unapproved_data'])
def test_replay_regenerates_recipe_instead_of_trusting_claims(tmp_path, public_inputs, field):
    path, value, _, _ = exported(tmp_path, public_inputs)
    recipe = value['fixture_recipe']
    if field == 'zip':
        recipe[field]['timestamp'][0] = 2000
    elif field == 'source_residues':
        recipe[field][10]['insertion_code'] = ''
    elif field in {'atom_count', 'residue_count'}:
        recipe[field] = True
    else:
        recipe[field] = '0' * 64
    write_evidence(path, value)
    with pytest.raises(ValueError):
        evidence.replay_execution(path, PUBLIC, **IDENTITIES)


def test_replay_requires_exact_pinned_public_input(tmp_path, public_inputs):
    path, _, _, _ = exported(tmp_path, public_inputs)
    changed = tmp_path / 'changed-public.pdb'
    changed.write_bytes(PUBLIC.read_bytes().replace(b'27.340', b'27.341', 1))
    with pytest.raises(ValueError, match='pinned public'):
        evidence.replay_execution(path, changed, **IDENTITIES)


@pytest.mark.parametrize('mutation', ['result_sha256', 'result_bytes', 'bool_bytes', 'result_text',
                                    'extra_root', 'unknown_fixture', 'not_text'])
def test_replay_rejects_changed_exact_result_and_extra_envelope_fields(tmp_path, public_inputs, mutation):
    path, value, _, _ = exported(tmp_path, public_inputs)
    if mutation == 'bool_bytes':
        value['result_bytes'] = True
    elif mutation == 'result_bytes':
        value['result_bytes'] += 1
    elif mutation == 'result_text':
        value['result_text'] += '\n'
    elif mutation == 'result_sha256':
        value['result_sha256'] = '0' * 64
    elif mutation == 'extra_root':
        value['private_data'] = 'not approved for export'
    elif mutation == 'unknown_fixture':
        value['fixture'] = 'private_structure'
    else:
        value['result_text'] = {}
    write_evidence(path, value)
    with pytest.raises(ValueError):
        evidence.replay_execution(path, PUBLIC, **IDENTITIES)


@pytest.mark.parametrize('file_kind', ['result', 'origins', 'evidence'])
@pytest.mark.parametrize('malformed', ['duplicate', 'nonfinite'])
def test_duplicate_keys_and_nonfinite_json_rejected_at_every_file_boundary(
        tmp_path, public_inputs, file_kind, malformed):
    path, _, result, origins = exported(tmp_path, public_inputs)
    target = {'result': result, 'origins': origins, 'evidence': path}[file_kind]
    raw = target.read_bytes().lstrip()
    if malformed == 'duplicate':
        schema = json.loads(raw)['schema']
        raw = ('{"schema":' + json.dumps(schema) + ',').encode() + raw[1:]
    else:
        raw = b'{"private_data":NaN,' + raw[1:]
    target.write_bytes(raw)
    if file_kind == 'evidence':
        with pytest.raises(ValueError):
            evidence.replay_execution(path, PUBLIC, **IDENTITIES)
    else:
        path.unlink()
        with pytest.raises(ValueError):
            export(tmp_path, result, origins, public_inputs, 'synthetic_af3_public_geometry')
        assert not path.exists()


@pytest.mark.parametrize('mutation', ['executable', 'binding', 'source_identity', 'missing_phase',
                                    'phase_order', 'extra_root', 'extra_snapshot', 'extra_native',
                                    'extra_environment', 'numeric_check', 'missing_module',
                                    'missing_role', 'unbundled_role', 'relative_system_path',
                                    'escaped_module_path'])
def test_invalid_origin_record_is_never_exported(tmp_path, public_inputs, mutation):
    prepared = public_inputs['public_1ubq']
    origins = mock_origins(prepared)
    row = origins['snapshots'][0]
    if mutation in {'executable', 'binding', 'source_identity'}:
        field = {'executable': 'executable_sha256', 'binding': 'input_binding_sha256',
                 'source_identity': 'source_identity_sha256'}[mutation]
        origins[field] = '0' * 64
    elif mutation == 'missing_phase':
        origins['snapshots'].pop()
    elif mutation == 'phase_order':
        origins['snapshots'].reverse()
    elif mutation == 'extra_root':
        origins['private_data'] = 'secret'
    elif mutation == 'extra_snapshot':
        row['private_data'] = 'secret'
    elif mutation == 'extra_native':
        row['native']['private_data'] = 'secret'
    elif mutation == 'extra_environment':
        row['environment']['private_data'] = True
    elif mutation == 'numeric_check':
        row['environment']['gpu_hidden'] = 1
    elif mutation == 'missing_module':
        row['modules'].pop('torch')
    elif mutation == 'missing_role':
        row['native']['required'].pop('python')
    elif mutation == 'unbundled_role':
        row['native']['required']['python'] = 'not-in-bundled/libpython.so'
    elif mutation == 'relative_system_path':
        row['native']['system'] = ['relative/libc.so.6']
    else:
        row['modules']['torch'] = '../outside/torch.py'
    result, origin_path = write_inputs(tmp_path, prepared, origins=origins)
    with pytest.raises(ValueError):
        export(tmp_path, result, origin_path, public_inputs, 'public_1ubq')
    assert not (tmp_path / EXPECTED_FILENAMES['public_1ubq']).exists()


@pytest.mark.parametrize('file_kind', ['result', 'origins', 'evidence'])
@pytest.mark.parametrize('unsafe', ['symlink', 'hardlink', 'oversized'])
def test_linked_or_oversized_evidence_files_fail_closed(tmp_path, public_inputs, file_kind, unsafe):
    path, _, result, origins = exported(tmp_path, public_inputs)
    target = {'result': result, 'origins': origins, 'evidence': path}[file_kind]
    if unsafe == 'oversized':
        limit = {'result': evidence.MAX_PUBLIC_RESULT_BYTES,
                 'origins': runtime_origin.MAX_ORIGIN_BYTES,
                 'evidence': evidence.MAX_EXECUTION_BYTES}[file_kind]
        target.write_bytes(b' ' * (limit + 1))
    else:
        original = target.with_suffix('.original')
        target.rename(original)
        try:
            target.symlink_to(original) if unsafe == 'symlink' else os.link(original, target)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f'{unsafe} is unavailable on this filesystem: {exc}')
    if file_kind == 'evidence':
        with pytest.raises(ValueError):
            evidence.replay_execution(path, PUBLIC, **IDENTITIES)
    else:
        path.unlink()
        with pytest.raises(ValueError):
            export(tmp_path, result, origins, public_inputs, 'synthetic_af3_public_geometry')
        assert not path.exists()


@pytest.mark.parametrize('stale', ['file', 'symlink', 'dangling_symlink', 'directory'])
def test_export_refuses_stale_destinations_without_overwriting(tmp_path, public_inputs, stale):
    result, origins = write_inputs(tmp_path, public_inputs['public_1ubq'])
    output = tmp_path / EXPECTED_FILENAMES['public_1ubq']
    original = tmp_path / 'preexisting.json'
    original.write_bytes(b'preexisting evidence')
    if stale == 'file':
        output.write_bytes(b'preexisting evidence')
    elif stale == 'directory':
        output.mkdir()
    else:
        try:
            output.symlink_to(original if stale == 'symlink' else tmp_path / 'missing')
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f'Symlinks unavailable on this filesystem: {exc}')
    with pytest.raises((OSError, ValueError)):
        export(tmp_path, result, origins, public_inputs, 'public_1ubq')
    assert original.read_bytes() == b'preexisting evidence'
    if stale == 'file':
        assert output.read_bytes() == b'preexisting evidence'
    elif stale == 'directory':
        assert output.is_dir()
    else:
        assert output.is_symlink()
    assert not list(tmp_path.glob('.kuma-audit-*'))


def test_export_does_not_copy_unrequested_neighbor_files(tmp_path, public_inputs):
    inputs, outputs = tmp_path / 'inputs', tmp_path / 'outputs'
    inputs.mkdir()
    outputs.mkdir()
    (inputs / 'private.txt').write_text('private notes that must stay local', encoding='utf-8')
    for fixture_id in FIXTURE_IDS:
        result, origins = write_inputs(inputs, public_inputs[fixture_id])
        export(outputs, result, origins, public_inputs, fixture_id)
    assert {path.name for path in outputs.iterdir()} == set(EXPECTED_FILENAMES.values())
    assert all(b'private notes' not in path.read_bytes() for path in outputs.iterdir())


def test_export_rejects_unapproved_extra_recipe_data(tmp_path, public_inputs):
    result, origins = write_inputs(tmp_path, public_inputs['public_1ubq'])
    recipe = copy.deepcopy(public_inputs['recipe'])
    recipe['private_unapproved_data'] = 'not part of the public fixture recipe'
    with pytest.raises(ValueError):
        export(tmp_path, result, origins, public_inputs, 'public_1ubq', recipe=recipe)
    assert not (tmp_path / EXPECTED_FILENAMES['public_1ubq']).exists()


@pytest.mark.parametrize('fixture_id', FIXTURE_IDS)
def test_export_rejects_other_prepared_input_even_with_valid_result(tmp_path, public_inputs, fixture_id):
    other_id = next(item for item in FIXTURE_IDS if item != fixture_id)
    other = public_inputs[other_id]
    result, origins = write_inputs(tmp_path, other)
    with pytest.raises(ValueError, match='independently regenerated public fixture'):
        export(tmp_path, result, origins, public_inputs, fixture_id, prepared=other)
    assert not (tmp_path / EXPECTED_FILENAMES[fixture_id]).exists()


def test_export_regenerates_the_supplied_public_fixture_before_writing(tmp_path, public_inputs):
    result, origins = write_inputs(tmp_path, public_inputs['public_1ubq'])
    changed = tmp_path / 'changed-public.pdb'
    changed.write_bytes(PUBLIC.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='pinned public'):
        export(tmp_path, result, origins, public_inputs, 'public_1ubq', fixture=changed)
    assert not (tmp_path / EXPECTED_FILENAMES['public_1ubq']).exists()


@pytest.mark.parametrize('field', ['generator_source_sha256', 'bundle_sha256', 'binding_sha256'])
def test_export_rejects_recipe_identity_substitution(tmp_path, public_inputs, field):
    result, origins = write_inputs(tmp_path, public_inputs['public_1ubq'])
    recipe = copy.deepcopy(public_inputs['recipe'])
    recipe[field] = '0' * 64
    with pytest.raises(ValueError, match='independently regenerated public fixture'):
        export(tmp_path, result, origins, public_inputs, 'public_1ubq', recipe=recipe)
    assert not (tmp_path / EXPECTED_FILENAMES['public_1ubq']).exists()


def test_complete_export_limit_counts_escaped_result_and_origin_bytes(tmp_path, public_inputs, monkeypatch):
    prepared = public_inputs['public_1ubq']
    base = canonical(mock_result(prepared))
    raw = b'\t' * (evidence.MAX_PUBLIC_RESULT_BYTES - len(base)) + base
    origins = mock_origins(prepared)
    # Long bounded paths are synthetic parser data, not real module origins.
    # Exercise a near-maximum valid envelope, then reduce only the complete
    # bound to one byte below its exact serialized size. Individual inputs
    # still fit their original limits; none of their validation is weakened.
    for snapshot in origins['snapshots']:
        for index in range(64):
            snapshot['modules'][f'torch.synthetic{index}'] = 'torch/' + 'x' * 3990 + '.pyc'
    origin_bytes = canonical(origins) + b'\n'
    assert len(raw) == evidence.MAX_PUBLIC_RESULT_BYTES
    assert len(origin_bytes) < runtime_origin.MAX_ORIGIN_BYTES
    evidence.strict_result(raw, prepared)
    runtime_origin.validate_origins(origins)
    result, origin_path = write_inputs(tmp_path, prepared, result=raw, origins=origins)
    metadata = export(tmp_path, result, origin_path, public_inputs, 'public_1ubq')
    output = tmp_path / EXPECTED_FILENAMES['public_1ubq']
    assert metadata['bytes'] == output.stat().st_size
    assert len(raw) + len(origin_bytes) < metadata['bytes'] <= evidence.MAX_EXECUTION_BYTES
    output.unlink()
    monkeypatch.setattr(evidence, 'MAX_EXECUTION_BYTES', metadata['bytes'] - 1)
    with pytest.raises(ValueError, match='complete bound'):
        export(tmp_path, result, origin_path, public_inputs, 'public_1ubq')
    assert not output.exists()


def test_owned_temporary_directory_aliases_are_canonicalized_but_caller_aliases_rejected(tmp_path, public_inputs, monkeypatch):
    from contextlib import contextmanager
    original = evidence.tempfile.TemporaryDirectory
    calls = []

    @contextmanager
    def aliased_temporary(*args, **kwargs):
        with original(*args, **kwargs) as actual:
            alias = tmp_path / ('owned-temp-alias-' + str(len(calls)))
            try:
                alias.symlink_to(Path(actual).resolve(), target_is_directory=True)
            except OSError:
                pytest.skip('Directory symlinks unavailable')
            calls.append(alias)
            try:
                yield str(alias)
            finally:
                alias.unlink()

    with aliased_temporary() as alias:
        with pytest.raises(ValueError):
            public_fixture.create_af3_fixture(PUBLIC, Path(alias) / 'caller.zip')
    monkeypatch.setattr(evidence.tempfile, 'TemporaryDirectory', aliased_temporary)
    path, _, _, _ = exported(tmp_path, public_inputs)
    assert evidence.replay_execution(path, PUBLIC, **IDENTITIES).total_residues == 76
    assert len(calls) == 3 and not any(alias.exists() for alias in calls)
