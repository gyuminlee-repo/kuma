"""Real service/registry/decoder wiring with an explicitly fake inference runner."""
from __future__ import annotations

import copy
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from kuma_core.kuro.domain_jobs import DomainJobService
from kuma_core.kuro.domain_process import DomainProcessError
from kuma_core.kuro.optional_runtime import current_platform_key
from scripts.merizo_runtime_archive import archive, build, roundtrip, runtime_entry
from scripts.merizo_runtime_archive.common import canonical, digest
from scripts.merizo_runtime_archive.execution_evidence import FILENAMES, replay_execution
from tests.test_merizo_runtime_archive_execution_evidence import PUBLIC, mock_origins, mock_result


def package(tmp_path):
    package = tmp_path / 'package'
    package.mkdir()
    (package / 'entry').write_bytes(b'Not an executable; injected runner test only')
    artifact, _ = archive.normalize_archive(package, tmp_path / 'archive', version='service-test',
        platform=current_platform_key(), executable='entry')
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    return tmp_path / 'archive/runtime.zip', artifact, evidence


def fake_runner(calls, failure=None):
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        assert kwargs['operation_lease'] is not None
        prepared = runtime_entry.load_prepared(Path(argv[argv.index('--input-pdb') + 1]),
                                               Path(argv[argv.index('--input-manifest') + 1]))
        if len(calls) == 2 and failure == 'process':
            raise DomainProcessError('Synthetic child failure')
        result = mock_result(prepared)
        if len(calls) == 2 and failure == 'decode':
            result['prediction']['labels'] = [0] * 76
        Path(kwargs['result_path']).write_bytes(canonical(result) + b'\n')
        if len(calls) == 2 and failure == 'missing_origins':
            return
        origins = mock_origins(prepared)
        origins['executable_sha256'] = digest(Path(argv[0]))
        origins['source_identity_sha256'] = 'c' * 64
        Path(argv[argv.index('--audit-origin-report') + 1]).write_bytes(canonical(origins) + b'\n')
    return run


def run_roundtrip(tmp_path, runner, report):
    path, artifact, evidence = package(tmp_path)
    roundtrip.service_roundtrip(path, artifact, PUBLIC, evidence_directory=evidence,
        source_identity_sha256='c' * 64, build_revision='d' * 40, runner=runner, report=report)
    return artifact, evidence


def test_actual_service_install_start_poll_import_remove_and_exactly_two_calls(tmp_path):
    calls, report = [], {}
    artifact, evidence = run_roundtrip(tmp_path, fake_runner(calls), report)
    assert report['status'] == 'passed'
    assert report['installed'] and report['verified'] and report['removed'] and report['temporary_storage_removed']
    assert report['service_terminal_state'] == 'succeeded' and report['service_shutdown_confirmed']
    assert report['service_import']['provenance'] == 'managed'
    assert report['invocation_count'] == len(calls) == 2
    # Main audit retains compact links, never duplicate raw origins/results.
    serialized = canonical(report)
    assert len(serialized) < 32 * 1024
    assert b'"result_text"' not in serialized and b'"snapshots"' not in serialized
    assert calls[0][1]['operation_lease'] is not calls[1][1]['operation_lease']
    assert 'on_stopping' in calls[1][1] and callable(calls[1][1]['cancelled'])
    assert calls[1][1]['timeout_seconds'] == 300
    assert calls[1][1]['result_limit'] == 8 * 1024 * 1024
    assert calls[1][1]['output_limit'] == 1024 * 1024
    for row in report['runs']:
        assert row['decoded'] and row['process_succeeded']
        replayed = replay_execution(evidence / FILENAMES[row['fixture']], PUBLIC,
            archive_sha256=artifact.archive_sha256, executable_sha256=row['executable_sha256'],
            source_identity_sha256='c' * 64, build_revision='d' * 40)
        assert replayed.total_residues == 76
        assert not Path(calls[report['runs'].index(row)][1]['cwd']).exists()


@pytest.mark.parametrize('failure', ['process', 'decode', 'missing_origins'])
def test_failed_second_job_preserves_first_evidence_and_original_error(tmp_path, failure):
    calls, report = [], {}
    with pytest.raises(Exception) as captured:
        run_roundtrip(tmp_path, fake_runner(calls, failure), report)
    assert report['status'] == 'failed' and report['invocation_count'] == 2
    assert report['removed'] and report['temporary_storage_removed']
    assert report['runs'][0]['execution_evidence']['filename'] == FILENAMES['public_1ubq']
    assert (tmp_path / 'evidence' / FILENAMES['public_1ubq']).is_file()
    assert not (tmp_path / 'evidence' / FILENAMES['synthetic_af3_public_geometry']).exists()
    assert report['runs'][1]['entry_diagnostic']['status'] == 'missing'
    if failure == 'process':
        assert isinstance(captured.value, DomainProcessError)
        assert report['runs'][1]['origin_diagnostic'] == 'missing'


def test_failed_normal_registry_remove_is_not_replaced_by_outer_cleanup_success(tmp_path):
    calls, report, roots = [], {}, []
    original = roundtrip.tempfile.mkdtemp
    def track(*args, **kwargs):
        path = original(*args, **kwargs)
        if kwargs.get('prefix') == 'kuma-runtime-roundtrip-': roots.append(Path(path).resolve(strict=True))
        return path
    try:
        with patch.object(roundtrip.tempfile, 'mkdtemp', side_effect=track), \
             patch.object(DomainJobService, 'remove', side_effect=PermissionError('synthetic remove')):
            with pytest.raises(PermissionError):
                run_roundtrip(tmp_path, fake_runner(calls), report)
        assert report['service_terminal_state'] == 'succeeded'
        assert not report['removed'] and not report['temporary_storage_removed']
        assert report['cleanup_errors'][0]['stage'] == 'remove'
        assert roots[0].exists()
    finally:
        for root in roots:
            shutil.rmtree(root)


def test_biopython_exclusion_checks_actual_toc_owners_modules_and_archive():
    provenance = {'installed_files': [{'owner': 'biopython', 'path': '/venv/unknown_native.so'}]}
    empty = {'Analysis.pure': []}
    assert build.assert_biopython_excluded(empty, provenance, embedded={'pyz_modules': []}, records=[]) == {
        'analysis_toc': True, 'actual_pyz': True, 'normalized_archive': True}
    cases = [({'Analysis.pure': [{'destination': 'Bio.PDB', 'source': '/x'}]}, None, None),
             ({'COLLECT.input': [{'destination': 'x', 'source': '/venv/unknown_native.so'}]}, None, None),
             (empty, {'pyz_modules': [{'module': 'BioSQL.BioSeq'}]}, None),
             (empty, None, [{'path': '_internal/Bio/cpairwise2.pyd'}]),
             (empty, None, [{'path': '_internal/biopython-1.84.dist-info/METADATA'}])]
    for toc, embedded, records in cases:
        with pytest.raises(ValueError): build.assert_biopython_excluded(toc, provenance, embedded=embedded, records=records)


def test_windows_toc_separator_mapping_is_exact_and_collision_checked():
    record = {'path': '_internal/torch/lib/c10.dll', 'original_path': '_internal/torch/lib/c10.dll',
              'aliases': [], 'sha256': '1' * 64, 'size': 12, 'executable': False}
    candidate = {'destination': r'torch\lib\c10.dll', 'source': '/verified/wheel/c10.dll',
                 'sha256': '1' * 64, 'size': 12, 'typecode': 'BINARY'}
    toc = {'Analysis.binaries': [candidate], 'COLLECT.input': [dict(candidate)]}
    edges, gaps = build.output_edges([record], toc, 'entry')
    assert not gaps and edges[0]['mapping'] == 'exact_build_input'
    assert edges[0]['inputs'][0]['destination'] == candidate['destination']
    for key, value in [('sha256', '2' * 64), ('size', 13)]:
        edges, gaps = build.output_edges([record], {'Analysis.binaries': [{**candidate, key: value}]}, 'entry')
        assert gaps and edges[0]['mapping'] == 'transformed_or_unmapped'
    for name in ['C:\\private\\x', '\\\\server\\share\\x', '/absolute/x', './x', 'a/../x', 'a//x', 'a/']:
        with pytest.raises(ValueError): build.output_edges([record], {'Analysis.binaries': [{**candidate, 'destination': name}]}, 'entry')
    with pytest.raises(ValueError):
        build.output_edges([record], {'Analysis.binaries': [candidate, {**candidate, 'destination': 'torch/lib/c10.dll'}]}, 'entry')
    edges, gaps = build.output_edges([record], {'Analysis.binaries': [{**candidate, 'destination': 'Torch/lib/c10.dll'}]}, 'entry')
    assert gaps  # No case folding.


@pytest.mark.parametrize('key,value', [('sha256', '2' * 64), ('size', 13)])
def test_conflicting_same_spelling_toc_candidate_is_preserved_unresolved(key, value):
    record = {'path': '_internal/torch/lib/c10.dll', 'original_path': '_internal/torch/lib/c10.dll',
              'aliases': [], 'sha256': '1' * 64, 'size': 12, 'executable': False}
    first = {'destination': r'torch\lib\c10.dll', 'source': '/first/c10.dll', 'sha256': '1' * 64, 'size': 12}
    second = {**first, 'source': '/second/c10.dll', key: value}
    edges, gaps = build.output_edges([record], {'Analysis.binaries': [first], 'COLLECT.input': [second]}, 'entry')
    assert gaps and edges[0]['mapping'] == 'transformed_or_unmapped'
    assert edges[0]['inputs'] == [first, second]


@pytest.mark.parametrize('operation', ['install', 'verify', 'start', 'poll', 'import_result'])
def test_service_stage_failure_keeps_partial_report_and_cleanup(tmp_path, operation):
    calls, report = [], {}
    primary = ValueError('Synthetic stage failure')
    owner = roundtrip.OptionalRuntimeManager if operation == 'verify' else DomainJobService
    with patch.object(owner, operation, side_effect=primary):
        with pytest.raises(ValueError) as caught:
            run_roundtrip(tmp_path, fake_runner(calls), report)
    assert caught.value is primary
    assert report['status'] == 'failed' and report['temporary_storage_removed']
    expected = {'install': 'install', 'verify': 'verify', 'start': 'service_start',
                'poll': 'service_poll', 'import_result': 'service_import'}
    assert report['failure'] == {'stage': expected[operation], 'error_type': 'ValueError'}
    assert len(calls) <= 2
    if operation != 'install':
        assert report['removed']


@pytest.mark.parametrize('cleanup,aliased_root', [('stop_error', False), ('stop_false', False),
    ('remove', False), ('workspace', False), ('workspace', True)],
    ids=['stop_error', 'stop_false', 'remove', 'workspace', 'workspace_lexical_alias'])
def test_secondary_cleanup_failure_preserves_original_and_owned_storage(tmp_path, cleanup, aliased_root):
    calls, report, roots = [], {}, []
    original = roundtrip.tempfile.mkdtemp
    def track(*args, **kwargs):
        path = original(*args, **kwargs)
        if kwargs.get('prefix') == 'kuma-runtime-roundtrip-':
            if aliased_root:
                # Cross-platform stand-in for Windows short/long temp spellings.
                parent = Path(path) / 'alias-parent'
                parent.mkdir()
                path = str(parent / '..')
            roots.append(Path(path).resolve(strict=True))
            if aliased_root:
                assert Path(path) != roots[-1] and Path(path).resolve(strict=True) == roots[-1]
        return path
    primary = DomainProcessError('Original child failure')
    def runner(argv, **kwargs):
        if calls:
            calls.append((argv, kwargs))
            raise primary
        fake_runner(calls)(argv, **kwargs)
    owner, method = (roundtrip.shutil, 'rmtree') if cleanup == 'workspace' else (DomainJobService, 'remove' if cleanup == 'remove' else 'stop')
    injected: dict = {'return_value': False} if cleanup == 'stop_false' else {'side_effect': PermissionError('Secondary cleanup failure')}
    try:
        # Patching rmtree must target only the controller-owned outer root.
        real_rmtree = shutil.rmtree
        def targeted_rmtree(path, *args, **kwargs):
            if Path(path).resolve(strict=True) in roots:
                raise PermissionError('Secondary cleanup failure')
            return real_rmtree(path, *args, **kwargs)
        if cleanup == 'workspace': injected = {'side_effect': targeted_rmtree}
        with patch.object(roundtrip.tempfile, 'mkdtemp', side_effect=track), patch.object(owner, method, **injected):
            with pytest.raises(DomainProcessError) as caught:
                run_roundtrip(tmp_path, runner, report)
        assert caught.value is primary and report['status'] == 'failed'
        assert report['failure']['error_type'] == 'DomainProcessError'
        assert report['cleanup_errors'] and not report['temporary_storage_removed']
        assert report['runs'][0]['execution_evidence']
        assert roots[0].exists()
    finally:
        for root in roots:
            shutil.rmtree(root)
