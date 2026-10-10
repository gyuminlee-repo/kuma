"""Native runtime-matrix and supervision contracts; no model/inference/download."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import signal
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("merizo_platform_smoke", ROOT / "scripts/merizo_windows_smoke/run.py")
assert SPEC is not None and SPEC.loader is not None
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class PlatformSmokeContractTests(unittest.TestCase):
    def setUp(self):
        # Mocked POSIX branches also run in the existing Windows harness suite,
        # where the real signal module does not expose SIGKILL.
        patcher = mock.patch.object(smoke.signal, "SIGKILL", getattr(signal, "SIGKILL", 9), create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_native_matrix_and_reported_architecture(self):
        for system, architecture, version in (("Linux", "x86_64", "2.0.1+cpu"),
                                               ("Darwin", "arm64", "2.0.1"),
                                               ("Windows", "AMD64", "2.0.1+cpu")):
            with self.subTest(system=system, architecture=architecture), \
                 mock.patch.object(smoke.platform, "system", return_value=system), \
                 mock.patch.object(smoke.platform, "machine", return_value=architecture):
                contract = smoke.runtime_contract()
                self.assertEqual(contract, {"system": system, "architecture": architecture,
                                            "expected_torch": version, "device": "cpu"})
                smoke.validate_torch_runtime(version, None, contract)
                for bad in ("2.0.2", "2.0.1+cu117", "2.0.1" if version.endswith("+cpu") else "2.0.1+cpu"):
                    with self.subTest(version=bad), self.assertRaisesRegex(ValueError, "CPU-only"):
                        smoke.validate_torch_runtime(bad, None, contract)
                with self.assertRaisesRegex(ValueError, "CPU-only"):
                    smoke.validate_torch_runtime(version, "11.7", contract)

    def test_wrong_architecture_rosetta_and_unlisted_os_fail_before_import(self):
        for system, architecture in (("Darwin", "x86_64"), ("Linux", "aarch64"),
                                     ("Windows", "ARM64"), ("FreeBSD", "x86_64")):
            with self.subTest(system=system, architecture=architecture), \
                 mock.patch.object(smoke.platform, "system", return_value=system), \
                 mock.patch.object(smoke.platform, "machine", return_value=architecture), \
                 mock.patch.object(smoke.importlib, "import_module") as importer, \
                 mock.patch.object(smoke, "verify_weights") as weights:
                with self.assertRaisesRegex(ValueError, "Unsupported smoke platform/architecture"):
                    smoke.inference(Path("unused.pdb"), Path("unused weights"))
                importer.assert_not_called()
                weights.assert_not_called()

    def test_posix_timeout_owns_session_and_kills_group_before_bounded_reap(self):
        process = mock.Mock(pid=12345, returncode=-signal.SIGKILL)
        events = []
        def communicate(*, timeout):
            events.append(("communicate", timeout))
            if timeout == 300:
                raise subprocess.TimeoutExpired("mock worker", timeout)
            return b"bounded stdout", b"bounded stderr"
        process.communicate.side_effect = communicate
        def killpg(pid, sig):
            events.append(("killpg", pid, sig))
        with mock.patch.object(smoke.sys, "platform", "linux"), \
             mock.patch.object(smoke.subprocess, "Popen", return_value=process) as launch, \
             mock.patch.object(smoke.os, "killpg", side_effect=killpg, create=True):
            result = smoke.supervise_worker([sys.executable, "path with spaces.py"], {"OMP_NUM_THREADS": "1"})
        self.assertEqual(result, (-signal.SIGKILL, b"bounded stdout", b"bounded stderr", True))
        self.assertTrue(launch.call_args.kwargs["start_new_session"])
        self.assertFalse(launch.call_args.kwargs["shell"])
        self.assertEqual(events, [("communicate", 300), ("killpg", 12345, signal.SIGKILL), ("communicate", 10)])
        process.kill.assert_not_called()

    def test_posix_normal_exit_cleans_remaining_group(self):
        process = mock.Mock(pid=12345, returncode=0)
        process.communicate.return_value = (b"", b"")
        with mock.patch.object(smoke.sys, "platform", "darwin"), \
             mock.patch.object(smoke.subprocess, "Popen", return_value=process), \
             mock.patch.object(smoke.os, "killpg", create=True) as group:
            self.assertEqual(smoke.supervise_worker(["mock"], {}), (0, b"", b"", False))
        group.assert_called_once_with(12345, signal.SIGKILL)

    def test_missing_group_is_already_stopped_and_cleanup_stays_bounded(self):
        process = mock.Mock(pid=12345, returncode=-signal.SIGKILL)
        process.communicate.side_effect = [subprocess.TimeoutExpired("mock", 300),
                                           subprocess.TimeoutExpired("mock drain", 10)]
        with mock.patch.object(smoke.sys, "platform", "linux"), \
             mock.patch.object(smoke.subprocess, "Popen", return_value=process), \
             mock.patch.object(smoke.os, "killpg", side_effect=ProcessLookupError, create=True):
            with self.assertRaises(subprocess.TimeoutExpired):
                smoke.supervise_worker(["mock"], {})
        self.assertEqual(process.communicate.call_args_list, [mock.call(timeout=300), mock.call(timeout=10)])

    def test_windows_keeps_native_taskkill_timeout_path(self):
        process = mock.Mock(pid=12345, returncode=-1)
        process.poll.return_value = None
        process.communicate.side_effect = [subprocess.TimeoutExpired("mock", 300), (b"", b"")]
        with mock.patch.object(smoke.sys, "platform", "win32"), \
             mock.patch.object(smoke.subprocess, "Popen", return_value=process) as launch, \
             mock.patch.object(smoke.subprocess, "run") as taskkill:
            self.assertTrue(smoke.supervise_worker(["mock"], {})[-1])
        self.assertFalse(launch.call_args.kwargs["start_new_session"])
        taskkill.assert_called_once_with(["taskkill", "/PID", "12345", "/T", "/F"],
                                         capture_output=True, timeout=10, check=False)
        process.kill.assert_called_once()

    def test_architecture_is_written_to_success_report(self):
        source = (ROOT / "scripts/merizo_windows_smoke/run.py").read_text()
        self.assertIn('"architecture": contract["architecture"]', source)
        self.assertIn('"device": contract["device"]', source)
        self.assertIn('torch.set_num_threads(1)', source)
        self.assertIn('torch.set_num_interop_threads(1)', source)
        self.assertIn('network = predict.Merizo().to("cpu")', source)


if __name__ == "__main__":
    unittest.main()
