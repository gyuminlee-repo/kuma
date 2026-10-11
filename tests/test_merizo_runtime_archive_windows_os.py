"""Synthetic OS-DLL policy tests; no freezer, model execution or host claims."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import zipfile

import pytest

from scripts.merizo_runtime_archive import windows_os_dll as policy, freeze_spec, runtime_origin as origin
from scripts.merizo_runtime_archive.common import strict_json
from tests.test_domain_merizo import prepared_synthetic
from tests.test_merizo_runtime_archive_origin import saved_origins

HOST = {'system': 'Windows', 'kernel_version': [10, 0, 26100],
        'architecture': 'win-amd64', 'pointer_bits': 64}

# Independently pinned from the reviewed PR12 226-row inventory/design, not a
# wildcard derived from the implementation. A changed name needs review.
EXACT_NAMES_SHA256 = '551356a34a6b2d5c34abbecc6203617406fb7e3fca637d685745d2cd21b031ff'


def rows(tmp_path):
    result = []
    for name in sorted(policy.EXCLUDED | policy.REQUIRED_RETAINED | {
            'python311.dll', 'torch_cpu.dll', 'c10.dll', 'api-ms-win-crt-new-l1-1-0.dll',
            'ucrtbase.dll.extra', 'msvcp140-wheelhash.dll'}):
        source = tmp_path / name
        source.write_bytes(('synthetic input ' + name).encode())
        result.append((name, str(source), 'BINARY'))
    return result


def filter_rows(tmp_path):
    value = rows(tmp_path)
    with patch.object(policy, 'host_identity', return_value=copy.deepcopy(HOST)):
        survivors, ledger = policy.filter_analysis(value)
    return value, survivors, ledger


def test_exact_reviewed_set_and_only_44_inputs_removed(tmp_path):
    assert len(policy.EXCLUDED) == 44
    assert hashlib.sha256(('\n'.join(sorted(policy.EXCLUDED)) + '\n').encode()).hexdigest() == EXACT_NAMES_SHA256
    original, survivors, ledger = filter_rows(tmp_path)
    assert len(original) - len(survivors) == 44
    assert ledger['schema'] == policy.LEDGER_SCHEMA and ledger['policy'] == policy.POLICY
    assert ledger['host'] == HOST and len(ledger['omitted']) == 44
    assert survivors == [row for row in original if policy.basename(row[0]) not in policy.EXCLUDED]
    assert {row['destination'] for row in ledger['retained_msvc_inputs']} == policy.REQUIRED_RETAINED | {'msvcp140-wheelhash.dll'}
    for row in ledger['omitted'] + ledger['retained_msvc_inputs']:
        raw = Path(row['source']).read_bytes()
        assert row['sha256'] == hashlib.sha256(raw).hexdigest() and row['size'] == len(raw)
    assert {'api-ms-win-crt-new-l1-1-0.dll', 'ucrtbase.dll.extra', 'python311.dll', 'torch_cpu.dll', 'c10.dll'} <= {row[0] for row in survivors}


def test_case_insensitive_exact_set_accepts_original_spelling(tmp_path):
    value = rows(tmp_path)
    value = [(name.upper(), source, kind) if name in policy.EXCLUDED else (name, source, kind)
             for name, source, kind in value]
    survivors, omitted, _ = policy.partition(value)
    assert len(omitted) == 44 and all(row[0] not in policy.EXCLUDED for row in survivors)


@pytest.mark.parametrize('change', ['nested', 'backslash', 'data', 'extension', 'symlink', 'source_alias',
    'destination_alias', 'collision', 'slash_collision', 'missing', 'missing_msvc'])
def test_unsafe_omission_and_collisions_fail_closed(tmp_path, change):
    value = rows(tmp_path)
    index = next(i for i, row in enumerate(value) if row[0] == 'ucrtbase.dll')
    name, source, kind = value[index]
    if change == 'nested': value[index] = ('nested/' + name, source, kind)
    elif change == 'backslash': value[index] = ('nested\\' + name, source, kind)
    elif change in {'data', 'extension', 'symlink'}: value[index] = (name, source, change.upper())
    elif change == 'source_alias': value[index] = (name, source + '.extra', kind)
    elif change == 'destination_alias': value[index] = (name + '.extra', source, kind)
    elif change == 'collision': value.append((name.upper(), source, kind))
    elif change == 'slash_collision': value.extend([('a/b.dll', source + '.extra', kind), ('a\\B.dll', source + '.extra', kind)])
    elif change == 'missing': value.pop(index)
    else: value = [row for row in value if row[0] != 'msvcp140.dll']
    with pytest.raises(ValueError): policy.partition(value)


@pytest.mark.parametrize('stage', ['Analysis.datas', 'Analysis.dependencies', 'PYZ.dependencies',
    'PKG.input', 'PKG.dependencies', 'EXE.input', 'EXE.dependencies', 'COLLECT.input'])
@pytest.mark.parametrize('kind', ['BINARY', 'DATA', 'SYMLINK', 'DEPENDENCY'])
def test_every_late_toc_route_rejects_reentry_by_source_or_destination(stage, kind):
    for row in [('nested/UCRTBASE.DLL', '/input/ucrtbase.dll', kind),
                ('innocent.dll', '/input/API-MS-WIN-CORE-FILE-L1-1-0.DLL', kind)]:
        with pytest.raises(ValueError): policy.reject_toc({stage: [row]})


@pytest.mark.parametrize('field', ['path', 'original_path', 'source_path', 'aliases'])
def test_disk_and_normalized_records_reject_nested_names_and_aliases(field):
    row = {'path': 'other.dll', 'original_path': 'other.dll', 'source_path': '/safe/other.dll', 'aliases': []}
    row[field] = ['safe -> nested/UCRTBASE.DLL'] if field == 'aliases' else 'nested/UCRTBASE.DLL'
    with pytest.raises(ValueError): policy.reject_packaged(records=[row])


@pytest.mark.parametrize('row', [
    {'name': 'nested/UCRTBASE.DLL', 'typecode': 'b'},
    {'name': 'nested/API-MS-WIN-CRT-HEAP-L1-1-0.DLL', 'typecode': 'x'},
    {'name': 'other-package:ucrtbase.dll', 'typecode': 'd'},
    {'name': 'alias.dll', 'typecode': 'n', 'link_target': 'nested/ucrtbase.dll'},
])
def test_embedded_archive_rejects_names_dependencies_and_alias_targets(row):
    with pytest.raises(ValueError): policy.reject_packaged(embedded={'carchive_members': [row]})


def test_final_zip_is_checked_independently_of_records(tmp_path):
    archive = tmp_path / 'final.zip'
    with zipfile.ZipFile(archive, 'w') as value:
        value.writestr('_internal/hidden/UCRTBASE.DLL', b'synthetic')
    with pytest.raises(ValueError): policy.reject_packaged(records=[], archive=archive)


def test_retained_runtime_bytes_must_match_survivors_and_outputs(tmp_path):
    _, survivors, ledger = filter_rows(tmp_path)
    toc = {'Analysis.binaries': freeze_spec.capture(survivors)}
    records = [{'path': '_internal/' + row['destination'], 'sha256': row['sha256'],
                'size': row['size'], 'aliases': []} for row in ledger['retained_msvc_inputs']]
    assert policy.verify_retained(ledger, toc, records)['retained_output_bytes_matched'] is True
    for change in ('input_source', 'input_sha', 'missing_output', 'output_sha', 'output_size', 'alias', 'duplicate'):
        modified_toc, modified = copy.deepcopy(toc), copy.deepcopy(records)
        if change.startswith('input'):
            item = next(row for row in modified_toc['Analysis.binaries'] if row['destination'] == 'msvcp140.dll')
            item['source' if change == 'input_source' else 'sha256'] += 'changed'
        elif change == 'missing_output': modified.pop()
        elif change == 'output_sha': modified[0]['sha256'] = '0' * 64
        elif change == 'output_size': modified[0]['size'] += 1
        elif change == 'alias': modified[0]['aliases'] = ['unexpected alias']
        else: modified.append(modified[0])
        with pytest.raises(ValueError): policy.verify_retained(ledger, modified_toc, modified)


@pytest.mark.parametrize('change', ['pre10', 'arm64', '32bit', 'wrong_system', 'bad_version'])
def test_saved_host_guard_is_narrow_and_replayable(change):
    value = copy.deepcopy(HOST)
    if change == 'pre10': value['kernel_version'][0] = 6
    elif change == 'arm64': value['architecture'] = 'win-arm64'
    elif change == '32bit': value['pointer_bits'] = 32
    elif change == 'wrong_system': value['system'] = 'Linux'
    else: value['kernel_version'][0] = True
    with pytest.raises(ValueError): policy.validate_host(value)


def test_live_host_and_freezer_version_are_guarded_without_installs():
    with patch.object(policy.sys, 'platform', 'linux'):
        with pytest.raises(ValueError): policy.host_identity(freezer=True)
    with patch.object(policy.sys, 'platform', 'win32'), patch.object(policy.importlib.metadata, 'version', return_value='6.15.0'):
        with pytest.raises(ValueError): policy.host_identity(freezer=True)
    with patch.object(policy.sys, 'platform', 'win32'), \
         patch.object(policy.importlib.metadata, 'version', return_value='6.16.0'), \
         patch.object(policy.sys, 'getwindowsversion', return_value=SimpleNamespace(platform_version=(10, 0, 26100)), create=True), \
         patch.object(policy.sysconfig, 'get_platform', return_value='win-amd64'), \
         patch.object(policy.struct, 'calcsize', return_value=8):
        assert policy.host_identity(freezer=True) == HOST


def windows_origins():
    value = saved_origins('Windows')
    value.update(schema=origin.WINDOWS_OS_SCHEMA, windows_os_dll_policy=policy.POLICY, windows_host=copy.deepcopy(HOST))
    for snapshot in value['snapshots']:
        snapshot['native']['python_copy_proof'] = None
        snapshot['native']['bundled'].append('_internal/msvcp140.dll')
        snapshot['native']['system'].append('System32/ucrtbase.dll')
    return value


def test_new_saved_policy_requires_both_phases_without_touching_filesystem():
    value = windows_origins()
    with patch.object(origin.Path, 'resolve', side_effect=AssertionError('No runner path replay')):
        assert origin.validate_origins(value, windows_os_dll_policy=True) is value
    for snapshot in value['snapshots']:
        assert len(snapshot['native']['system']) == 2  # No demand to load 43 API-set contracts.


@pytest.mark.parametrize('phase', [0, 1])
@pytest.mark.parametrize('change', ['missing_ucrt', 'wrong_ucrt_root', 'bundled_ucrt', 'bundled_api', 'missing_msvc',
    'wrong_msvc_path', 'missing_python', 'missing_torch', 'missing_c10', 'wrong_basis', 'external'])
def test_new_saved_origin_negative_controls(phase, change):
    value = windows_origins()
    native = value['snapshots'][phase]['native']
    if change == 'missing_ucrt': native['system'].pop()
    elif change == 'wrong_ucrt_root': native['system'][-1] = 'Other/ucrtbase.dll'
    elif change == 'bundled_ucrt': native['bundled'].append('_internal/hidden/UCRTBASE.DLL')
    elif change == 'bundled_api': native['bundled'].append('_internal/API-MS-WIN-CRT-STDIO-L1-1-0.DLL')
    elif change == 'missing_msvc': native['bundled'].remove('_internal/msvcp140.dll')
    elif change == 'wrong_msvc_path': native['bundled'][-1] = '_internal/renamed/msvcp140.dll'
    elif change.startswith('missing_'): native['bundled'].remove(native['required'][change.removeprefix('missing_').replace('torch', 'torch_cpu')])
    elif change == 'wrong_basis': native['system_path_basis'] = 'absolute_windows'
    else: native['system'].append('C:/external/bad.dll')
    with pytest.raises(ValueError): origin.validate_origins(value, windows_os_dll_policy=True)


def test_legacy_and_posix_origins_unchanged_but_cannot_downgrade_new_policy():
    for system in ('Windows', 'Linux', 'Darwin'):
        legacy = saved_origins(system)
        assert origin.validate_origins(legacy) is legacy
        with pytest.raises(ValueError): origin.validate_origins(legacy, windows_os_dll_policy=True)
    legacy = saved_origins('Windows')
    legacy['snapshots'][0]['native']['bundled'].append('_internal/ucrtbase.dll')
    assert origin.validate_origins(legacy) is legacy  # Historical observation stays historical.
    for change in ('policy', 'host', 'platform'):
        value = windows_origins()
        if change == 'policy': value['windows_os_dll_policy'] = 'invented'
        elif change == 'host': value['windows_host']['kernel_version'][0] = 6
        else: value['platform'] = 'Linux'
        with pytest.raises(ValueError): origin.validate_origins(value)


@pytest.mark.parametrize('bad_stage', [None, 'Analysis.datas', 'PYZ.dependencies', 'EXE.dependencies', 'COLLECT.input'])
def test_generated_spec_filter_order_and_separate_ledger(tmp_path, bad_stage):
    source, generated = tmp_path / 'source', tmp_path / 'generated'
    source.mkdir(); generated.mkdir()
    spec, evidence = tmp_path / 'runtime.spec', tmp_path / 'toc.json'
    value = rows(source)
    bad = ('nested/ucrtbase.dll', str(source / 'ucrtbase.dll'), 'DATA')
    calls = []
    def analysis(*args, **kwargs):
        calls.append('analysis')
        return SimpleNamespace(binaries=value, datas=[bad] if bad_stage == 'Analysis.datas' else [],
                               scripts=[], pure=[], dependencies=[])
    def pyz(pure):
        calls.append('pyz')
        assert len(value) - len(namespace['a'].binaries) == 44
        return SimpleNamespace(dependencies=[bad] if bad_stage == 'PYZ.dependencies' else [])
    def exe(*args, **kwargs):
        calls.append('exe')
        return SimpleNamespace(toc=[], dependencies=[bad] if bad_stage == 'EXE.dependencies' else [],
                               pkg=SimpleNamespace(toc=[], dependencies=[]))
    def collect(executable, binaries, datas, **kwargs):
        calls.append('collect')
        return SimpleNamespace(toc=[*binaries, *datas, *([bad] if bad_stage == 'COLLECT.input' else [])])
    freeze_spec.write_spec(spec, source=source, project=Path(__file__).resolve().parents[1], generated=generated,
                           evidence=evidence, package_name='kuma-merizo', windows_os_dll_policy=True)
    # Execute only our generated spec with inert test stage objects, not PyInstaller.
    namespace = {'Analysis': analysis, 'PYZ': pyz, 'EXE': exe, 'COLLECT': collect}
    with patch.dict('sys.modules', {'PyInstaller.utils.hooks': SimpleNamespace(copy_metadata=lambda _: [])}), \
         patch.object(policy, 'host_identity', return_value=copy.deepcopy(HOST)):
        if bad_stage is not None:
            with pytest.raises(ValueError): exec(compile(spec.read_text(), str(spec), 'exec'), namespace)
            assert not evidence.exists()
        else:
            exec(compile(spec.read_text(), str(spec), 'exec'), namespace)
            toc = strict_json(evidence.read_bytes())
            assert not any('omitted' in key.lower() for key in toc)
            ledger = strict_json(evidence.with_name('windows-os-dll-omitted.json').read_bytes())
            assert len(ledger['omitted']) == 44
            policy.verify_retained(ledger, toc)
            policy.reject_packaged(toc=toc)
            assert calls == ['analysis', 'pyz', 'exe', 'collect']


def test_default_spec_has_no_exclusion_code_or_policy(tmp_path):
    spec = tmp_path / 'default.spec'
    freeze_spec.write_spec(spec, source=tmp_path, project=tmp_path, generated=tmp_path,
                           evidence=tmp_path / 'toc.json', package_name='kuma-merizo')
    assert 'windows_os_dll' not in spec.read_text() and 'omitted' not in spec.read_text()


@pytest.mark.parametrize('failure', [None, 'missing_ucrt', 'bundled_ucrt', 'missing_msvc', 'external'])
def test_live_new_policy_uses_existing_system_root_and_loaded_module_snapshot(tmp_path, monkeypatch, failure):
    from kuma_core.kuro.domain_process import _environment
    root, windows, work = tmp_path / 'installed', tmp_path / 'Windows', tmp_path / 'work'
    internal = root / '_internal'
    internal.mkdir(parents=True)
    (windows / 'System32').mkdir(parents=True)
    work.mkdir()
    executable = root / 'kuma-merizo.exe'
    executable.write_bytes(b'synthetic executable')
    names = ['python311.dll', 'torch_cpu.dll', 'c10.dll', 'msvcp140.dll']
    if failure == 'missing_msvc': names.remove('msvcp140.dll')
    if failure == 'bundled_ucrt': names.append('ucrtbase.dll')
    native = [internal / name for name in names]
    if failure != 'missing_ucrt': native.append(windows / 'System32/ucrtbase.dll')
    if failure == 'external': native.append(tmp_path / 'ucrtbase.dll')
    for path in native:
        path.write_bytes(b'synthetic library')
    private = work / 'domain-private-test'
    private.mkdir()
    env = _environment(private)
    env['SystemRoot'] = str(windows)
    modules = {name: str(internal / (name.replace('.', '/') + '.py'))
               for name in ('torch', 'predict', 'model.network', 'model.utils.features')}
    monkeypatch.setattr(origin.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(origin.sys, 'executable', str(executable))
    monkeypatch.setattr(origin.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(origin.Path, 'cwd', lambda: work)
    monkeypatch.setattr(origin.os, 'environ', env)
    monkeypatch.setattr(policy, 'host_identity', lambda: copy.deepcopy(HOST))
    monkeypatch.setattr(origin.shared, 'module_origins', lambda *args, **kwargs: modules)
    with patch.object(origin.shared, 'windows_loaded_native_paths', return_value=[str(x) for x in native]) as enumeration:
        audit = origin.OriginAudit(internal, '1' * 64, windows_os_dll_policy=policy.POLICY)
        if failure is not None:
            with pytest.raises(ValueError): audit.capture('before_weights', prepared_synthetic())
            assert enumeration.call_count == 1
            return
        audit.capture('before_weights', prepared_synthetic())
        audit.capture('after_inference', prepared_synthetic())
        audit.finish(work / 'origins.json')
        assert enumeration.call_count == 2
        value = origin.read_origins(work / 'origins.json', windows_os_dll_policy=True)
        assert value['windows_host'] == HOST
        assert all(row['native']['system'] == ['System32/ucrtbase.dll'] for row in value['snapshots'])


def test_execution_export_requires_explicit_policy_when_requested(tmp_path):
    from scripts.merizo_runtime_archive import execution_evidence as evidence, public_fixture
    from tests.test_merizo_runtime_archive_execution_evidence import IDENTITIES, original_result_bytes
    fixture = Path(__file__).resolve().parent / 'data/domain_annotation/1ubq.pdb'
    prepared = public_fixture.public_prepared(fixture)
    _, _, recipe = public_fixture.create_af3_fixture(fixture, tmp_path / 'synthetic.zip')
    from scripts.merizo_runtime_archive.common import canonical
    value = windows_origins()
    value.update(executable_sha256=IDENTITIES['executable_sha256'], source_identity_sha256=IDENTITIES['source_identity_sha256'],
                 input_binding_sha256=prepared.binding_sha256)
    result, origins = tmp_path / 'result.json', tmp_path / 'origins.json'
    result.write_bytes(original_result_bytes(prepared))
    origins.write_bytes(canonical(value))
    metadata = evidence.export_execution(tmp_path, result, origins, fixture=fixture, prepared=prepared,
        fixture_id='public_1ubq', recipe=recipe, **IDENTITIES, windows_os_dll_policy=True)
    output = tmp_path / metadata['filename']
    assert evidence.replay_execution(output, fixture, **IDENTITIES, windows_os_dll_policy=True).total_residues == 76
    exported = strict_json(output.read_bytes())
    exported['origins']['schema'] = origin.SCHEMA
    del exported['origins']['windows_host'], exported['origins']['windows_os_dll_policy']
    output.write_bytes(canonical(exported))
    with pytest.raises(ValueError): evidence.replay_execution(output, fixture, **IDENTITIES, windows_os_dll_policy=True)


@pytest.mark.parametrize('change', ['missing_hash', 'bad_hash', 'bad_size', 'extra_field', 'missing_omitted', 'scope'])
def test_omitted_ledger_is_bounded_and_strict(tmp_path, change):
    _, survivors, ledger = filter_rows(tmp_path)
    toc = {'Analysis.binaries': freeze_spec.capture(survivors)}
    if change == 'missing_hash': del ledger['omitted'][0]['sha256']
    elif change == 'bad_hash': ledger['omitted'][0]['sha256'] = 'not a digest'
    elif change == 'bad_size': ledger['omitted'][0]['size'] = True
    elif change == 'extra_field': ledger['omitted'][0]['license_cleared'] = True
    elif change == 'missing_omitted': ledger['omitted'].pop()
    else: ledger['scope'] = 'packaged_input'
    with pytest.raises(ValueError): policy.verify_retained(ledger, toc)


def test_omission_never_follows_input_link(tmp_path):
    value = rows(tmp_path)
    source = tmp_path / 'ucrtbase.dll'
    source.unlink()
    target = tmp_path / 'renamed.dll'
    target.write_bytes(b'synthetic bytes')
    try:
        source.symlink_to(target)
    except OSError:
        pytest.skip('Symbolic links unavailable')
    with patch.object(policy, 'host_identity', return_value=copy.deepcopy(HOST)):
        with pytest.raises(ValueError): policy.filter_analysis(value)


def test_omission_rejects_relative_source_and_unbounded_rows(tmp_path):
    value = rows(tmp_path)
    index = next(i for i, row in enumerate(value) if row[0] == 'ucrtbase.dll')
    value[index] = ('ucrtbase.dll', 'ucrtbase.dll', 'BINARY')
    with pytest.raises(ValueError): policy.partition(value)
    with patch.object(policy, 'MAX_ROWS', 1):
        with pytest.raises(ValueError): policy.partition(value)
        with pytest.raises(ValueError): policy.reject_toc({'EXE.dependencies': value})


@pytest.mark.parametrize('kind,name,blob', [('d', 'other:ucrtbase.dll', b''),
    ('n', 'alias.dll', b'nested/UCRTBASE.DLL\0')])
def test_actual_carchive_reader_inventory_keeps_dependency_and_link_evidence(tmp_path, kind, name, blob):
    from scripts.merizo_runtime_archive import build
    executable = tmp_path / 'kuma-merizo.exe'
    executable.write_bytes(b'synthetic executable')
    code = compile('pass', 'synthetic.py', 'exec')
    pyz = SimpleNamespace(toc={'synthetic': ()}, extract=lambda _: code)
    reader = SimpleNamespace(toc={'PYZ.pyz': (0, 0, 0, 'z'), name: (0, 0, 0, kind)},
                             open_embedded_archive=lambda _: pyz,
                             extract=lambda entry: b'pyz' if entry == 'PYZ.pyz' else blob)
    with patch.dict('sys.modules', {'PyInstaller.archive.readers': SimpleNamespace(CArchiveReader=lambda _: reader)}), \
         patch.object(build.importlib.metadata, 'distribution', return_value=SimpleNamespace(files=[])):
        embedded = build.embedded_inventory(executable)
    assert len(embedded['carchive_members']) == 2
    with pytest.raises(ValueError): policy.reject_packaged(embedded=embedded)
