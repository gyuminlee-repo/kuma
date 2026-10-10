"""Stdlib-only frozen-harness contracts; no PyInstaller, Torch or model execution."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts/merizo_windows_smoke"
def load_harness(name: str):
    spec = importlib.util.spec_from_file_location(name, HARNESS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


smoke = load_harness("run")
build = load_harness("build_frozen")
frozen = load_harness("frozen_entry")


class FrozenHarnessContracts(unittest.TestCase):
    def test_freezer_requirement_pins_match_preflight(self):
        requirements = {
            line.split("==")[0]: line.split("==")[1]
            for line in (HARNESS / "freezer-requirements.txt").read_text().splitlines()
            if line and not line.startswith("#")
        }
        self.assertEqual(requirements, {"pyinstaller": build.PYINSTALLER_VERSION,
                                       "backports.tarfile": build.BACKPORTS_TARFILE_VERSION})
        self.assertEqual(build.REQUIRED_BOOTSTRAP_IMPORTS, ("backports", "backports.tarfile"))

    def test_freezer_preflight_rejects_missing_wrong_or_vendored_backport(self):
        with tempfile.TemporaryDirectory() as folder:
            # A noncanonical spelling reproduces the short/long Windows temp
            # path discrepancy on every OS without weakening the origin guard.
            spelling = Path(folder) / "spelling"
            spelling.mkdir()
            standalone = spelling / ".." / "site-packages/backports/tarfile/__init__.py"
            standalone.parent.mkdir(parents=True)
            standalone.write_text("# mock only; never imported")
            for problem in (None, "version", "missing", "vendored", "wrong_origin"):
                with self.subTest(problem=problem):
                    location = standalone
                    if problem == "vendored":
                        location = Path(folder) / "site-packages/setuptools/_vendor/backports/tarfile/__init__.py"
                    distribution = mock.Mock()
                    distribution.locate_file.return_value = location
                    versions = {"pyinstaller": "6.16.0", "backports.tarfile": "0.0" if problem == "version" else "1.2.0"}
                    spec = None if problem == "missing" else mock.Mock(origin=str(
                        standalone.parent / "unexpected.py" if problem == "wrong_origin" else standalone))
                    with mock.patch.object(build.importlib.metadata, "version", side_effect=versions.__getitem__), \
                         mock.patch.object(build.importlib.metadata, "distribution", return_value=distribution), \
                         mock.patch.object(build.importlib.util, "find_spec", return_value=spec):
                        if problem is None:
                            report = build.verify_freezer_dependencies()
                            self.assertTrue(report["standalone_backport_verified"])
                            self.assertEqual(report["backports_tarfile_origin"], str(standalone.resolve()))
                        else:
                            with self.assertRaises(ValueError):
                                build.verify_freezer_dependencies()

    def test_built_archive_inventory_requires_bare_namespace_and_tarfile(self):
        for names in (("backports", "backports.tarfile"), ("backports",), ("backports.tarfile",), ()):
            with self.subTest(names=names):
                archive = mock.Mock()
                archive.toc = {"PYZ.pyz": (0, 0, 0, 0, "z"), "entry": (0, 0, 0, 0, "s")}
                archive.open_embedded_archive.return_value.toc = {name: (0, 0, 0) for name in names}
                readers = mock.Mock()
                readers.CArchiveReader.return_value = archive
                with mock.patch.object(build.importlib, "import_module", return_value=readers) as importer:
                    if len(names) == 2:
                        report = build.verify_frozen_bootstrap_imports(Path("mock.exe"))
                        self.assertTrue(report["verified"])
                        self.assertEqual(report["collected_modules"], list(names))
                    else:
                        with self.assertRaisesRegex(ValueError, "missing from embedded PYZ"):
                            build.verify_frozen_bootstrap_imports(Path("mock.exe"))
                importer.assert_called_once_with("PyInstaller.archive.readers")
                readers.CArchiveReader.assert_called_once_with("mock.exe")
                archive.open_embedded_archive.assert_called_once_with("PYZ.pyz")
                archive.extract.assert_not_called()

    def test_build_stops_before_analysis_when_freezer_preflight_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with mock.patch.object(build.sys, "platform", "win32"), \
                 mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                 mock.patch.object(build, "verify_freezer_dependencies", side_effect=ValueError("missing backport")), \
                 mock.patch.object(build.subprocess, "Popen") as process:
                code = build.build(base / "source", base / "build", base / "evidence.json")
            self.assertEqual(code, 2)
            process.assert_not_called()
            report = json.loads((base / "evidence.json").read_text())
            self.assertFalse(report["verified_before_build"])
            self.assertIn("missing backport", report["error"])

    def test_native_child_disables_bytecode_even_in_isolated_mode(self):
        source = (HARNESS / "run.py").read_text()
        self.assertIn('command = [sys.executable, "-I", "-B",', source)

    def test_build_command_is_onedir_explicit_and_only_three_weights(self):
        command = build.build_command(Path("source with spaces"), Path("output with spaces"))
        self.assertIn("--onedir", command)
        self.assertNotIn("--onefile", command)
        self.assertEqual(command[:3], [sys.executable, "-m", "PyInstaller"])
        hidden = [command[i + 1] for i, word in enumerate(command) if word == "--hidden-import"]
        self.assertTrue({"torch", "predict", "model.network", "model.utils.features", "backports", "backports.tarfile"} <= set(hidden))
        data = [command[i + 1] for i, word in enumerate(command) if word == "--add-data"]
        self.assertEqual(len(data), 3)
        self.assertTrue(all(item.endswith(os.pathsep + "merizo_weights") for item in data))
        self.assertTrue(all(str(Path("source with spaces") / "weights" / name) in "\n".join(data)
                            for name in smoke.WEIGHTS))
        self.assertEqual(Path(command[-1]).name, "frozen_entry.py")

    def test_unapproved_local_build_fails_without_starting_any_process(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with mock.patch.object(build.sys, "platform", "linux"), mock.patch.object(build.subprocess, "Popen") as process:
                code = build.build(base / "source", base / "build", base / "evidence.json")
            self.assertEqual(code, 2)
            process.assert_not_called()
            evidence = json.loads((base / "evidence.json").read_text())
            self.assertFalse(evidence["verified_before_build"])
            self.assertEqual(evidence["status"], "failed")
            self.assertFalse((base / "build").exists())

    def test_mock_build_preserves_preverification_and_bounded_timeout(self):
        for outcome in ("success", "timeout", "missing_import"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                source, output, report = base / "source", base / "output", base / "report.json"
                source.mkdir()
                process = mock.Mock()
                def launch(command, **kwargs):
                    self.assertFalse(kwargs["shell"])
                    self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
                    self.assertEqual(json.loads(report.read_text())["status"], "verified")
                    package = output / "dist" / build.PACKAGE_NAME
                    package.mkdir(parents=True)
                    (package / (build.PACKAGE_NAME + ".exe")).write_bytes(b"mock-only executable marker")
                    return process
                if outcome != "timeout":
                    process.wait.return_value = 0
                else:
                    process.wait.side_effect = build.subprocess.TimeoutExpired("mock packaging", 600)
                with mock.patch.object(build.sys, "platform", "win32"), \
                     mock.patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), \
                     mock.patch.object(build, "verify_freezer_dependencies", return_value={"pyinstaller": "6.16.0", "backports.tarfile": "1.2.0", "standalone_backport_verified": True}), \
                     mock.patch.object(build, "verify_upstream", return_value=smoke.WEIGHTS), \
                     mock.patch.object(build, "source_hashes", return_value={"predict.py": "mock-source"}), \
                     mock.patch.object(build, "own_hashes", return_value={"run.py": "mock-harness"}), \
                     mock.patch.object(build.subprocess, "Popen", side_effect=launch), \
                     mock.patch.object(build, "verify_frozen_bootstrap_imports",
                         side_effect=ValueError("backports missing") if outcome == "missing_import" else None,
                         return_value={"verified": True, "collected_modules": ["backports", "backports.tarfile"]}) as inventory, \
                     mock.patch.object(build, "_stop_build", return_value=True) as stop:
                    code = build.build(source, output, report)
                evidence = json.loads(report.read_text())
                self.assertTrue(evidence["verified_before_build"])
                self.assertEqual(evidence["weights_sha256"], smoke.WEIGHTS)
                if outcome == "success":
                    self.assertEqual(code, 0)
                    self.assertEqual(evidence["status"], "built")
                    self.assertEqual(evidence["package_file_count"], 1)
                    self.assertTrue(evidence["frozen_bootstrap_imports"]["verified"])
                    inventory.assert_called_once()
                    stop.assert_not_called()
                elif outcome == "missing_import":
                    self.assertEqual(code, 2)
                    self.assertEqual(evidence["status"], "failed")
                    self.assertIn("backports missing", evidence["error"])
                    self.assertFalse(output.exists())
                    stop.assert_not_called()
                else:
                    self.assertEqual(code, 2)
                    self.assertEqual(evidence["status"], "timed_out")
                    self.assertTrue(evidence["build_tree_termination_verified"])
                    self.assertFalse(output.exists())
                    stop.assert_called_once_with(process)

    def test_runtime_origin_guard_runs_before_any_weight_deserialization(self):
        fake_torch = mock.Mock()
        fake_torch.__version__ = "2.0.1+cpu"
        fake_torch.version.cuda = None
        fake_predict = mock.Mock()
        with mock.patch.object(smoke, "verify_weights", return_value=smoke.WEIGHTS), \
             mock.patch.object(smoke.importlib, "import_module", side_effect=[fake_torch, fake_predict, mock.Mock()]):
            with self.assertRaisesRegex(ValueError, "outside bundle"):
                smoke.inference(ROOT / "tests/data/domain_annotation/1ubq.pdb", Path("unused"),
                                mock.Mock(side_effect=ValueError("outside bundle")))
        fake_predict.Merizo.assert_not_called()
        fake_predict.read_split_weight_files.assert_not_called()

    def test_weight_set_hashes_fail_closed_before_import(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "weights_part_0.pt").write_bytes(b"not a model")
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                smoke.verify_weights(directory)
            with mock.patch.object(smoke.importlib, "import_module") as importer:
                with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                    smoke.inference(ROOT / "tests/data/domain_annotation/1ubq.pdb", directory)
                importer.assert_not_called()

    def test_verified_fake_bytes_then_tamper(self):
        # Harmless bytes exercise the hash boundary; torch.load is never called.
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            payload = b"mock weight verification only"
            file = directory / "weights_part_0.pt"
            file.write_bytes(payload)
            with mock.patch.object(smoke, "WEIGHTS", {file.name: smoke.sha(payload)}):
                self.assertEqual(smoke.verify_weights(directory), {file.name: smoke.sha(payload)})
                file.write_bytes(payload + b"tamper")
                with self.assertRaises(ValueError):
                    smoke.verify_weights(directory)

    def test_source_guard_refuses_wrong_commit_tracked_untracked_or_ignored(self):
        with mock.patch.object(smoke.subprocess, "check_output", return_value="wrong"), \
             mock.patch.object(smoke, "verify_weights") as weights:
            with self.assertRaisesRegex(ValueError, "HEAD"):
                smoke.verify_upstream(Path("official source"))
            weights.assert_not_called()
        for outputs in ([smoke.COMMIT, "extra.py"], [smoke.COMMIT, "", "ignored.py"]):
            with self.subTest(outputs=outputs), mock.patch.object(smoke.subprocess, "check_output", side_effect=outputs), \
                 mock.patch.object(smoke.subprocess, "run"), mock.patch.object(smoke, "verify_weights") as weights:
                with self.assertRaises(ValueError):
                    smoke.verify_upstream(Path("official source"))
                weights.assert_not_called()
        with mock.patch.object(smoke.subprocess, "check_output", return_value=smoke.COMMIT), \
             mock.patch.object(smoke.subprocess, "run", side_effect=RuntimeError("tracked diff")), \
             mock.patch.object(smoke, "verify_weights") as weights:
            with self.assertRaises(RuntimeError):
                smoke.verify_upstream(Path("official source"))
            weights.assert_not_called()

    def test_module_provenance_requires_bundle_and_all_critical_modules(self):
        with tempfile.TemporaryDirectory() as folder:
            internal = Path(folder) / "bundle/_internal"
            modules = []
            for name in ("torch", "predict", "model.network", "model.utils.features"):
                module = ModuleType(name)
                module.__file__ = str(internal / (name.replace(".", "/") + ".pyc"))
                modules.append((name, module))
            self.assertEqual(set(frozen.module_origins(modules, internal)), {name for name, _ in modules})
            with self.assertRaises(ValueError):
                frozen.module_origins(modules[:-1], internal)
            modules[0][1].__file__ = str(Path(folder) / "system-python/torch/__init__.py")
            with self.assertRaisesRegex(ValueError, "outside"):
                frozen.module_origins(modules, internal)

    def test_native_dlls_cannot_fall_back_to_system_python(self):
        with tempfile.TemporaryDirectory() as folder:
            root, windows = Path(folder) / "bundle", Path(folder) / "Windows"
            required = [str(root / "_internal" / name) for name in ("python311.dll", "torch_cpu.dll", "c10.dll")]
            paths = required + [str(windows / "System32/kernel32.dll")]
            self.assertEqual(len(frozen.validate_native_paths(paths, root, windows)["bundled"]), 3)
            for bad in (paths[1:], paths + [str(Path(folder) / "outside/extra.dll")],
                        paths + [str(windows / "System32/python311.dll")]):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    frozen.validate_native_paths(bad, root, windows)

    def test_native_entry_refuses_development_python(self):
        with mock.patch.object(frozen.sys, "platform", "linux"):
            with self.assertRaisesRegex(ValueError, "frozen native Windows"):
                frozen.bundle_root()

    def test_gate_required_bounded_and_local(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "launcher"):
                frozen.wait_for_job_gate()
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            with mock.patch.object(frozen.Path, "cwd", return_value=base), \
                 mock.patch.dict(os.environ, {"KUMA_MERIZO_START_GATE": str(base / "gate")}), \
                 mock.patch.object(frozen.time, "monotonic", side_effect=[0, 31]):
                with self.assertRaises(TimeoutError):
                    frozen.wait_for_job_gate()
            (base / "gate").write_text("ready")
            with mock.patch.object(frozen.Path, "cwd", return_value=base), \
                 mock.patch.dict(os.environ, {"KUMA_MERIZO_START_GATE": str(base / "gate")}):
                frozen.wait_for_job_gate()
            with mock.patch.object(frozen.Path, "cwd", return_value=base), \
                 mock.patch.dict(os.environ, {"KUMA_MERIZO_START_GATE": str(base.parent / "outside")}):
                with self.assertRaises(ValueError):
                    frozen.wait_for_job_gate()

    def test_paths_and_small_reports_are_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            self.assertFalse(build.disjoint(base, base / "nested"))
            self.assertFalse(build.disjoint(base / "nested", base))
            self.assertTrue(build.disjoint(base / "a", base / "b"))
            with mock.patch.object(frozen, "MAX_REPORT_BYTES", 30):
                with self.assertRaisesRegex(ValueError, "size limit"):
                    frozen.write_report(base / "large.json", {"error": "x" * 50})
            self.assertFalse((base / "large.json").exists())

    def test_frozen_code_directly_calls_shared_inference_without_cli_bootstrap(self):
        source = (HARNESS / "frozen_entry.py").read_text()
        self.assertIn('report = inference(', source)
        self.assertNotIn('subprocess.', source)
        self.assertNotIn('"-I"', source)
        self.assertNotIn('"--worker"', source)
        self.assertIn('wait_for_job_gate()', source)


if __name__ == "__main__":
    unittest.main()
