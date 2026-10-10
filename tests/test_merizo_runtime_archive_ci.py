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
