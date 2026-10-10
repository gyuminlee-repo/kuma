"""Synthetic origin-adapter contracts; hosted binaries provide actual evidence."""
from __future__ import annotations

import copy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from kuma_core.kuro.domain_process import _environment
from scripts.merizo_runtime_archive import runtime_origin as origin, runtime_entry as entry
from scripts.merizo_runtime_archive.common import canonical, write_json
from tests.test_domain_merizo import prepared_synthetic


def test_fresh_snapshots_bind_this_executable_and_normalize_private_paths(tmp_path):
    root = tmp_path / 'installed'
    internal = root / '_internal'
    internal.mkdir(parents=True)
    executable = root / 'kuma-merizo'
    executable.write_bytes(b'synthetic executable')
    native = [internal / name for name in ('libpython3.11.so', 'libtorch_cpu.so', 'libc10.so')]
    for path in native:
        path.write_bytes(b'library')
    modules = {name: str(internal / (name.replace('.', '/') + '.py'))
               for name in ('torch', 'predict', 'model.network', 'model.utils.features')}
    work = tmp_path / 'work'
    work.mkdir()
    private = work / 'domain-private-test'
    private.mkdir()
    env = _environment(private)
    prepared = prepared_synthetic()
    with patch.object(origin.sys, 'frozen', True, create=True), patch.object(origin.sys, 'executable', str(executable)), \
         patch.object(origin.platform, 'system', return_value='Linux'), patch.object(origin.Path, 'cwd', return_value=work), \
         patch.dict(origin.os.environ, env, clear=True), patch.object(origin.shared, 'module_origins', return_value=modules) as module_check, \
         patch.object(origin.shared, 'linux_native_paths', return_value=[str(x) for x in native]) as enumerate_native:
        audit = origin.OriginAudit(internal, '1' * 64)
        with pytest.raises(ValueError):
            audit.capture('after_inference', prepared)
        audit.capture('before_weights', prepared)
        with pytest.raises(ValueError):
            audit.finish()
        audit.capture('after_inference', prepared)
        report = work / 'origins.json'
        audit.finish(report)
        assert enumerate_native.call_count == 2
        assert module_check.call_args.kwargs == {'check_namespace_paths': True}
        parsed = origin.read_origins(report, executable_sha256=origin.digest(executable),
                                    binding_sha256=prepared.binding_sha256, source_identity_sha256='1' * 64)
        assert str(tmp_path) not in canonical(parsed).decode()
        with pytest.raises(ValueError):
            audit.finish(report)
        with pytest.raises(ValueError):
            audit.capture('after_inference', prepared)
        executable.write_bytes(b'changed')
        with pytest.raises(ValueError):
            audit.finish()


@pytest.mark.parametrize('change', ['path', 'home', 'python', 'loader', 'gpu', 'thread', 'cache'])
def test_clean_environment_rejects_external_or_inherited_settings(tmp_path, change):
    work = tmp_path / 'work'
    work.mkdir()
    private = work / 'domain-private-test'
    private.mkdir()
    env = _environment(private)
    changes = {'path': ('PATH', '/external/bin'), 'home': ('HOME', '/private/person'),
               'python': ('PYTHONPATH', '/external/site-packages'), 'loader': ('LD_LIBRARY_PATH', '/external/lib'),
               'gpu': ('CUDA_VISIBLE_DEVICES', '0'), 'thread': ('OMP_NUM_THREADS', '2'),
               'cache': ('MPLCONFIGDIR', str(tmp_path))}
    env.update([changes[change]])
    with patch.object(origin.Path, 'cwd', return_value=work), patch.dict(origin.os.environ, env, clear=True):
        with pytest.raises(ValueError):
            origin.environment_checks(tmp_path, tmp_path / '_internal', tmp_path / 'kuma-merizo')


def test_bootstrap_paths_and_private_matplotlib_hook_are_allowed(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    private = work / 'domain-private-test'
    private.mkdir()
    env = _environment(private)
    cache = private / 'tmp' / 'matplotlib-hook'
    cache.mkdir()
    internal, executable = tmp_path / '_internal', tmp_path / 'kuma-merizo'
    env.update(MPLCONFIGDIR=str(cache), LD_LIBRARY_PATH=str(internal), LD_LIBRARY_PATH_ORIG='',
               _PYI_APPLICATION_HOME_DIR=str(internal), _PYI_ARCHIVE_FILE=str(executable))
    with patch.object(origin.Path, 'cwd', return_value=work), patch.dict(origin.os.environ, env, clear=True):
        assert all(origin.environment_checks(tmp_path, internal, executable).values())


def test_origin_failure_prevents_atomic_scientific_result(tmp_path):
    prepared = prepared_synthetic()
    pdb, manifest, output = tmp_path / 'input.pdb', tmp_path / 'input.json', tmp_path / 'result.json'
    pdb.write_bytes(prepared.normalized_pdb.encode('ascii'))
    write_json(manifest, entry.domain_input_manifest(prepared))
    from tests.test_domain_merizo import envelope
    audit = SimpleNamespace(finish=lambda _: (_ for _ in ()).throw(ValueError('origin rejected')))
    with patch.object(entry, 'verify_payload', return_value=(tmp_path, tmp_path, {})), \
         patch.object(entry, 'infer', return_value=envelope(prepared)):
        with pytest.raises(ValueError):
            entry.execute(pdb, manifest, output, tmp_path, '0' * 64, origin_audit=audit)
    assert not output.exists()


@pytest.mark.parametrize('failure_phase', [None, 'before_weights', 'after_inference'])
def test_origin_hooks_bracket_weights_and_inference_without_loading_model(tmp_path, failure_phase):
    prepared, events = prepared_synthetic(), []
    from kuma_core.kuro.domain_merizo import expected_ca_coordinates
    features = {'nres': len(prepared.sequence), 'sequence': prepared.sequence,
                'residue_numbers': list(range(1, len(prepared.sequence) + 1)),
                'ca_coordinates': [list(x) for x in expected_ca_coordinates(prepared)]}
    class Tensor:
        def flatten(self): return self
        def tolist(self): return [1] * len(prepared.sequence)
        def numel(self): return len(prepared.sequence)
        def all(self): return True
        def any(self): return False
        def __lt__(self, _): return self
        def __gt__(self, _): return self
    class Network:
        def __init__(self): events.append('network')
        def to(self, _): return self
        def load_state_dict(self, _, strict): assert strict; events.append('weights')
        def eval(self): events.append('eval')
    class Audit:
        def capture(self, phase, _):
            events.append(phase)
            if phase == failure_phase: raise ValueError('synthetic origin refusal')
    torch = SimpleNamespace(__version__=entry.expected_cpu_torch(), version=SimpleNamespace(cuda=None),
        set_num_threads=lambda _: None, set_num_interop_threads=lambda _: None, manual_seed=lambda _: None,
        no_grad=nullcontext, isfinite=lambda _: Tensor())
    def segment(*args):
        events.append('segment')
        predict.generate_features_domain()
        return {'domain_ids': Tensor(), 'conf_res': Tensor(), 'ndom': 1, 'conf_global': .9}
    predict = SimpleNamespace(Merizo=Network, read_split_weight_files=lambda _: {},
                              generate_features_domain=lambda: {}, segment=segment)
    modules = {'torch': torch, 'predict': predict, 'model.utils.features': object()}
    with patch.object(entry.importlib, 'import_module', side_effect=lambda name: modules[name]), \
         patch.object(entry, 'validate_features', return_value=features):
        if failure_phase is None:
            assert entry.infer(prepared, tmp_path, tmp_path, origin_audit=Audit())['process']['status'] == 'ok'
        else:
            with pytest.raises(ValueError):
                entry.infer(prepared, tmp_path, tmp_path, origin_audit=Audit())
    assert events[0] == 'before_weights'
    if failure_phase == 'before_weights':
        assert events == ['before_weights']
    else:
        assert events == ['before_weights', 'network', 'weights', 'eval', 'segment', 'after_inference']


def test_stable_audit_reads_and_exclusive_publication_reject_aliases(tmp_path):
    path = tmp_path / 'evidence.json'
    origin.publish_exclusive(path, b'{}\n', 4)
    assert origin.read_stable(path, 4) == b'{}\n'
    with pytest.raises(ValueError): origin.publish_exclusive(path, b'{}', 4)
    with pytest.raises(ValueError): origin.read_stable(path, 2)
    linked = tmp_path / 'linked.json'
    try:
        linked.hardlink_to(path)
    except OSError:
        pytest.skip('Hardlinks unavailable')
    with pytest.raises(ValueError): origin.read_stable(linked, 4)


def saved_origins(system):
    from tests.test_merizo_runtime_archive_execution_evidence import mock_origins
    value = mock_origins(prepared_synthetic())
    value['platform'] = system
    for row in value['snapshots']:
        native = row['native']
        if system == 'Darwin':
            row.update(mechanism='dyld_stable_indexed_cache_snapshots', contract='darwin_dyld_shared_cache_v2')
            native['required'] = {role: path.replace('.so.1.0', '.dylib').replace('.so', '.dylib')
                                  for role, path in native['required'].items()}
            native['bundled'] = list(native['required'].values())
            native['system'] = ['/usr/lib/libSystem.B.dylib']
            row['images'] = [{'image_index': index, 'kind': kind, 'path': path, 'resolved_path': path,
                'header_address': 4096 + index * 8, 'magic': origin.shared.MH_MAGIC_64,
                'cputype': origin.shared.CPU_TYPE_ARM64, 'cpusubtype': 2, 'filetype': origin.shared.MH_DYLIB,
                'flags': origin.shared.MH_DYLIB_IN_CACHE if kind == 'system' else 0,
                'shared_cache_member': kind == 'system'}
                for index, (kind, path) in enumerate([('bundled', path) for path in native['bundled']]
                                                     + [('system', path) for path in native['system']])]
        elif system == 'Windows':
            row.update(mechanism='enum_process_modules_ex', contract='windows_loaded_origins_v1')
            native['system_path_basis'] = 'windows_directory_relative'
            native['required'] = {role: '_internal/' + name for role, name in
                                 {'python': 'python311.dll', 'torch_cpu': 'torch_cpu.dll', 'c10': 'c10.dll'}.items()}
            native['bundled'], native['system'] = list(native['required'].values()), ['System32/kernel32.dll']
    return value


@pytest.mark.parametrize('system', ['Linux', 'Darwin', 'Windows'])
def test_saved_policy_replay_never_dereferences_addresses_or_runner_files(system):
    value = saved_origins(system)
    with patch.object(origin.Path, 'resolve', side_effect=AssertionError('No runner filesystem replay')), \
         patch.object(origin.shared, 'darwin_native_images', side_effect=AssertionError('No enumeration')):
        assert origin.validate_origins(value) is value
    for change in ('environment_bool', 'module_scope', 'required_role', 'outside_system', 'external_core'):
        altered = copy.deepcopy(value)
        row = altered['snapshots'][0]
        if change == 'environment_bool': row['environment']['gpu_hidden'] = 1
        elif change == 'module_scope': row['modules']['private.secret'] = 'private.py'
        elif change == 'required_role': row['native']['required']['python'] = row['native']['required']['torch_cpu']
        elif change == 'outside_system': row['native']['system'] = ['C:/private/x.dll' if system == 'Windows' else '/private/libc.so.6']
        else: row['native']['system'] = ['System32/torch_cpu.dll' if system == 'Windows' else '/usr/lib/libtorch_cpu.so']
        with pytest.raises(ValueError): origin.validate_origins(altered)


@pytest.mark.parametrize('field,value', [('shared_cache_member', False), ('flags', 0), ('filetype', 8),
    ('flags', (1 << 63) | origin.shared.MH_DYLIB_IN_CACHE), ('flags', 1 << 32),
    ('filetype', (1 << 32) | origin.shared.MH_DYLIB), ('magic', (1 << 32) | origin.shared.MH_MAGIC_64),
    ('magic', 0), ('cputype', 0), ('cpusubtype', 3), ('header_address', 1), ('image_index', 99),
    ('path', '/private/libSystem.B.dylib'), ('resolved_path', '/private/libSystem.B.dylib')])
def test_darwin_saved_cache_header_and_raw_resolved_paths_are_independently_bound(field, value):
    report = saved_origins('Darwin')
    report['snapshots'][0]['images'][-1][field] = value
    with pytest.raises(ValueError): origin.validate_origins(report)


def test_darwin_saved_native_lists_must_match_indexed_snapshot():
    report = saved_origins('Darwin')
    report['snapshots'][0]['native']['system'].append('/usr/lib/libobjc.A.dylib')
    with pytest.raises(ValueError): origin.validate_origins(report)


def test_entry_and_origin_imports_do_not_load_host_parser_or_inference_packages():
    import subprocess
    import sys
    script = '''import importlib.abc
import sys
blocked = ('Bio', 'BioSQL', 'torch', 'model', 'predict', 'kuma_core.kuro.domain_jobs',
           'kuma_core.kuro.domain_af3', 'scripts.merizo_runtime_archive.public_fixture',
           'scripts.merizo_runtime_archive.execution_evidence')
class NoUnexpectedImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('Unexpected early or host-only import')
sys.meta_path.insert(0, NoUnexpectedImports())
import scripts.merizo_runtime_archive.runtime_entry
import scripts.merizo_runtime_archive.runtime_origin
assert not any(any(name == item or name.startswith(item + '.') for item in blocked) for name in sys.modules)
'''
    completed = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                               capture_output=True, text=True, check=False, timeout=30)
    assert completed.returncode == 0, completed.stderr
