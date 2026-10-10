"""Local prediction evidence adapter for strict selection and a derived CA trace.

Scientific coordinates and full source identities stay in the certificate. The
viewer derivative uses reference numbering only and never supplies new geometry.
"""
from __future__ import annotations

import hashlib
import math

from kuma_core.kuro.alphafold import _THREE_TO_ONE
from kuma_core.kuro.prediction_bundle import load_prediction_bundle
from kuma_core.kuro.residue_mapping import confidence_diagnostics


def prediction_context(path: str, model_id: str, chain_id: str, reference: str,
                       expected_bundle_sha256: str) -> dict:
    reference = reference.strip().rstrip('*')
    evidence = load_prediction_bundle(path, model_id, chain_id, reference,
                                     expected_bundle_sha256=expected_bundle_sha256)
    if len(reference) > 9999:
        raise ValueError('Reference exceeds the bounded CA-trace viewer numbering capacity')
    confidence = confidence_diagnostics(evidence.mapping, plddt=evidence.plddt, pae=evidence.pae)
    three = {v: k for k, v in _THREE_TO_ONE.items() if k not in {"MSE", "SEC", "PYL"}}
    records: list[dict] = []
    lines: list[str] = []
    missing: list[int] = []
    for residue in evidence.mapping.residues:
        identity, xyz, p = residue.residue_id, residue.coordinate, residue.reference_position
        if identity is None or xyz is None:
            missing.append(p)
            continue
        columns = [f'{value:8.3f}' for value in xyz]
        if any(len(value) != 8 for value in columns):
            raise ValueError('Coordinate exceeds the bounded CA-trace display range')
        display_xyz = tuple(float(value) for value in columns)
        if math.dist(xyz, display_xyz) > math.sqrt(3) * 0.000501:
            raise ValueError('CA-trace display precision cannot preserve the source coordinate')
        # B=0 is a display placeholder. Confidence comes only from paired evidence.
        lines.append(f'ATOM  {len(lines)+1:5d}  CA  {three[residue.reference_aa]:3s} A{p:4d}    '
                     + ''.join(columns) + '  1.00  0.00           C')
        records.append({'reference_position': p, 'polymer_position': residue.polymer_position,
                        'structure_position': identity.author_number, 'chain_id': identity.chain_id,
                        'model_id': identity.model_id, 'insertion_code': identity.insertion_code,
                        'coordinate': xyz, 'viewer_position': p, 'viewer_chain_id': 'A',
                        'viewer_insertion_code': ''})
    if not records:
        raise ValueError('Imported prediction has no mapped CA coordinates')
    display = '\n'.join(lines) + '\nEND\n'
    pae_values = ([] if evidence.pae is None else
                  [v for i, row in enumerate(evidence.pae.values) for j, v in enumerate(row)
                   if i != j and v is not None])
    pae_mean = math.fsum(v / len(pae_values) for v in pae_values) if pae_values else None
    return {
        'schema_version': 1, 'source_accession': 'local-prediction',
        'source_sha256': evidence.structure_sha256,
        'reference_sha256': hashlib.sha256(reference.encode()).hexdigest(),
        'coordinate_frame': 'reference', 'mapping': records, 'pdb_text': display, 'structure_format': 'pdb',
        'selection_policy': 'single-site-full-pool-fps-v1',
        'prediction_bundle': {
            'format': evidence.format, 'source_name': evidence.source_name,
            'bundle_sha256': evidence.bundle_sha256, 'model_id': evidence.model_id,
            'chain_id': evidence.chain_id, 'author_chain_id': evidence.mapping.polymer.chain_id,
            'structure_member': evidence.structure_member, 'confidence_member': evidence.confidence_member,
            'structure_sha256': evidence.structure_sha256, 'confidence_sha256': evidence.confidence_sha256,
            'source_url': evidence.source_terms[0].url, 'terms_url': evidence.source_terms[1].url,
            'source_notices': [{'member': n.member, 'sha256': n.sha256, 'text': n.text} for n in evidence.notices],
            'sequence_member': evidence.sequence_member, 'sequence_sha256': evidence.sequence_sha256,
            'display_sha256': hashlib.sha256(display.encode()).hexdigest(),
            'display_kind': 'reference-ca-trace', 'plddt_by_reference': list(confidence.plddt_by_reference),
            'plddt_source': evidence.plddt.provenance.source,
            'pae': {'status': 'available' if evidence.pae is not None else 'unavailable',
                    'source': evidence.pae.provenance.source if evidence.pae is not None else None,
                    'dimension': len(evidence.mapping.polymer.sequence),
                    'mean': pae_mean, 'max': max(pae_values) if pae_values else None,
                    'scope': 'selected-chain-polymer', 'directional': True},
            'interdomain_confidence': 'not_assessed', 'warnings': list(evidence.warnings),
            'missing_reference_positions': missing,
        },
    }
