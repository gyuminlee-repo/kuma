"""Offline CI orchestration contracts; never download or infer in unit tests."""
import ast
import json
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import os
import stat

import pytest

from scripts.merizo_runtime_archive import ci
from scripts.merizo_runtime_archive import roundtrip as trip
from tests.test_optional_runtime import setup_runtime


def test_remove_diagnostic_locates_real_rename_failure_without_paths(tmp_path, monkeypatch):
    manager, archive, artifact = setup_runtime(tmp_path)
    manager.install(archive)
    target = manager._target(artifact)

    def denied(source, destination):
        error = PermissionError(13, 'PRIVATE_REMOVE_MESSAGE', str(source))
        error.winerror = 32
        error.filename2 = str(destination)
        raise error

    with monkeypatch.context() as scoped:
        scoped.setattr(os, 'rename', denied)
        with pytest.raises(PermissionError) as caught:
            manager.remove()
        detail = trip.remove_failure_diagnostic(caught.value, tmp_path.resolve(), manager, artifact)
    assert detail['errno'] == 13 and detail['winerror'] == 32
    assert any(frame['call'] == 'manager.remove' for frame in detail['frames'])
    assert detail['target']['role'] == 'installed_target'
    assert detail['target']['directory'] is True
    assert detail['target2']['role'] == 'removal_stage_entry'
    assert detail['target2']['observation'] == 'missing'
    raw = json.dumps(detail)
    assert str(tmp_path) not in raw and 'PRIVATE_REMOVE_MESSAGE' not in raw
    assert len(raw) < 4096 and manager.verify().state == 'installed'
    assert manager.remove().state == 'missing'


def test_remove_diagnostic_locates_recursive_delete_and_observes_attributes(tmp_path, monkeypatch):
    manager, archive, artifact = setup_runtime(tmp_path)
    manager.install(archive)
    original_unlink = os.unlink

    def denied(path, *args, **kwargs):
        if Path(path).name == 'NOTICE.txt':
            stage = next(manager.root.glob(manager._stage_prefix(artifact) + '*'))
            raise PermissionError(13, 'PRIVATE_UNLINK_MESSAGE', str(stage / 'payload' / 'NOTICE.txt'))
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, 'unlink', denied)
        with pytest.raises(PermissionError) as caught:
            manager.remove()
        original_lstat = Path.lstat

        def attributes(path):
            info = original_lstat(path)
            if str(path) == caught.value.filename:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=1)
            return info

        scoped.setattr(Path, 'lstat', attributes)
        detail = trip.remove_failure_diagnostic(caught.value, tmp_path.resolve(), manager, artifact)
    calls = {frame['call'] for frame in detail['frames']}
    assert 'runtime._remove_tree' in calls and 'shutil.rmtree' in calls
    assert detail['target'] == {'role': 'removal_stage_entry', 'observation': 'observed',
                                'readonly': True, 'reparse': False, 'directory': False}
    assert detail['evidence'] == 'post_failure_observation_not_cause'
    assert 'PRIVATE_UNLINK_MESSAGE' not in json.dumps(detail)
    assert manager.cleanup_interrupted() == 1


@pytest.mark.parametrize('filename', ['outside', 'parent_escape', 'relative', 'bytes'])
def test_remove_diagnostic_never_stats_unrecognized_exception_paths(tmp_path, monkeypatch, filename):
    manager, _, artifact = setup_runtime(tmp_path)
    value = {'outside': str(tmp_path.parent / 'private-outside'),
             'parent_escape': str(tmp_path / '..' / 'private-outside'),
             'relative': 'private-relative', 'bytes': b'private-bytes'}[filename]
    error = PermissionError(13, 'PRIVATE', value)
    monkeypatch.setattr(Path, 'lstat', lambda *args: pytest.fail('Unrecognized path was inspected'))
    detail = trip.remove_failure_diagnostic(error, tmp_path, manager, artifact)
    assert detail['target']['role'] == 'unknown' and detail['target']['observation'] == 'unavailable'
    assert 'private-' not in json.dumps(detail)


def test_remove_diagnostic_stops_before_reparse_ancestor_and_does_not_guess_readonly(tmp_path, monkeypatch):
    manager, archive, artifact = setup_runtime(tmp_path)
    manager.install(archive)
    target = manager._target(artifact)
    member = target / 'bin' / 'merizo-cpu'
    original_lstat = Path.lstat
    seen = []

    def reparse(path):
        seen.append(path)
        assert path != member
        if path == member.parent:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        return original_lstat(path)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, 'lstat', reparse)
        detail = trip.remove_failure_diagnostic(PermissionError(13, 'PRIVATE', str(member)),
                                                tmp_path.resolve(), manager, artifact)
    assert member.parent in seen
    assert detail['target']['observation'] == 'unsafe_ancestor'
    assert detail['target']['readonly'] is None
    if os.name != 'nt':
        detail = trip.remove_failure_diagnostic(PermissionError(13, 'PRIVATE', str(member)),
                                                tmp_path.resolve(), manager, artifact)
        assert detail['target']['observation'] == 'observed' and detail['target']['readonly'] is None


def test_remove_diagnostic_rejects_spoofed_frames_and_bounds_codes_and_size(tmp_path, monkeypatch):
    manager, _, artifact = setup_runtime(tmp_path)
    error = PermissionError('PRIVATE')
    error.errno = True
    error.winerror = 2**40
    with pytest.raises(PermissionError) as caught:
        exec(compile('raise error', trip._runtime.__file__, 'exec'), {'error': error})
    detail = trip.remove_failure_diagnostic(caught.value, tmp_path, manager, artifact)
    assert detail['frames'] == [] and detail['errno'] is None and detail['winerror'] is None
    monkeypatch.setattr(trip, '_MAX_REMOVE_DIAGNOSTIC_BYTES', 1)
    assert trip.remove_failure_diagnostic(error, tmp_path, manager, artifact)['status'] == 'unavailable'


def test_remove_diagnostic_caps_traceback_traversal_and_retained_frames(tmp_path, monkeypatch):
    manager, _, artifact = setup_runtime(tmp_path)

    def recurse(remaining):
        if remaining:
            recurse(remaining - 1)
        raise PermissionError('PRIVATE_RECURSION')

    # Test the cap independently; production uses only its immutable snapshot of
    # trusted source code identities, as the spoofed-filename test also checks.
    monkeypatch.setattr(trip, '_CLEANUP_CODES', {recurse.__code__: 'runtime._tree'})
    with pytest.raises(PermissionError) as caught:
        recurse(80)
    detail = trip.remove_failure_diagnostic(caught.value, tmp_path, manager, artifact)
    assert len(detail['frames']) == 8 and detail['frames_truncated'] is True
    assert len(json.dumps(detail)) < 4096


@pytest.mark.parametrize('diagnostic_failure', [False, True])
def test_roundtrip_cleanup_diagnostic_preserves_primary_failure(tmp_path, monkeypatch, diagnostic_failure):
    from kuma_core.kuro.domain_process import DomainProcessError

    _, archive, artifact = setup_runtime(tmp_path)
    prepared = SimpleNamespace(source_sha256='a' * 64, binding_sha256='b' * 64, normalized_pdb='synthetic')
    primary = DomainProcessError('PRIVATE_PRIMARY')
    secondary = PermissionError(13, 'PRIVATE_SECONDARY', str(tmp_path / 'private-name'))
    monkeypatch.setattr(trip, 'domain_input_manifest', lambda value: {})
    if diagnostic_failure:
        monkeypatch.setattr(trip, '_cleanup_target', lambda *args: (_ for _ in ()).throw(ValueError('PRIVATE_DIAGNOSTIC')))

    def runner(*args, **kwargs):
        raise primary

    report = {}
    with patch.object(trip.OptionalRuntimeManager, 'remove', side_effect=secondary):
        with pytest.raises(DomainProcessError) as caught:
            trip.roundtrip(archive, artifact, [('synthetic', prepared)], runner=runner, report=report)
    assert caught.value is primary
    assert report['failure'] == {'stage': 'runtime_process', 'error_type': 'DomainProcessError'}
    assert report['cleanup_errors'] == [{'stage': 'remove', 'error_type': 'PermissionError'}]
    assert report['removed'] is False and report['temporary_storage_removed'] is True
    assert report['remove_failure_diagnostic']['status'] == ('unavailable' if diagnostic_failure else 'collected')
    assert 'PRIVATE' not in json.dumps(report)


@pytest.fixture(autouse=True)
def internal_ci_marker(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("KUMA_GITHUB_METADATA_TOKEN", "dummy_ci_metadata_token")
    monkeypatch.setattr(ci, "acquire_cpython_origin", lambda *args, **kwargs: {})


def test_archive_ci_prepares_bounded_inputs_without_nesting_build_supervisors(tmp_path, monkeypatch):
    original_write_text = Path.write_text

    def windows_text_write(path, data, *args, **kwargs):
        if path.name == '.kuma-audit-owner' and kwargs.get('newline') is None:
            return path.write_bytes(data.replace('\n', '\r\n').encode('ascii'))
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, 'write_text', windows_text_write)
    source = tmp_path / 'official source'
    source.mkdir()
    (source / 'fixture.txt').write_text('synthetic')
    evidence = tmp_path / 'reports'
    task = tmp_path / 'task with spaces'
    commands = []

    def runner(argv, **kwargs):
        assert len(argv) == 3 and argv[1] == '-I'
        script = Path(argv[2]).read_text()
        ast.parse(script)
        assert 'os.environ["PATH"]' in script
        assert 'runpy.run_module' in script
        assert kwargs['output_limit'] == 1024 * 1024
        assert kwargs['result_limit'] == 4096
        assert 0 < kwargs['timeout_seconds'] <= 1200
        assert kwargs['cwd'].is_relative_to(task)
        commands.append(script)
        kwargs['result_path'].write_text('{}')

    with patch.object(ci, 'run_managed_process', runner), patch.object(ci, 'target', return_value='linux-x64'):
        assert ci.run(source, evidence, task) == 0
    report = json.loads((evidence / 'archive-ci.json').read_text())
    assert report['status'] == 'prepared' and not report['payloads_removed']
    assert not report['distribution_cleared']
    assert len(commands) == 4
    assert '--require-hashes' in commands[3] and '--no-index' in commands[3]
    assert all('scripts.merizo_runtime_archive.build' not in command for command in commands)
    assert source.exists() and task.exists()
    assert (task / '.kuma-audit-owner').read_bytes() == b'kuma-merizo-internal-audit-v1\n'


def test_command_failure_still_removes_payload_and_keeps_failure(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    evidence, task = tmp_path / 'evidence', tmp_path / 'task'
    with patch.object(ci, 'run_managed_process', side_effect=ValueError('synthetic command failure')):
        assert ci.run(source, evidence, task) == 1
    report = json.loads((evidence / 'archive-ci.json').read_text())
    assert report['status'] == 'failed' and report['payloads_removed']
    assert 'synthetic command failure' in report['error']
    assert source.exists() and not task.exists()


def test_cleanup_failure_cannot_report_success(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    evidence, task = tmp_path / 'evidence', tmp_path / 'task'
    with patch.object(ci, 'run_managed_process', side_effect=ValueError('synthetic failure')), patch.object(ci.shutil, 'rmtree', side_effect=OSError('synthetic cleanup')):
        assert ci.run(source, evidence, task) == 1
    report = json.loads((evidence / 'archive-ci.json').read_text())
    assert report['status'] == 'failed' and not report['payloads_removed']
    assert 'cleanup_error' in report and task.exists()


def test_existing_or_overlapping_directory_is_never_deleted(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    for task, evidence in ((source, tmp_path / 'evidence'), (source / 'nested', tmp_path / 'evidence'), (tmp_path / 'new', tmp_path / 'new' / 'evidence')):
        monkeypatch.setenv('KUMA_GITHUB_METADATA_TOKEN', 'dummy_ci_metadata_token')
        with pytest.raises(ValueError, match='fresh task directory'):
            ci.run(source, evidence, task)
    assert source.exists()


def test_unexpected_native_target_is_refused():
    with patch.object(ci.platform, 'machine', return_value='unknown-fixture-cpu'):
        with pytest.raises(ValueError, match='exact supported'):
            ci.target()


def test_archive_audit_refuses_outside_ci(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS")
    with pytest.raises(ValueError, match="restricted"):
        ci.run(tmp_path, tmp_path / "evidence", tmp_path / "task")


@pytest.mark.parametrize("proof", [None, {}, {"schema": "kuma-merizo-runtime-audit-v1", "execution_controller_completed": False}])
def test_unknown_controller_cleanup_never_deletes_payload(tmp_path, proof):
    task, evidence = tmp_path / 'task', tmp_path / 'evidence'
    task.mkdir(); evidence.mkdir()
    (task / '.kuma-audit-owner').write_bytes(b'kuma-merizo-internal-audit-v1\n')
    if proof is not None:
        (evidence / 'runtime-archive.json').write_text(json.dumps(proof))
    assert ci.cleanup(task, evidence) == 1
    assert task.exists()
    assert json.loads((evidence / 'archive-cleanup.json').read_text())['status'] == 'unverified'


def test_completed_direct_controller_allows_owned_payload_cleanup(tmp_path):
    task, evidence = tmp_path / 'task', tmp_path / 'evidence'
    task.mkdir(); evidence.mkdir()
    (task / '.kuma-audit-owner').write_bytes(b'kuma-merizo-internal-audit-v1\n')
    (evidence / 'runtime-archive.json').write_text(json.dumps({
        'schema': 'kuma-merizo-runtime-audit-v1', 'execution_controller_completed': True}))
    assert ci.cleanup(task, evidence) == 0
    assert not task.exists()
    assert json.loads((evidence / 'archive-cleanup.json').read_text())['controller_return_confirmed']


def test_stale_controller_audit_refuses_preparation(tmp_path):
    source, evidence = tmp_path / 'source', tmp_path / 'evidence'
    source.mkdir(); evidence.mkdir()
    (evidence / 'runtime-archive.json').write_text('{}')
    with pytest.raises(ValueError, match='stale'):
        ci.run(source, evidence, tmp_path / 'task')
    assert not (tmp_path / 'task').exists()


@pytest.mark.parametrize("diagnostic", [
    {"type": "ValueError", "message": "synthetic wheel mismatch", "traceback": "bounded traceback"},
    {"type": "ValueError", "message": "x" * 1025, "traceback": ""},
    {"type": "ValueError", "message": "x" * 20000, "traceback": ""},
    {"unexpected": "field"}, [{"nested": "list"}], None,
])
def test_bounded_failure_diagnostic_preserves_original_failure_and_cleanup(tmp_path, diagnostic):
    source, evidence, task = tmp_path / 'source', tmp_path / 'evidence', tmp_path / 'task'
    source.mkdir()
    def runner(argv, **kwargs):
        if diagnostic is not None:
            (kwargs['cwd'] / 'failure.json').write_text(json.dumps(diagnostic))
        raise RuntimeError('original process failure')
    with patch.object(ci, 'run_managed_process', runner):
        assert ci.run(source, evidence, task) == 1
    report = json.loads((evidence / 'archive-ci.json').read_text())
    assert report['status'] == 'failed' and report['payloads_removed']
    assert report['error'] == 'RuntimeError: original process failure'
    step = report['steps'][0]
    assert step['name'] == 'create_isolated_environment' and not step['passed']
    if isinstance(diagnostic, dict) and diagnostic.get('message') == 'synthetic wheel mismatch':
        assert step['diagnostic'] == diagnostic
    else:
        assert 'diagnostic' not in step


def test_actual_generated_driver_writes_bounded_exception_before_cleanup(tmp_path):
    import subprocess
    import sys
    source, evidence, task = tmp_path / 'source', tmp_path / 'evidence', tmp_path / 'task'
    source.mkdir()
    def runner(argv, **kwargs):
        driver = Path(argv[2])
        text = driver.read_text().replace('runpy.run_module(sys.argv[0], run_name="__main__", alter_sys=True)',
                                         'raise ValueError("synthetic driver failure")')
        driver.write_text(text)
        completed = subprocess.run([sys.executable, '-I', str(driver)], capture_output=True, timeout=10)
        assert completed.returncode != 0
        assert not kwargs['result_path'].exists()
        raise RuntimeError('original process failure')
    with patch.object(ci, 'run_managed_process', runner):
        assert ci.run(source, evidence, task) == 1
    report = json.loads((evidence / 'archive-ci.json').read_text())
    detail = report['steps'][0]['diagnostic']
    assert detail['type'] == 'ValueError' and detail['message'] == 'synthetic driver failure'
    assert 'ValueError: synthetic driver failure' in detail['traceback']
    assert report['payloads_removed']


@pytest.mark.parametrize("raw", ["{broken json", "[" * 7000 + "]" * 7000])
def test_malformed_or_deep_diagnostic_does_not_mask_process_failure(tmp_path, raw):
    source, evidence, task = tmp_path / 'source', tmp_path / 'evidence', tmp_path / 'task'
    source.mkdir()
    def runner(argv, **kwargs):
        (kwargs['cwd'] / 'failure.json').write_text(raw)
        raise RuntimeError('original process failure')
    with patch.object(ci, 'run_managed_process', runner):
        assert ci.run(source, evidence, task) == 1
    report = json.loads((evidence / 'archive-ci.json').read_text())
    assert report['error'] == 'RuntimeError: original process failure'
    assert report['payloads_removed'] and 'diagnostic' not in report['steps'][0]


def test_readonly_git_object_is_copied_as_deletable_bytes_without_mutating_source(tmp_path):
    import stat
    source, evidence, task = tmp_path / 'source', tmp_path / 'evidence', tmp_path / 'task'
    original = source / '.git' / 'objects' / 'aa' / 'fixture'
    original.parent.mkdir(parents=True)
    original.write_bytes(b'synthetic pinned object bytes')
    original.chmod(stat.S_IREAD)
    initial = original.stat().st_mode
    try:
        def runner(argv, **kwargs):
            copied = task / 'official source' / '.git' / 'objects' / 'aa' / 'fixture'
            assert copied.read_bytes() == original.read_bytes()
            assert copied.stat().st_mode & stat.S_IWRITE
            raise RuntimeError('original process failure')
        with patch.object(ci, 'run_managed_process', runner):
            assert ci.run(source, evidence, task) == 1
        report = json.loads((evidence / 'archive-ci.json').read_text())
        assert report['payloads_removed'] and not task.exists()
        assert original.exists() and original.stat().st_mode == initial
        assert original.read_bytes() == b'synthetic pinned object bytes'
    finally:
        original.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_metadata_token_is_controller_only_and_error_is_redacted(tmp_path, monkeypatch):
    import os
    source, evidence, task = tmp_path / 'source', tmp_path / 'evidence', tmp_path / 'task'
    source.mkdir()
    token = 'dummy_ci_metadata_token'
    seen = []
    def runner(argv, **kwargs):
        assert 'KUMA_GITHUB_METADATA_TOKEN' not in os.environ
        script = Path(argv[2]).read_text()
        assert token not in script and token not in str(argv) and token not in str(kwargs)
        seen.append(script)
        kwargs['result_path'].write_text('{}')
    def acquire(*args, **kwargs):
        assert 'KUMA_GITHUB_METADATA_TOKEN' not in os.environ
        assert kwargs['github_token'] == token
        assert len(seen) == 4
        raise RuntimeError('simulated request header Authorization: Bearer ' + token)
    monkeypatch.setattr(ci, 'acquire_cpython_origin', acquire)
    with patch.object(ci, 'run_managed_process', runner):
        assert ci.run(source, evidence, task) == 1
    raw = (evidence / 'archive-ci.json').read_text()
    assert token not in raw and '[redacted]' in raw
    report = json.loads(raw)
    assert report['status'] == 'failed' and report['payloads_removed']
    assert report['steps'][-1]['name'] == 'acquire_cpython_origin_bytes'
    assert report['steps'][-1]['passed'] is False
    assert not task.exists()


def test_missing_step_metadata_token_refuses_before_any_child(tmp_path, monkeypatch):
    monkeypatch.delenv('KUMA_GITHUB_METADATA_TOKEN')
    with patch.object(ci, 'run_managed_process') as runner:
        with pytest.raises(ValueError, match='Missing step-scoped'):
            ci.run(tmp_path, tmp_path / 'reports', tmp_path / 'task')
    runner.assert_not_called()
