"""Test-only POSIX frozen executable supervisor, never a product launcher.

The CI supervisor uses Python; the supervised program is the absolute frozen
executable, with no developer Python, loader variables or executable search path.
Process groups are lifecycle control, not a sandbox against setsid()/escape.
"""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import BinaryIO

from run import COMMIT, INPUT_SHA, WEIGHTS, prepare, sha, validate_prediction

TIMEOUT_SECONDS = 300
CLEANUP_SECONDS = 10
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_RUNTIME_BYTES = 1024 * 1024
MAX_CAPTURE_BYTES = 64 * 1024
MAX_NATIVE_DIAGNOSTIC_BYTES = 256 * 1024
MAX_NATIVE_DIAGNOSTIC_PATHS = 2048
MAX_NATIVE_DIAGNOSTIC_PATH_BYTES = 4096
NATIVE_DIAGNOSTIC_SNAPSHOT = "rejected_validation_snapshot"
TAIL_BYTES = 8192
TAIL_CHARACTERS = 2048
PACKAGE_NAME = "merizo-frozen-smoke"


def disjoint(first: Path, second: Path) -> bool:
    a, b = first.resolve(), second.resolve()
    return not a.is_relative_to(b) and not b.is_relative_to(a)


def read_small_json(path: Path, limit: int) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("JSON report missing, symbolic, or oversized")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("JSON report grew beyond its limit")
    report = json.loads(raw)
    if not isinstance(report, dict):
        raise ValueError("JSON report must be an object")
    return report


def write_report(path: Path, report: dict) -> None:
    text = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if len(text.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("Combined report exceeds 2 MiB")
    if path.is_symlink():
        raise ValueError("Result file must not be a symbolic link")
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    temporary.replace(path)


def package_inventory(package: Path) -> dict[str, int]:
    if not package.is_dir():
        raise ValueError("Frozen package directory is missing")
    entries = list(package.rglob("*"))
    identities: set[tuple[int, int]] = set()
    total = count = links = 0
    for path in entries:
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(package):
                raise ValueError("Bundle symbolic link escapes its package")
            links += 1
            continue
        details = path.stat()
        if not stat.S_ISREG(details.st_mode) and not stat.S_ISDIR(details.st_mode):
            raise ValueError("Unexpected special file in frozen package")
        identity = details.st_dev, details.st_ino
        if stat.S_ISREG(details.st_mode) and identity not in identities:
            identities.add(identity)
            total += details.st_size
            count += 1
    return {"package_bytes": total, "package_file_count": count, "package_symlink_count": links}


def sanitized_environment(runtime: Path) -> dict[str, str]:
    paths = {"PATH": runtime / "empty executable path", "HOME": runtime / "home",
             "TMPDIR": runtime / "tmp", "XDG_CACHE_HOME": runtime / "cache",
             "MPLCONFIGDIR": runtime / "matplotlib", "TORCH_HOME": runtime / "torch"}
    for path in paths.values():
        path.mkdir()
    env = {name: str(path) for name, path in paths.items()}
    env.update({"TEMP": env["TMPDIR"], "TMP": env["TMPDIR"], "LANG": "C", "LC_ALL": "C",
                "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MPLBACKEND": "Agg", "CUDA_VISIBLE_DEVICES": "",
                "KUMA_MERIZO_START_GATE": str(runtime / "process group ready")})
    return env


class Capture:
    """Drain arbitrary output, retaining a capped temporary prefix and short tail."""

    def __init__(self, directory: Path):
        self.file: BinaryIO = tempfile.TemporaryFile(dir=directory)
        self.byte_count = 0
        self.tail = b""

    def feed(self, data: bytes) -> None:
        remaining = max(0, MAX_CAPTURE_BYTES - self.byte_count)
        if remaining:
            self.file.write(data[:remaining])
        self.byte_count += len(data)
        self.tail = (self.tail + data)[-TAIL_BYTES:]

    def tail_text(self) -> str:
        return self.tail.decode("utf-8", errors="replace")[-TAIL_CHARACTERS:]


class Cancelled(Exception):
    pass


def cancel(signum: int, _frame: object) -> None:
    raise Cancelled(f"Supervisor received signal {signum}")


class Subreaper:
    """Linux can reap orphaned group members; macOS delegates them to launchd."""

    def __init__(self):
        self.previous = ctypes.c_int(0)
        self.library: ctypes.CDLL | None = None

    def enable(self) -> bool:
        if sys.platform != "linux":
            return False
        library = ctypes.CDLL(None, use_errno=True)
        # prctl(int option, ...) is variadic; declare its fixed parameter and
        # integer return value, leaving pointer-sized optional args to ctypes.
        library.prctl.argtypes = [ctypes.c_int]
        library.prctl.restype = ctypes.c_int
        if library.prctl(37, ctypes.byref(self.previous), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot read child-subreaper state")
        if library.prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot enable bounded descendant reaping")
        self.library = library
        return True

    def restore(self) -> None:
        if self.library is not None:
            if self.library.prctl(36, self.previous.value, 0, 0, 0) != 0:
                raise OSError(ctypes.get_errno(), "Cannot restore child-subreaper state")


@dataclass
class ObservedProcess:
    process: subprocess.Popen[bytes]
    rss_raw: float | None = None
    reaped_descendants: int = 0

    def reap(self, group: bool = False) -> None:
        if not group and self.process.returncode is not None:
            return
        while True:
            try:
                pid, status, usage = os.wait4(-self.process.pid if group else self.process.pid, os.WNOHANG)
            except ChildProcessError:
                return
            if pid == 0:
                return
            if pid == self.process.pid:
                self.process.returncode = os.waitstatus_to_exitcode(status)
                self.rss_raw = float(usage.ru_maxrss)
            else:
                self.reaped_descendants += 1
            if not group:
                return


def group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True  # PermissionError propagates; it is never proof of termination.


def stop_group(observed: ObservedProcess) -> bool:
    """Bound the entire TERM/KILL/reap sequence, including after root success."""
    deadline = time.monotonic() + CLEANUP_SECONDS
    pgid = observed.process.pid
    observed.reap(group=True)
    if not group_exists(pgid):
        if observed.process.returncode is not None:
            return True
        # A startup refusal may happen before session ownership is observed.
        # Kill only our still-unreaped root PID; never signal the parent's group.
        try:
            os.kill(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    hard_kill_at = time.monotonic() + 0.25
    killed = False
    while time.monotonic() < deadline:
        observed.reap(group=True)
        observed.reap()
        if not group_exists(pgid):
            return observed.process.returncode is not None
        if not killed and time.monotonic() >= hard_kill_at:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            killed = True
        time.sleep(0.02)
    observed.reap(group=True)
    return not group_exists(pgid) and observed.process.returncode is not None


def drain_ready(selector: selectors.BaseSelector, captures: dict[str, Capture], timeout: float) -> None:
    for key, _ in selector.select(timeout):
        data = os.read(key.fd, 64 * 1024)
        if data:
            captures[key.data].feed(data)
        else:
            selector.unregister(key.fileobj)


def validate_runtime(report: dict, package: Path, fixture: bytes) -> None:
    normalized, mapping, _ = prepare(fixture.decode("ascii"))
    if (report.get("status") != "passed" or report.get("frozen") is not True
            or report.get("source_commit") != COMMIT or report.get("weights_sha256") != WEIGHTS
            or report.get("input_sha256") != INPUT_SHA or report.get("mapping") != mapping
            or report.get("normalized_sha256") != sha(normalized.encode("ascii"))
            or report.get("atom_count") != 602 or report.get("reference_length") != 76
            or report.get("feature_sequence_and_coordinates_checked") is not True
            or report.get("insertion_roundtrip_checked") is not True):
        raise ValueError("Frozen runtime pin, identity, or all-atom evidence is incomplete")
    for name in ("bundle_root", "package_directory"):
        if not isinstance(report.get(name), str) or Path(report[name]).resolve() != package:
            raise ValueError("Frozen runtime bundle path differs from the built package")
    validate_prediction(report["prediction"])


def failed_runtime(report: dict) -> dict:
    """Allowlist failed-child diagnostics without promoting them to provenance."""
    failure = {"status": "failed", "error": str(report.get("error", ""))[:12000]}
    keys = ("native_diagnostic_paths", "native_diagnostic_total", "native_diagnostic_truncated",
            "native_diagnostic_snapshot")
    if not any(key in report for key in keys):
        return failure
    try:
        diagnostic = {key: report[key] for key in keys}
        paths = diagnostic["native_diagnostic_paths"]
        total = diagnostic["native_diagnostic_total"]
        truncated = diagnostic["native_diagnostic_truncated"]
        if (not isinstance(paths, list) or len(paths) > MAX_NATIVE_DIAGNOSTIC_PATHS
                or type(total) is not int or not len(paths) <= total <= 2**31 - 1
                or type(truncated) is not bool or truncated != (total != len(paths))
                or diagnostic["native_diagnostic_snapshot"] != NATIVE_DIAGNOSTIC_SNAPSHOT):
            raise ValueError("Invalid native diagnostic format")
        for path in paths:
            if (not isinstance(path, str) or not path.startswith("/")
                    or any(character in path for character in "\x00\r\n")
                    or len(path.encode("utf-8")) > MAX_NATIVE_DIAGNOSTIC_PATH_BYTES):
                raise ValueError("Invalid native diagnostic path")
        if len(json.dumps(diagnostic, indent=2, allow_nan=False).encode("utf-8")) > MAX_NATIVE_DIAGNOSTIC_BYTES:
            raise ValueError("Native diagnostic exceeds byte limit")
        failure.update(diagnostic)
    except (KeyError, TypeError, ValueError):
        # Keep the original status/error even if optional diagnostics are bad.
        pass
    return failure


def supervise(package_directory: Path, fixture: Path, result_directory: Path, pin_report: Path) -> int:
    report: dict = {"status": "failed", "scope": "frozen_posix_cpu_public_fixture_smoke_only",
        "platform": sys.platform, "timeout_seconds": TIMEOUT_SECONDS, "cleanup_timeout_seconds": CLEANUP_SECONDS,
        "source_removed": False, "process_started": False, "process_group_termination_verified": None,
        "runtime_directory_removed": None, "system_python_physically_removed": False,
        "not_verified": ["absence of system Python installation", "KUMA integration", "installer",
                         "redistribution rights", "biological accuracy", "processes deliberately escaping their group",
                         "summed process-tree peak memory"]}
    result_path: Path | None = None
    runtime: Path | None = None
    observed: ObservedProcess | None = None
    source: Path | None = None
    captures: dict[str, Capture] = {}
    selector = selectors.DefaultSelector()
    subreaper = Subreaper()
    original_signals = {}
    started: float | None = None
    exit_code = 1
    try:
        if sys.platform not in {"linux", "darwin"} or not hasattr(os, "wait4"):
            raise ValueError("This supervisor requires native Linux or macOS with wait4")
        if package_directory.is_symlink() or fixture.is_symlink() or pin_report.is_symlink():
            raise ValueError("Top-level package, fixture, and pin report cannot be symbolic links")
        package, fixture, result_directory, pin_report = (
            path.resolve() for path in (package_directory, fixture, result_directory, pin_report))
        repo = Path(__file__).resolve().parents[2]
        if not disjoint(package, result_directory):
            raise ValueError("Result and package directories overlap")
        result_directory.mkdir(parents=True, exist_ok=True)
        result_path = result_directory / "frozen-posix-cpu.json"
        if result_path in {fixture, pin_report} or result_path.is_symlink():
            result_path = None
            raise ValueError("Result file would replace an input or symbolic link")
        write_report(result_path, {"status": "started"})
        pins = read_small_json(pin_report, MAX_RUNTIME_BYTES)
        if (pins.get("status") != "built" or pins.get("verified_before_build") is not True
                or pins.get("source_commit") != COMMIT or pins.get("weights_sha256") != WEIGHTS):
            raise ValueError("Build report lacks verified official source and model pins")
        raw_source = Path(pins["source_directory"])
        if not raw_source.is_absolute() or not Path(pins["package_directory"]).is_absolute():
            raise ValueError("Build evidence paths must be absolute")
        source = raw_source.resolve()
        if (Path(pins["package_directory"]).resolve() != package or not disjoint(source, package)
                or not disjoint(source, result_directory)):
            raise ValueError("Build source/package/result paths overlap or do not match")
        if os.path.lexists(raw_source):
            raise ValueError("Workflow must remove official upstream source before launch")
        report["source_removed"] = True
        fixture_bytes = fixture.read_bytes()
        if sha(fixture_bytes) != INPUT_SHA or pins.get("input_sha256", INPUT_SHA) != INPUT_SHA:
            raise ValueError("Only the pinned public 1UBQ fixture is permitted")
        prepare(fixture_bytes.decode("ascii"))
        inventory = package_inventory(package)
        if any(pins.get(name) != value for name, value in inventory.items()):
            raise ValueError("Package inventory differs from build evidence")
        report.update(inventory)
        report["source_commit"], report["weights_sha256"], report["input_sha256"] = COMMIT, WEIGHTS, INPUT_SHA
        report["build_elapsed_seconds"] = pins.get("elapsed_seconds")
        executable = package / PACKAGE_NAME
        if executable.is_symlink() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError("Expected executable is missing or is not a regular executable file")
        temp_parent = Path(tempfile.gettempdir()).resolve()
        # Check BEFORE mkdir: never create/delete anything in a source/package.
        candidate = temp_parent / ("kuma merizo frozen " + os.urandom(12).hex())
        if any(not disjoint(candidate, other) for other in (repo, source, package, result_directory)):
            raise ValueError("Fresh runtime directory must be outside repository/source/package/results")
        candidate.mkdir(mode=0o700)
        runtime = candidate
        runtime_fixture = runtime / "public input with spaces.pdb"
        runtime_report = runtime / "frozen-runtime.json"
        runtime_fixture.write_bytes(fixture_bytes)
        env = sanitized_environment(runtime)
        report["sanitized_env"] = {"inherited_environment_cleared": True,
            "permitted_names": sorted(env), "path_contains_only_empty_private_directory": True,
            "python_loader_venv_variables_present": [name for name in env
                if name.startswith(("PYTHON", "LD_", "DYLD_", "CONDA", "VIRTUAL_ENV"))],
            "home_tmp_and_caches_are_private": True}
        report["working_directory_has_spaces"] = " " in runtime.name
        report["working_directory_outside_repository_source_package"] = True
        report["copied_inputs"] = ["pinned_public_1ubq_fixture_only"]
        captures = {name: Capture(runtime) for name in ("stdout", "stderr")}
        report["linux_child_subreaper_enabled"] = subreaper.enable()
        for signum in (signal.SIGINT, signal.SIGTERM):
            original_signals[signum] = signal.signal(signum, cancel)
        if os.path.lexists(raw_source):
            report["source_removed"] = False
            raise ValueError("Official source reappeared before launch")
        started = time.monotonic()
        process = subprocess.Popen([str(executable), "--fixture", str(runtime_fixture), "--output", str(runtime_report)],
            cwd=runtime, env=env, shell=False, start_new_session=True, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        observed = ObservedProcess(process)
        report["process_started"] = True
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            assert stream is not None
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        if os.getpgid(process.pid) != process.pid or os.getsid(process.pid) != process.pid:
            raise ValueError("Frozen child does not own its isolated session/process group")
        report["process_group_owned_before_inference"] = True
        Path(env["KUMA_MERIZO_START_GATE"]).write_text("ready", encoding="ascii")
        while process.returncode is None:
            observed.reap()
            if process.returncode is not None:
                break
            if time.monotonic() - started >= TIMEOUT_SECONDS:
                raise TimeoutError("Frozen process exceeded 300-second watchdog")
            drain_ready(selector, captures, 0.05)
        report["exit_code"] = process.returncode
        if process.returncode != 0:
            if runtime_report.exists():
                try:
                    failed = read_small_json(runtime_report, MAX_RUNTIME_BYTES)
                    report["runtime"] = failed_runtime(failed)
                except (OSError, ValueError):
                    report["runtime_report_error"] = "Failed runtime report was invalid or oversized"
            raise RuntimeError("Frozen executable exited unsuccessfully")
        child_report = read_small_json(runtime_report, MAX_RUNTIME_BYTES)
        validate_runtime(child_report, package, fixture_bytes)
        report["runtime"] = child_report
        report["status"] = "passed"
        exit_code = 0
    except Cancelled as exc:
        report.update(status="cancelled", error=str(exc))
        exit_code = 130
    except TimeoutError as exc:
        report.update(status="timed_out", error=str(exc), watchdog_triggered=True)
        exit_code = 2
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}"[:2000])
    finally:
        for signum in original_signals:
            signal.signal(signum, signal.SIG_IGN)
        if observed is not None:
            try:
                report["remaining_group_after_root_exit"] = group_exists(observed.process.pid)
                dead = stop_group(observed)
                report["process_group_termination_verified"] = dead
                report["reaped_descendants"] = observed.reaped_descendants
                report["exit_code"] = observed.process.returncode
                if not dead:
                    raise RuntimeError("Process-group termination/reaping could not be verified")
                drain_deadline = time.monotonic() + 0.5
                while selector.get_map() and time.monotonic() < drain_deadline:
                    drain_ready(selector, captures, 0.01)
                report["output_streams_closed"] = not selector.get_map()
                if selector.get_map():
                    raise RuntimeError("Output streams remain open after group termination")
                if observed.rss_raw is not None and math.isfinite(observed.rss_raw):
                    unit = "bytes" if sys.platform == "darwin" else "KiB"
                    report["peak_rss_raw"] = observed.rss_raw
                    report["peak_rss_raw_unit"] = unit
                    report["peak_rss_bytes"] = int(observed.rss_raw * (1 if unit == "bytes" else 1024))
                    report["peak_rss_basis"] = "os.wait4 root-process rusage.ru_maxrss; not a summed process-group peak"
            except Exception as exc:
                report.update(status="cleanup_failed", cleanup_error=str(exc)[:2000])
                exit_code = 3
            finally:
                for stream in (observed.process.stdout, observed.process.stderr):
                    if stream is not None:
                        stream.close()
        selector.close()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3) if started is not None else 0
        for name, capture in captures.items():
            report[name + "_bytes_drained"] = capture.byte_count
            if name == "stderr" and report["status"] != "passed":
                report["stderr_tail"] = capture.tail_text()
            capture.file.close()
        try:
            subreaper.restore()
        except Exception as exc:
            report.update(status="cleanup_failed", cleanup_error=str(exc)[:2000])
            exit_code = 3
        try:
            if runtime is not None:
                shutil.rmtree(runtime)
                report["runtime_directory_removed"] = not runtime.exists()
                if not report["runtime_directory_removed"]:
                    raise RuntimeError("Temporary runtime directory remains")
        except Exception as exc:
            report.update(status="cleanup_failed", cleanup_error=str(exc)[:2000])
            exit_code = 3
        for signum, previous in original_signals.items():
            signal.signal(signum, previous)
        if result_path is not None:
            try:
                write_report(result_path, report)
            except Exception:
                # Never leave the earlier started/success status as a result.
                if not result_path.is_symlink():
                    result_path.write_text('{"status":"failed","error":"Could not save bounded result"}\n', encoding="utf-8")
                exit_code = 1
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-directory", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--result-directory", type=Path, required=True)
    parser.add_argument("--pin-report", type=Path, required=True)
    args = parser.parse_args(argv)
    return supervise(args.package_directory, args.fixture, args.result_directory, args.pin_report)


if __name__ == "__main__":
    raise SystemExit(main())
