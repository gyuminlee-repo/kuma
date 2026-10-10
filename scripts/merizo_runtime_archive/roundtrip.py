"""Internal archive install -> verification -> managed CPU CLI -> decoder -> removal."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
import stat
from pathlib import Path
import tempfile
import time

from kuma_core.kuro.domain_annotation import prepare_domain_input
from kuma_core.kuro.domain_merizo import decode_merizo_result, domain_input_manifest
from kuma_core.kuro.domain_process import run_managed_process
from kuma_core.kuro.optional_runtime import OptionalRuntimeManager, PRODUCTION_CATALOG
from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId
from scripts.merizo_runtime_archive.common import digest, read_regular, strict_json, write_json
from scripts.merizo_runtime_archive.runtime_entry import (
    FAILURE_SCHEMA, FAILURE_ERROR_TYPES, FAILURE_STAGES, MAX_FAILURE_BYTES, MAX_FAILURE_FRAMES, safe_error_type,
)

PUBLIC_SHA = 'd4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161'
SEQUENCE = 'MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG'
_STAGE_STARTED = time.monotonic()
_MAX_STAGE_SECONDS = 3600.0
_STAGES = {
    'build': frozenset({'preflight', 'public_fixture', 'source_verification', 'installed_provenance',
        'cpython_origin', 'build_identity', 'build_workspace', 'freeze', 'source_reverification',
        'build_input_mapping', 'embedded_inventory', 'stdlib_mapping', 'source_companion',
        'package_notices', 'normalize_archive', 'output_mapping', 'remove_original_source', 'archive_roundtrip'}),
    'freezer': frozenset({'freezer_dependencies', 'freezer_spec', 'freezer_process', 'freezer_toc'}),
    'roundtrip': frozenset({'catalog', 'workspace', 'install', 'verify', 'prepare_protocol',
                          'runtime_process', 'decode_result', 'remove', 'workspace_cleanup'}),
    'cleanup': frozenset({'build_payload_cleanup'}),
}


def stage_event(report: dict, scope: str, stage: str, *, enabled: bool = False) -> None:
    """Controller-only progress observations, never completion/cleanup proof."""
    if scope not in _STAGES or stage not in _STAGES[scope]:
        raise ValueError('Unknown internal audit stage')
    report['current_stage'] = stage
    if not enabled:
        return
    try:
        elapsed = time.monotonic() - _STAGE_STARTED
        if not math.isfinite(elapsed) or elapsed < 0:
            return
        event = {'schema': 'kuma-merizo-stage-v1', 'scope': scope, 'stage': stage,
                 'event': 'entered', 'evidence': 'progress_only',
                 'elapsed_seconds': round(min(elapsed, _MAX_STAGE_SECONDS), 6),
                 'elapsed_capped': elapsed > _MAX_STAGE_SECONDS}
        print(json.dumps(event, sort_keys=True, allow_nan=False), flush=True)
    except Exception:
        pass  # Logging must not change the operation's result or cleanup error.


def public_inputs(fixture: Path):
    raw = read_regular(fixture, 1024 * 1024)
    if hashlib.sha256(raw).hexdigest() != PUBLIC_SHA:
        raise ValueError('Internal smoke requires the pinned public fixture')
    text = raw.decode('ascii')
    polymer = PolymerRecord(SEQUENCE, 'RCSB 1UBQ SEQRES', 'public-1ubq', '1', 'A',
                            tuple(ResidueId('1', 'A', i) for i in range(1, 77)))
    public = prepare_domain_input(text, polymer, SEQUENCE, source_sha256=PUBLIC_SHA)
    # A synthetic SOURCE IDENTITY case with exactly the public coordinates.
    # It is not synthetic biological validation or a new long-protein benchmark.
    lines, identities = [], []
    for i in range(1, 77):
        number, insertion = (110, 'A') if i == 11 else (100 + i, '')
        identities.append(ResidueId('1', 'B', number, insertion))
    for line in text.splitlines():
        if line.startswith('ATOM  ') and line[21] == 'A':
            identity = identities[int(line[22:26]) - 1]
            line = line[:21] + 'B' + f'{identity.author_number:4d}' + (identity.insertion_code or ' ') + line[27:]
        lines.append(line)
    reframed_text = '\n'.join(lines) + '\n'
    reframed = prepare_domain_input(reframed_text,
        PolymerRecord(SEQUENCE, 'synthetic author labels; public 1UBQ coordinates',
                      'synthetic-author-frame', '1', 'B', tuple(identities)),
        SEQUENCE, source_sha256=hashlib.sha256(reframed_text.encode()).hexdigest())
    if reframed.normalized_pdb != public.normalized_pdb or reframed.binding_sha256 == public.binding_sha256:
        raise ValueError('Synthetic identity fixture does not preserve the public geometry')
    return [('public_1ubq', public), ('synthetic_author_labels_public_geometry', reframed)]


def read_failure(path: Path, *, schema=FAILURE_SCHEMA, line_key='runtime_entry_lines',
                 stages=FAILURE_STAGES) -> dict:
    """Read only bounded regular-file diagnostics; never propagate their content unchecked."""
    try:
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or getattr(before, 'st_file_attributes', 0) & 0x400
                or before.st_size > MAX_FAILURE_BYTES):
            raise ValueError('Invalid diagnostic file')
        flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(path, flags), 'rb') as stream:
            opened, after = os.fstat(stream.fileno()), path.lstat()
            if (not stat.S_ISREG(after.st_mode) or getattr(after, 'st_file_attributes', 0) & 0x400
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                    or (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)):
                raise ValueError('Diagnostic identity changed')
            raw = stream.read(MAX_FAILURE_BYTES + 1)
        if len(raw) > MAX_FAILURE_BYTES:
            raise ValueError('Diagnostic exceeds bound')
        value = strict_json(raw)
        if (not isinstance(value, dict)
                or set(value) != {'schema', 'error_type', 'stage', line_key, 'truncated'}
                or value['schema'] != schema or value['error_type'] not in FAILURE_ERROR_TYPES
                or value['stage'] not in stages or type(value['truncated']) is not bool
                or not isinstance(value[line_key], list) or len(value[line_key]) > MAX_FAILURE_FRAMES
                or any(type(line) is not int or not 1 <= line <= 1000000 for line in value[line_key])):
            raise ValueError('Invalid diagnostic schema')
        return {'status': 'validated', 'report': value}
    except FileNotFoundError:
        return {'status': 'missing'}
    except Exception:
        return {'status': 'rejected'}


def roundtrip(archive: Path, artifact, inputs, *, runner=run_managed_process, report=None,
              stage_events: bool = False) -> dict:
    if report is None:
        report = {}
    if report:
        raise ValueError('Partial roundtrip report must start empty')
    report.update(catalog_scope='test_only_exact_archive_bytes', installed=False, verified=False,
                  removed=False, runs=[], status='running', current_stage='catalog',
                  temporary_storage_removed=False, cleanup_errors=[])
    primary = None
    temporary = None
    root = None
    manager = None
    def checkpoint(stage):
        stage_event(report, 'roundtrip', stage, enabled=stage_events)
    try:
        checkpoint('catalog')
        if PRODUCTION_CATALOG:
            raise ValueError('Internal audit must not activate the production catalog')
        checkpoint('workspace')
        temporary = tempfile.TemporaryDirectory(prefix='kuma-runtime-roundtrip-')
        root = Path(temporary.name).resolve()
        manager = OptionalRuntimeManager(root / 'app', catalog={(artifact.engine, artifact.platform): artifact},
                                         platform_key=artifact.platform)
        checkpoint('install')
        status = manager.install(archive)
        if status.state != 'installed':
            raise ValueError('Registry installation did not succeed')
        report['installed'] = True
        for name, prepared in inputs:
            run = {'fixture': name, 'verified': False, 'process_invoked': False,
                   'process_succeeded': False, 'decoded': False, 'current_stage': 'verify',
                   'source_sha256': prepared.source_sha256, 'binding_sha256': prepared.binding_sha256}
            report['runs'].append(run)
            try:
                checkpoint('verify')
                with manager.operation_lock() as lease:
                    verified = manager.verify()
                    if verified.state != 'installed' or not verified.executable_path:
                        raise ValueError('Registry verification failed after extraction')
                    report['verified'] = run['verified'] = True
                    report['executable_sha256'] = digest(Path(verified.executable_path))
                    run['current_stage'] = 'prepare_protocol'
                    checkpoint('prepare_protocol')
                    work = root / name
                    work.mkdir()
                    pdb, manifest, result = work / 'input.pdb', work / 'input.json', work / 'result.json'
                    diagnostic = work / 'entry-failure.json'
                    pdb.write_text(prepared.normalized_pdb, encoding='ascii', newline='\n')
                    write_json(manifest, domain_input_manifest(prepared))
                    run['current_stage'] = 'runtime_process'
                    checkpoint('runtime_process')
                    run['process_invoked'] = True
                    try:
                        runner([verified.executable_path, '--input-pdb', str(pdb), '--input-manifest', str(manifest),
                                '--output', str(result), '--device', 'cpu', '--audit-failure-report', str(diagnostic)],
                               cwd=work, cancelled=lambda: False, timeout_seconds=300, output_limit=1024 * 1024,
                               result_path=result, result_limit=8 * 1024 * 1024, operation_lease=lease)
                    except BaseException:
                        try:
                            run['entry_diagnostic'] = read_failure(diagnostic)
                        except Exception:
                            run['entry_diagnostic'] = {'status': 'rejected'}
                        # Missing entry evidence cannot distinguish bootloader,
                        # interpreter bootstrap, or later abrupt process failure.
                        raise
                    run['process_succeeded'] = True
                    run['current_stage'] = 'decode_result'
                    checkpoint('decode_result')
                    text = read_regular(result, 8 * 1024 * 1024).decode('utf-8')
                    annotation = decode_merizo_result(text, prepared, current_binding_sha256=prepared.binding_sha256)
                    run.update(decoded=True, residues=annotation.total_residues, domains=len(annotation.domains),
                               coverage=annotation.coverage, confidence=annotation.confidence,
                               result_sha256=digest(result), current_stage='completed')
            except BaseException as exc:
                run['error_type'] = safe_error_type(exc)
                raise
        report['current_stage'] = 'completed'
    except BaseException as exc:
        primary = exc
        report['failure'] = {'stage': report['current_stage'], 'error_type': safe_error_type(exc)}
    finally:
        if manager is not None and report['installed']:
            checkpoint('remove')
            try:
                report['removed'] = manager.remove().state == 'missing'
                if not report['removed']:
                    raise ValueError('Internal registry removal failed')
            except BaseException as exc:
                report['cleanup_errors'].append({'stage': 'remove', 'error_type': safe_error_type(exc)})
                if primary is None:
                    primary = exc
                    report['failure'] = {'stage': 'remove', 'error_type': safe_error_type(exc)}
        checkpoint('workspace_cleanup')
        if temporary is not None:
            try:
                temporary.cleanup()
            except BaseException as exc:
                report['cleanup_errors'].append({'stage': 'workspace_cleanup', 'error_type': safe_error_type(exc)})
                if primary is None:
                    primary = exc
                    report['failure'] = {'stage': 'workspace_cleanup', 'error_type': safe_error_type(exc)}
        report['temporary_storage_removed'] = root is None or not root.exists()
        if not report['temporary_storage_removed']:
            report['cleanup_errors'].append({'stage': 'workspace_cleanup', 'error_type': 'OSError'})
            if primary is None:
                primary = OSError('Roundtrip temporary storage remains')
                report['failure'] = {'stage': 'workspace_cleanup', 'error_type': 'OSError'}
        report['status'] = 'failed' if primary is not None else 'passed'
        report['current_stage'] = 'failed' if primary is not None else 'completed'
    if primary is not None:
        raise primary
    return report
