"""Stdlib launcher tests with harmless mock scripts; never Torch or models.

Mock executable tests exercise supervision only. A Python shebang in those
fixtures is deliberately not evidence of frozen-runtime portability.
"""
from __future__ import annotations

import copy
import errno
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
    def test_entry_generated_full_and_truncated_diagnostics_match_launcher_contract(self):
        specification = importlib.util.spec_from_file_location("diagnostic_contract_entry", HARNESS / "frozen_posix_entry.py")
        assert specification is not None and specification.loader is not None
        entry = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(entry)
        self.assertEqual(entry.MAX_NATIVE_DIAGNOSTIC_BYTES, launcher.MAX_NATIVE_DIAGNOSTIC_BYTES)
        self.assertEqual(entry.MAX_NATIVE_IMAGES, launcher.MAX_NATIVE_DIAGNOSTIC_PATHS)
        self.assertEqual(entry.MAX_PATH_BYTES, launcher.MAX_NATIVE_DIAGNOSTIC_PATH_BYTES)
        self.assertEqual(entry.NATIVE_DIAGNOSTIC_SNAPSHOT, launcher.NATIVE_DIAGNOSTIC_SNAPSHOT)
        for paths in (("/rejected image",), tuple(f"/image/{index}" for index in range(2050)),
                      tuple("/" + "\U0001f9ec" * 1000 + str(index) for index in range(300))):
            with self.subTest(total=len(paths)):
                diagnostic = entry.native_diagnostic(paths)
                self.assertEqual(launcher.failed_runtime({"error": "original", **diagnostic}),
                                 {"status": "failed", "error": "original", **diagnostic})

    def test_failed_runtime_preserves_only_valid_bounded_snapshot_fields(self):
        diagnostic = {"native_diagnostic_paths": ["/rejected/native image"], "native_diagnostic_total": 1,
                      "native_diagnostic_truncated": False, "native_diagnostic_snapshot": "rejected_validation_snapshot"}
        report = launcher.failed_runtime({"status": "passed", "error": "original rejection", **diagnostic,
                                          "arbitrary_payload": {"must": "not be copied"}})
        self.assertEqual(report, {"status": "failed", "error": "original rejection", **diagnostic})
        for patch in ({"native_diagnostic_paths": "not a list"}, {"native_diagnostic_paths": [42]},
                      {"native_diagnostic_paths": ["relative"]}, {"native_diagnostic_paths": ["/bad\nname"]},
                      {"native_diagnostic_paths": ["/" + "x" * 4096]},
                      {"native_diagnostic_paths": ["/path"] * 2049, "native_diagnostic_total": 2049},
                      {"native_diagnostic_paths": ["/" + "x" * 4000] * 100, "native_diagnostic_total": 100},
                      {"native_diagnostic_total": True}, {"native_diagnostic_total": -1},
                      {"native_diagnostic_total": 2**31}, {"native_diagnostic_truncated": 0},
                      {"native_diagnostic_truncated": True}, {"native_diagnostic_snapshot": "approved"}):
            with self.subTest(patch=tuple(patch)):
                result = launcher.failed_runtime({"error": "original rejection", **diagnostic, **patch})
                self.assertEqual(result, {"status": "failed", "error": "original rejection"})
        missing = dict(diagnostic)
        missing.pop("native_diagnostic_total")
        self.assertEqual(launcher.failed_runtime({"error": "original rejection", **missing}),
                         {"status": "failed", "error": "original rejection"})

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


@unittest.skipUnless(sys.platform in {"linux", "darwin"}, "POSIX cleanup state machine")
class PosixCleanupRaceTests(unittest.TestCase):
    def test_transient_probe_eperm_requires_reap_and_real_esrch(self):
        process = mock.Mock(pid=43210, returncode=None)
        observed = launcher.ObservedProcess(process)
        not_ready = (0, 0, mock.Mock(ru_maxrss=0))
        reaped = (process.pid, 15, mock.Mock(ru_maxrss=10))
        with mock.patch.object(launcher.os, "wait4", side_effect=[
                not_ready, not_ready, reaped, ChildProcessError(errno.ECHILD, "reaped")]), \
             mock.patch.object(launcher.os, "killpg", side_effect=[
                 PermissionError(errno.EPERM, "unknown group state"), ProcessLookupError(errno.ESRCH, "gone")]) as killpg, \
             mock.patch.object(launcher.time, "sleep"):
            self.assertTrue(launcher.stop_group(observed))
        self.assertEqual(process.returncode, -15)
        self.assertEqual([call.args[1] for call in killpg.call_args_list], [0, 0])
        self.assertTrue(any(event["stage"] == "initial_probe" and event["errno"] == errno.EPERM
                            and not event["root_reaped"] for event in observed.cleanup_events))
        self.assertEqual(observed.cleanup_events[-1]["errno"], errno.ESRCH)
        self.assertTrue(observed.cleanup_events[-1]["root_reaped"])

    def test_post_term_zombie_window_recovers_by_observation(self):
        process = mock.Mock(pid=43210, returncode=None)
        observed = launcher.ObservedProcess(process)
        not_ready = (0, 0, mock.Mock(ru_maxrss=0))
        reaped = (process.pid, 15, mock.Mock(ru_maxrss=10))
        with mock.patch.object(launcher.os, "wait4", side_effect=[
                not_ready, not_ready, not_ready, not_ready, reaped, ChildProcessError(errno.ECHILD, "reaped")]), \
             mock.patch.object(launcher.os, "killpg", side_effect=[
                 None, None, PermissionError(errno.EPERM, "unknown group state"),
                 ProcessLookupError(errno.ESRCH, "gone")]) as killpg, \
             mock.patch.object(launcher.time, "sleep"):
            self.assertTrue(launcher.stop_group(observed))
        self.assertEqual([call.args[1] for call in killpg.call_args_list], [0, launcher.signal.SIGTERM, 0, 0])
        self.assertTrue(any(event["stage"] == "loop_probe" and event["errno"] == errno.EPERM
                            for event in observed.cleanup_events))

    def test_persistent_eperm_is_unknown_until_original_deadline_then_false(self):
        process = mock.Mock(pid=43210, returncode=0)  # Reaped root alone is insufficient.
        observed = launcher.ObservedProcess(process)
        clock = 100.0

        def sleep(seconds):
            nonlocal clock
            clock += seconds

        with mock.patch.object(launcher.os, "wait4", side_effect=ChildProcessError(errno.ECHILD, "reaped")), \
             mock.patch.object(launcher.os, "killpg", side_effect=PermissionError(errno.EPERM, "still unknown")) as killpg, \
             mock.patch.object(launcher.os, "kill") as root_kill, \
             mock.patch.object(launcher.time, "monotonic", side_effect=lambda: clock), \
             mock.patch.object(launcher.time, "sleep", side_effect=sleep):
            self.assertFalse(launcher.stop_group(observed))
        self.assertAlmostEqual(clock, 100.0 + launcher.CLEANUP_SECONDS)
        self.assertTrue(all(call.args[1] == 0 for call in killpg.call_args_list))
        root_kill.assert_not_called()
        self.assertEqual(len(observed.cleanup_events), 32)
        self.assertGreater(observed.cleanup_event_count, 32)
        self.assertEqual(observed.cleanup_events[-1]["stage"], "final_probe")
        self.assertEqual(observed.cleanup_events[-1]["errno"], errno.EPERM)

    def test_group_esrch_without_root_reap_still_fails_at_deadline(self):
        process = mock.Mock(pid=43210, returncode=None)
        observed = launcher.ObservedProcess(process)
        clock = 100.0

        def sleep(seconds):
            nonlocal clock
            clock += seconds

        with mock.patch.object(launcher.os, "wait4", return_value=(0, 0, mock.Mock(ru_maxrss=0))), \
             mock.patch.object(launcher.os, "killpg", side_effect=ProcessLookupError(errno.ESRCH, "group absent")), \
             mock.patch.object(launcher.os, "kill") as root_kill, \
             mock.patch.object(launcher.time, "monotonic", side_effect=lambda: clock), \
             mock.patch.object(launcher.time, "sleep", side_effect=sleep):
            self.assertFalse(launcher.stop_group(observed))
        self.assertIsNone(process.returncode)
        self.assertAlmostEqual(clock, 100.0 + launcher.CLEANUP_SECONDS)
        root_kill.assert_called_once_with(process.pid, launcher.signal.SIGKILL)
        self.assertEqual(observed.cleanup_events[-1]["stage"], "final_probe")
        self.assertEqual(observed.cleanup_events[-1]["errno"], errno.ESRCH)
        self.assertFalse(observed.cleanup_events[-1]["root_reaped"])

    def test_signal_eperm_is_traced_and_requires_independent_death_evidence(self):
        for denied_signal in (launcher.signal.SIGTERM, launcher.signal.SIGKILL):
            with self.subTest(denied_signal=denied_signal):
                process = mock.Mock(pid=43210, returncode=None)
                observed = launcher.ObservedProcess(process)
                signal_denied = False
                root_reaped = False
                clock = 100.0

                def sleep(seconds):
                    nonlocal clock
                    clock += seconds

                def wait4(_pid, _options):
                    nonlocal root_reaped
                    if root_reaped:
                        raise ChildProcessError(errno.ECHILD, "reaped")
                    if signal_denied:
                        root_reaped = True
                        return process.pid, 15, mock.Mock(ru_maxrss=10)
                    return 0, 0, mock.Mock(ru_maxrss=0)

                def killpg(_pgid, signum):
                    nonlocal signal_denied
                    if root_reaped:
                        raise ProcessLookupError(errno.ESRCH, "gone")
                    if signum == denied_signal:
                        signal_denied = True
                        raise PermissionError(errno.EPERM, "unknown signal result")

                with mock.patch.object(launcher.os, "wait4", side_effect=wait4), \
                     mock.patch.object(launcher.os, "killpg", side_effect=killpg) as send, \
                     mock.patch.object(launcher.time, "monotonic", side_effect=lambda: clock), \
                     mock.patch.object(launcher.time, "sleep", side_effect=sleep):
                    self.assertTrue(launcher.stop_group(observed))
                stage = "sigterm" if denied_signal == launcher.signal.SIGTERM else "sigkill"
                self.assertTrue(any(event["stage"] == stage and event["errno"] == errno.EPERM
                                    for event in observed.cleanup_events))
                self.assertEqual(sum(call.args[1] == denied_signal for call in send.call_args_list), 1)
                self.assertTrue(root_reaped)
                self.assertEqual(observed.cleanup_events[-1]["errno"], errno.ESRCH)

    def test_non_child_wait4_errors_are_not_swallowed(self):
        observed = launcher.ObservedProcess(mock.Mock(pid=43210, returncode=None))
        with mock.patch.object(launcher.os, "wait4", side_effect=OSError(errno.EINVAL, "bad wait")), \
             mock.patch.object(launcher.os, "killpg") as killpg:
            with self.assertRaises(OSError) as caught:
                launcher.stop_group(observed)
        self.assertEqual(caught.exception.errno, errno.EINVAL)
        killpg.assert_not_called()
        self.assertEqual(observed.cleanup_events[-1]["stage"], "wait4_group")
        self.assertEqual(observed.cleanup_events[-1]["errno"], errno.EINVAL)


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

    def test_nonzero_child_snapshot_is_forwarded_without_promoting_failure(self):
        diagnostic = {"native_diagnostic_paths": ["/rejected/first", "/rejected/second"],
                      "native_diagnostic_total": 2, "native_diagnostic_truncated": False,
                      "native_diagnostic_snapshot": "rejected_validation_snapshot"}
        failed = {"status": "passed", "error": "original native rejection", **diagnostic,
                  "arbitrary_runtime": "must not be copied"}
        self.configure(f"report = json.loads({json.dumps(failed)!r})\n"
                       "pathlib.Path(sys.argv[sys.argv.index('--output') + 1]).write_text(json.dumps(report))\n"
                       "sys.exit(7)\n")
        code, report = self.run_probe()
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["runtime"], {"status": "failed", "error": "original native rejection", **diagnostic})
        self.assertTrue(report["process_group_termination_verified"])
        self.assertTrue(report["runtime_directory_removed"])

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

    def test_initial_diagnostic_eperm_does_not_skip_actual_cleanup(self):
        self.configure(self.success_body())
        exists = launcher.group_exists
        diagnostic_called = False

        def diagnostic_unknown_once(pgid):
            nonlocal diagnostic_called
            if not diagnostic_called:
                diagnostic_called = True
                raise PermissionError(errno.EPERM, "mock diagnostic race")
            return exists(pgid)

        with mock.patch.object(launcher, "group_exists", side_effect=diagnostic_unknown_once), \
             mock.patch.object(launcher, "stop_group", wraps=launcher.stop_group) as cleanup:
            code, report = self.run_probe()
        self.assertEqual(code, 0, report)
        cleanup.assert_called_once()
        self.assertIsNone(report["remaining_group_after_root_exit"])
        self.assertTrue(report["process_group_termination_verified"])
        self.assertTrue(report["runtime_directory_removed"])
        self.assertEqual(report["cleanup_trace"][0]["stage"], "diagnostic_probe")
        self.assertEqual(report["cleanup_trace"][0]["errno"], errno.EPERM)
        self.assertEqual(report["cleanup_trace"][-1]["errno"], errno.ESRCH)
        self.assertIn("undetermined", report["cleanup_eperm_cause"])

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
