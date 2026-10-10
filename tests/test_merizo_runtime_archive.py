"""Synthetic/offline runtime-archive tests; no actual Torch inference claim."""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from typing import Any
from unittest.mock import patch
import zipfile

from kuma_core.kuro.domain_merizo import domain_input_manifest, decode_merizo_result
from kuma_core.kuro.optional_runtime import OptionalRuntimeManager, PRODUCTION_CATALOG
from scripts.merizo_runtime_archive import archive, runtime_entry, inputs
from scripts.merizo_runtime_archive.common import canonical, digest, strict_json, write_json
from scripts.merizo_runtime_archive.roundtrip import public_inputs, roundtrip
from tests.test_domain_merizo import prepared_synthetic, envelope

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/data/domain_annotation/1ubq.pdb'


class PreparedInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prepared = prepared_synthetic()
        self.pdb, self.manifest = self.root / 'input.pdb', self.root / 'input.json'
        self.pdb.write_text(self.prepared.normalized_pdb, encoding='ascii')
        write_json(self.manifest, domain_input_manifest(self.prepared))

    def test_general_lengths_and_source_identities(self):
        for sequence in ('A', 'ACDEFG', 'ACDEFGHIKLMNPQRSTVWY'):
            expected = prepared_synthetic(sequence)
            self.pdb.write_text(expected.normalized_pdb, encoding='ascii')
            write_json(self.manifest, domain_input_manifest(expected))
            self.assertEqual(runtime_entry.load_prepared(self.pdb, self.manifest), expected)

    def test_rejects_duplicate_keys_nonfinite_unknown_and_boolean_identity(self):
        value = domain_input_manifest(self.prepared)
        corruptions = [dict(value, extra=True), dict(value, normalized_sha256='0' * 64),
                       dict(value, sequence='AAAAAA')]
        boolean = copy.deepcopy(value)
        boolean['residues'][0]['normalized_position'] = True
        corruptions.append(boolean)
        for wrong in corruptions:
            write_json(self.manifest, wrong)
            with self.assertRaises(ValueError):
                runtime_entry.load_prepared(self.pdb, self.manifest)
        for raw in (b'{"sequence":"A","sequence":"A"}', b'{"v":NaN}'):
            with self.assertRaises(ValueError):
                strict_json(raw)

    def test_input_hash_and_atom_gate_before_inference(self):
        self.pdb.write_text(self.prepared.normalized_pdb.replace(' CA ', ' CB ', 1))
        with patch.object(runtime_entry, 'verify_payload') as verify:
            with self.assertRaises(ValueError):
                runtime_entry.execute(self.pdb, self.manifest, self.root / 'result.json', self.root, '0' * 64)
            verify.assert_not_called()
        self.assertFalse((self.root / 'result.json').exists())

    def test_model_verification_precedes_inference_and_atomic_success(self):
        output = self.root / 'result.json'
        with patch.object(runtime_entry, 'verify_payload', side_effect=ValueError('bad model')), \
             patch.object(runtime_entry, 'infer') as infer:
            with self.assertRaises(ValueError):
                runtime_entry.execute(self.pdb, self.manifest, output, self.root, '0' * 64)
            infer.assert_not_called()
        self.assertFalse(output.exists())
        with patch.object(runtime_entry, 'verify_payload', return_value=(self.root, self.root, {})), \
             patch.object(runtime_entry, 'infer', return_value=envelope(self.prepared)):
            runtime_entry.execute(self.pdb, self.manifest, output, self.root, '0' * 64)
        self.assertEqual(decode_merizo_result(output.read_text(), self.prepared,
                         current_binding_sha256=self.prepared.binding_sha256).total_residues, 6)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['input.json', 'input.pdb', 'result.json'])
        with self.assertRaises(ValueError):
            runtime_entry.execute(self.pdb, self.manifest, output, self.root, '0' * 64)

    def test_bad_prediction_never_publishes_output(self):
        bad = envelope(self.prepared)
        bad['features']['ca_coordinates'][0][0] += 1
        with patch.object(runtime_entry, 'verify_payload', return_value=(self.root, self.root, {})), \
             patch.object(runtime_entry, 'infer', return_value=bad):
            with self.assertRaises(ValueError):
                runtime_entry.execute(self.pdb, self.manifest, self.root / 'result.json', self.root, '0' * 64)
        self.assertFalse((self.root / 'result.json').exists())

    def test_payload_source_and_weights_exact_before_loading(self):
        source = self.root / 'merizo_source'
        source.mkdir()
        (source / 'predict.py').write_text('# test only\n')
        weights = self.root / 'merizo_weights'
        weights.mkdir()
        hashes = {}
        for i in range(3):
            path = weights / f'weights_part_{i}.pt'
            path.write_bytes(f'synthetic model {i}'.encode())
            hashes[path.name] = digest(path)
        identity_path = self.root / 'merizo-source-identity.json'
        write_json(identity_path, {'schema': 'kuma-merizo-source-v1', 'commit': runtime_entry.MERIZO_COMMIT,
                                  'python_files': {'predict.py': digest(source / 'predict.py')}})
        with patch.object(runtime_entry, 'MERIZO_WEIGHTS_SHA256', hashes):
            runtime_entry.verify_payload(self.root, digest(identity_path))
            (weights / 'weights_part_1.pt').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                runtime_entry.verify_payload(self.root, digest(identity_path))
        (source / 'surprise.py').write_text('# extra module\n')
        with self.assertRaises(ValueError):
            runtime_entry.verify_payload(self.root, digest(identity_path))

    def test_pinned_float32_residue_indices_become_exact_protocol_integers(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from kuma_core.kuro.domain_merizo import expected_ca_coordinates
        length = len(self.prepared.sequence)
        class Tensor:
            def __init__(self, shape, values=None):
                self.shape, self.values = shape, values
                self.device = SimpleNamespace(type='cpu')
                self.finite = True
            def flatten(self):
                return self
            def tolist(self):
                return self.values
        shapes = {'s': (1, length, 20), 'z': (1, length, length, 1), 'r': (1, length, 3, 3),
                  't': (1, length, 3), 'ri': (1, length), 'b': (length,)}
        features: dict[str, Any] = {key: Tensor(shape) for key, shape in shapes.items()}
        features['ri'].values = [float(i) for i in range(1, length + 1)]
        rows = [dict(zip(('x', 'y', 'z'), xyz)) for xyz in expected_ca_coordinates(self.prepared)]
        pdb = MagicMock()
        names: Any = MagicMock()
        names.__eq__.return_value = True
        pdb.__getitem__.side_effect = lambda key: names if key == 'n' else rows
        features.update(nres=length, pdb=pdb)
        torch = SimpleNamespace(isfinite=lambda tensor: SimpleNamespace(all=lambda: tensor.finite))
        module = SimpleNamespace(pdb_to_fasta=lambda value: self.prepared.sequence)
        actual = runtime_entry.validate_features(features, self.prepared, module, torch)
        self.assertTrue(all(type(value) is int for value in actual['residue_numbers']))
        self.assertEqual(actual['residue_numbers'], list(range(1, length + 1)))
        features['ri'].values[0] = 1.5
        with self.assertRaises(ValueError):
            runtime_entry.validate_features(features, self.prepared, module, torch)
        features['ri'].values[0] = 1.0
        features['b'].shape = (length - 1,)
        with self.assertRaises(ValueError):
            runtime_entry.validate_features(features, self.prepared, module, torch)

    def test_public_and_synthetic_author_frames_normalize_but_bind_separately(self):
        first, second = public_inputs(FIXTURE)
        self.assertEqual(first[1].normalized_pdb, second[1].normalized_pdb)
        self.assertNotEqual(first[1].binding_sha256, second[1].binding_sha256)
        self.assertEqual(second[1].residues[10].insertion_code, 'A')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'package'
        self.package.mkdir()
        (self.package / 'entry').write_bytes(b'synthetic executable\n')
        (self.package / 'entry').chmod(0o700)
        (self.package / '_internal').mkdir()
        (self.package / '_internal/data').write_bytes(b'bytes')

    def build(self, name='out'):
        return archive.normalize_archive(self.package, self.root / name,
             version='internal-test', platform='linux-x86_64', executable='entry')

    def test_regular_zip_is_reproducible_and_real_registry_roundtrip(self):
        artifact, records = self.build('first')
        repeated, _ = self.build('second')
        self.assertEqual(artifact, repeated)
        manager = OptionalRuntimeManager(self.root / 'app', catalog={('merizo', artifact.platform): artifact},
                                         platform_key=artifact.platform)
        self.assertEqual(manager.install(self.root / 'first/runtime.zip').state, 'installed')
        self.assertEqual(manager.verify().state, 'installed')
        if os.name != 'nt':
            installed_status = manager.verify()
            assert installed_status.executable_path is not None
            self.assertEqual(stat.S_IMODE(Path(installed_status.executable_path).stat().st_mode), 0o700)
        self.assertEqual(manager.remove().state, 'missing')
        with zipfile.ZipFile(self.root / 'first/runtime.zip') as handle:
            for entry in handle.infolist():
                self.assertEqual(stat.S_IFMT(entry.external_attr >> 16), stat.S_IFREG)
                self.assertFalse(entry.extra)
                self.assertFalse(entry.comment)
        self.assertFalse(PRODUCTION_CATALOG)

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink fixture')
    def test_internal_file_and_directory_aliases_materialize(self):
        (self.package / 'alias-file').symlink_to('_internal/data')
        (self.package / 'alias-dir').symlink_to('_internal', target_is_directory=True)
        artifact, rows = self.build()
        self.assertIn('alias-dir/data', {row['path'] for row in rows})
        for row in rows:
            self.assertFalse((self.root / 'out/normalized' / row['path']).is_symlink())
        self.assertTrue(next(row for row in rows if row['path'] == 'alias-dir/data')['aliases'])

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink fixture')
    def test_reject_external_dangling_and_directory_cycle(self):
        outside = self.root / 'outside'
        outside.write_text('x')
        link = self.package / 'alias'
        for target in (outside, self.root / 'missing', self.package):
            link.symlink_to(target)
            with self.assertRaises((ValueError, OSError)):
                self.build()
            link.unlink()
            self.assertFalse((self.root / 'out').exists())

    def test_casefold_reserved_and_registry_bounds_fail_before_archive(self):
        for name in ('CON', 'bad.'):
            with self.assertRaises(ValueError):
                archive._safe_name(name)
        for name in ('ENTRY', '.kuma-runtime.json'):
            path = self.package / name
            if os.name == 'nt' and name == 'ENTRY':
                continue
            path.write_text('invalid')
            with self.assertRaises(ValueError):
                self.build()
            path.unlink()
        with patch.object(archive, 'MAX_FILES', 1):
            with self.assertRaises(ValueError):
                self.build()
        self.assertFalse((self.root / 'out').exists())

    def test_decoder_roundtrip_with_explicit_synthetic_runner(self):
        artifact, _ = self.build()
        prepared = prepared_synthetic('ACDEFGHIK')
        leases = []
        def synthetic_runner(argv, **kwargs):
            self.assertEqual(argv[-2:], ['--device', 'cpu'])
            loaded = runtime_entry.load_prepared(Path(argv[2]), Path(argv[4]))
            self.assertEqual(loaded, prepared)
            self.assertIsNotNone(kwargs['operation_lease'])
            leases.append(kwargs['operation_lease'])
            write_json(Path(argv[6]), envelope(loaded))
        report = roundtrip(self.root / 'out/runtime.zip', artifact,
                          [('synthetic_protocol_only', prepared), ('second_protocol_only', prepared)], runner=synthetic_runner)
        self.assertIsNot(leases[0], leases[1])
        self.assertTrue(report['removed'])
        self.assertTrue(report['temporary_storage_removed'])
        self.assertEqual(report['runs'][0]['residues'], 9)


class WheelRecordTests(unittest.TestCase):
    def wheel(self, directory, *, corrupt=False, extra=False, payload=None,
              owners=('sample-1.dist-info/RECORD',), after_record=None):
        path = Path(directory) / 'sample-1-py3-none-any.whl'
        values = {'sample.py': b'example source\n', 'sample-1.dist-info/LICENSE': b'example grant\n'}
        values.update(payload or {})
        records = []
        for name, data in values.items():
            checksum = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            records.append([name, 'sha256=' + checksum, str(len(data))])
        records.extend([name, '', ''] for name in owners)
        text = io.StringIO()
        csv.writer(text, lineterminator='\n').writerows(records)
        for name in owners:
            values[name] = text.getvalue().encode()
        if corrupt:
            values['sample.py'] += b'changed'
        if extra:
            values['hidden.py'] = b'not in RECORD'
        values.update(after_record or {})
        with zipfile.ZipFile(path, 'w') as archive_file:
            for name, data in values.items():
                archive_file.writestr(name, data)
        return path

    def test_record_verified_against_every_original_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(len(inputs.wheel_members(self.wheel(directory))), 3)
            for kwargs in ({'corrupt': True}, {'extra': True}):
                with self.assertRaises(ValueError):
                    inputs.wheel_members(self.wheel(directory, **kwargs))

    def test_nested_vendor_record_is_covered_by_owning_record(self):
        nested = 'sample/_vendor/dependency-1.dist-info/RECORD'
        data = b'dependency.py,sha256=vendor_assertion,12\n'
        with tempfile.TemporaryDirectory() as directory:
            members = inputs.wheel_members(self.wheel(directory, payload={nested: data}))
        by_name = {member['member']: member for member in members}
        self.assertEqual(len(members), 4)
        self.assertEqual(by_name[nested]['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(by_name[nested]['size'], len(data))

    def test_nested_records_do_not_replace_missing_or_multiple_owners(self):
        nested = 'sample/_vendor/dependency-1.dist-info/RECORD'
        with tempfile.TemporaryDirectory() as directory:
            for owners in ((), ('sample-1.dist-info/RECORD', 'other-2.dist-info/RECORD')):
                with self.subTest(owners=owners), self.assertRaisesRegex(ValueError, 'one root-level wheel RECORD'):
                    inputs.wheel_members(self.wheel(directory, payload={nested: b'vendor metadata\n'}, owners=owners))

    def test_nested_record_tampering_and_unlisted_bytes_are_rejected(self):
        nested = 'sample/_vendor/dependency-1.dist-info/RECORD'
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'hash/size mismatch'):
                inputs.wheel_members(self.wheel(directory, payload={nested: b'original\n'},
                                                after_record={nested: b'changed\n'}))
            with self.assertRaisesRegex(ValueError, 'does not inventory every file'):
                inputs.wheel_members(self.wheel(directory, after_record={nested: b'unlisted\n'}))

    def test_changed_installed_nested_record_is_not_attributed_to_pip(self):
        from importlib.metadata import PathDistribution
        from scripts.merizo_runtime_archive import provenance
        nested = 'sample/_vendor/dependency-1.dist-info/RECORD'
        owner = 'sample-1.dist-info/RECORD'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            wheel = self.wheel(root, payload={nested: b'original vendor metadata\n',
                'sample-1.dist-info/METADATA': b'Metadata-Version: 2.1\nName: sample\nVersion: 1\n'})
            installed = root / 'installed'
            with zipfile.ZipFile(wheel) as zipped:
                for name in zipped.namelist():
                    destination = installed / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(zipped.read(name))
            # Even a self-consistent rewritten installed RECORD cannot attribute
            # altered vendored metadata to pip's owning-RECORD rewrite behavior.
            (installed / nested).write_bytes(b'changed vendor metadata\n')
            rows = []
            for path in sorted(installed.rglob('*')):
                if path.is_file() and path != installed / owner:
                    data = path.read_bytes()
                    checksum = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
                    rows.append([path.relative_to(installed).as_posix(), 'sha256=' + checksum, str(len(data))])
            rows.append([owner, '', ''])
            text = io.StringIO()
            csv.writer(text, lineterminator='\n').writerows(rows)
            (installed / owner).write_text(text.getvalue(), encoding='utf-8', newline='\n')
            wheel_sha = digest(wheel)
            lock = root / 'lock.json'
            write_json(lock, {'schema': 'kuma-merizo-input-lock-v1', 'wheels': [
                {'name': 'sample', 'version': '1', 'filename': wheel.name,
                 'url': 'https://files.pythonhosted.org/' + wheel.name,
                 'sha256': wheel_sha, 'size': wheel.stat().st_size}]})
            distribution = PathDistribution(installed / 'sample-1.dist-info')
            with patch.object(provenance.importlib.metadata, 'distributions', return_value=[distribution]), \
                 patch.object(provenance.sys, 'prefix', str(installed)):
                report = provenance.installed_provenance(lock, root)
                by_member = {row['wheel_member']: row for row in report['installed_files']}
                self.assertEqual(by_member[owner]['mapping'], 'pip_rewritten_RECORD')
                self.assertEqual(by_member[nested]['mapping'], 'unexplained_installer_transform')
                self.assertEqual(by_member[nested]['owner'], 'sample')
                self.assertEqual(by_member[nested]['wheel_sha256'], wheel_sha)
                self.assertIn({'kind': 'installed_transform', 'path': str(installed / nested),
                               'owner': 'sample'}, report['unresolved'])
                (installed / nested).write_bytes(b'changed again without matching installed RECORD\n')
                with self.assertRaisesRegex(ValueError, 'Installed RECORD digest differs'):
                    provenance.installed_provenance(lock, root)
                wheel.write_bytes(wheel.read_bytes() + b'changed wheel bytes')
                with self.assertRaisesRegex(ValueError, 'Original wheel bytes differ'):
                    provenance.installed_provenance(lock, root)

    def test_unknown_origin_rejected_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'version': '1', 'install': [{'metadata': {'name': 'x', 'version': '1'},
                'download_info': {'url': 'https://untrusted.example/x-1-py3-none-any.whl',
                                  'archive_info': {'hashes': {'sha256': '0' * 64}}}}]}
            write_json(root / 'report.json', report)
            with patch('urllib.request.urlopen') as network:
                with self.assertRaises(ValueError):
                    inputs.freeze([root / 'report.json'], root / 'wheels', root / 'lock.json', root / 'requirements.txt')
                network.assert_not_called()


class BuildAuditTests(unittest.TestCase):
    def test_cleanup_failure_changes_success_exit_to_failure(self):
        from types import SimpleNamespace
        from scripts.merizo_runtime_archive import build
        from kuma_core.kuro.optional_runtime import RuntimeArtifact, RuntimeFile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'upstream'
            source.mkdir()
            (root / 'lock.json').write_text('{}')
            args = SimpleNamespace(source=source, output_directory=root / 'build', evidence=root / 'audit.json',
                fixture=FIXTURE, input_lock=root / 'lock.json', wheelhouse=root / 'wheels',
                cpython_origin=None, remove_source_before_run=False)
            artifact = RuntimeArtifact('merizo', 'test', 'linux-x86_64', '0' * 64, 1,
                (RuntimeFile('entry', '0' * 64, 1, True),), 'entry')
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), \
                 patch.object(build, 'verify_source', return_value={'python_files': {}, 'files': []}), \
                 patch.object(build, 'installed_provenance', return_value={'installed_files': []}), \
                 patch.object(build, 'freeze', return_value=({}, [])), \
                 patch.object(build, 'map_build_inputs', return_value={'unresolved': [], 'edges': []}), \
                 patch.object(build, 'embedded_inventory', return_value={'stdlib_compilation_inputs': []}), \
                 patch.object(build, 'source_companion', return_value={}), \
                 patch.object(build, 'package_legal', return_value={}), \
                 patch.object(build, 'normalize_archive', return_value=(artifact, [])), \
                 patch.object(build, 'output_edges', return_value=([], [])), \
                 patch.object(build, 'roundtrip', return_value={'removed': True}), \
                 patch.object(build.shutil, 'rmtree', side_effect=PermissionError('synthetic cleanup failure')):
                self.assertEqual(build.build(args), 2)
            report = strict_json((root / 'audit.json').read_bytes())
            self.assertEqual(report['status'], 'cleanup_failed')
            self.assertTrue(report['execution_controller_completed'])
            self.assertNotIn('error', report)
            self.assertFalse(report['cleanup']['build_archive_source_companion_removed'])
            self.assertFalse(report['distribution_cleared'])

    def test_runtime_cold_import_without_product_dependencies(self):
        import subprocess
        import sys
        code = """import sys, types, typing
sys.modules['typing_extensions'] = types.SimpleNamespace(TypedDict=typing.TypedDict)
from scripts.merizo_runtime_archive import runtime_entry
assert not any(name in sys.modules for name in ('torch', 'numpy', 'pandas', 'Bio', 'psutil'))
"""
        completed = subprocess.run([sys.executable, '-S', '-c', code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_cpython_member_bytes_reverified_from_archive(self):
        from scripts.merizo_runtime_archive import cpython_origin
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / 'python.zip'
            with zipfile.ZipFile(binary, 'w') as zipped:
                zipped.writestr('bin/python', b'synthetic interpreter bytes')
            record: dict[str, Any] = {'schema': 'kuma-cpython-origin-v1'}
            for key in ('binary_archive', 'source_archive', 'provider_build_recipe'):
                record[key] = {'path': str(binary), 'sha256': digest(binary), 'size': binary.stat().st_size}
            record['binary_archive']['members'] = cpython_origin.archive_inventory(binary)
            self.assertEqual(cpython_origin.verify(record), record)
            record['binary_archive']['members'][0]['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                cpython_origin.verify(record)

    def test_pytorch_cdn_scope_is_only_verified_fixed_wheels(self):
        from urllib.parse import urlsplit
        for name in ('linux_x86_64', 'win_amd64'):
            self.assertTrue(inputs.official_wheel_url(urlsplit(
                f'https://download-r2.pytorch.org/whl/cpu/torch-2.0.1%2Bcpu-cp311-cp311-{name}.whl')))
        self.assertFalse(inputs.official_wheel_url(urlsplit('https://download-r2.pytorch.org/other.whl')))
        self.assertFalse(inputs.official_wheel_url(urlsplit('https://download-r2.pytorch.org.attacker.test/whl/cpu/torch.whl')))


if __name__ == '__main__':
    unittest.main()
