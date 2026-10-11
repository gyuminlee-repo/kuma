"""Internal archive install -> verification -> managed CPU CLI -> decoder -> removal."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
import re
import shutil
import stat
from pathlib import Path
import tempfile
import time

from kuma_core.kuro.domain_annotation import prepare_domain_input
from kuma_core.kuro.domain_merizo import decode_merizo_result, domain_input_manifest
from kuma_core.kuro.domain_process import run_managed_process
from kuma_core.kuro import domain_lease as _lease, optional_runtime as _runtime
from kuma_core.kuro.optional_runtime import OptionalRuntimeManager, PRODUCTION_CATALOG
from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId
from scripts.merizo_runtime_archive.common import canonical, digest, read_regular, strict_json, write_json
from scripts.merizo_runtime_archive.runtime_entry import (
    FAILURE_SCHEMA, FAILURE_ERROR_TYPES, FAILURE_STAGES, MAX_FAILURE_BYTES, MAX_FAILURE_FRAMES, safe_error_type, validate_warning_report,
)

PUBLIC_SHA = 'd4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161'
SEQUENCE = 'MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG'
_STAGE_STARTED = time.monotonic()
_MAX_STAGE_SECONDS = 3600.0
_MAX_REMOVE_DIAGNOSTIC_BYTES = 4096


def _cleanup_codes() -> dict:
    """Snapshot trusted code identities, never traceback filename/name strings."""
    result = {}
    for prefix, owner, names in (
        ('runtime', _runtime, ('_directory_chain', '_open_regular', '_read_exact', '_tree', '_remove_tree')),
        ('manager', OptionalRuntimeManager, ('_check_root', 'operation_lock', 'remove', 'status')),
        ('lease', _lease, ('_root_identity', '_check_root', '_check_named', '_primary', '_read_record',
                            '_sync_root', 'check_execution_admission')),
        ('guard', _lease._Guard, ('__init__', 'check', 'close')),
        ('shutil', shutil, ('rmtree', '_rmtree_unsafe', '_rmtree_safe_fd', '_rmtree_isdir', '_rmtree_islink')),
    ):
        for name in names:
            function = getattr(owner, name, None)
            function = getattr(function, '__wrapped__', function)
            code = getattr(function, '__code__', None)
            if code is not None:
                result[code] = prefix + '.' + name
    return result


_CLEANUP_CODES = _cleanup_codes()


def _cleanup_target(value, root: Path, manager: OptionalRuntimeManager, artifact) -> dict:
    observed = {'role': 'unknown', 'observation': 'unavailable',
                'readonly': None, 'reparse': None, 'directory': None}
    if not isinstance(value, str) or len(value) > 4096 or '\0' in value:
        return observed
    path = Path(value)
    if (not path.is_absolute() or '..' in path.parts or len(path.parts) > 64
            or not path.is_relative_to(root)):
        return observed
    target = manager._target(artifact)
    known = {root: 'workspace_root', manager.app_data_root: 'app_root', manager.root: 'registry_root',
             manager.root / _runtime._LOCK_FILE: 'primary_lock',
             manager.root / _runtime._ROOT_MARKER: 'root_marker',
             manager.root / _lease.EXECUTION_GUARD_NAME: 'execution_guard',
             manager.root / _lease.EXECUTION_RECORD_NAME: 'execution_record',
             target: 'installed_target', target / _runtime._RECEIPT: 'installed_receipt'}
    role = known.get(path)
    if role is None and path.is_relative_to(target):
        role = 'installed_payload_entry'
    if role is None and path.is_relative_to(manager.root):
        relative = path.relative_to(manager.root).parts
        if relative and re.fullmatch(re.escape(manager._stage_prefix(artifact)) + r'[a-z0-9_]{8}', relative[0]):
            role = 'removal_stage' if len(relative) == 1 else 'removal_stage_entry'
    if role is None:
        return observed
    observed['role'] = role
    try:
        # No resolve(), content reads, or traversal through a link/reparse point.
        # These are post-failure observations, never authority to mutate/delete.
        for ancestor in reversed(path.parents):
            info = ancestor.lstat()
            if (_runtime._is_link(info) or not stat.S_ISDIR(info.st_mode)):
                observed['observation'] = 'unsafe_ancestor'
                return observed
        info = path.lstat()
        attributes = getattr(info, 'st_file_attributes', None)
        observed.update(observation='observed',
                        readonly=bool(attributes & 1) if type(attributes) is int else None,
                        reparse=_runtime._is_link(info), directory=stat.S_ISDIR(info.st_mode))
    except FileNotFoundError:
        observed['observation'] = 'missing'
    except OSError:
        pass
    return observed


def remove_failure_diagnostic(exc: BaseException, root: Path, manager: OptionalRuntimeManager, artifact) -> dict:
    """Bounded syscall-location evidence; no exception text or filesystem paths."""
    fallback = {'schema': 'kuma-runtime-remove-failure-v1', 'status': 'unavailable'}
    try:
        def number(name):
            value = getattr(exc, name, None)
            return value if type(value) is int and 0 <= value <= 0xFFFFFFFF else None

        frames = []
        current, inspected, truncated = exc.__traceback__, 0, False
        while current is not None and inspected < 64:
            call = _CLEANUP_CODES.get(current.tb_frame.f_code)
            if call is not None and 1 <= current.tb_lineno <= 1000000:
                frames.append({'call': call, 'line': current.tb_lineno})
                if len(frames) > 8:
                    frames.pop(0)
                    truncated = True
            current, inspected = current.tb_next, inspected + 1
        result = {'schema': fallback['schema'], 'status': 'collected',
                  'evidence': 'post_failure_observation_not_cause',
                  'errno': number('errno'), 'winerror': number('winerror'),
                  'frames': frames, 'frames_truncated': truncated or current is not None,
                  'target': _cleanup_target(getattr(exc, 'filename', None), root, manager, artifact),
                  'target2': _cleanup_target(getattr(exc, 'filename2', None), root, manager, artifact)}
        if len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode('ascii')) > _MAX_REMOVE_DIAGNOSTIC_BYTES:
            return fallback
        return result
    except BaseException:
        return fallback  # Diagnostic failure cannot replace either real failure.
_STAGES = {
    'build': frozenset({'preflight', 'public_fixture', 'source_verification', 'installed_provenance',
        'cpython_origin', 'build_identity', 'build_workspace', 'freeze', 'source_reverification',
        'build_input_mapping', 'embedded_inventory', 'stdlib_mapping', 'source_companion',
        'package_notices', 'normalize_archive', 'output_mapping', 'remove_original_source', 'archive_roundtrip'}),
    'freezer': frozenset({'freezer_dependencies', 'freezer_spec', 'freezer_process', 'freezer_toc'}),
    'roundtrip': frozenset({'catalog', 'workspace', 'install', 'verify', 'prepare_protocol',
                          'runtime_process', 'decode_result', 'remove', 'workspace_cleanup',
                          'prepare_af3', 'service_start', 'service_poll', 'service_import', 'service_shutdown', 'evidence_retention'}),
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
        fields = {'schema', 'error_type', 'stage', line_key, 'truncated'}
        if schema == FAILURE_SCHEMA:
            fields.update({'warning_observations', 'origin_failure'})
        if (not isinstance(value, dict)
                or set(value) != fields
                or value['schema'] != schema or value['error_type'] not in FAILURE_ERROR_TYPES
                or value['stage'] not in stages or type(value['truncated']) is not bool
                or not isinstance(value[line_key], list) or len(value[line_key]) > MAX_FAILURE_FRAMES
                or any(type(line) is not int or not 1 <= line <= 1000000 for line in value[line_key])):
            raise ValueError('Invalid diagnostic schema')
        if schema == FAILURE_SCHEMA:
            validate_warning_report(value['warning_observations'])
            from scripts.merizo_runtime_archive.runtime_origin import validate_origin_failure
            validate_origin_failure(value['origin_failure'])
        return {'status': 'validated', 'report': value}
    except FileNotFoundError:
        return {'status': 'missing'}
    except Exception:
        return {'status': 'rejected'}


def roundtrip(archive: Path, artifact, inputs, *, runner=run_managed_process, report=None,
              stage_events: bool = False, fixture=None, evidence_directory=None,
              source_identity_sha256=None, build_revision=None) -> dict:
    if fixture is not None:
        return service_roundtrip(archive, artifact, fixture, evidence_directory=evidence_directory,
            source_identity_sha256=source_identity_sha256, build_revision=build_revision,
            runner=runner, report=report, stage_events=stage_events)
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
                    notices = strict_json(text.encode('utf-8'))['process'].get('compatibility_notices')
                    if notices is not None:
                        run['compatibility_notices'] = notices  # Strict decoder validation completed above.
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
                if root is not None:
                    report['remove_failure_diagnostic'] = remove_failure_diagnostic(exc, root, manager, artifact)
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


def service_roundtrip(archive, artifact, fixture, *, evidence_directory, source_identity_sha256,
                      build_revision, runner=run_managed_process, report=None, stage_events=False):
    """Exactly two invocations: direct public PDB and real AF3 DomainJobService."""
    from kuma_core.kuro.domain_jobs import DomainJobService, TERMINAL_STATES
    from scripts.merizo_runtime_archive.public_fixture import create_af3_fixture, public_prepared
    from scripts.merizo_runtime_archive.execution_evidence import export_execution, strict_result
    from scripts.merizo_runtime_archive.runtime_origin import read_stable, MAX_ORIGIN_BYTES
    if report is None:
        report = {}
    if report:
        raise ValueError('Partial roundtrip report must start empty')
    report.update(catalog_scope='test_only_exact_archive_bytes', installed=False, verified=False,
                  removed=False, runs=[], status='running', current_stage='catalog',
                  temporary_storage_removed=False, cleanup_errors=[], invocation_count=0)
    root = manager = service = job_id = primary = None
    invocation_failures = []
    def checkpoint(stage):
        stage_event(report, 'roundtrip', stage, enabled=stage_events)
    try:
        checkpoint('catalog')
        if PRODUCTION_CATALOG or not Path(evidence_directory).is_dir():
            raise ValueError('Public audit requires empty production catalog and existing evidence directory')
        checkpoint('workspace')
        root = Path(tempfile.mkdtemp(prefix='kuma-runtime-roundtrip-')).resolve()
        manager = OptionalRuntimeManager(root / 'app', catalog={(artifact.engine, artifact.platform): artifact},
                                         platform_key=artifact.platform)
        checkpoint('prepare_af3')
        source, synthetic, recipe = create_af3_fixture(fixture, root / 'synthetic-af3.zip')
        public = public_prepared(fixture)
        rows = {}
        for name, prepared in (('public_1ubq', public), ('synthetic_af3_public_geometry', synthetic)):
            row = {'fixture': name, 'verified': False, 'process_invoked': False, 'process_succeeded': False,
                   'decoded': False, 'current_stage': 'verify', 'source_sha256': prepared.source_sha256,
                   'binding_sha256': prepared.binding_sha256}
            rows[name] = row
            report['runs'].append(row)
        service_failure = []
        def invoke(argv, prepared, name, **kwargs):
            row = rows[name]
            work, result = Path(kwargs['cwd']), Path(kwargs['result_path'])
            failure, origins = work / 'entry-failure.json', work / 'entry-origins.json'
            row['executable_sha256'] = digest(Path(argv[0]))
            row['verified'] = report['verified'] = True  # Real manager verify precedes each runner call.
            row['current_stage'] = 'runtime_process'
            stage_event(row, 'roundtrip', 'runtime_process', enabled=stage_events)
            if report['invocation_count'] >= 2 or kwargs.get('operation_lease') is None:
                raise ValueError('Public audit invocation/lease contract differs')
            report['invocation_count'] += 1
            row['process_invoked'] = True
            try:
                runner([*argv, '--audit-failure-report', str(failure), '--audit-origin-report', str(origins)], **kwargs)
                # The real runner returns only after owned process/lease cleanup.
                row['process_succeeded'] = True
                row['current_stage'] = 'decode_result'
                stage_event(row, 'roundtrip', 'decode_result', enabled=stage_events)
                raw = read_stable(result, 256 * 1024)
                _, annotation, envelope = strict_result(raw, prepared)
                row.update(decoded=True, residues=annotation.total_residues, domains=len(annotation.domains),
                           coverage=annotation.coverage, confidence=annotation.confidence,
                           result_sha256=hashlib.sha256(raw).hexdigest())
                notices = envelope['process'].get('compatibility_notices')
                if notices is not None:
                    row['compatibility_notices'] = notices
                row['current_stage'] = 'evidence_retention'
                stage_event(row, 'roundtrip', 'evidence_retention', enabled=stage_events)
                row['execution_evidence'] = export_execution(Path(evidence_directory), result, origins,
                    fixture=fixture, prepared=prepared, fixture_id=name, recipe=recipe, archive_sha256=artifact.archive_sha256,
                    executable_sha256=row['executable_sha256'], source_identity_sha256=source_identity_sha256,
                    build_revision=build_revision, runtime_artifact=strict_json(canonical(asdict(artifact))))
                row['current_stage'] = 'completed'
            except BaseException as exc:
                invocation_failures.append((exc, row['current_stage']))
                row['error_type'] = safe_error_type(exc)
                row['entry_diagnostic'] = read_failure(failure)
                try:
                    read_stable(origins, MAX_ORIGIN_BYTES)
                    row['origin_diagnostic'] = 'present_unvalidated'
                except FileNotFoundError:
                    row['origin_diagnostic'] = 'missing'
                except Exception:
                    row['origin_diagnostic'] = 'rejected'
                raise
        def service_runner(argv, **kwargs):
            try:
                return invoke(argv, synthetic, 'synthetic_af3_public_geometry', **kwargs)
            except BaseException as exc:
                service_failure.append(exc)
                raise
        service = DomainJobService(manager, runner=service_runner)
        checkpoint('install')
        if service.install(str(archive))['state'] != 'installed':
            raise ValueError('Service installation failed')
        report['installed'] = True
        checkpoint('verify')
        with manager.operation_lock() as lease:
            verified = manager.verify()
            if verified.state != 'installed' or not verified.executable_path:
                raise ValueError('Public runtime verification failed')
            work = root / 'public_1ubq'
            work.mkdir()
            pdb, manifest, result = work / 'input.pdb', work / 'input.json', work / 'result.json'
            checkpoint('prepare_protocol')
            pdb.write_bytes(public.normalized_pdb.encode('ascii'))
            write_json(manifest, domain_input_manifest(public))
            checkpoint('runtime_process')
            invoke([verified.executable_path, '--input-pdb', str(pdb), '--input-manifest', str(manifest),
                    '--output', str(result), '--device', 'cpu'], public, 'public_1ubq', cwd=work,
                   cancelled=lambda: False, timeout_seconds=300, output_limit=1024 * 1024,
                   result_path=result, result_limit=8 * 1024 * 1024, operation_lease=lease)
        checkpoint('service_start')
        job = service.start(source, attempt_id='76' * 16)
        job_id = job['job_id']
        checkpoint('service_poll')
        while job['state'] not in TERMINAL_STATES:
            time.sleep(0.02)
            job = service.poll(job_id)
        report['service_terminal_state'] = job['state']
        if job['state'] != 'succeeded':
            if service_failure:
                raise service_failure[0]
            raise ValueError('Public AF3 service job failed')
        checkpoint('service_import')
        imported = service.import_result(job_id, source)
        if (imported['provenance'] != 'managed' or imported['binding_sha256'] != synthetic.binding_sha256
                or imported['total_residues'] != 76 or report['invocation_count'] != 2):
            raise ValueError('Service import binding or invocation count differs')
        report['service_import'] = {'provenance': imported['provenance'], 'binding': imported['binding'],
                                    'binding_sha256': imported['binding_sha256'], 'decoded': True}
    except BaseException as exc:
        primary = exc
        failed_stage = next((stage for error, stage in invocation_failures if error is exc), report['current_stage'])
        report['failure'] = {'stage': failed_stage, 'error_type': safe_error_type(exc)}
    finally:
        def cleanup_failure(stage, exc):
            nonlocal primary
            row: dict = {'stage': stage, 'error_type': safe_error_type(exc)}
            if stage == 'remove' and root is not None and manager is not None:
                row['diagnostic'] = remove_failure_diagnostic(exc, root, manager, artifact)
            report['cleanup_errors'].append(row)
            if primary is None:
                primary = exc
                report['failure'] = {'stage': stage, 'error_type': safe_error_type(exc)}

        confirmed = True
        if service is not None:
            terminal = job_id is None
            if job_id is not None:
                try:
                    terminal = service.poll(job_id)['state'] in TERMINAL_STATES
                except BaseException as exc:
                    cleanup_failure('service_poll', exc)
            stopped = False
            if not terminal:
                checkpoint('service_shutdown')
                try:
                    confirmed = service.stop() is True
                except BaseException as exc:
                    confirmed = False
                    cleanup_failure('service_shutdown', exc)
                stopped = True
            # Normal completion exercises service.remove. If an interrupted job
            # required stop(), the closed service cannot admit mutations, so
            # remove through the same manager only after confirmed shutdown.
            remover = ((service.remove if terminal else manager.remove)
                       if confirmed and report['installed'] and manager is not None else None)
            if remover is not None:
                checkpoint('remove')
                try:
                    removed = remover()
                    report['removed'] = (removed['state'] if isinstance(removed, dict) else removed.state) == 'missing'
                    if not report['removed']:
                        raise ValueError('Public service registry removal failed')
                except BaseException as exc:
                    cleanup_failure('remove', exc)
            if not stopped:
                checkpoint('service_shutdown')
                try:
                    confirmed = service.stop() is True
                except BaseException as exc:
                    confirmed = False
                    cleanup_failure('service_shutdown', exc)
            report['service_shutdown_confirmed'] = confirmed
            if not confirmed and not any(row['stage'] == 'service_shutdown' for row in report['cleanup_errors']):
                cleanup_failure('service_shutdown', RuntimeError('Public service shutdown remains unverified'))
        checkpoint('workspace_cleanup')
        if root is not None and confirmed and (report['removed'] or not report['installed']):
            try:
                shutil.rmtree(root)
            except BaseException as exc:
                cleanup_failure('workspace_cleanup', exc)
        try:
            report['temporary_storage_removed'] = root is None or not root.exists()
        except BaseException as exc:
            report['temporary_storage_removed'] = False
            cleanup_failure('workspace_cleanup', exc)
        if not report['temporary_storage_removed'] and primary is None:
            cleanup_failure('workspace_cleanup', RuntimeError('Public audit cleanup remains unverified'))
        report['status'] = 'failed' if primary is not None else 'passed'
        report['current_stage'] = 'failed' if primary is not None else 'completed'
    if primary is not None:
        raise primary
    return report
