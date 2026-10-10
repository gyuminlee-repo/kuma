"""POSIX build guards; no freezer, upstream or model execution."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / 'scripts/merizo_windows_smoke'


def load(name):
    spec = importlib.util.spec_from_file_location(name, HARNESS / (name + '.py'))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load('run')
load('build_frozen')
build = load('build_frozen_posix')


class PosixBuildTests(unittest.TestCase):
    def test_command_direct_entry_and_exact_mac_architecture(self):
        for platform in ('linux', 'darwin'):
            with self.subTest(platform=platform), mock.patch.object(build.sys, 'platform', platform):
                command = build.build_command(Path('source with spaces'), Path('output with spaces'))
                self.assertEqual(command[-1], str(HARNESS / 'frozen_posix_entry.py'))
                self.assertIn('--onedir', command)
                self.assertIn('--hidden-import', command)
                self.assertIn('backports.tarfile', command)
                self.assertEqual('--target-arch' in command, platform == 'darwin')
                if platform == 'darwin':
                    self.assertEqual(command[command.index('--target-arch') + 1], 'arm64')

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink semantics')
    def test_internal_links_counted_without_duplicate_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'real').mkdir()
            (root / 'real' / 'library').write_bytes(b'abc')
            (root / 'alias').symlink_to('real/library')
            (root / 'dir-alias').symlink_to('real', target_is_directory=True)
            self.assertEqual(build.package_inventory(root),
                {'package_bytes': 3, 'package_file_count': 1, 'package_symlink_count': 2})

    @unittest.skipIf(os.name == 'nt', 'POSIX symlink semantics')
    def test_external_broken_and_cyclic_links_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'package'; root.mkdir()
            outside = Path(folder) / 'external'; outside.write_bytes(b'bad')
            for target in ('../external', 'missing', 'alias'):
                with self.subTest(target=target):
                    link = root / 'alias'; link.symlink_to(target)
                    with self.assertRaises((ValueError, OSError, RuntimeError)):
                        build.package_inventory(root)
                    link.unlink()

    def test_stop_group_kills_owned_group_then_bounded_reap(self):
        process = mock.Mock(pid=12345)
        with mock.patch.object(build.os, 'killpg', create=True) as kill, \
             mock.patch.object(build.signal, 'SIGKILL', 9, create=True):
            build.stop_group(process)
        kill.assert_called_once_with(12345, 9)
        process.wait.assert_called_once_with(timeout=10)

    def test_missing_group_still_reaps_root(self):
        process = mock.Mock(pid=12345)
        with mock.patch.object(build.os, 'killpg', side_effect=ProcessLookupError, create=True), \
             mock.patch.object(build.signal, 'SIGKILL', 9, create=True):
            build.stop_group(process)
        process.wait.assert_called_once_with(timeout=10)

    def test_build_denies_non_ci_before_dependencies_and_keeps_existing_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root/'source'; source.mkdir(); output=root/'output'; output.mkdir()
            marker=output/'keep'; marker.write_text('preserve')
            with mock.patch.dict(build.os.environ, {'GITHUB_ACTIONS': 'false'}), \
                 mock.patch.object(build.shared, 'verify_freezer_dependencies') as verify:
                self.assertEqual(build.build(source, output, root/'result.json'), 2)
            verify.assert_not_called()
            self.assertEqual(marker.read_text(), 'preserve')
            self.assertEqual(json.loads((root/'result.json').read_text())['status'], 'failed')

    def test_build_refuses_existing_output_without_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/'source'; source.mkdir(); output=root/'output'; output.mkdir()
            with mock.patch.dict(build.os.environ, {'GITHUB_ACTIONS': 'true'}), \
                 mock.patch.object(build.sys, 'platform', 'linux'), \
                 mock.patch.object(build, 'runtime_contract', return_value={}), \
                 mock.patch.object(build.shared, 'verify_freezer_dependencies') as verify:
                self.assertEqual(build.build(source, output, root/'result.json'), 2)
            verify.assert_not_called(); self.assertTrue(output.is_dir())


if __name__ == '__main__':
    unittest.main()
