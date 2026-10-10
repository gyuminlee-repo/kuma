"""Temporary POSIX onedir feasibility build; no download or product distribution."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

import build_frozen as shared
from run import COMMIT, runtime_contract, verify_upstream


def package_inventory(package: Path) -> dict[str, int]:
    """Allow PyInstaller's POSIX links only when they resolve inside this bundle.

    Count physical regular-file bytes once (not alias targets again), and report
    link count separately. No directory-link recursion is needed.
    """
    root = package.resolve(strict=True)
    count = total = links = 0
    seen: set[tuple[int, int]] = set()
    for path in root.rglob('*'):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f'Bundle entry resolves outside package: {path}')
        if path.is_symlink():
            links += 1
            continue
        if path.is_file():
            info = path.stat()
            identity = (info.st_dev, info.st_ino)
            if identity not in seen:
                seen.add(identity)
                total += info.st_size
                count += 1
        elif not path.is_dir():
            raise ValueError(f'Unexpected non-regular package entry: {path}')
    return {'package_bytes': total, 'package_file_count': count, 'package_symlink_count': links}


def build_command(source: Path, output: Path) -> list[str]:
    command = shared.build_command(source, output)
    command[-1] = str(Path(__file__).with_name('frozen_posix_entry.py'))
    if sys.platform == 'darwin':
        command[-1:-1] = ['--target-arch', 'arm64']
    return command


def stop_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=10)


def build(source: Path, output: Path, evidence_path: Path) -> int:
    source, output, evidence_path = source.resolve(), output.resolve(), evidence_path.resolve()
    started = time.perf_counter()
    evidence: dict = {'status': 'failed', 'source_commit': COMMIT,
        'source_directory': str(source), 'package_directory': str(output / 'dist' / shared.PACKAGE_NAME),
        'verified_before_build': False, 'build_timeout_seconds': shared.BUILD_TIMEOUT_SECONDS,
        'not_verified': ['KUMA integration', 'redistribution rights', 'clean-machine installation',
                         'developer signing/notarization', 'other OS versions/architectures']}
    created_output = False
    try:
        if sys.platform not in {'linux', 'darwin'} or os.environ.get('GITHUB_ACTIONS') != 'true':
            raise ValueError('POSIX frozen build is restricted to the approved CI experiment')
        evidence['runtime_contract'] = runtime_contract()
        if not shared.disjoint(source, output) or not shared.disjoint(source, evidence_path) or not shared.disjoint(output, evidence_path):
            raise ValueError('Source, output and evidence must be disjoint')
        if output.exists():
            raise ValueError('Choose a fresh output directory')
        evidence['freezer_dependencies'] = shared.verify_freezer_dependencies()
        evidence['weights_sha256'] = verify_upstream(source)
        evidence['source_python_sha256'] = shared.source_hashes(source)
        own = Path(__file__).resolve().parent
        names = ('run.py', 'build_frozen.py', 'build_frozen_posix.py', 'frozen_posix_entry.py',
                 'run_frozen_posix.py', 'freezer-requirements.txt')
        evidence['own_harness_sha256'] = {name: shared.digest_file(own / name) for name in names}
        evidence['pyinstaller'] = shared.PYINSTALLER_VERSION
        evidence['verified_before_build'] = True
        evidence['status'] = 'verified'
        shared.write_evidence(evidence_path, evidence)
        output.mkdir(parents=True, exist_ok=False)
        created_output = True
        environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'MPLBACKEND': 'Agg',
            'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'CUDA_VISIBLE_DEVICES': ''}
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(build_command(source, output), cwd=output, env=environment,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, shell=False, start_new_session=True)
            try:
                try:
                    code = process.wait(timeout=shared.BUILD_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    evidence['status'] = 'timed_out'
                    raise TimeoutError('PyInstaller exceeded 600 seconds')
            finally:
                stop_group(process)
                evidence['build_process_group_termination_requested'] = True
                evidence['build_root_reaped'] = True
            if code:
                log.seek(0, os.SEEK_END)
                log.seek(max(0, log.tell() - 12000))
                evidence['build_log_tail'] = log.read(12000).decode('utf-8', errors='replace')
                raise RuntimeError(f'PyInstaller exited with code {code}')
        if verify_upstream(source) != evidence['weights_sha256']:
            raise ValueError('Upstream changed during build')
        package = output / 'dist' / shared.PACKAGE_NAME
        executable = package / shared.PACKAGE_NAME
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError('Frozen executable was not produced')
        evidence['frozen_bootstrap_imports'] = shared.verify_frozen_bootstrap_imports(executable)
        evidence.update(package_inventory(package))
        evidence['entry_executable'] = str(executable)
        evidence['status'] = 'built'
        return 0
    except Exception as exc:
        evidence['error'] = f'{type(exc).__name__}: {exc}'[:12000]
        if evidence['status'] != 'timed_out':
            evidence['status'] = 'failed'
        if created_output:
            try:
                shutil.rmtree(output)
                evidence['failed_output_removed'] = True
            except OSError as cleanup_error:
                evidence['failed_output_removed'] = False
                evidence['cleanup_error'] = str(cleanup_error)[:2000]
        return 2
    finally:
        evidence['elapsed_seconds'] = time.perf_counter() - started
        shared.write_evidence(evidence_path, evidence)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    return build(args.source, args.output_directory, args.evidence)


if __name__ == '__main__':
    raise SystemExit(main())
