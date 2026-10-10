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


class RuntimeArchitectureTests(unittest.TestCase):
    def test_windows_compiled_abi_survives_removed_processor_environment(self):
        with patch.object(runtime_entry.platform, 'system', return_value='Windows'), \
             patch.object(runtime_entry.platform, 'machine', return_value=''), \
             patch.object(os, 'name', 'nt'), \
             patch.object(runtime_entry.sys, 'version', '3.11.9 (synthetic) [MSC v.1938 64 bit (AMD64)]'), \
             patch.object(runtime_entry.struct, 'calcsize', return_value=8), \
             patch.dict(os.environ, {}, clear=True):
            self.assertEqual(runtime_entry.expected_cpu_torch(), '2.0.1+cpu')

    def test_windows_unsupported_build_or_pointer_width_remains_rejected(self):
        for build, width in (('win32', 4), ('win-arm64', 8), ('win-amd64', 4), ('unknown', 8)):
            with self.subTest(build=build, width=width), \
                 patch.object(runtime_entry.platform, 'system', return_value='Windows'), \
                 patch.object(runtime_entry.platform, 'machine', return_value='AMD64'), \
                 patch.object(runtime_entry.sysconfig, 'get_platform', return_value=build), \
                 patch.object(runtime_entry.struct, 'calcsize', return_value=width):
                self.assertIsNone(runtime_entry.expected_cpu_torch())

    def test_posix_machine_contract_is_unchanged(self):
        for system, machine, expected in (('Linux', 'x86_64', '2.0.1+cpu'),
                ('Darwin', 'arm64', '2.0.1'), ('Linux', 'aarch64', None), ('Darwin', 'x86_64', None)):
            with self.subTest(system=system, machine=machine), \
                 patch.object(runtime_entry.platform, 'system', return_value=system), \
                 patch.object(runtime_entry.platform, 'machine', return_value=machine):
                self.assertEqual(runtime_entry.expected_cpu_torch(), expected)


class ControllerStageEventTests(unittest.TestCase):
    def test_stage_event_is_flushed_bounded_and_progress_only(self):
        from scripts.merizo_runtime_archive import roundtrip as module
        report = {}
        with patch.object(module.time, 'monotonic', return_value=module._STAGE_STARTED + 5000), \
             patch('builtins.print') as printed:
            module.stage_event(report, 'build', 'freeze', enabled=True)
        printed.assert_called_once()
        self.assertEqual(printed.call_args.kwargs, {'flush': True})
        event = json.loads(printed.call_args.args[0])
        self.assertEqual(set(event), {'schema', 'scope', 'stage', 'event', 'evidence',
                                     'elapsed_seconds', 'elapsed_capped'})
        self.assertEqual(event['elapsed_seconds'], 3600.0)
        self.assertTrue(event['elapsed_capped'])
        self.assertEqual(event['event'], 'entered')
        self.assertEqual(event['evidence'], 'progress_only')
        self.assertEqual(report, {'current_stage': 'freeze'})

    def test_invalid_private_stage_or_scope_is_never_emitted(self):
        from scripts.merizo_runtime_archive.roundtrip import stage_event
        for scope, stage in (('private/path', 'freeze'), ('build', 'private sequence'),
                             ('build', 'runtime_process'), ('build', 'completed')):
            report = {}
            with self.subTest(scope=scope, stage=stage), patch('builtins.print') as printed:
                with self.assertRaises(ValueError):
                    stage_event(report, scope, stage, enabled=True)
                printed.assert_not_called()
                self.assertEqual(report, {})

    def test_disabled_invalid_clock_and_failed_logging_do_not_change_stage(self):
        from scripts.merizo_runtime_archive import roundtrip as module
        report = {}
        with patch('builtins.print') as printed:
            module.stage_event(report, 'build', 'freeze')
            printed.assert_not_called()
        for clock in (float('inf'), float('nan'), module._STAGE_STARTED - 1):
            with self.subTest(clock=clock), patch.object(module.time, 'monotonic', return_value=clock), \
                 patch('builtins.print') as printed:
                module.stage_event(report, 'build', 'freeze', enabled=True)
                printed.assert_not_called()
        with patch('builtins.print', side_effect=BrokenPipeError('private logging failure')):
            module.stage_event(report, 'build', 'freeze', enabled=True)
        self.assertEqual(report, {'current_stage': 'freeze'})


class RuntimeFailureDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.prepared = prepared_synthetic()
        self.pdb, self.manifest = self.root / 'input.pdb', self.root / 'input.json'
        self.pdb.write_bytes(self.prepared.normalized_pdb.encode('ascii'))
        write_json(self.manifest, domain_input_manifest(self.prepared))
        self.output, self.audit = self.root / 'result.json', self.root / 'failure.json'

    def call_entry(self, *, audit=True, internal: bool | None = True, destination=None):
        from types import SimpleNamespace
        argv = ['--input-pdb', str(self.pdb), '--input-manifest', str(self.manifest),
                '--output', str(self.output), '--device', 'cpu']
        if audit:
            argv += ['--audit-failure-report', str(destination or self.audit)]
        identity = SimpleNamespace(SOURCE_IDENTITY_SHA256='0' * 64, INTERNAL_AUDIT=internal)
        if internal is None:
            del identity.INTERNAL_AUDIT
        with patch.object(runtime_entry.sys, 'frozen', True, create=True), \
             patch.object(runtime_entry.sys, '_MEIPASS', str(self.root), create=True), \
             patch.object(runtime_entry.sys, 'executable', str(self.root / 'entry')), \
             patch.object(runtime_entry.Path, 'cwd', return_value=self.root), \
             patch.object(runtime_entry.importlib, 'import_module', return_value=identity):
            return runtime_entry.main(argv)

    def test_safe_failure_has_only_owned_lines_and_no_hostile_text(self):
        secret = 'PRIVATE_SEQUENCE /private/person/location secret\nmessage'
        with patch.object(runtime_entry, 'verify_payload', side_effect=ValueError(secret)), \
             patch('sys.stderr', new_callable=io.StringIO) as stderr:
            self.assertEqual(self.call_entry(), 2)
        raw = self.audit.read_text()
        report = strict_json(raw.encode())
        self.assertEqual(set(report), {'schema', 'error_type', 'stage', 'runtime_entry_lines', 'truncated', 'warning_observations'})
        self.assertEqual(report['error_type'], 'ValueError')
        self.assertEqual(report['stage'], 'execute')
        self.assertTrue(report['runtime_entry_lines'])
        self.assertTrue(all(type(line) is int for line in report['runtime_entry_lines']))
        self.assertNotIn(secret, raw + stderr.getvalue())
        self.assertNotIn(str(self.root), raw)
        self.assertFalse(self.output.exists())
        self.assertEqual(runtime_entry.safe_error_type(type('PRIVATE_ERROR', (Exception,), {})()), 'OtherError')

    def test_success_and_normal_failure_do_not_publish_audit(self):
        with patch.object(runtime_entry, 'verify_payload', return_value=(self.root, self.root, {})), \
             patch.object(runtime_entry, 'infer', return_value=envelope(self.prepared)):
            self.assertEqual(self.call_entry(), 0)
        self.assertTrue(self.output.exists())
        self.assertFalse(self.audit.exists())
        self.output.unlink()
        with patch.object(runtime_entry, 'verify_payload', side_effect=ValueError('private')):
            self.assertEqual(self.call_entry(audit=False), 2)
        self.assertFalse(self.audit.exists())
        self.assertFalse(self.output.exists())

    def test_audit_gate_and_private_fresh_destination_are_enforced(self):
        with patch.object(runtime_entry, 'execute') as execute:
            for destination in (self.root.parent / 'outside.json', self.output, self.pdb):
                with self.subTest(destination=destination):
                    self.assertEqual(self.call_entry(destination=destination), 2)
            self.assertEqual(self.call_entry(internal=False), 2)
            self.assertEqual(self.call_entry(internal=None), 2)
            self.audit.write_text('stale bytes')
            self.assertEqual(self.call_entry(), 2)
            self.assertEqual(self.audit.read_text(), 'stale bytes')
            execute.assert_not_called()

    def test_diagnostic_write_failure_preserves_original_failure(self):
        with patch.object(runtime_entry, 'verify_payload', side_effect=ValueError('private original')), \
             patch.object(runtime_entry, 'publish_failure', side_effect=PermissionError('private secondary')):
            self.assertEqual(self.call_entry(), 2)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.audit.exists())

    def test_atomic_publication_never_overwrites_a_racing_destination(self):
        original_link = os.link
        def race(source, destination):
            Path(destination).write_text('preexisting bytes')
            original_link(source, destination)
        with patch.object(runtime_entry.Path, 'cwd', return_value=self.root), \
             patch.object(runtime_entry.os, 'link', side_effect=race), \
             self.assertRaises(FileExistsError):
            runtime_entry.publish_failure(self.audit, runtime_entry.failure_diagnostic(ValueError()))
        self.assertEqual(self.audit.read_text(), 'preexisting bytes')
        self.assertFalse(list(self.root.glob('.kuma-failure-*')))

    def test_failure_frames_are_bounded_and_filename_spoof_is_not_owned(self):
        def recurse(count):
            if count:
                recurse(count - 1)
            raise ValueError('private recursion detail')
        lines, stage, truncated = [], "", False
        try:
            recurse(40)
        except ValueError as exc:
            lines, stage, truncated = runtime_entry.failure_lines(exc, {recurse.__code__: 'inference'})
        self.assertEqual(len(lines), runtime_entry.MAX_FAILURE_FRAMES)
        self.assertEqual(stage, 'inference')
        self.assertTrue(truncated)
        report = {}
        try:
            exec(compile("raise ValueError('private spoofed frame')", runtime_entry.__file__, 'exec'), {})
        except ValueError as exc:
            report = runtime_entry.failure_diagnostic(exc)
        self.assertEqual(report['runtime_entry_lines'], [])
        self.assertEqual(report['stage'], 'bootstrap')

    def test_report_reader_is_bounded_exact_and_rejects_links(self):
        from scripts.merizo_runtime_archive.roundtrip import read_failure
        valid = runtime_entry.failure_diagnostic(ValueError())
        self.assertEqual(read_failure(self.audit), {'status': 'missing'})
        for value in ({**valid, 'private': 'secret'}, {**valid, 'stage': 'secret'},
                      {**valid, 'runtime_entry_lines': [True]}, {**valid, 'truncated': 1},
                      {**valid, 'runtime_entry_lines': [1] * 33}):
            write_json(self.audit, value)
            self.assertEqual(read_failure(self.audit), {'status': 'rejected'})
        self.audit.write_bytes(b'x' * (runtime_entry.MAX_FAILURE_BYTES + 1))
        self.assertEqual(read_failure(self.audit), {'status': 'rejected'})
        self.audit.write_text('{"schema":"x","schema":"y"}')
        self.assertEqual(read_failure(self.audit), {'status': 'rejected'})
        write_json(self.audit, valid)
        self.assertEqual(read_failure(self.audit), {'status': 'validated', 'report': valid})
        link = self.root / 'linked.json'
        try:
            link.symlink_to(self.audit)
        except OSError:
            return  # Windows runners may lack symlink privilege.
        self.assertEqual(read_failure(link), {'status': 'rejected'})
        with patch.object(runtime_entry.Path, 'cwd', return_value=self.root), self.assertRaises(ValueError):
            runtime_entry.failure_destination(link)


class WarningObservationTests(unittest.TestCase):
    def setUp(self):
        from types import ModuleType
        import warnings
        self.warnings = warnings
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'merizo_source'
        self.category = type('PyparsingDeprecationWarning', (UserWarning, DeprecationWarning), {})
        self.module = ModuleType('pyparsing.warnings')
        setattr(self.module, 'PyparsingDeprecationWarning', self.category)
        self.table = {'wheel': {'pyparsing/util.py': [runtime_entry._PYPARSING_SOURCE, 600, 'pyparsing'],
                               'torch/storage.py': [runtime_entry._TORCH_STORAGE_SOURCE, 1100, 'torch']},
                      'merizo': {}, 'owners': {'pyparsing': '1' * 64, 'torch': '2' * 64}}

    def emitter(self, member='pyparsing/util.py', function='_inner', line=461, declared=None, stacklevel=2, code_filename=None):
        path = str(self.root / member)
        namespace = {'__file__': path if declared is None else declared, 'warnings': self.warnings}
        code = '\n' * (line - 2) + f'def {function}(message, category):\n    warnings.warn(message, category, stacklevel={stacklevel})\n'
        exec(compile(code, path if code_filename is None else code_filename, 'exec'), namespace)
        return namespace[function]

    def capture(self, emit, message, category=None):
        report = {}
        with patch.dict(runtime_entry.sys.modules, {'pyparsing.warnings': self.module}), \
             self.warnings.catch_warnings(record=True) as recorded:
            self.warnings.simplefilter('always')
            original = self.warnings.showwarning
            observer = runtime_entry.WarningObserver(self.root, self.source, self.table, report)
            with observer.observe():
                emit(message, category or self.category)
            self.assertIs(self.warnings.showwarning, original)
        self.assertEqual(len(recorded), 1)
        runtime_entry.validate_warning_report(report)
        return report

    def test_exact_candidate_binds_class_message_source_function_and_immediate_line(self):
        for old, new in runtime_entry._ALIAS_PAIRS:
            with self.subTest(alias=old):
                report = self.capture(self.emitter(), f"'{old}' deprecated - use '{new}'")
                row = report['items'][0]
                self.assertEqual(row['known_id'], 'pyparsing_' + new + '_alias')
                self.assertEqual(row['active_source']['member'], 'pyparsing/util.py')
                self.assertEqual(row['active_source']['line'], 461)
                self.assertIsNone(row['reported_source'])  # stacklevel points to this test, outside bundle.
                self.assertNotIn(str(self.root), json.dumps(report))
        typed = self.capture(self.emitter('torch/storage.py', '_warn_typed_storage_removal', 335),
                             runtime_entry._TYPED_STORAGE_MESSAGE, UserWarning)
        self.assertEqual(typed['items'][0]['known_id'], 'torch_typed_storage_deprecated')
        keyword = self.capture(self.emitter(function='deprecate_argument', line=506),
                               "'unquoteResults' argument is deprecated, use 'unquote_results'")
        self.assertEqual(keyword['items'][0]['known_id'], 'pyparsing_unquote_results_argument')

    def test_mpmath_fixed_candidates_are_diagnostic_only_and_pin_bound(self):
        candidates = [('mpmath/ctx_mp.py', 'e16b0facbe7e4a4120cab9af09629b32f008f199cbd6f98ed3bee6676e2d4d04',
                       35, 'mpnumeric is deprecated', 'mpmath_mpnumeric_alias_deprecated'),
                      ('mpmath/rational.py', '91cb2c603a6057510c46a707f60afb0102f428331b11e2e0f09beb4ef75647b9',
                       4, 'the rational private module is deprecated', 'mpmath_rational_private_module_deprecated')]
        self.table['owners']['mpmath'] = '3' * 64
        for member, sha, line, message, identifier in candidates:
            self.table['wheel'][member] = [sha, 1000, 'mpmath']
            with self.subTest(member=member):
                emit = self.emitter(member, '__getattr__', line, stacklevel=1)
                self.assertEqual(self.capture(emit, message, DeprecationWarning)['items'][0]['known_id'], identifier)
                self.assertEqual(self.capture(emit, message + ' ', DeprecationWarning)['items'][0]['known_id'], 'unrecognized')
                self.assertEqual(self.capture(emit, message, UserWarning)['items'][0]['known_id'], 'unrecognized')

    def test_stack_walk_is_bounded_and_pyc_location_is_only_a_reference(self):
        emit = self.emitter(declared=str(self.root / 'pyparsing/util.pyc'))
        self.assertEqual(self.capture(emit, "'parseString' deprecated - use 'parse_string'")['items'][0]['known_id'],
                         'pyparsing_parse_string_alias')
        with patch.object(runtime_entry, 'MAX_WARNING_STACK', 1):
            report = self.capture(emit, "'parseString' deprecated - use 'parse_string'")
        self.assertIsNone(report['items'][0]['active_source'])
        self.assertEqual(report['items'][0]['known_id'], 'unrecognized')
        observer = runtime_entry.WarningObserver(self.root, self.source, self.table, {})
        for filename, line in ((str(self.root / 'pyparsing/util.py'), True),
                               (str(self.root / 'pyparsing/util.py'), 601),
                               (str(self.root / 'elsewhere/../pyparsing/util.py'), 461),
                               ('pyparsing/util.py', 461)):
            with self.subTest(filename=filename), self.assertNoLogs():
                self.assertIsNone(observer.reference(filename, line))

    def test_frozen_relative_code_requires_exact_absolute_bundle_module_anchor(self):
        message = "'parseString' deprecated - use 'parse_string'"
        for filename in {'pyparsing/util.py', str(Path('pyparsing/util.py'))}:
            with self.subTest(filename=filename):
                report = self.capture(self.emitter(code_filename=filename, stacklevel=1), message)
                row = report['items'][0]
                self.assertEqual(row['known_id'], 'pyparsing_parse_string_alias')
                self.assertEqual(row['active_source']['member'], 'pyparsing/util.py')
                self.assertIsNone(row['reported_source'])  # No independent relative-path attribution.
        controls = [('util.py', None), ('other/pyparsing/util.py', None),
                    ('./pyparsing/util.py', None), ('../pyparsing/util.py', None),
                    ('pyparsing/../pyparsing/util.py', None), ('C:pyparsing/util.py', None),
                    ('//server/share/pyparsing/util.py', None), ('/outside/pyparsing/util.py', None),
                    ('pyparsing/util.py', '/private/unrelated.py'),
                    ('pyparsing/util.py', str(self.root / 'torch/storage.py'))]
        for filename, declared in controls:
            with self.subTest(filename=filename, declared=declared):
                row = self.capture(self.emitter(code_filename=filename, declared=declared), message)['items'][0]
                self.assertIsNone(row['active_source'])
                self.assertEqual(row['known_id'], 'unrecognized')

    def test_near_match_wrong_frame_category_and_pin_remain_unknown(self):
        message = "'parseString' deprecated - use 'parse_string'"
        controls = [(self.emitter(), message + ' ', self.category),
                    (self.emitter(function='different'), message, self.category),
                    (self.emitter(line=460), message, self.category),
                    (self.emitter(declared='/private/unrelated.py'), message, self.category),
                    (self.emitter(), message, type('PyparsingDeprecationWarning', (UserWarning,), {})),
                    (self.emitter(), 'nonfinite private tensor', RuntimeWarning)]
        for emit, text, category in controls:
            with self.subTest(text=text, category=category):
                row = self.capture(emit, text, category)['items'][0]
                self.assertEqual(row['known_id'], 'unrecognized')
        self.table['wheel']['pyparsing/util.py'][0] = '0' * 64
        self.assertEqual(self.capture(self.emitter(), message)['items'][0]['known_id'], 'unrecognized')

    def test_unknown_source_has_public_reference_but_no_arbitrary_path_or_ancestor_attribution(self):
        self.table['wheel']['other/public.py'] = ['3' * 64, 900, 'torch']
        row = self.capture(self.emitter('other/public.py', 'unknown', 51, stacklevel=1),
                           'PRIVATE /secret/path sequence', UserWarning)['items'][0]
        self.assertEqual(row['known_id'], 'unrecognized')
        self.assertEqual(row['active_source']['member'], 'other/public.py')
        self.assertEqual(row['reported_source'], row['active_source'])
        self.assertNotIn('PRIVATE', json.dumps(row))
        self.assertNotIn('/secret/path', json.dumps(row))
        unknown = self.emitter('not_inventory.py', 'unknown', 51)
        namespace = {'__file__': str(self.root / 'pyparsing/util.py'), 'unknown': unknown}
        exec(compile('\n' * 459 + 'def _inner(message, category):\n    unknown(message, category)\n',
                     namespace['__file__'], 'exec'), namespace)
        row = self.capture(namespace['_inner'], "'parseString' deprecated - use 'parse_string'")['items'][0]
        self.assertIsNone(row['active_source'])
        self.assertEqual(row['known_id'], 'unrecognized')

    def test_collector_failures_delegate_and_restore_even_if_inference_raises(self):
        with self.warnings.catch_warnings(record=True) as recorded:
            self.warnings.simplefilter('always')
            original = self.warnings.showwarning
            report = {}
            observer = runtime_entry.WarningObserver(self.root, self.source, self.table, report)
            with patch.object(observer, 'collect', side_effect=ValueError('PRIVATE')), self.assertRaisesRegex(RuntimeError, 'original'):
                with observer.observe():
                    self.warnings.warn('first', UserWarning)
                    raise RuntimeError('original')
            self.assertIs(self.warnings.showwarning, original)
            self.assertEqual(len(recorded), 1)
            self.assertTrue(report['collection_failed'])
        for target in ('reference',):
            report = {}
            with self.warnings.catch_warnings(record=True) as recorded:
                self.warnings.simplefilter('always')
                observer = runtime_entry.WarningObserver(self.root, self.source, self.table, report)
                with patch.object(observer, target, side_effect=ValueError('PRIVATE')), observer.observe():
                    self.emitter()('warning', UserWarning)
            self.assertEqual(len(recorded), 1)
            self.assertTrue(report['collection_failed'])

    def test_default_suppression_and_showwarning_delegation_are_unchanged(self):
        with self.warnings.catch_warnings(record=True) as recorded:
            self.warnings.simplefilter('ignore', DeprecationWarning)
            self.warnings.simplefilter('always', UserWarning)
            report = {}
            observer = runtime_entry.WarningObserver(self.root, self.source, self.table, report)
            with observer.observe():
                self.emitter()('suppressed', DeprecationWarning)
                self.emitter()('observed', UserWarning)
        self.assertEqual(len(recorded), 1)
        self.assertEqual(report['count'], 1)

    def test_oversized_messages_counts_and_final_envelope_are_bounded(self):
        row = self.capture(self.emitter(), 'x' * (runtime_entry.MAX_WARNING_MESSAGE + 1))['items'][0]
        self.assertEqual(row['message_status'], 'oversized')
        self.assertIsNone(row['message_sha256'])
        report = {}
        observer = runtime_entry.WarningObserver(self.root, self.source, self.table, report)
        with self.warnings.catch_warnings(record=True) as recorded:
            self.warnings.simplefilter('always')
            with observer.observe():
                for _ in range(runtime_entry.MAX_WARNING_ITEMS + 2):
                    self.emitter()('warning', UserWarning)
        self.assertEqual(len(recorded), runtime_entry.MAX_WARNING_ITEMS + 2)
        self.assertEqual(len(report['items']), runtime_entry.MAX_WARNING_ITEMS)
        self.assertTrue(report['truncated'])
        report['count'] = runtime_entry.MAX_WARNING_COUNT
        observer.collect('warning', UserWarning, '/private', 1)
        self.assertTrue(report['count_capped'])
        long_member = 'a/' * 100 + 'source.py'
        for item in report['items']:
            ref = {'kind': 'wheel', 'member': long_member, 'sha256': '1' * 64, 'line': 1, 'owner': 'a' * 100}
            item['active_source'] = item['reported_source'] = ref
        diagnostic = runtime_entry.failure_diagnostic(ValueError(), report)
        self.assertLessEqual(len(canonical(diagnostic)) + 1, runtime_entry.MAX_FAILURE_BYTES)
        self.assertLess(len(report['items']), runtime_entry.MAX_WARNING_ITEMS)
        self.assertTrue(report['truncated'])

    def test_custom_str_is_never_called_and_hash_failure_does_not_hide_warning(self):
        class HostileWarning(UserWarning):
            def __str__(self):
                raise AssertionError('PRIVATE __str__ must not be called')
        # warnings.warn itself may call __str__ before showwarning. Exercise
        # the observer boundary directly without changing that upstream behavior.
        def direct(message, _):
            self.warnings.showwarning(message, type(message), str(self.root / 'pyparsing/util.py'), 461)
        row = self.capture(direct, HostileWarning('private'))['items'][0]
        self.assertEqual(row['message_status'], 'unavailable')
        report = {}
        with self.warnings.catch_warnings(record=True) as recorded:
            self.warnings.simplefilter('always')
            observer = runtime_entry.WarningObserver(self.root, self.source, self.table, report)
            with patch.object(runtime_entry.hashlib, 'sha256', side_effect=ValueError('private')), observer.observe():
                self.emitter()('warning', UserWarning)
        self.assertEqual(len(recorded), 1)
        self.assertTrue(report['collection_failed'])

    def test_execute_keeps_known_unknown_and_numeric_warnings_fatal(self):
        prepared = prepared_synthetic()
        pdb, manifest, output = self.root / 'input.pdb', self.root / 'input.json', self.root / 'result.json'
        pdb.write_bytes(prepared.normalized_pdb.encode('ascii'))
        write_json(manifest, domain_input_manifest(prepared))
        for text, category in (("'parseString' deprecated - use 'parse_string'", self.category),
                               ('unknown', UserWarning), ('nonfinite', RuntimeWarning)):
            report = {}
            def infer(*_):
                self.emitter()(text, category)
                return envelope(prepared)
            with patch.dict(runtime_entry.sys.modules, {'pyparsing.warnings': self.module}), \
                 patch.object(runtime_entry, 'verify_payload', return_value=(self.source, self.root, {'warning_sources': self.table})), \
                 patch.object(runtime_entry, 'infer', side_effect=infer), self.assertRaises(ValueError):
                runtime_entry.execute(pdb, manifest, output, self.root, '0' * 64, warning_report=report)
            self.assertEqual(report['count'], 1)
            self.assertFalse(output.exists())

    def test_reader_rejects_malformed_warning_fields(self):
        from scripts.merizo_runtime_archive.roundtrip import read_failure
        report = self.capture(self.emitter(), 'warning')
        valid = runtime_entry.failure_diagnostic(ValueError(), report)
        path = self.root / 'failure.json'
        bad_values = [dict(report, count=True), dict(report, count=65536), dict(report, private='secret')]
        for field, value in (('category', 'PrivateClass'), ('known_id', 'invented'), ('message_status', 'partial'),
                             ('message_sha256', 'private'), ('active_source', {'member': '/private'})):
            altered = copy.deepcopy(report)
            altered['items'][0][field] = value
            bad_values.append(altered)
        for bad in bad_values:
            with self.subTest(bad=bad):
                write_json(path, {**valid, 'warning_observations': bad})
                self.assertEqual(read_failure(path), {'status': 'rejected'})


class WarningSourceInventoryTests(unittest.TestCase):
    def setUp(self):
        from scripts.merizo_runtime_archive import build
        self.build = build
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'source'
        self.source.mkdir()
        self.py = self.root / 'site' / 'public.py'
        self.py.parent.mkdir()
        self.py.write_bytes(b'# public source\n')
        (self.source / 'predict.py').write_bytes(b'# pinned source\n')
        self.identity = {'python_files': {'predict.py': digest(self.source / 'predict.py')}}
        self.row = {'path': str(self.py), 'wheel_member': 'public.py', 'wheel_installation_scheme': 'site',
                    'mapping': 'exact_wheel_member', 'sha256': digest(self.py), 'wheel_member_sha256': digest(self.py),
                    'owner': 'test-package', 'wheel_sha256': '1' * 64}

    def inventory(self, rows=None):
        with patch.object(self.build.sys, 'prefix', str(self.root)):
            return self.build.warning_source_inventory(self.source, self.identity,
                {'installed_files': [self.row] if rows is None else rows})

    def test_identity_copy_and_compact_audit_projection(self):
        identity, summary = self.inventory()
        self.assertNotIn('warning_sources', self.identity)
        self.assertEqual(identity['warning_sources']['wheel']['public.py'], [digest(self.py), 2, 'test-package'])
        self.assertFalse(summary['loaded_code_authentication'])
        self.assertLess(len(canonical(summary)), 400)
        self.assertEqual(summary['runtime_identity_bytes'], len(canonical(identity)) + 1)
        self.assertEqual(summary['table_sha256'], hashlib.sha256(canonical(identity['warning_sources'])).hexdigest())
        # Near-current audit occupancy: only the compact projection is appended.
        report = {'existing_evidence': 'x' * 31_200_000, 'build': {'warning_source_references': summary}}
        self.assertLess(len(canonical(report)) + 1, 32 * 1024 * 1024)

    def test_hash_owner_collision_escape_and_bounds_refuse(self):
        controls = [[self.row, dict(self.row, owner='another')],
                    [dict(self.row, sha256='0' * 64)],
                    [dict(self.row, wheel_member_sha256='0' * 64)],
                    [dict(self.row, mapping='unexplained_installer_transform')],
                    [dict(self.row, path='/outside/private.py')],
                    [dict(self.row, wheel_member='../private.py')],
                    [self.row, dict(self.row, wheel_member='x.data/purelib/public.py')]]
        for rows in controls:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.inventory(rows)
        for constant, bound in (('MAX_WARNING_SOURCES', 1), ('MAX_WARNING_SOURCE_BYTES', 1),
                                ('MAX_WARNING_SOURCE_TOTAL', 1), ('MAX_SOURCE_IDENTITY_BYTES', 10)):
            with self.subTest(constant=constant), patch.object(self.build, constant, bound), self.assertRaises(ValueError):
                self.inventory()
        self.py.write_bytes(b'# changed after prior verification\n')
        with self.assertRaises(ValueError):
            self.inventory()

    def test_runtime_source_table_rejects_malformed_colliding_and_overbound_entries(self):
        identity, _ = self.inventory()
        table = identity['warning_sources']
        for member, row in (('../bad.py', ['0' * 64, 1, 'test-package']),
                            ('bad.py', ['0' * 64, True, 'test-package']),
                            ('bad.py', ['0' * 64, 1, 'unknown']),
                            ('x.data/purelib/public.py', ['0' * 64, 1, 'test-package'])):
            altered = copy.deepcopy(table)
            altered['wheel'][member] = row
            with self.subTest(member=member), self.assertRaises(ValueError):
                runtime_entry.validate_warning_sources(altered)
        with patch.object(runtime_entry, 'MAX_WARNING_SOURCES', 1), self.assertRaises(ValueError):
            runtime_entry.validate_warning_sources(table)


class PreparedInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prepared = prepared_synthetic()
        self.pdb, self.manifest = self.root / 'input.pdb', self.root / 'input.json'
        self.pdb.write_bytes(self.prepared.normalized_pdb.encode('ascii'))
        write_json(self.manifest, domain_input_manifest(self.prepared))

    def test_general_lengths_and_source_identities(self):
        for sequence in ('A', 'ACDEFG', 'ACDEFGHIKLMNPQRSTVWY'):
            expected = prepared_synthetic(sequence)
            self.pdb.write_bytes(expected.normalized_pdb.encode('ascii'))
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
        self.pdb.write_bytes(self.prepared.normalized_pdb.replace(' CA ', ' CB ', 1).encode('ascii'))
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
            self.assertEqual(argv[7:9], ['--device', 'cpu'])
            self.assertEqual(argv[9], '--audit-failure-report')
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

    def test_partial_roundtrip_records_each_failed_stage_and_cleanup(self):
        from contextlib import ExitStack
        from kuma_core.kuro.domain_process import DomainProcessError
        artifact, _ = self.build()
        prepared = prepared_synthetic()
        for stage in ('install', 'verify', 'runtime_process', 'decode_result', 'remove'):
            with self.subTest(stage=stage), ExitStack() as stack:
                primary = DomainProcessError('private original failure')
                report = {}
                def runner(argv, **kwargs):
                    if stage == 'runtime_process':
                        raise primary
                    write_json(Path(argv[6]), {} if stage == 'decode_result' else envelope(prepared))
                if stage in {'install', 'verify', 'remove'}:
                    stack.enter_context(patch.object(OptionalRuntimeManager, stage, side_effect=primary))
                with self.assertRaises(Exception) as caught:
                    roundtrip(self.root / 'out/runtime.zip', artifact, [('synthetic', prepared)],
                              runner=runner, report=report)
                if stage != 'decode_result':
                    self.assertIs(caught.exception, primary)
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(report['failure']['stage'], stage)
                self.assertTrue(report['temporary_storage_removed'])
                self.assertEqual(report['installed'], stage != 'install')
                self.assertEqual(report['removed'], stage not in {'install', 'remove'})
                if stage == 'runtime_process':
                    self.assertEqual(report['runs'][0]['entry_diagnostic'], {'status': 'missing'})
                    self.assertFalse(report['runs'][0]['process_succeeded'])
                if stage == 'remove':
                    self.assertTrue(report['runs'][0]['decoded'])
                    self.assertEqual(report['cleanup_errors'][0]['stage'], 'remove')

    def test_failed_run_keeps_diagnostic_and_original_error_despite_cleanup_failure(self):
        from kuma_core.kuro.domain_process import DomainProcessError
        artifact, _ = self.build()
        prepared = prepared_synthetic()
        primary = DomainProcessError('private process failure')
        for mode in ('valid', 'oversized', 'malformed'):
            report = {}
            def runner(argv, **kwargs):
                diagnostic = Path(argv[argv.index('--audit-failure-report') + 1])
                if mode == 'valid':
                    write_json(diagnostic, runtime_entry.failure_diagnostic(ValueError('private detail')))
                else:
                    diagnostic.write_text('x' * (runtime_entry.MAX_FAILURE_BYTES + 1) if mode == 'oversized' else '{}')
                raise primary
            with self.subTest(mode=mode), \
                 patch.object(OptionalRuntimeManager, 'remove', side_effect=PermissionError('private cleanup')), \
                 self.assertRaises(DomainProcessError) as caught:
                roundtrip(self.root / 'out/runtime.zip', artifact, [('synthetic', prepared)],
                          runner=runner, report=report)
            self.assertIs(caught.exception, primary)
            self.assertEqual(report['failure']['stage'], 'runtime_process')
            self.assertEqual(report['runs'][0]['entry_diagnostic']['status'],
                             'validated' if mode == 'valid' else 'rejected')
            self.assertEqual(report['cleanup_errors'], [{'stage': 'remove', 'error_type': 'PermissionError'}])
            self.assertTrue(report['temporary_storage_removed'])
            self.assertNotIn('private', json.dumps(report))

    def test_completed_first_run_survives_second_run_failure(self):
        from kuma_core.kuro.domain_process import DomainProcessError
        artifact, _ = self.build()
        prepared = prepared_synthetic()
        report = {}
        calls = 0
        def runner(argv, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise DomainProcessError('synthetic failure')
            write_json(Path(argv[6]), envelope(prepared))
        with self.assertRaises(DomainProcessError):
            roundtrip(self.root / 'out/runtime.zip', artifact, [('first', prepared), ('second', prepared)],
                      runner=runner, report=report)
        self.assertTrue(report['runs'][0]['decoded'])
        self.assertFalse(report['runs'][1]['decoded'])
        self.assertTrue(report['removed'])
        self.assertTrue(report['temporary_storage_removed'])

    def test_controller_events_precede_process_and_cleanup_calls(self):
        from kuma_core.kuro.domain_process import DomainProcessError
        artifact, _ = self.build()
        prepared = prepared_synthetic()
        primary = DomainProcessError('private original failure')
        events = []
        original_remove = OptionalRuntimeManager.remove
        def printed(raw, *, flush):
            self.assertTrue(flush)
            events.append(json.loads(raw))
        def runner(*args, **kwargs):
            self.assertEqual(events[-1]['stage'], 'runtime_process')
            raise primary  # Simulates a call that blocks, then fails.
        def remove(manager):
            self.assertEqual(events[-1]['stage'], 'remove')
            return original_remove(manager)
        report = {}
        with patch('builtins.print', side_effect=printed), \
             patch.object(OptionalRuntimeManager, 'remove', remove), \
             self.assertRaises(DomainProcessError) as caught:
            roundtrip(self.root / 'out/runtime.zip', artifact, [('synthetic', prepared)],
                      runner=runner, report=report, stage_events=True)
        self.assertIs(caught.exception, primary)
        self.assertTrue(report['removed'])
        self.assertEqual(events[-1]['stage'], 'workspace_cleanup')
        self.assertTrue(all(event['event'] == 'entered' and event['evidence'] == 'progress_only'
                            for event in events))
        self.assertNotIn('private', json.dumps(events))

    def test_broken_controller_stdout_preserves_original_process_failure(self):
        from kuma_core.kuro.domain_process import DomainProcessError
        artifact, _ = self.build()
        prepared = prepared_synthetic()
        primary = DomainProcessError('original failure')
        report = {}
        with patch('builtins.print', side_effect=BrokenPipeError('logging failed')), \
             self.assertRaises(DomainProcessError) as caught:
            roundtrip(self.root / 'out/runtime.zip', artifact, [('synthetic', prepared)],
                      runner=lambda *a, **kw: (_ for _ in ()).throw(primary), report=report, stage_events=True)
        self.assertIs(caught.exception, primary)
        self.assertTrue(report['removed'])
        self.assertTrue(report['temporary_storage_removed'])


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

    def data_installation(self, root, *, extra_payload=None):
        from importlib.metadata import PathDistribution
        data_member = 'sample-1.data/data/share/man/man1/sample.1'
        payload = {data_member: b'synthetic manual page\n',
                   'sample-1.dist-info/METADATA': b'Metadata-Version: 2.1\nName: sample\nVersion: 1\n'}
        payload.update(extra_payload or {})
        wheel = self.wheel(root, payload=payload)
        prefix = root / 'venv'
        site = prefix / 'lib/python3.11/site-packages'
        with zipfile.ZipFile(wheel) as zipped:
            for name in zipped.namelist():
                destination = (prefix / name.removeprefix('sample-1.data/data/')
                               if name.startswith('sample-1.data/data/') else site / name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(zipped.read(name))
        owner = site / 'sample-1.dist-info/RECORD'
        rows = []
        for path in sorted(prefix.rglob('*')):
            if path.is_file() and path != owner:
                data = path.read_bytes()
                checksum = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
                rows.append([os.path.relpath(path, site).replace(os.sep, '/'), 'sha256=' + checksum, str(len(data))])
        rows.append(['sample-1.dist-info/RECORD', '', ''])
        text = io.StringIO()
        csv.writer(text, lineterminator='\n').writerows(rows)
        owner.write_text(text.getvalue(), encoding='utf-8', newline='\n')
        lock = root / 'lock.json'
        write_json(lock, {'schema': 'kuma-merizo-input-lock-v1', 'wheels': [
            {'name': 'sample', 'version': '1', 'filename': wheel.name,
             'url': 'https://files.pythonhosted.org/' + wheel.name,
             'sha256': digest(wheel), 'size': wheel.stat().st_size}]})
        return lock, prefix, PathDistribution(site / 'sample-1.dist-info'), data_member

    def test_data_scheme_maps_manual_page_to_verified_venv_bytes(self):
        from scripts.merizo_runtime_archive import provenance
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lock, prefix, distribution, member = self.data_installation(root)
            with patch.object(provenance.importlib.metadata, 'distributions', return_value=[distribution]), \
                 patch.object(provenance.sys, 'prefix', str(prefix)), \
                 patch.object(provenance.sysconfig, 'get_path', return_value=str(prefix)) as scheme:
                report = provenance.installed_provenance(lock, root)
                scheme.assert_called_once_with('data')
                row = next(row for row in report['installed_files'] if row.get('wheel_member') == member)
                installed = prefix / 'share/man/man1/sample.1'
                self.assertEqual(row['path'], str(installed))
                self.assertEqual(row['mapping'], 'exact_wheel_member')
                self.assertEqual(row['wheel_installation_scheme'], 'data')
                self.assertEqual(row['wheel_member_sha256'], digest(installed))
                self.assertEqual(row['owner'], 'sample')
                self.assertFalse(report['unresolved'])
                installed.write_bytes(b'tampered documentation\n')
                with self.assertRaisesRegex(ValueError, 'Installed RECORD digest differs'):
                    provenance.installed_provenance(lock, root)

    def test_data_scheme_rejects_outside_or_relative_root(self):
        from scripts.merizo_runtime_archive import provenance
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lock, prefix, distribution, _ = self.data_installation(root)
            for scheme_root in (str(root / 'outside'), 'relative-data'):
                with self.subTest(scheme_root=scheme_root), \
                     patch.object(provenance.importlib.metadata, 'distributions', return_value=[distribution]), \
                     patch.object(provenance.sys, 'prefix', str(prefix)), \
                     patch.object(provenance.sysconfig, 'get_path', return_value=scheme_root), \
                     self.assertRaisesRegex(ValueError, 'scheme escapes isolated environment'):
                    provenance.installed_provenance(lock, root)

    def test_data_and_root_members_cannot_collide_after_installation(self):
        from scripts.merizo_runtime_archive import provenance
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            lock, prefix, distribution, _ = self.data_installation(root, extra_payload={
                'sample-1.data/data/lib/python3.11/site-packages/sample.py': b'colliding source\n'})
            with patch.object(provenance.importlib.metadata, 'distributions', return_value=[distribution]), \
                 patch.object(provenance.sys, 'prefix', str(prefix)), \
                 patch.object(provenance.sysconfig, 'get_path', return_value=str(prefix)), \
                 self.assertRaisesRegex(ValueError, 'colliding installed destinations'):
                provenance.installed_provenance(lock, root)

    def test_unknown_malformed_or_traversing_data_schemes_remain_refused(self):
        from scripts.merizo_runtime_archive import provenance
        for member in ('sample-1.data/headers/sample.h', 'sample-1.data/unknown/file',
                       'sample-1.data/data', 'sample-1.data/data/../escape'):
            with self.subTest(member=member), self.assertRaises(ValueError):
                provenance._wheel_destination(member)

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

    def test_build_retains_attached_partial_roundtrip_before_cleanup(self):
        from contextlib import ExitStack
        from types import SimpleNamespace
        from scripts.merizo_runtime_archive import build
        from kuma_core.kuro.optional_runtime import RuntimeArtifact, RuntimeFile
        from kuma_core.kuro.domain_process import DomainProcessError
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'upstream'
            source.mkdir()
            (root / 'lock.json').write_text('{}')
            args = SimpleNamespace(source=source, output_directory=root / 'build', evidence=root / 'audit.json',
                fixture=FIXTURE, input_lock=root / 'lock.json', wheelhouse=root / 'wheels',
                cpython_origin=None, remove_source_before_run=False)
            artifact = RuntimeArtifact('merizo', 'test', 'linux-x86_64', '0' * 64, 1,
                (RuntimeFile('entry', '0' * 64, 1, True),), 'entry')
            def failed_roundtrip(*args, report, **kwargs):
                report.update(installed=True, verified=True, removed=True, status='failed',
                              failure={'stage': 'runtime_process', 'error_type': 'DomainProcessError'})
                raise DomainProcessError('synthetic process failure')
            values = {'verify_source': {'python_files': {}, 'files': []},
                      'installed_provenance': {'installed_files': []}, 'freeze': ({}, []),
                      'map_build_inputs': {'unresolved': [], 'edges': []},
                      'embedded_inventory': {'stdlib_compilation_inputs': []},
                      'source_companion': {}, 'package_legal': {},
                      'normalize_archive': (artifact, []), 'output_edges': ([], [])}
            with ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}))
                for name, value in values.items():
                    stack.enter_context(patch.object(build, name, return_value=value))
                stack.enter_context(patch.object(build, 'roundtrip', side_effect=failed_roundtrip))
                self.assertEqual(build.build(args), 2)
            report = strict_json((root / 'audit.json').read_bytes())
            self.assertEqual(report['failure_stage'], 'archive_roundtrip')
            self.assertEqual(report['archive']['roundtrip']['failure']['stage'], 'runtime_process')
            self.assertTrue(report['archive']['roundtrip']['verified'])
            self.assertTrue(report['cleanup']['build_archive_source_companion_removed'])

    def test_freezer_driver_diagnostic_excludes_external_frames_and_text(self):
        from types import SimpleNamespace
        from scripts.merizo_runtime_archive import build
        from scripts.merizo_runtime_archive.roundtrip import read_failure
        secret = 'private compiler input /private/path'
        def failed(options):
            raise ValueError(secret)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch.dict('sys.modules', {'PyInstaller.__main__': SimpleNamespace(run=failed)}), \
                 patch.object(runtime_entry.Path, 'cwd', return_value=root), \
                 self.assertRaisesRegex(ValueError, 'private compiler'):
                build.run_freezer([])
            path = root / 'freezer-failure.json'
            value = read_failure(path, schema='kuma-merizo-freezer-failure-v1',
                                 line_key='freezer_lines', stages=frozenset({'freezer'}))
            self.assertEqual(value['status'], 'validated')
            self.assertEqual(len(value['report']['freezer_lines']), 1)
            self.assertNotIn(secret, path.read_text())
            self.assertNotIn(str(root), path.read_text())

    def test_build_event_precedes_blocking_source_verification(self):
        from types import SimpleNamespace
        from scripts.merizo_runtime_archive import build
        events = []
        def blocked(source):
            self.assertEqual(events[-1]['scope'], 'build')
            self.assertEqual(events[-1]['stage'], 'source_verification')
            raise RuntimeError('synthetic source failure')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'source'
            source.mkdir()
            args = SimpleNamespace(source=source, output_directory=root / 'output', evidence=root / 'audit.json',
                                   fixture=FIXTURE)
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), \
                 patch.object(build, 'public_inputs', return_value=[]), \
                 patch.object(build, 'verify_source', side_effect=blocked), \
                 patch('builtins.print', side_effect=lambda raw, **kw: events.append(json.loads(raw))):
                self.assertEqual(build.build(args), 2)
            self.assertEqual(events[-1]['stage'], 'build_payload_cleanup')
            self.assertEqual(strict_json(args.evidence.read_bytes())['failure_stage'], 'source_verification')

    def test_freezer_controller_event_precedes_process_without_child_events(self):
        from types import SimpleNamespace
        from kuma_core.kuro import domain_process
        from scripts.merizo_runtime_archive import build
        events = []
        primary = domain_process.DomainProcessError('synthetic compiler failure')
        def blocked(*args, **kwargs):
            self.assertEqual(events[-1]['scope'], 'freezer')
            self.assertEqual(events[-1]['stage'], 'freezer_process')
            raise primary
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            generated = root / 'generated'
            generated.mkdir()
            report = {}
            with patch.object(build.importlib.metadata, 'version', return_value='6.16.0'), \
                 patch.object(build, 'write_spec'), \
                 patch.object(domain_process, 'run_managed_process', side_effect=blocked), \
                 patch('builtins.print', side_effect=lambda raw, **kw: events.append(json.loads(raw))), \
                 self.assertRaises(domain_process.DomainProcessError) as caught:
                build.freeze(root, ROOT, root, generated, report=report, stage_events=True)
            self.assertIs(caught.exception, primary)
            self.assertEqual(report['diagnostic'], {'status': 'missing'})
            with patch.dict('sys.modules', {'PyInstaller.__main__': SimpleNamespace(run=lambda options: None)}), \
                 patch('builtins.print') as printed:
                build.run_freezer([])
                printed.assert_not_called()

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
