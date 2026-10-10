"""Internal archive install -> verification -> managed CPU CLI -> decoder -> removal."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile

from kuma_core.kuro.domain_annotation import prepare_domain_input
from kuma_core.kuro.domain_merizo import decode_merizo_result, domain_input_manifest
from kuma_core.kuro.domain_process import run_managed_process
from kuma_core.kuro.optional_runtime import OptionalRuntimeManager, PRODUCTION_CATALOG
from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId
from scripts.merizo_runtime_archive.common import digest, read_regular, write_json

PUBLIC_SHA = 'd4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161'
SEQUENCE = 'MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG'


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


def roundtrip(archive: Path, artifact, inputs, *, runner=run_managed_process) -> dict:
    if PRODUCTION_CATALOG:
        raise ValueError('Internal audit must not activate the production catalog')
    report = {'catalog_scope': 'test_only_exact_archive_bytes', 'installed': False,
              'verified': False, 'removed': False, 'runs': []}
    with tempfile.TemporaryDirectory(prefix='kuma-runtime-roundtrip-') as temporary:
        root = Path(temporary).resolve()
        manager = OptionalRuntimeManager(root / 'app', catalog={(artifact.engine, artifact.platform): artifact},
                                         platform_key=artifact.platform)
        try:
            status = manager.install(archive)
            if status.state != 'installed':
                raise ValueError('Registry installation did not succeed')
            report['installed'] = True
            for name, prepared in inputs:
                with manager.operation_lock() as lease:
                    verified = manager.verify()
                    if verified.state != 'installed' or not verified.executable_path:
                        raise ValueError('Registry verification failed after extraction')
                    report['verified'] = True
                    report['executable_sha256'] = digest(Path(verified.executable_path))
                    work = root / name
                    work.mkdir()
                    pdb, manifest, result = work / 'input.pdb', work / 'input.json', work / 'result.json'
                    pdb.write_text(prepared.normalized_pdb, encoding='ascii', newline='\n')
                    write_json(manifest, domain_input_manifest(prepared))
                    runner([verified.executable_path, '--input-pdb', str(pdb), '--input-manifest', str(manifest),
                            '--output', str(result), '--device', 'cpu'], cwd=work, cancelled=lambda: False,
                           timeout_seconds=300, output_limit=1024 * 1024, result_path=result,
                           result_limit=8 * 1024 * 1024, operation_lease=lease)
                    text = read_regular(result, 8 * 1024 * 1024).decode('utf-8')
                    annotation = decode_merizo_result(text, prepared, current_binding_sha256=prepared.binding_sha256)
                    report['runs'].append({'fixture': name, 'decoded': True, 'source_sha256': prepared.source_sha256,
                        'binding_sha256': prepared.binding_sha256, 'residues': annotation.total_residues,
                        'domains': len(annotation.domains), 'coverage': annotation.coverage,
                        'confidence': annotation.confidence, 'result_sha256': digest(result)})
        finally:
            if report['installed']:
                report['removed'] = manager.remove().state == 'missing'
                if not report['removed']:
                    raise ValueError('Internal registry removal failed')
    report['temporary_storage_removed'] = not root.exists()
    return report
