"""Stdlib launcher tests with harmless mock scripts; never Torch or models.

Mock executable tests exercise supervision only. A Python shebang in those
fixtures is deliberately not evidence of frozen-runtime portability.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts/merizo_windows_smoke"
SPEC = importlib.util.spec_from_file_location("merizo_posix_launcher", HARNESS / "run_frozen_posix.py")
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = launcher  # dataclass resolves annotations via its module.
sys.path.insert(0, str(HARNESS))
try:
    SPEC.loader.exec_module(launcher)
finally:
    sys.path.remove(str(HARNESS))

FIXTURE = ROOT / "tests/data/domain_annotation/1ubq.pdb"


def runtime_report(package: Path) -> dict:
    normalized, mapping, _ = launcher.prepare(FIXTURE.read_text(encoding="ascii"))
    return {"status": "passed", "frozen": True, "source_commit": launcher.COMMIT,
            "weights_sha256": launcher.WEIGHTS, "input_sha256": launcher.INPUT_SHA,
            "mapping": mapping, "normalized_sha256": launcher.sha(normalized.encode("ascii")),
            "atom_count": 602, "reference_length": 76,
            "feature_sequence_and_coordinates_checked": True, "insertion_roundtrip_checked": True,
            "bundle_root": str(package), "package_directory": str(package),
            "prediction": {"nres": 76, "ndom": 1, "confidence": 0.8,
                           "labels": [1] * 76, "residue_numbers": list(range(1, 77))}}


class PosixLauncherContracts(unittest.TestCase):
    def test_environment_does_not_inherit_python_loader_or_venv(self):
        with tempfile.TemporaryDirectory(prefix="mock merizo env ") as folder:
            with mock.patch.dict(os.environ, {"PYTHONPATH": "outside", "LD_LIBRARY_PATH": "outside",
                                              "DYLD_LIBRARY_PATH": "outside", "VIRTUAL_ENV": "outside"}):
                env = launcher.sanitized_environment(Path(folder))
            self.assertTrue(Path(env["PATH"]).is_dir())
            self.assertEqual(list(Path(env["PATH"]).iterdir()), [])
            self.assertFalse(any(name.startswith(("PYTHON", "LD_", "DYLD_", "VIRTUAL_ENV", "CONDA")) for name in env))
            self.assertTrue(all(Path(env[name]).is_relative_to(folder)
                                for name in ("HOME", "TMPDIR", "XDG_CACHE_HOME", "MPLCONFIGDIR", "TORCH_HOME")))

    def test_capture_files_and_tail_are_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = launcher.Capture(Path(folder))
            try:
                for _ in range(200):
                    capture.feed(b"x" * 4096)
                capture.feed(b"last error")
                self.assertEqual(capture.byte_count, 200 * 4096 + 10)
                self.assertLessEqual(capture.file.tell(), launcher.MAX_CAPTURE_BYTES)
                self.assertLessEqual(len(capture.tail), launcher.TAIL_BYTES)
                self.assertLessEqual(len(capture.tail_text()), 2048)
                self.assertTrue(capture.tail_text().endswith("last error"))
            finally:
                capture.file.close()

    def test_runtime_mapping_pins_and_all_atom_checks_fail_closed(self):
        package = Path("package").resolve()
        valid = runtime_report(package)
        launcher.validate_runtime(valid, package, FIXTURE.read_bytes())
        for patch in ({"frozen": False}, {"input_sha256": "wrong"}, {"mapping": []}, {"atom_count": 76},
                      {"weights_sha256": {}}, {"reference_length": 75}, {"source_commit": "wrong"},
                      {"bundle_root": str(package.parent)}, {"insertion_roundtrip_checked": False}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                launcher.validate_runtime({**copy.deepcopy(valid), **patch}, package, FIXTURE.read_bytes())

    def test_path_ancestor_relations_are_not_disjoint(self):
        root = Path(tempfile.gettempdir()) / "mock path"
        self.assertFalse(launcher.disjoint(root, root / "child"))
        self.assertFalse(launcher.disjoint(root / "child", root))
        self.assertFalse(launcher.disjoint(root, root))
        self.assertTrue(launcher.disjoint(root / "source", root / "package"))

    def test_report_bytes_are_checked_before_write(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "report.json"
            with mock.patch.object(launcher, "MAX_REPORT_BYTES", 20), self.assertRaises(ValueError):
                launcher.write_report(target, {"error": "x" * 40})
            self.assertFalse(target.exists())

    def test_subreaper_abi_is_explicit_linux_only_and_restored(self):
        library = mock.Mock()
        library.prctl.return_value = 0
        with mock.patch.object(launcher.sys, "platform", "linux"), \
             mock.patch.object(launcher.ctypes, "CDLL", return_value=library):
            reaper = launcher.Subreaper()
            self.assertTrue(reaper.enable())
            reaper.restore()
        self.assertEqual(library.prctl.argtypes, [launcher.ctypes.c_int])
        self.assertEqual(library.prctl.restype, launcher.ctypes.c_int)
        self.assertEqual([call.args[0] for call in library.prctl.call_args_list], [37, 36, 36])
        self.assertEqual(library.prctl.call_args_list[-1].args[1], 0)
        with mock.patch.object(launcher.sys, "platform", "darwin"), \
             mock.patch.object(launcher.ctypes, "CDLL") as load:
            self.assertFalse(launcher.Subreaper().enable())
        load.assert_not_called()


@unittest.skipUnless(sys.platform in {"linux", "darwin"}, "POSIX-only process/symlink supervision")
class PosixMockProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mock merizo launcher ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.package = self.base / "package"
        self.package.mkdir()
        self.source = self.base / "absent upstream"
        self.results = self.base / "results"
        self.pins = self.base / "build.json"

    def configure(self, body: str) -> None:
        executable = self.package / launcher.PACKAGE_NAME
        executable.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, signal, sys, time\n"
            "gate = pathlib.Path(os.environ['KUMA_MERIZO_START_GATE'])\n"
            "while not gate.is_file(): time.sleep(0.005)\n" + body,
            encoding="utf-8")
        executable.chmod(0o700)
        pins = {"status": "built", "verified_before_build": True,
                "source_commit": launcher.COMMIT, "weights_sha256": launcher.WEIGHTS,
                "source_directory": str(self.source), "package_directory": str(self.package),
                "elapsed_seconds": 1.25, **launcher.package_inventory(self.package)}
        self.pins.write_text(json.dumps(pins), encoding="utf-8")

    def run_probe(self) -> tuple[int, dict]:
        code = launcher.supervise(self.package, FIXTURE, self.results, self.pins)
        report = json.loads((self.results / "frozen-posix-cpu.json").read_text(encoding="utf-8"))
        return code, report

    def success_body(self) -> str:
        report = runtime_report(self.package)
        return (
            "assert os.getpgrp() == os.getpid() == os.getsid(0)\n"
            "assert not any(k.startswith(('PYTHON','LD_','DYLD_','VIRTUAL_ENV','CONDA')) for k in os.environ)\n"
            "assert not list(pathlib.Path(os.environ['PATH']).iterdir())\n"
            f"report = json.loads({json.dumps(report)!r})\n"
            "report['mock_working_directory'] = os.getcwd()\n"
            "pathlib.Path(sys.argv[sys.argv.index('--output') + 1]).write_text(json.dumps(report))\n"
        )

    def test_mock_success_verifies_reap_rss_and_removes_working_directory(self):
        self.configure(self.success_body())
        code, report = self.run_probe()
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "passed")
        self.assertTrue(report["process_group_termination_verified"])
        self.assertTrue(report["runtime_directory_removed"])
        self.assertGreater(report["peak_rss_bytes"], 0)
        expected_unit = "bytes" if sys.platform == "darwin" else "KiB"
        self.assertEqual(report["peak_rss_raw_unit"], expected_unit)
        self.assertFalse(Path(report["runtime"]["mock_working_directory"]).exists())
        self.assertNotIn("stderr_tail", report)

    def test_failure_keeps_only_bounded_diagnostic_tail(self):
        self.configure("os.write(2, b'x' * 100000 + b'BOOTLOADER ERROR')\nsys.exit(7)\n")
        code, report = self.run_probe()
        self.assertEqual(code, 1, report)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["process_group_termination_verified"])
        self.assertTrue(report["runtime_directory_removed"])
        self.assertEqual(report["exit_code"], 7)
        self.assertEqual(report["stderr_bytes_drained"], 100016)
        self.assertLessEqual(len(report["stderr_tail"]), 2048)
        self.assertTrue(report["stderr_tail"].endswith("BOOTLOADER ERROR"))

    def test_timeout_kills_and_reaps_stubborn_descendant_group(self):
        self.configure("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                       "child = os.fork()\n"
                       "while True: time.sleep(0.01)\n")
        with mock.patch.object(launcher, "TIMEOUT_SECONDS", 0.15):
            code, report = self.run_probe()
        self.assertEqual(code, 2, report)
        self.assertEqual(report["status"], "timed_out")
        self.assertTrue(report["process_group_termination_verified"])
        self.assertTrue(report["runtime_directory_removed"])
        self.assertLess(report["elapsed_seconds"], 10)
        if sys.platform == "linux":
            self.assertEqual(report["reaped_descendants"], 1)

    def test_success_also_cleans_up_descendants_left_by_root(self):
        self.configure("child = os.fork()\n"
                       "if child == 0:\n"
                       "    while True: time.sleep(0.01)\n" + self.success_body())
        code, report = self.run_probe()
        self.assertEqual(code, 0, report)
        self.assertTrue(report["remaining_group_after_root_exit"])
        self.assertTrue(report["process_group_termination_verified"])
        if sys.platform == "linux":
            self.assertEqual(report["reaped_descendants"], 1)

    def test_cancelled_supervisor_still_kills_group_and_writes_failure(self):
        self.configure("while True: time.sleep(0.01)\n")
        drain = launcher.drain_ready
        cancelled = False

        def interrupt_once(*args):
            nonlocal cancelled
            if not cancelled:
                cancelled = True
                raise launcher.Cancelled("mock cancellation")
            return drain(*args)

        with mock.patch.object(launcher, "drain_ready", side_effect=interrupt_once):
            code, report = self.run_probe()
        self.assertEqual(code, 130, report)
        self.assertEqual(report["status"], "cancelled")
        self.assertTrue(report["process_group_termination_verified"])
        self.assertTrue(report["runtime_directory_removed"])

    def test_unverified_group_death_cannot_report_success(self):
        self.configure(self.success_body())
        with mock.patch.object(launcher, "stop_group", return_value=False):
            code, report = self.run_probe()
        self.assertEqual(code, 3)
        self.assertEqual(report["status"], "cleanup_failed")
        self.assertFalse(report["process_group_termination_verified"])
        self.assertTrue(report["runtime_directory_removed"])

    def test_existing_source_is_preserved_and_refused_before_launch(self):
        self.configure(self.success_body())
        self.source.mkdir()
        marker = self.source / "do not delete"
        marker.write_text("preserve", encoding="utf-8")
        with mock.patch.object(launcher.subprocess, "Popen") as process:
            code, report = self.run_probe()
        self.assertEqual(code, 1)
        process.assert_not_called()
        self.assertFalse(report["source_removed"])
        self.assertEqual(marker.read_text(), "preserve")

    def test_subreaper_failure_refuses_launch_but_cleans_runtime(self):
        self.configure(self.success_body())
        with mock.patch.object(launcher.Subreaper, "enable", side_effect=OSError("mock prctl refusal")), \
             mock.patch.object(launcher.subprocess, "Popen") as process:
            code, report = self.run_probe()
        self.assertEqual(code, 1, report)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(report["runtime_directory_removed"])
        process.assert_not_called()

    def test_symlinks_are_internal_and_physical_file_sizes_are_unique(self):
        data = self.package / "payload"
        data.write_bytes(b"hello")
        os.link(data, self.package / "same inode")
        (self.package / "internal link").symlink_to(data)
        self.assertEqual(launcher.package_inventory(self.package),
                         {"package_bytes": 5, "package_file_count": 1, "package_symlink_count": 1})
        outside = self.base / "outside"
        outside.write_bytes(b"not bundled")
        (self.package / "escape").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "escapes"):
            launcher.package_inventory(self.package)


if __name__ == "__main__":
    unittest.main()
