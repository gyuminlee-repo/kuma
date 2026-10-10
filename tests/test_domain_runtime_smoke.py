"""Synthetic host fixture tests; frozen platform evidence belongs to CI probes."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "scripts" / "domain_runtime_smoke"
SPEC = importlib.util.spec_from_file_location("domain_smoke_driver", DIRECTORY / "run.py")
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class DomainRuntimeProbeTests(unittest.TestCase):
    def test_source_cli_reports_actual_ipc_and_lifecycle_without_frozen_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            process = subprocess.run([sys.executable, "-I", str(DIRECTORY / "run.py"),
                                      "--report", str(report_path), "--timeout-seconds", "3"],
                                     cwd=ROOT, capture_output=True, text=True, timeout=90)
            report = json.loads(report_path.read_text())
            self.assertEqual(process.returncode, 0, report)
            self.assertEqual(json.loads(process.stdout), report)
            self.assertEqual(process.stderr, "")
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["mode"], "source")
            self.assertFalse(report["checks"]["actual_frozen_identity"])
            self.assertTrue(report["checks"]["hard_loss"]["helper_exit_verified"])
            self.assertTrue(report["checks"]["hard_loss"]["registry_refused_during_suspended_helper_cleanup"])
            self.assertTrue(report["temporary_files_removed"])
            for name in ("success", "cancel", "timeout", "hard_loss"):
                self.assertTrue(report["checks"][name]["termination_verified"], name)
            self.assertEqual(report["checks"]["hard_loss"]["method"], "host_os_exit_without_cleanup")

    def test_exact_private_entry_dispatch_precedes_stdout(self):
        process = subprocess.run([sys.executable, "-I", str(DIRECTORY / "entry.py"),
                                  "--kuma-domain-supervisor", "invalid"],
                                 capture_output=True, timeout=10)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(process.stdout, b"")
        self.assertEqual(process.stderr, b"")

    def test_invalid_utf8_frame_does_not_drop_following_rpc(self):
        with tempfile.TemporaryDirectory() as directory:
            process = smoke.Process([sys.executable, "-I", str(DIRECTORY / "entry.py"), "--ipc"],
                                    Path(directory))
            try:
                process.send(b"\xff\n" + smoke.request(5, "echo", "日本"))
                self.assertEqual(process.receive()["error"]["code"], -32700)
                self.assertEqual(process.receive()["result"]["text"], "日本")
                process.send(smoke.request(6, "shutdown"))
                self.assertTrue(process.receive()["result"]["ok"])
                self.assertEqual(process.process.wait(timeout=10), 0)
            finally:
                process.close()

    def test_stdout_timeout_is_bounded_and_child_is_cleaned(self):
        with tempfile.TemporaryDirectory() as directory:
            process = smoke.Process([sys.executable, "-I", "-c", "import time; time.sleep(30)"],
                                    Path(directory))
            try:
                with self.assertRaisesRegex(TimeoutError, "timed out"):
                    process.receive(timeout=0.05)
            finally:
                process.close()
            self.assertIsNotNone(process.process.poll())

    def test_bad_binary_and_timeout_report_json_failure(self):
        for extra in (("--binary", "does-not-exist-fixture-binary"), ("--timeout-seconds", "0")):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "error.json"
                process = subprocess.run([sys.executable, "-I", str(DIRECTORY / "run.py"),
                                          "--report", str(path), *extra],
                                         cwd=ROOT, capture_output=True, text=True, timeout=10)
                self.assertEqual(process.returncode, 1)
                report = json.loads(path.read_text())
                self.assertEqual(report["status"], "failed")
                self.assertEqual(json.loads(process.stdout), report)
                self.assertEqual(process.stderr, "")


if __name__ == "__main__":
    unittest.main()
