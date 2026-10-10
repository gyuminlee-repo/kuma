"""Model-free native CPython 3.11.9 venv/helper identity and lifecycle probe.

The caller creates the venv and installs only psutil==7.2.2. Run this file with
that venv's python.exe -I. The caller owns its venv; this script never installs,
downloads, or removes it. Only a final cleanup_verified=true permits removal.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "kuma_core" / "kuro"))
import domain_process  # type: ignore[import-not-found]  # Exact stdlib source alias.
import domain_watchdog  # type: ignore[import-not-found]

SCHEMA = "kuma-windows-venv-domain-contract-v1"
MAX_REPORT = 16 * 1024
CHILD = """
import json, os, pathlib, psutil, sys
print(json.dumps({
    'pid': os.getpid(), 'created': psutil.Process().create_time(),
    'prefix': sys.prefix, 'executable': sys.executable,
    'dependency': str(pathlib.Path(psutil.__file__).resolve()),
    'psutil_version': psutil.__version__, 'isolated': sys.flags.isolated,
    'version': list(sys.version_info[:3]),
}), flush=True)
"""


def _exact_exited(pid: int, created: float) -> bool:
    try:
        return psutil.Process(pid).create_time() != created
    except psutil.NoSuchProcess:
        return True


def _interpreter_probe(executable: str, env: dict[str, str], cwd: Path) -> dict:
    child = subprocess.Popen([executable, "-I", "-c", CHILD], cwd=cwd, env=env,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, shell=False)
    try:
        stdout, stderr = child.communicate(timeout=10)
    finally:
        if child.poll() is None:
            # Only this probe's owned Popen handle; never a PID search/guess.
            # For a redirector this is NOT descendant cleanup proof. Any
            # failure keeps cleanup_verified false and preserves the workspace.
            child.kill()
            child.wait(timeout=5)
        for stream in (child.stdout, child.stderr):
            if stream is not None:
                stream.close()
    if child.returncode != 0 or stderr or len(stdout) > 4096:
        raise RuntimeError("Interpreter identity probe failed")
    value = json.loads(stdout)
    if (not isinstance(value, dict)
            or set(value) != {"pid", "created", "prefix", "executable", "dependency",
                              "psutil_version", "isolated", "version"}
            or type(value["pid"]) is not int or value["pid"] <= 1
            or type(value["created"]) not in {float, int}
            or not math.isfinite(value["created"]) or value["created"] <= 0
            or any(not isinstance(value[key], str) for key in ("prefix", "executable", "dependency"))):
        raise ValueError("Invalid interpreter identity report")
    prefix = Path(sys.prefix).resolve()
    checks = {
        "popen_pid": child.pid, "python_pid": value["pid"],
        "popen_pid_matches_python": child.pid == value["pid"],
        "popen_exit_verified": child.returncode == 0,
        "python_identity_exit_verified": _exact_exited(value["pid"], value["created"]),
        "venv_prefix_retained": Path(value["prefix"]).resolve() == prefix,
        "venv_executable_retained": Path(value["executable"]).resolve() == Path(sys.executable).resolve(),
        "psutil_from_venv": Path(value["dependency"]).resolve().is_relative_to(prefix),
        "psutil_version_retained": value["psutil_version"] == "7.2.2",
        "isolated_mode_retained": value["isolated"] == 1,
        "python_version_retained": value["version"] == [3, 11, 9],
    }
    if not all(value for key, value in checks.items()
               if key not in {"popen_pid", "python_pid", "popen_pid_matches_python"}):
        raise RuntimeError("Interpreter context or cleanup was not verified")
    return checks


def _source_lifecycle() -> dict:
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("windows_venv_source_lifecycle", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_probe(None, timeout_seconds=3)


def run_probe(report_path: Path) -> dict:
    report = {"schema": SCHEMA, "status": "running", "stage": "validate_host",
              "python_version": platform.python_version(), "cleanup_verified": False,
              "private_workspace_removed": False,
              "scope": "synthetic_windows_venv_helper_identity_and_lifecycle_only",
              "checks": {}, "not_verified": ["historical_stall_stack", "all_phase_absolute_deadline",
                                                "Merizo_inference", "runtime_distribution"]}
    started = time.monotonic()

    def checkpoint(stage: str) -> None:
        report["stage"] = stage
        raw = json.dumps(report, sort_keys=True, allow_nan=False) + "\n"
        if len(raw.encode("utf-8")) > MAX_REPORT:
            raise ValueError("Probe report exceeds bound")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = report_path.with_name(report_path.name + ".tmp")
        temporary.write_text(raw, encoding="utf-8")
        temporary.replace(report_path)
        print(json.dumps({"schema": SCHEMA, "stage": stage}), flush=True)

    try:
        checkpoint("validate_host")
        if (os.name != "nt" or platform.python_implementation() != "CPython"
                or sys.version_info[:3] != (3, 11, 9) or sys.prefix == sys.base_prefix
                or psutil.__version__ != "7.2.2"):
            raise RuntimeError("Require native Windows CPython 3.11.9 venv with psutil 7.2.2")
        # Do not use TemporaryDirectory here: a failed raw redirector probe can
        # leave an unobserved interpreter alive. Preserve its cwd on every
        # failure; the isolated CI runner's teardown is the explicit fallback.
        work = Path(tempfile.mkdtemp(prefix="kuma venv helper probe ")).resolve()
        private = work / "private"
        private.mkdir()
        env = domain_process._environment(private)
        checkpoint("raw_redirector")
        raw = _interpreter_probe(sys.executable, env, work)
        report["checks"]["raw_redirector"] = raw
        if raw["popen_pid_matches_python"]:
            raise AssertionError("Expected the pinned Windows venv redirector topology")
        checkpoint("direct_helper")
        helper_python, helper_env = domain_watchdog._helper_interpreter(env)
        direct = _interpreter_probe(helper_python, helper_env, work)
        report["checks"]["direct_helper"] = direct
        if not direct["popen_pid_matches_python"] or "__PYVENV_LAUNCHER__" in env:
            raise AssertionError("Direct helper identity or runtime environment isolation failed")
        report["checks"]["runtime_environment_unchanged"] = True
        checkpoint("leased_source_lifecycle")
        lifecycle = _source_lifecycle()
        report["checks"]["lifecycle"] = lifecycle.get("checks", {})
        stage = lifecycle.get("stage")
        report["lifecycle_outcome"] = {
            "stage": stage if stage in {"ipc", "success", "cancel", "timeout", "hard_loss", "completed"} else "unknown",
            "passed": lifecycle.get("status") == "passed",
            "temporary_files_removed": lifecycle.get("temporary_files_removed") is True,
            "error_present": "error" in lifecycle,
            "cleanup_error_present": "cleanup_error" in lifecycle,
        }  # Never forward the inner probe's arbitrary diagnostic/path strings.
        if (lifecycle.get("status") != "passed" or lifecycle.get("mode") != "source"
                or lifecycle.get("temporary_files_removed") is not True):
            raise RuntimeError("Source lifecycle or cleanup was not verified")
        for mode in ("success", "cancel", "timeout", "hard_loss"):
            checked = lifecycle["checks"].get(mode, {})
            if not all(checked.get(key) is True for key in (
                    "passed", "termination_verified", "helper_exit_verified", "registry_admitted_after_cleanup",
                    "host_pid_verified")):
                raise RuntimeError("Incomplete leased lifecycle cleanup evidence")
        shutil.rmtree(work)  # Every probe's child/helper exit has been verified.
        report["private_workspace_removed"] = not work.exists()
        if not report["private_workspace_removed"]:
            raise RuntimeError("Probe workspace cleanup was not verified")
        report["cleanup_verified"] = True
        report["status"] = "passed"
        checkpoint("completed")
    except Exception as exc:
        report["status"] = "failed"
        report["cleanup_verified"] = False
        report["error_type"] = type(exc).__name__[:80]
        checkpoint(report["stage"])
    report["seconds"] = round(time.monotonic() - started, 3)
    checkpoint(report["stage"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Refuse a stale probe report")
    return 0 if run_probe(args.report)["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
