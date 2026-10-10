"""One bounded CI-only build and internal install/run/removal; JSON evidence only.

Never publishes binaries, models or source payloads and never edits the catalog.
Unresolved native/source correspondence remains a separate distribution gate.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.metadata
import json
import marshal
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time
import zipfile

from kuma_core.kuro.optional_runtime import current_platform_key, PRODUCTION_CATALOG
from scripts.merizo_runtime_archive.archive import normalize_archive
from scripts.merizo_runtime_archive.common import canonical, digest, read_regular, strict_json, write_json
from scripts.merizo_runtime_archive.freeze_spec import write_spec
from scripts.merizo_runtime_archive.cpython_origin import verify as verify_cpython_origin
from scripts.merizo_runtime_archive.provenance import installed_provenance, map_build_inputs, verify_source
from scripts.merizo_runtime_archive.roundtrip import public_inputs, roundtrip, read_failure, stage_event
from scripts.merizo_runtime_archive.runtime_entry import (
    MAX_RUNTIME_RESIDUES, safe_error_type, failure_lines, publish_failure,
)

PACKAGE = 'kuma-merizo'
BUILD_TIMEOUT_SECONDS = 600
MAX_SOURCE_COMPANION = 2 * 1024 * 1024 * 1024


def run_freezer(options):
    """CI-only owned driver; preserve safe evidence before compiler cleanup."""
    try:
        run = __import__('importlib').import_module('PyInstaller.__main__').run
        run(options)
    except BaseException as exc:
        if isinstance(exc, SystemExit) and exc.code in (None, 0):
            return
        lines, _, truncated = failure_lines(exc, {run_freezer.__code__: 'freezer'})
        try:
            publish_failure(Path.cwd() / 'freezer-failure.json', {
                'schema': 'kuma-merizo-freezer-failure-v1', 'error_type': safe_error_type(exc),
                'stage': 'freezer', 'freezer_lines': lines, 'truncated': truncated})
        except Exception:
            pass
        raise


def freeze(source, project, output, generated, *, report=None, stage_events: bool = False):
    from kuma_core.kuro.domain_process import run_managed_process
    if report is None:
        report = {}
    def checkpoint(stage):
        stage_event(report, 'freezer', stage, enabled=stage_events)
    checkpoint('freezer_dependencies')
    if importlib.metadata.version('pyinstaller') != '6.16.0':
        raise ValueError('Require PyInstaller 6.16.0')
    spec, toc = generated / 'runtime.spec', output / 'pyinstaller-toc.json'
    checkpoint('freezer_spec')
    write_spec(spec, source=source, project=project, generated=generated, evidence=toc, package_name=PACKAGE)
    options = ['--clean', '--noconfirm', '--distpath', str(output / 'dist'),
               '--workpath', str(output / 'work'), str(spec)]
    build_path = os.environ.get('PATH', '')
    if not build_path or len(build_path) > 65536 or any(c in build_path for c in '\0\r\n'):
        raise ValueError('Missing or invalid trusted CI build-tool path')
    # Compiler inspection/signing tools need the CI runner PATH. Restore only
    # that explicit value inside this CI-only driver, never runtime inference.
    environment = {'PATH': build_path, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0',
                   'SOURCE_DATE_EPOCH': '1690000000', 'MPLBACKEND': 'Agg',
                   'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1',
                   'CUDA_VISIBLE_DEVICES': ''}
    driver = generated / 'freeze_driver.py'
    driver.write_text('import os, sys\n' +
        'sys.dont_write_bytecode = True\n' +
        f'os.environ.update({environment!r})\n' +
        f'sys.path.insert(0, {str(project)!r})\n' +
        'from scripts.merizo_runtime_archive.build import run_freezer\n' +
        f'run_freezer({options!r})\n', encoding='utf-8')
    command = [sys.executable, str(driver)]
    # Reuse the application's actual process-group / Windows Job Object owner.
    # It proves tree exit and never targets a completed Windows PID with taskkill.
    checkpoint('freezer_process')
    try:
        run_managed_process(command, cwd=output, cancelled=lambda: False,
            timeout_seconds=BUILD_TIMEOUT_SECONDS, output_limit=1024 * 1024,
            result_path=toc, result_limit=32 * 1024 * 1024)
    except BaseException as exc:
        report['error_type'] = safe_error_type(exc)
        try:
            report['diagnostic'] = read_failure(output / 'freezer-failure.json',
                schema='kuma-merizo-freezer-failure-v1', line_key='freezer_lines', stages=frozenset({'freezer'}))
        except Exception:
            report['diagnostic'] = {'status': 'rejected'}
        raise
    checkpoint('freezer_toc')
    result = strict_json(read_regular(toc, 32 * 1024 * 1024))
    report['current_stage'] = 'completed'
    return result, command


def embedded_inventory(executable: Path) -> dict:
    readers = __import__('importlib').import_module('PyInstaller.archive.readers')
    reader = readers.CArchiveReader(str(executable))
    members, modules = [], []
    for name, row in reader.toc.items():
        kind = row[-1]
        if kind == 'z':
            pyz = reader.open_embedded_archive(name)
            for module in sorted(pyz.toc):
                code = pyz.extract(module)
                modules.append({'module': module, 'compiled_sha256': __import__('hashlib').sha256(marshal.dumps(code)).hexdigest()})
        # The container and embedded item hashes complement source TOC edges.
        blob = reader.extract(name)
        if blob is not None:
            if len(blob) > 256 * 1024 * 1024:
                raise ValueError('Embedded archive member exceeds evidence working-set bound')
            members.append({'name': name, 'typecode': kind, 'size': len(blob),
                            'sha256': __import__('hashlib').sha256(blob).hexdigest()})
    if not modules or len(modules) > 30000:
        raise ValueError('Missing or oversized frozen module inventory')
    distribution = importlib.metadata.distribution('pyinstaller')
    bootloaders = []
    for file in distribution.files or ():
        if 'bootloader/' in str(file) and Path(str(file)).name in {'run', 'runw', 'run.exe', 'runw.exe'}:
            path = Path(str(distribution.locate_file(file)))
            bootloaders.append({'wheel_member': str(file), 'sha256': digest(path), 'size': path.stat().st_size})
    standard_library = []
    base_library = executable.parent / '_internal/base_library.zip'
    if base_library.is_file():
        with zipfile.ZipFile(base_library) as archive:
            for name in sorted(archive.namelist()):
                raw = archive.read(name)
                path = Path(sysconfig.get_path('stdlib')) / (name[:-1] if name.endswith('.pyc') else name)
                standard_library.append({'member': name, 'compiled_sha256': __import__('hashlib').sha256(raw).hexdigest(),
                    'size': len(raw), 'source': str(path) if path.is_file() else None,
                    'source_sha256': digest(path) if path.is_file() else None})
    return {'container_sha256': digest(executable),
            'stdlib_archive_sha256': digest(base_library) if base_library.is_file() else None,
            'stdlib_compilation_inputs': standard_library, 'carchive_members': members, 'pyz_modules': modules,
            'bootloader_candidates': bootloaders, 'python_abi': sys.implementation.cache_tag,
            'compiler_flags': {'optimization': sys.flags.optimize},
            'native_processing_recipe': 'PyInstaller 6.16.0 process_collected_binary; strip=False, upx=False; default platform rewriting/signing',
            'reproducible_frozen_executable_claimed': False}


def source_companion(source, identity, project, generated, destination, cpython_origin=None, toc=None):
    files = [(source / row['path'], 'Merizo/' + row['path']) for row in identity['files']]
    recipe = sorted((project / 'scripts/merizo_runtime_archive').glob('*.py'))
    recipe += [project / 'scripts/merizo_runtime_archive/README.md', project / 'LICENSE', project / 'pyproject.toml']
    recipe += [project / 'kuma_core/kuro' / name for name in
               ('domain_annotation.py', 'domain_merizo.py', 'residue_mapping.py')]
    # Include every actually analyzed KUMA source module, including package
    # initializers and their transitive imports; three adapter files alone are
    # not the complete compilation input of an eager package initializer.
    for stage in ('Analysis.pure', 'Analysis.scripts'):
        for row in (toc or {}).get(stage, []):
            path = Path(row['source']).resolve()
            if path.is_relative_to(project) and path.suffix == '.py':
                recipe.append(path)
    recipe = sorted(set(recipe))
    recipe += sorted((project / '.github/workflows').glob('merizo*.yml'))
    recipe += [project / 'scripts/merizo_windows_smoke/requirements.txt',
               project / 'scripts/merizo_windows_smoke/freezer-requirements.txt']
    files += [(path, 'KUMA/' + path.relative_to(project).as_posix()) for path in recipe if path.is_file()]
    if cpython_origin is not None:
        for key in ('source_archive', 'provider_build_recipe'):
            path = Path(cpython_origin[key]['path'])
            files.append((path, 'CPython/' + path.name))
    files += [(path, 'build/' + path.name) for path in generated.iterdir() if path.is_file()]
    manifest = []
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED, allowZip64=False) as archive:
        for path, name in files:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            with archive.open(info, 'w') as outgoing, path.open('rb') as incoming:
                shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
            manifest.append({'path': name, 'sha256': digest(path), 'size': path.stat().st_size})
            if destination.stat().st_size > MAX_SOURCE_COMPANION:
                raise ValueError('Source companion exceeds declared bound')
    return {'sha256': digest(destination), 'size': destination.stat().st_size, 'files': manifest,
            'scope': 'exact_Merizo_tree_and_KUMA_adapter_recipe; native_corresponding_sources_incomplete',
            'future_delivery': 'unpublished; release requires matching freely accessible sufficient corresponding source'}


def package_legal(package, source, provenance, source_record):
    legal = {'Merizo': {'license_sha256': digest(source / 'LICENSE'),
                       'license_text': (source / 'LICENSE').read_text(encoding='utf-8'),
                       'root_grant_scope': 'root GPLv3 reasonably covers co-located source and weights; model-source obligations remain reviewable'},
             'wheel_original_texts': provenance['legal_texts'], 'components': provenance['components']}
    python_license = None
    for path in (Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE',
                 Path(sys.base_prefix) / 'lib/python3.11/LICENSE.txt'):
        if path.is_file():
            raw = read_regular(path, 4 * 1024 * 1024)
            python_license = {'sha256': digest(path), 'text': raw.decode('utf-8-sig')}
            break
    legal['CPython'] = python_license
    write_json(package / 'LEGAL.json', legal)
    write_json(package / 'SOURCES.json', source_record)
    write_json(package / 'CAPABILITIES.json', {'schema': 'kuma-merizo-capabilities-v1',
        'device': 'cpu', 'input_schema': 'kuma-domain-input-v1', 'output_schema': 'kuma-merizo-result-v1',
        'max_residues': MAX_RUNTIME_RESIDUES,
        'max_residues_basis': 'conservative implementation allocation guard, not measured safe capacity',
        'feature_tensor_bytes_at_guard': 4 * (MAX_RUNTIME_RESIDUES ** 2 + 33 * MAX_RUNTIME_RESIDUES) + 8 * MAX_RUNTIME_RESIDUES,
        'feature_memory_scope': 'returned s/z/r/t/ri float32 plus b float64 only; excludes temporaries and network activations; not a peak memory bound',
        'validated_biological_fixture_lengths': [76], 'biological_accuracy_validated': False})
    (package / 'NOTICE.txt').write_text(
        'KUMA optional Merizo CPU runtime: INTERNAL TEST CANDIDATE, NOT A RELEASE.\n'
        'Merizo: psipred/Merizo commit 41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd.\n'
        'Root GPLv3 grant and original copyright/license/notice texts are in LEGAL.json.\n'
        'KUMA adapter is supplied as source in the matching internal source companion.\n'
        'Changes: managed CPU CLI, strict input/result validation, offline packaging; upstream source/model bytes unchanged.\n'
        'SOURCES.json binds the source companion to exact bytes and identifies incomplete native source correspondence.\n'
        'CAPABILITIES.json describes conservative input allocation limits and validation scope.\n'
        'No biological function or accuracy claim; no redistribution clearance is granted by this audit.\n', encoding='utf-8')
    return {'original_texts_sha256': digest(package / 'LEGAL.json'), 'python_text_found': python_license is not None}


def output_edges(records, toc, executable):
    source_rows = {}
    for stage in ('Analysis.binaries', 'Analysis.datas', 'COLLECT.input'):
        for row in toc.get(stage, []):
            source_rows.setdefault(row['destination'], []).append(row)
    edges, unresolved = [], []
    for row in records:
        logical = row['path'].removeprefix('_internal/')
        canonical_destination = row['original_path'].removeprefix('_internal/')
        candidates = source_rows.get(logical, [])
        if canonical_destination != logical:
            candidates += source_rows.get(canonical_destination, [])
        exact = [candidate for candidate in candidates if candidate.get('sha256') == row['sha256']]
        edge = {'path': row['path'], 'sha256': row['sha256'], 'size': row['size'],
                'executable': row['executable'], 'aliases': row['aliases'], 'original_path': row['original_path']}
        if row['path'] == executable:
            edge.update(mapping='composite_executable', provenance='embedded_inventory_and_PKG_EXE_TOC')
        elif exact:
            edge.update(mapping='exact_build_input', inputs=exact)
        elif row['path'] in {'LEGAL.json', 'NOTICE.txt', 'SOURCES.json', 'CAPABILITIES.json'}:
            edge.update(mapping='generated_review_payload', provenance='hashed_recipe_and_collected_original_texts')
        else:
            edge.update(mapping='transformed_or_unmapped', inputs=candidates)
            unresolved.append({'kind': 'output_transform_or_ownership', 'path': row['path'],
                               'output_sha256': row['sha256'], 'input_sha256': [item.get('sha256') for item in candidates]})
        edges.append(edge)
    return edges, unresolved


def build(args) -> int:
    started = time.perf_counter()
    source, output, evidence = args.source.resolve(), args.output_directory.resolve(), args.evidence.resolve()
    project = Path(__file__).resolve().parents[2]
    report = {'schema': 'kuma-merizo-runtime-audit-v1', 'status': 'blocked',
              'scope': 'internal_candidate_archive_and_managed_CPU_inference_only',
              'distribution_cleared': False, 'production_catalog_modified': False, 'truncated': False,
              'unresolved': [], 'cleanup': {}, 'current_stage': 'preflight'}
    stage_events = os.environ.get('GITHUB_ACTIONS') == 'true'
    def checkpoint(stage):
        stage_event(report, 'build', stage, enabled=stage_events)
    created = False
    exit_code = 2
    try:
        checkpoint('preflight')
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            raise ValueError('Real build is restricted to the authorized internal CI experiment')
        if PRODUCTION_CATALOG or current_platform_key() not in {'linux-x86_64', 'windows-x86_64', 'macos-arm64'}:
            raise ValueError('Unexpected catalog or target')
        if (output.exists() or output == source or source.is_relative_to(output) or output.is_relative_to(source)
                or evidence.is_relative_to(output) or evidence.is_relative_to(source)):
            raise ValueError('Build directory must be fresh and disjoint from source/evidence')
        checkpoint('public_fixture')
        inputs = public_inputs(args.fixture)
        checkpoint('source_verification')
        identity = verify_source(source)
        checkpoint('installed_provenance')
        provenance = installed_provenance(args.input_lock, args.wheelhouse)
        checkpoint('cpython_origin')
        origin = None if args.cpython_origin is None else verify_cpython_origin(
            strict_json(read_regular(args.cpython_origin, 8 * 1024 * 1024)))
        report['inputs'] = {'source': identity, 'wheels': provenance, 'candidate_pin_status': 'candidate_inputs_unreviewed'}
        checkpoint('build_identity')
        report['build'] = {'target': current_platform_key(), 'python': platform.python_version(),
                           'build_commit': subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip(),
                           'run_id': os.environ.get('GITHUB_RUN_ID'), 'runner_image': os.environ.get('ImageOS'),
                           'runner_image_version': os.environ.get('ImageVersion'), 'pyinstaller': '6.16.0',
                           'recipe_sha256': {path.name: digest(path) for path in Path(__file__).parent.glob('*.py')}}
        checkpoint('build_workspace')
        output.mkdir(parents=True, exist_ok=False)
        created = True
        generated = output / 'generated'
        generated.mkdir()
        write_json(generated / 'merizo-source-identity.json', identity)
        identity_sha = digest(generated / 'merizo-source-identity.json')
        (generated / '_merizo_build_identity.py').write_text(f'SOURCE_IDENTITY_SHA256 = {identity_sha!r}\nINTERNAL_AUDIT = True\n', encoding='ascii')
        shutil.copyfile(args.input_lock, generated / 'input-lock.json')
        checkpoint('freeze')
        report['freezer'] = {}
        toc, command = freeze(source, project, output, generated, report=report['freezer'], stage_events=stage_events)
        checkpoint('source_reverification')
        if verify_source(source) != identity:
            raise ValueError('Official source changed during freeze')
        report['build']['command'] = command
        report['pyinstaller'] = toc
        report['build']['kuma_compilation_modules'] = [row['destination'] for row in toc.get('Analysis.pure', [])
                                                       if row['destination'].startswith('kuma_core')]
        checkpoint('build_input_mapping')
        mapping = map_build_inputs(toc, provenance, source, identity, project, origin)
        report['provenance'] = mapping
        report['unresolved'].extend(mapping['unresolved'])
        package = output / 'dist' / PACKAGE
        entry = PACKAGE + ('.exe' if os.name == 'nt' else '')
        checkpoint('embedded_inventory')
        report['embedded'] = embedded_inventory(package / entry)
        toc['stdlib.compilation'] = [{'destination': row['member'], 'source': row['source'],
            'typecode': 'PYMODULE', 'sha256': row['source_sha256']}
            for row in report['embedded']['stdlib_compilation_inputs'] if row['source']]
        checkpoint('stdlib_mapping')
        stdlib_mapping = map_build_inputs({'stdlib.compilation': toc['stdlib.compilation']},
                                         {'installed_files': provenance['installed_files'], 'unresolved': []},
                                         source, identity, project, origin)
        report['provenance']['edges'].extend(stdlib_mapping['edges'])
        report['unresolved'].extend(stdlib_mapping['unresolved'])
        checkpoint('source_companion')
        source_record = source_companion(source, identity, project, generated, output / 'source-companion.zip', origin, toc)
        report['sources'] = source_record
        checkpoint('package_notices')
        report['notices'] = package_legal(package, source, provenance, source_record)
        checkpoint('normalize_archive')
        artifact, records = normalize_archive(package, output / 'archive', version='internal-41d12fb-v1',
                                             platform=current_platform_key(), executable=entry)
        checkpoint('output_mapping')
        report['files'], gaps = output_edges(records, toc, entry)
        report['unresolved'].extend(gaps)
        report['archive'] = {'candidate_manifest': asdict(artifact), 'installed_bytes': sum(row['size'] for row in records),
                              'file_count': len(records), 'alias_files': sum(bool(row['aliases']) for row in records)}
        checkpoint('remove_original_source')
        if args.remove_source_before_run:
            shutil.rmtree(source)
            if source.exists():
                raise ValueError('Original source removal failed')
        report['original_source_removed_before_run'] = not source.exists()
        checkpoint('archive_roundtrip')
        report['archive']['roundtrip'] = {}
        roundtrip(output / 'archive/runtime.zip', artifact, inputs,
                  report=report['archive']['roundtrip'], stage_events=stage_events)
        report['unresolved'].extend([{'kind': 'candidate_inputs_unreviewed'},
            {'kind': 'native_source_and_license_obligation_review'},
            {'kind': 'product_dependency_security_baseline'}, {'kind': 'source_delivery_and_rights_review'}])
        report['current_stage'] = 'completed'
        report['status'] = 'internal_roundtrip_passed_distribution_blocked'
        exit_code = 0
    except Exception as exc:
        report['failure_stage'] = report['current_stage']
        report['error'] = {'type': safe_error_type(exc), 'message': str(exc)[:2048]}
        exit_code = 2
    finally:
        stage_event(report['cleanup'], 'cleanup', 'build_payload_cleanup', enabled=stage_events)
        if created:
            try:
                shutil.rmtree(output)
                report['cleanup']['build_archive_source_companion_removed'] = not output.exists()
                if output.exists():
                    raise OSError('Build payload remains after cleanup')
            except OSError as exc:
                report['cleanup']['build_archive_source_companion_removed'] = False
                report['cleanup']['error_type'] = type(exc).__name__
                report['status'] = 'cleanup_failed'
                exit_code = 2
        report['cleanup']['original_source_exists'] = source.exists()
        report['cleanup']['current_stage'] = 'failed' if report['cleanup'].get('error_type') else 'completed'
        report['elapsed_seconds'] = time.perf_counter() - started
        # Written only after owned process calls and this controller's finally.
        report['execution_controller_completed'] = True
        try:
            write_json(evidence, report)
        except ValueError as exc:
            # A bounded failure summary is not a silently truncated audit.
            write_json(evidence, {'schema': 'kuma-merizo-runtime-audit-v1',
                'status': 'audit_size_or_serialization_blocked', 'scope': 'failure_summary_only',
                'complete_audit_written': False, 'distribution_cleared': False,
                'execution_controller_completed': True,
                'production_catalog_modified': False, 'truncated': False,
                'unresolved': [{'kind': 'complete_audit_exceeds_bound_or_serialization_failed'}],
                'cleanup': report['cleanup'], 'error_type': type(exc).__name__,
                'failure_stage': report.get('failure_stage'), 'current_stage': report['current_stage'],
                'original_error': report.get('error'), 'freezer': report.get('freezer'),
                'roundtrip': report.get('archive', {}).get('roundtrip')})
            exit_code = 2
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--input-lock', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--cpython-origin', type=Path)
    parser.add_argument('--remove-source-before-run', action='store_true')
    return build(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
