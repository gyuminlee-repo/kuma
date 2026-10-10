"""Strict, public-fixture-only exact result/origin export and offline decode replay."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import tempfile

from kuma_core.kuro.domain_merizo import decode_merizo_result, domain_input_manifest
from scripts.merizo_runtime_archive.common import canonical, strict_json
from scripts.merizo_runtime_archive.runtime_origin import (
    MAX_ORIGIN_BYTES, publish_exclusive, read_stable, validate_origins,
)

SCHEMA = 'kuma-merizo-public-execution-evidence-v1'
MAX_EXECUTION_BYTES = 1024 * 1024
MAX_PUBLIC_RESULT_BYTES = 256 * 1024
FILENAMES = {'public_1ubq': 'archive-public-1ubq-execution.json',
             'synthetic_af3_public_geometry': 'archive-synthetic-af3-execution.json'}


def strict_result(raw, prepared):
    if not isinstance(raw, bytes) or len(raw) > MAX_PUBLIC_RESULT_BYTES:
        raise ValueError('Public result exceeds export bound')
    text = raw.decode('utf-8', errors='strict')
    if text.startswith('\ufeff') or text.encode('utf-8') != raw:
        raise ValueError('Public result is not byte-identical strict UTF-8')
    data = strict_json(raw)
    if (not isinstance(data, dict) or set(data) != {'schema', 'tool_commit', 'weights_sha256', 'input',
                                                   'process', 'features', 'prediction'}):
        raise ValueError('Unexpected public result fields')
    for field, required, optional in (
        ('process', {'status', 'exit_code', 'warnings'}, {'compatibility_notices'}),
        ('features', {'nres', 'sequence', 'residue_numbers', 'ca_coordinates'}, set()),
        ('prediction', {'nres', 'ndom', 'labels', 'residue_numbers', 'confidence', 'time_sec'}, set()),
    ):
        value = data[field]
        if not isinstance(value, dict) or not required <= set(value) or not set(value) <= required | optional:
            raise ValueError('Unexpected nested public result fields')
    annotation = decode_merizo_result(text, prepared, current_binding_sha256=prepared.binding_sha256)
    return text, annotation, data


def validate_execution(value, *, prepared, fixture_id, recipe, archive_sha256,
                       executable_sha256, source_identity_sha256, build_revision):
    keys = {'schema', 'fixture', 'fixture_recipe', 'archive_sha256', 'executable_sha256',
            'source_identity_sha256', 'build_revision', 'input_binding_sha256',
            'result_text', 'result_sha256', 'result_bytes', 'origins'}
    if not isinstance(value, dict) or set(value) != keys or value['schema'] != SCHEMA or fixture_id not in FILENAMES:
        raise ValueError('Invalid public execution evidence schema')
    expected = {'fixture': fixture_id, 'fixture_recipe': recipe, 'archive_sha256': archive_sha256,
                'executable_sha256': executable_sha256, 'source_identity_sha256': source_identity_sha256,
                'build_revision': build_revision, 'input_binding_sha256': prepared.binding_sha256}
    if any(canonical(value[key]) != canonical(item) for key, item in expected.items()):
        raise ValueError('Public execution evidence identity differs')
    for key in ('archive_sha256', 'executable_sha256', 'source_identity_sha256', 'input_binding_sha256', 'result_sha256'):
        if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{64}', value[key]):
            raise ValueError('Invalid execution evidence hash')
    if not isinstance(value['build_revision'], str) or not re.fullmatch('[0-9a-f]{40}', value['build_revision']):
        raise ValueError('Invalid generator/build revision')
    if not isinstance(value['result_text'], str):
        raise ValueError('Public result text missing')
    raw = value['result_text'].encode('utf-8', errors='strict')
    if (type(value['result_bytes']) is not int or value['result_bytes'] != len(raw)
            or hashlib.sha256(raw).hexdigest() != value['result_sha256']):
        raise ValueError('Exact public result bytes differ')
    _, annotation, _ = strict_result(raw, prepared)
    validate_origins(value['origins'], executable_sha256=executable_sha256,
                     binding_sha256=prepared.binding_sha256, source_identity_sha256=source_identity_sha256)
    if len(canonical(value)) + 1 > MAX_EXECUTION_BYTES:
        raise ValueError('Public execution evidence exceeds complete bound')
    return annotation


def export_execution(directory: Path, result: Path, origins: Path, *, fixture: Path, prepared, fixture_id,
                     recipe, archive_sha256, executable_sha256, source_identity_sha256, build_revision):
    from scripts.merizo_runtime_archive.public_fixture import create_af3_fixture, public_prepared
    with tempfile.TemporaryDirectory(prefix='kuma-public-export-') as temporary:
        _, synthetic, known_recipe = create_af3_fixture(fixture, Path(temporary).resolve(strict=True) / 'synthetic.zip')
        known = public_prepared(fixture) if fixture_id == 'public_1ubq' else synthetic
        if (fixture_id not in FILENAMES or canonical(recipe) != canonical(known_recipe)
                or canonical(domain_input_manifest(prepared)) != canonical(domain_input_manifest(known))):
            raise ValueError('Export requires exact independently regenerated public fixture')
    raw = read_stable(result, MAX_PUBLIC_RESULT_BYTES)
    text, _, _ = strict_result(raw, prepared)
    value = {'schema': SCHEMA, 'fixture': fixture_id, 'fixture_recipe': recipe,
             'archive_sha256': archive_sha256, 'executable_sha256': executable_sha256,
             'source_identity_sha256': source_identity_sha256, 'build_revision': build_revision,
             'input_binding_sha256': prepared.binding_sha256, 'result_text': text,
             'result_sha256': hashlib.sha256(raw).hexdigest(), 'result_bytes': len(raw),
             'origins': strict_json(read_stable(origins, MAX_ORIGIN_BYTES))}
    validate_execution(value, prepared=prepared, fixture_id=fixture_id, recipe=recipe, archive_sha256=archive_sha256,
                       executable_sha256=executable_sha256, source_identity_sha256=source_identity_sha256,
                       build_revision=build_revision)
    output = directory / FILENAMES[fixture_id]
    serialized = canonical(value) + b'\n'
    publish_exclusive(output, serialized, MAX_EXECUTION_BYTES)
    return {'filename': output.name, 'sha256': hashlib.sha256(serialized).hexdigest(), 'bytes': len(serialized),
            'result_sha256': value['result_sha256'], 'result_bytes': len(raw),
            'input_binding_sha256': prepared.binding_sha256, 'origin_phases': ['before_weights', 'after_inference']}


def replay_execution(path: Path, fixture: Path, *, archive_sha256, executable_sha256,
                     source_identity_sha256, build_revision):
    """Regenerate the public input and decode, never execute the runtime/model."""
    from scripts.merizo_runtime_archive.public_fixture import create_af3_fixture, public_prepared
    value = strict_json(read_stable(path, MAX_EXECUTION_BYTES))
    if not isinstance(value, dict) or value.get('fixture') not in FILENAMES:
        raise ValueError('Unknown public replay fixture')
    with tempfile.TemporaryDirectory(prefix='kuma-public-replay-') as temporary:
        _, synthetic, recipe = create_af3_fixture(fixture, Path(temporary).resolve(strict=True) / 'synthetic.zip')
        # Exact regenerated recipe includes generator bytes, ZIP SHA and full
        # input binding. No trusting a version label or reported geometry alone.
        prepared = public_prepared(fixture) if value['fixture'] == 'public_1ubq' else synthetic
        return validate_execution(value, prepared=prepared, fixture_id=value['fixture'], recipe=recipe,
            archive_sha256=archive_sha256, executable_sha256=executable_sha256,
            source_identity_sha256=source_identity_sha256, build_revision=build_revision)
