"""Managed Merizo CPU CLI. No downloads, input discovery, or external Python.

The process owner supplies private files and owns timeout/cancellation. This
entry verifies prepared input and build-bound source/model bytes before imports
or pickle loading, then atomically publishes only a fully decoded result.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import re
import sys
import sysconfig
import struct
import tempfile
import time
import warnings
from types import CodeType

from kuma_core.kuro.domain_annotation import DomainInput, MAX_SOURCE_BYTES, MAX_RESULT_BYTES
from kuma_core.kuro.domain_merizo import (
    MERIZO_COMMIT, MERIZO_WEIGHTS_SHA256, decode_merizo_result,
    domain_input_manifest, expected_ca_coordinates,
)
from kuma_core.kuro.residue_mapping import ResidueId
from scripts.merizo_runtime_archive.common import (
    MAX_INPUT_MANIFEST_BYTES, canonical, digest, read_regular, strict_json, write_json,
)

CPU_TORCH = {('Linux', 'x86_64'): '2.0.1+cpu', ('Windows', 'AMD64'): '2.0.1+cpu',
             ('Darwin', 'arm64'): '2.0.1'}
MAX_SOURCE_IDENTITY_BYTES = 2 * 1024 * 1024
MAX_RUNTIME_RESIDUES = 2000  # Unmeasured conservative allocation guard, not safe-capacity evidence.
MAX_FAILURE_BYTES = 4096
MAX_FAILURE_FRAMES = 32
FAILURE_SCHEMA = 'kuma-merizo-entry-failure-v1'
FAILURE_ERROR_TYPES = frozenset({'ValueError', 'TypeError', 'KeyError', 'IndexError', 'RuntimeError',
    'ImportError', 'ModuleNotFoundError', 'OSError', 'FileNotFoundError', 'PermissionError',
    'MemoryError', 'OverflowError', 'AssertionError', 'TimeoutError', 'InputLimitError',
    'DomainAnnotationError', 'DomainProcessError', 'DomainProcessCancelled', 'SystemExit', 'OtherError'})
FAILURE_STAGES = frozenset({'bootstrap', 'execute', 'input_validation', 'payload_verification',
                          'architecture', 'inference', 'feature_validation', 'result_envelope'})


class InputLimitError(ValueError):
    """A public capability refusal, before any tensor allocation."""


def load_prepared(pdb: Path, manifest: Path) -> DomainInput:
    raw = read_regular(pdb, MAX_SOURCE_BYTES)
    metadata = strict_json(read_regular(manifest, MAX_INPUT_MANIFEST_BYTES))
    if not isinstance(metadata, dict):
        raise ValueError('Input manifest must be an object')
    sequence = metadata.get('sequence')
    if not isinstance(sequence, str) or not 1 <= len(sequence) <= MAX_RUNTIME_RESIDUES:
        raise InputLimitError('CPU runtime supports 1..2000 complete residues per job')
    residues = metadata.get('residues')
    if not isinstance(residues, list) or len(residues) != len(sequence):
        raise ValueError('Manifest residue count differs from sequence')
    fields = {'model_id', 'chain_id', 'author_number', 'insertion_code'}
    identities = []
    for position, row in enumerate(residues, 1):
        if not isinstance(row, dict) or set(row) != fields | {
            'normalized_position', 'reference_position', 'polymer_position'}:
            raise ValueError('Unexpected residue identity fields')
        if any(type(row[key]) is not int or row[key] != position for key in
               ('normalized_position', 'reference_position', 'polymer_position')):
            raise ValueError('Residue identity is not complete and ordered')
        identities.append(ResidueId(**{key: row[key] for key in fields}))
    text_fields = ('source_sha256', 'reference_sha256', 'normalized_sha256', 'binding_sha256',
                   'polymer_source', 'frame_id', 'model_id', 'chain_id')
    if any(not isinstance(metadata.get(key), str) or not metadata[key]
           or len(metadata[key].encode('utf-8')) > 16384 for key in text_fields):
        raise ValueError('Invalid input identity text')
    prepared = DomainInput(normalized_pdb=raw.decode('ascii'), sequence=sequence,
                           residues=tuple(identities), **{key: metadata[key] for key in text_fields})
    if canonical(metadata) != canonical(domain_input_manifest(prepared)):
        raise ValueError('Input manifest has missing, extra or inconsistent fields')
    expected_ca_coordinates(prepared)  # Reapply the full-atom, finite-coordinate gate.
    return prepared


def verify_payload(internal: Path, expected_identity_sha256: str) -> tuple[Path, Path, dict]:
    """The manifest hash is compiled into the entry's generated build module."""
    if not re.fullmatch('[0-9a-f]{64}', expected_identity_sha256):
        raise ValueError('Missing compiled source identity')
    raw = read_regular(internal / 'merizo-source-identity.json', MAX_SOURCE_IDENTITY_BYTES)
    if hashlib.sha256(raw).hexdigest() != expected_identity_sha256:
        raise ValueError('Source identity differs from the compiled build identity')
    identity = strict_json(raw)
    if (identity.get('schema') != 'kuma-merizo-source-v1' or identity.get('commit') != MERIZO_COMMIT
            or not isinstance(identity.get('python_files'), dict)
            or not 1 <= len(identity['python_files']) <= 128):
        raise ValueError('Unpinned source identity')
    source, weights = internal / 'merizo_source', internal / 'merizo_weights'
    for directory in (source, weights):
        if (not directory.is_dir() or directory.is_symlink()
                or getattr(directory.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Runtime source/model root must be a real directory')
    actual = {}
    # Do not follow directory aliases at runtime. The builder normalizes them.
    for base, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            path = Path(base) / name
            if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                raise ValueError('Runtime source aliases are forbidden')
        for name in files:
            path = Path(base) / name
            relative = path.relative_to(source).as_posix()
            if not name.endswith('.py') or path.stat().st_size > MAX_SOURCE_IDENTITY_BYTES:
                raise ValueError('Unexpected runtime source file')
            actual[relative] = digest(path)
    if actual != identity['python_files']:
        raise ValueError('Pinned source bytes mismatch before model loading')
    if not weights.is_dir() or {p.name for p in weights.iterdir()} != set(MERIZO_WEIGHTS_SHA256):
        raise ValueError('Unexpected model file set')
    for name, expected in MERIZO_WEIGHTS_SHA256.items():
        path = weights / name
        info = path.lstat()
        if (path.is_symlink() or not path.is_file() or info.st_size > 512 * 1024 * 1024
                or getattr(info, 'st_file_attributes', 0) & 0x400):
            raise ValueError('Invalid model file')
        if digest(path) != expected:
            raise ValueError('Pinned model SHA-256 mismatch before torch.load')
    return source, weights, identity


def validate_features(features: dict, prepared: DomainInput, features_module, torch) -> dict:
    length = len(prepared.sequence)
    raw_positions = features['ri'].flatten().tolist()
    # Pinned Merizo intentionally stores ri as float32 for ALiBi. Only exact
    # finite 1..N values are converted to protocol integer identities.
    if (type(features['nres']) is not int or features['nres'] != length
            or len(raw_positions) != length or any(type(value) not in (int, float)
                or not math.isfinite(value) or value != position
                for position, value in enumerate(raw_positions, 1))):
        raise ValueError('Feature residue identity/count mismatch')
    positions = [int(value) for value in raw_positions]
    shapes = {'s': (1, length, 20), 'z': (1, length, length, 1), 'r': (1, length, 3, 3),
              't': (1, length, 3), 'ri': (1, length), 'b': (length,)}
    for name, shape in shapes.items():
        tensor = features[name]
        if (tuple(tensor.shape) != shape or tensor.device.type != 'cpu'
                or not bool(torch.isfinite(tensor).all())):
            raise ValueError('Nonfinite, non-CPU or wrong-shape feature tensor')
    sequence = features_module.pdb_to_fasta(features['pdb'])
    if sequence != prepared.sequence:
        raise ValueError('Feature sequence mismatch')
    ca = features['pdb'][features['pdb']['n'] == 'CA']
    coordinates = [[float(row[key]) for key in ('x', 'y', 'z')] for row in ca]
    return {'nres': length, 'sequence': sequence, 'residue_numbers': positions,
            'ca_coordinates': coordinates}


def expected_cpu_torch() -> str | None:
    system = platform.system()
    if system == 'Windows':
        # CPython 3.11 platform.machine() reads PROCESSOR_* environment values,
        # deliberately absent from managed jobs. get_platform() instead reads
        # the interpreter's compiled sys.version identity on Windows.
        if sysconfig.get_platform() != 'win-amd64' or struct.calcsize('P') != 8:
            return None
        return CPU_TORCH[('Windows', 'AMD64')]
    return CPU_TORCH.get((system, platform.machine()))


def infer(prepared: DomainInput, source: Path, weights: Path) -> dict:
    expected_torch = expected_cpu_torch()
    if expected_torch is None or sys.version_info[:2] != (3, 11):
        raise ValueError('Unsupported CPU architecture or Python ABI')
    # Verification is completed by the caller before any of these imports.
    sys.path.insert(0, str(source))
    sys.dont_write_bytecode = True
    torch = importlib.import_module('torch')
    if torch.__version__ != expected_torch or torch.version.cuda is not None:
        raise ValueError('Require the pinned CPU-only torch wheel')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    predict = importlib.import_module('predict')
    feature_module = importlib.import_module('model.utils.features')
    for name, module in list(sys.modules.items()):
        if name == 'predict' or name.startswith('model.'):
            origin = getattr(module, '__file__', None)
            if origin is not None and not Path(origin).resolve().is_relative_to(source.resolve()):
                raise ValueError('Merizo module did not load from verified source')
    started = time.perf_counter()
    network = predict.Merizo().to('cpu')
    network.load_state_dict(predict.read_split_weight_files(str(weights)), strict=True)
    network.eval()
    generate = predict.generate_features_domain
    checked = []
    def guarded_features(*args, **kwargs):
        features = generate(*args, **kwargs)
        checked.append(validate_features(features, prepared, feature_module, torch))
        # Decoder provides exact float32-aware CA comparison before inference.
        probe = make_envelope(prepared, checked[-1], [1] * len(prepared.sequence), 1, 0.0, 0.0)
        decode_merizo_result(json.dumps(probe), prepared, current_binding_sha256=prepared.binding_sha256)
        return features
    setattr(predict, 'generate_features_domain', guarded_features)
    try:
        with tempfile.TemporaryDirectory(prefix='kuma-merizo-') as temporary:
            pdb = Path(temporary) / 'input.pdb'
            pdb.write_text(prepared.normalized_pdb, encoding='ascii', newline='\n')
            with torch.no_grad():
                result = predict.segment(str(pdb), network, 'cpu', False, False, 3, False, 'A')
        if len(checked) != 1:
            raise ValueError('Unexpected feature generation count')
        final_features = validate_features(result, prepared, feature_module, torch)
        if canonical(final_features) != canonical(checked[0]):
            raise ValueError('Inference changed input feature identity')
        labels = result['domain_ids'].flatten().tolist()
        confidence = result['conf_res'].flatten()
        if (confidence.numel() != len(prepared.sequence) or not bool(torch.isfinite(confidence).all())
                or bool((confidence < 0).any()) or bool((confidence > 1).any())):
            raise ValueError('Invalid per-residue confidence')
        return make_envelope(prepared, final_features, labels, int(result['ndom']),
                             float(result['conf_global']), time.perf_counter() - started)
    finally:
        setattr(predict, 'generate_features_domain', generate)


def make_envelope(prepared, features, labels, ndom, confidence, elapsed):
    return {'schema': 'kuma-merizo-result-v1', 'tool_commit': MERIZO_COMMIT,
            'weights_sha256': MERIZO_WEIGHTS_SHA256, 'input': domain_input_manifest(prepared),
            'process': {'status': 'ok', 'exit_code': 0, 'warnings': []}, 'features': features,
            'prediction': {'nres': len(prepared.sequence), 'ndom': ndom, 'labels': labels,
                           'residue_numbers': features['residue_numbers'],
                           'confidence': confidence, 'time_sec': elapsed}}


def execute(pdb: Path, manifest: Path, output: Path, internal: Path, identity_sha: str) -> None:
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError('Result destination must be a fresh file in an existing private directory')
    prepared = load_prepared(pdb, manifest)
    source, weights, _ = verify_payload(internal, identity_sha)
    with warnings.catch_warnings(record=True) as observed:
        # Respect Python's default DeprecationWarning suppression, while
        # retaining actionable runtime/numerical warnings as a failed result.
        warnings.simplefilter('always', RuntimeWarning)
        warnings.simplefilter('always', UserWarning)
        result = infer(prepared, source, weights)
    if observed:
        raise ValueError('Inference emitted a warning; no result was published')
    decode_merizo_result(json.dumps(result, allow_nan=False), prepared,
                         current_binding_sha256=prepared.binding_sha256)
    write_json(output, result, MAX_RESULT_BYTES)


def safe_error_type(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name in FAILURE_ERROR_TYPES else 'OtherError'


def failure_lines(exc: BaseException, codes: dict[CodeType, str]) -> tuple[list[int], str, bool]:
    lines, stage, scanned = [], 'bootstrap', 0
    trace = exc.__traceback__
    while trace is not None and scanned < 256:
        scanned += 1
        if trace.tb_frame.f_code in codes:
            stage = codes[trace.tb_frame.f_code]
            lines.append(trace.tb_lineno)
        trace = trace.tb_next
    return lines[-MAX_FAILURE_FRAMES:], stage, trace is not None or len(lines) > MAX_FAILURE_FRAMES


def failure_diagnostic(exc: BaseException) -> dict:
    lines, stage, truncated = failure_lines(exc, _FAILURE_CODE_STAGES)
    return {'schema': FAILURE_SCHEMA, 'error_type': safe_error_type(exc), 'stage': stage,
            'runtime_entry_lines': lines, 'truncated': truncated}


def failure_destination(path: Path, forbidden: tuple[Path, ...] = ()) -> Path:
    # Only a direct child of the caller-owned cwd, never an input/result alias.
    if (path.parent.resolve() != Path.cwd().resolve() or path.exists() or path.is_symlink()
            or path.resolve() in {item.resolve() for item in forbidden}):
        raise ValueError('Invalid private failure-report destination')
    return Path.cwd().resolve() / path.name


def publish_failure(path: Path, report: dict) -> None:
    path = failure_destination(path)
    raw = canonical(report) + b'\n'
    if len(raw) > MAX_FAILURE_BYTES:
        raise ValueError('Failure report exceeds bound')
    descriptor, temporary = tempfile.mkstemp(prefix='.kuma-failure-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic, exclusive publication: unlike replace(), never overwrite a
        # stale file or a link introduced after destination validation.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-pdb', required=True, type=Path)
    parser.add_argument('--input-manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--device', required=True, choices=['cpu'])
    parser.add_argument('--audit-failure-report', type=Path)
    args = parser.parse_args(argv)
    audit_path = None
    try:
        if not getattr(sys, 'frozen', False):
            raise ValueError('Use the managed frozen runtime')
        identity_module = importlib.import_module('_merizo_build_identity')
        if args.audit_failure_report is not None:
            if getattr(identity_module, 'INTERNAL_AUDIT', False) is not True:
                raise ValueError('Failure diagnostics require an internal audit build')
            audit_path = failure_destination(args.audit_failure_report,
                                             (args.input_pdb, args.input_manifest, args.output))
        internal = Path(getattr(sys, '_MEIPASS')).resolve()
        if not internal.is_relative_to(Path(sys.executable).resolve().parent):
            raise ValueError('Frozen payload escapes its installed runtime')
        execute(args.input_pdb, args.input_manifest, args.output, internal, identity_module.SOURCE_IDENTITY_SHA256)
        return 0
    except Exception as exc:
        if audit_path is not None:
            try:
                publish_failure(audit_path, failure_diagnostic(exc))
            except Exception:
                pass  # Diagnostic failure must never replace the original failure.
        # No private input, paths or arbitrary upstream exception text in logs.
        if isinstance(exc, InputLimitError):
            print('Merizo runtime input exceeds conservative limit: 2000 complete residues.', file=sys.stderr)
        else:
            print('Merizo runtime refused or failed: ' + safe_error_type(exc), file=sys.stderr)
        return 2


def _owned_failure_codes() -> dict[CodeType, str]:
    result = {}
    for function, stage in ((main, 'bootstrap'), (execute, 'execute'),
            (load_prepared, 'input_validation'), (verify_payload, 'payload_verification'),
            (expected_cpu_torch, 'architecture'), (infer, 'inference'),
            (validate_features, 'feature_validation'), (make_envelope, 'result_envelope')):
        pending = [function.__code__]
        while pending:
            code = pending.pop()
            result[code] = stage
            pending.extend(value for value in code.co_consts if isinstance(value, CodeType))
    return result


# Exact code objects, including owned nested functions; never match an arbitrary
# upstream frame merely because its filename resembles runtime_entry.py.
_FAILURE_CODE_STAGES = _owned_failure_codes()


if __name__ == '__main__':
    raise SystemExit(main())
