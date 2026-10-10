"""Offline CI orchestration contracts; never download or infer in unit tests."""
import ast
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.merizo_runtime_archive import ci


@pytest.fixture(autouse=True)
def internal_ci_marker(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")


def test_archive_ci_prepares_bounded_inputs_without_nesting_build_supervisors(tmp_path):
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
    assert len(commands) == 5
    assert '--require-hashes' in commands[3] and '--no-index' in commands[3]
    assert all('scripts.merizo_runtime_archive.build' not in command for command in commands)
    assert source.exists() and task.exists()


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


def test_existing_or_overlapping_directory_is_never_deleted(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    for task, evidence in ((source, tmp_path / 'evidence'), (source / 'nested', tmp_path / 'evidence'), (tmp_path / 'new', tmp_path / 'new' / 'evidence')):
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
    (task / '.kuma-audit-owner').write_text('kuma-merizo-internal-audit-v1\n')
    if proof is not None:
        (evidence / 'runtime-archive.json').write_text(json.dumps(proof))
    assert ci.cleanup(task, evidence) == 1
    assert task.exists()
    assert json.loads((evidence / 'archive-cleanup.json').read_text())['status'] == 'unverified'


def test_completed_direct_controller_allows_owned_payload_cleanup(tmp_path):
    task, evidence = tmp_path / 'task', tmp_path / 'evidence'
    task.mkdir(); evidence.mkdir()
    (task / '.kuma-audit-owner').write_text('kuma-merizo-internal-audit-v1\n')
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
