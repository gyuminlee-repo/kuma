"""One bounded internal archive audit; retain JSON, never model/runtime payloads."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import sys
import time

from kuma_core.kuro.domain_process import run_managed_process
from scripts.merizo_runtime_archive.common import read_regular, strict_json, write_json
from scripts.merizo_runtime_archive.cpython_origin import acquire as acquire_cpython_origin


def target() -> str:
    pair = (sys.platform, platform.machine().lower())
    targets = {('linux', 'x86_64'): 'linux-x64', ('win32', 'amd64'): 'windows-x64',
               ('darwin', 'arm64'): 'macos-arm64'}
    if pair not in targets or sys.version_info[:2] != (3, 11):
        raise ValueError('Require an exact supported Python 3.11 CI target')
    return targets[pair]


def run(source: Path, evidence: Path, task_directory: Path) -> int:
    # This step-scoped existing CI token never enters a generated driver or child.
    github_token = os.environ.pop("KUMA_GITHUB_METADATA_TOKEN", None)
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Candidate archive execution is restricted to the internal CI audit")
    if not github_token:
        raise ValueError("Missing step-scoped GitHub metadata token")
    project = Path(__file__).resolve().parents[2]
    source = source.resolve(strict=True)
    evidence = evidence.resolve()
    task_directory = task_directory.resolve()
    if (task_directory.exists() or source.is_relative_to(task_directory)
            or task_directory.is_relative_to(source) or evidence.is_relative_to(task_directory)):
        raise ValueError('Require a fresh task directory distinct from source and evidence')
    evidence.mkdir(parents=True, exist_ok=True)
    if (evidence / 'runtime-archive.json').exists():
        raise ValueError('Refuse a stale build-controller audit')
    report = {'schema': 'kuma-merizo-archive-ci-v1', 'status': 'failed', 'distribution_cleared': False,
              'target': target(), 'steps': [], 'payloads_removed': False}
    started = time.monotonic()
    build_path = os.environ.get("PATH", "")
    ci_identity = {key: os.environ[key] for key in ("GITHUB_ACTIONS", "GITHUB_RUN_ID", "ImageOS", "ImageVersion") if key in os.environ}
    if any(len(value) > 256 or any(c in value for c in "\0\r\n") for value in ci_identity.values()):
        raise ValueError("Invalid public CI identity metadata")
    task_directory.mkdir(parents=True)
    (task_directory / '.kuma-audit-owner').write_bytes(b'kuma-merizo-internal-audit-v1\n')

    def command(name: str, argv: list[str], timeout: int = 300) -> None:
        before = time.monotonic()
        if not build_path or len(build_path) > 65536 or any(c in build_path for c in '\0\r\n'):
            raise ValueError('Invalid trusted CI build-tool path')
        if len(argv) < 3 or argv[1] != '-m':
            raise ValueError('Internal CI commands must be fixed Python modules')
        work = task_directory / ('step-' + name)
        work.mkdir()
        sentinel = work / 'completed.json'
        driver = work / 'command.py'
        diagnostic = work / 'failure.json'
        # Build tools need the trusted CI tool path. This driver is not shipped
        # and does not change the production inference environment contract.
        driver.write_text('import json, os, runpy, sys, traceback\nfrom pathlib import Path\n' +
            f'os.environ["PATH"] = {build_path!r}\n' +
            f'os.environ.update({ci_identity!r})\n' +
            f'sys.path.insert(0, {str(project)!r})\n' +
            f'sys.argv = {argv[2:]!r}\n' +
            'try:\n    try:\n        runpy.run_module(sys.argv[0], run_name="__main__", alter_sys=True)\n' +
            '    except SystemExit as exc:\n        if exc.code not in (None, 0): raise\n' +
            'except BaseException as exc:\n    try:\n' +
            f'        Path({str(diagnostic)!r}).write_text(json.dumps({{"type": type(exc).__name__[:128], "message": str(exc)[:1024], "traceback": traceback.format_exc(limit=6)[-2048:]}}, ensure_ascii=False), encoding="utf-8")\n' +
            '    except OSError:\n        pass\n    raise\n' +
            f'Path({str(sentinel)!r}).write_text("{{}}", encoding="ascii")\n', encoding='utf-8')
        try:
            run_managed_process([argv[0], '-I', str(driver)], cwd=work, cancelled=lambda: False,
                                timeout_seconds=timeout, output_limit=1024 * 1024,
                                result_path=sentinel, result_limit=4096)
        except Exception:
            failed = {'name': name, 'passed': False, 'seconds': time.monotonic() - before}
            try:
                detail = strict_json(read_regular(diagnostic, 16384))
                limits = {'type': 128, 'message': 1024, 'traceback': 2048}
                if (isinstance(detail, dict) and set(detail) == set(limits)
                        and all(isinstance(detail[key], str) and len(detail[key]) <= limit
                                for key, limit in limits.items())):
                    failed['diagnostic'] = detail
            except (OSError, ValueError, RecursionError):
                pass  # Diagnostic failure must not replace the original process failure.
            report['steps'].append(failed)
            raise
        report['steps'].append({'name': name, 'passed': True, 'seconds': time.monotonic() - before})

    try:
        copied = task_directory / 'official source'
        # Preserve source bytes, not Git object read-only attributes. The owned
        # Windows copy must remain deletable without changing original permissions.
        shutil.copytree(source, copied, copy_function=shutil.copyfile)
        venv = task_directory / 'build environment'
        command('create_isolated_environment', [sys.executable, '-m', 'venv', str(venv)])
        python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        wheel = {'linux-x64': 'torch==2.0.1+cpu', 'windows-x64': 'torch==2.0.1+cpu',
                 'macos-arm64': 'torch==2.0.1'}[report['target']]
        # Pip records exact official URLs and SHA-256 before any candidate is installed.
        # inputs.py independently bounds and verifies each wheel and its RECORD.
        resolution = task_directory / 'resolution.json'
        args = [str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir',
                '--dry-run', '--ignore-installed', '--only-binary=:all:', '--report', str(resolution),
                '-r', str(project / 'scripts/merizo_runtime_archive/requirements.txt'), wheel]
        if report['target'] != 'macos-arm64':
            args += ['--extra-index-url', 'https://download.pytorch.org/whl/cpu']
        command('resolve_candidate_wheels', args)
        wheelhouse = task_directory / 'wheelhouse'
        lock = evidence / 'archive-input-lock.json'
        requirements = task_directory / 'locked.txt'
        command('verify_candidate_wheel_bytes', [sys.executable, '-m', 'scripts.merizo_runtime_archive.inputs',
            '--report', str(resolution), '--wheelhouse', str(wheelhouse), '--output', str(lock),
            '--requirements-lock', str(requirements)])
        command('offline_hash_install', [str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
            '--no-cache-dir', '--no-index', '--require-hashes', '--only-binary=:all:',
            '--find-links', str(wheelhouse), '-r', str(requirements)])
        origin = evidence / 'archive-cpython-origin.json'
        # Metadata credentials stay in this controller only. The acquisition has
        # its own deadline and the preparation step retains its 10-minute cap.
        before = time.monotonic()
        try:
            acquire_cpython_origin(origin, task_directory / 'cpython-origin',
                runner_platform_version='22.04' if report['target'] == 'linux-x64' else None,
                github_token=github_token)
        except Exception:
            report['steps'].append({'name': 'acquire_cpython_origin_bytes', 'passed': False,
                                    'seconds': time.monotonic() - before})
            raise
        report['steps'].append({'name': 'acquire_cpython_origin_bytes', 'passed': True,
                                'seconds': time.monotonic() - before})
        report['status'] = 'prepared'
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'.replace(github_token, '[redacted]')[:4000]
    finally:
        if report['status'] != 'prepared':
            try:
                shutil.rmtree(task_directory)
                report['payloads_removed'] = not task_directory.exists()
            except Exception as exc:
                report['status'] = 'failed'
                report['cleanup_error'] = f'{type(exc).__name__}: {exc}'.replace(github_token, '[redacted]')[:1000]
        report['seconds'] = time.monotonic() - started
        write_json(evidence / 'archive-ci.json', report)
    return 0 if report['status'] == 'prepared' else 1


def cleanup(task_directory: Path, evidence: Path) -> int:
    """Only remove retained payload after the direct build controller returned.

    Timeout/cancellation without the controller-written completion audit is unknown,
    not proof that inner helpers have exited. Leave that payload to the ephemeral
    runner's own teardown instead of racing a still-cleaning helper.
    """
    task_directory, evidence = task_directory.resolve(), evidence.resolve()
    report = {'schema': 'kuma-merizo-archive-cleanup-v1', 'status': 'unverified',
              'controller_return_confirmed': False, 'payloads_removed': False}
    try:
        if not task_directory.exists():
            report.update(status='no_payload', payloads_removed=True)
        else:
            from scripts.merizo_runtime_archive.common import read_regular, strict_json
            if read_regular(task_directory / '.kuma-audit-owner', 64) != b'kuma-merizo-internal-audit-v1\n':
                raise ValueError('Task payload ownership not confirmed')
            returned = strict_json(read_regular(evidence / 'runtime-archive.json', 32 * 1024 * 1024))
            if (returned.get('schema') != 'kuma-merizo-runtime-audit-v1'
                    or returned.get('execution_controller_completed') is not True):
                raise ValueError('Direct controller return is not confirmed')
            report['controller_return_confirmed'] = True
            shutil.rmtree(task_directory)
            report.update(status='removed', payloads_removed=not task_directory.exists())
    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {exc}'[:1000]
    write_json(evidence / 'archive-cleanup.json', report)
    return 0 if report['payloads_removed'] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--evidence-directory', required=True, type=Path)
    parser.add_argument('--task-directory', required=True, type=Path)
    parser.add_argument('--cleanup', action='store_true')
    args = parser.parse_args()
    if args.cleanup:
        return cleanup(args.task_directory, args.evidence_directory)
    if args.source is None:
        parser.error('--source is required for preparation')
    return run(args.source, args.evidence_directory, args.task_directory)


if __name__ == '__main__':
    raise SystemExit(main())
