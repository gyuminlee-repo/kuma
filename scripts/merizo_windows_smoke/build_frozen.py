"""Bounded CI-only Merizo onedir packaging probe; never a product distribution.

This script uses already-installed, pinned CI dependencies. It cannot install or
fetch anything. Only a small evidence JSON is retained outside the build folder.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from run import COMMIT, WEIGHTS, verify_upstream

PYINSTALLER_VERSION = "6.16.0"
BUILD_TIMEOUT_SECONDS = 600
PACKAGE_NAME = "merizo-frozen-smoke"
HIDDEN_IMPORTS = (
    "predict", "model.network", "model.utils.features", "model.utils.utils",
    "torch", "numpy", "scipy", "networkx", "einops", "rotary_embedding_torch", "natsort",
)
MAX_EVIDENCE_BYTES = 1024 * 1024


def disjoint(first: Path, second: Path) -> bool:
    a, b = first.resolve(), second.resolve()
    return not a.is_relative_to(b) and not b.is_relative_to(a)


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def own_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    return {name: digest_file(root / name) for name in
            ("run.py", "frozen_entry.py", "build_frozen.py", "run_frozen.ps1")}


def source_hashes(source: Path) -> dict[str, str]:
    raw = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"], timeout=30)
    names = raw.decode("utf-8").split("\0")
    return {name: digest_file(source / name) for name in names if name.endswith(".py")}


def write_evidence(path: Path, evidence: dict) -> None:
    text = json.dumps(evidence, indent=2, allow_nan=False) + "\n"
    if len(text.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise ValueError("Build evidence exceeds byte limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def build_command(source: Path, output: Path) -> list[str]:
    own = Path(__file__).resolve().parent
    command = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--onedir",
               "--console", "--noupx", "--name", PACKAGE_NAME,
               "--distpath", str(output / "dist"), "--workpath", str(output / "work"),
               "--specpath", str(output / "spec"), "--paths", str(source), "--paths", str(own),
               "--collect-submodules", "model", "--copy-metadata", "torch"]
    for name in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", name])
    for name in WEIGHTS:
        command.extend(["--add-data", str(source / "weights" / name) + os.pathsep + "merizo_weights"])
    command.append(str(own / "frozen_entry.py"))
    return command


def package_inventory(package: Path) -> dict[str, int]:
    files = list(package.rglob("*"))
    if any(path.is_symlink() for path in files):
        raise ValueError("Frozen bundle must not contain symbolic links")
    regular = [path for path in files if path.is_file()]
    return {"package_bytes": sum(path.stat().st_size for path in regular), "package_file_count": len(regular)}


def _stop_build(process: subprocess.Popen) -> bool:
    # taskkill /T stops PyInstaller's analysis/build children as well as its root.
    taskkill = Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"
    try:
        completed = subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                                   stdin=subprocess.DEVNULL, capture_output=True, timeout=10, check=False)
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def build(source: Path, output: Path, evidence_path: Path) -> int:
    source, output, evidence_path = source.resolve(), output.resolve(), evidence_path.resolve()
    started = time.perf_counter()
    evidence: dict = {"status": "failed", "source_commit": COMMIT,
                      "source_directory": str(source), "package_directory": str(output / "dist" / PACKAGE_NAME),
                      "verified_before_build": False, "build_timeout_seconds": BUILD_TIMEOUT_SECONDS,
                      "not_verified": ["KUMA integration", "distribution rights", "clean machine installation"]}
    created_output = False
    try:
        if sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true":
            raise ValueError("Frozen build is allowed only in the approved Windows CI experiment")
        if not disjoint(source, output) or not disjoint(source, evidence_path) or not disjoint(output, evidence_path):
            raise ValueError("Source, package output and evidence paths must be separate")
        if output.exists():
            raise ValueError("Choose a fresh packaging output directory")
        version = importlib.metadata.version("pyinstaller")
        if version != PYINSTALLER_VERSION:
            raise ValueError(f"Expected PyInstaller {PYINSTALLER_VERSION}")
        # This happens before any PyInstaller analysis imports upstream Python.
        evidence["weights_sha256"] = verify_upstream(source)
        evidence["source_python_sha256"] = source_hashes(source)
        evidence["own_harness_sha256"] = own_hashes()
        evidence["verified_before_build"] = True
        evidence["pyinstaller"] = version
        evidence["status"] = "verified"
        write_evidence(evidence_path, evidence)
        output.mkdir(parents=True, exist_ok=False)
        created_output = True
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "MPLBACKEND": "Agg",
                       "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                       "CUDA_VISIBLE_DEVICES": ""}
        # Logs are temporary and bounded in the evidence, never artifact payloads.
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(build_command(source, output), cwd=output, env=environment,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, shell=False)
            try:
                code = process.wait(timeout=BUILD_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                dead = _stop_build(process)
                evidence["build_tree_termination_verified"] = dead
                evidence["status"] = "timed_out" if dead else "failed"
                raise TimeoutError("Frozen build exceeded 600 seconds; " +
                                   ("process tree terminated" if dead else "tree termination not verified"))
            if code:
                log.seek(max(0, log.tell() - 12000))
                evidence["build_log_tail"] = log.read(12000).decode("utf-8", errors="replace")
                raise RuntimeError(f"PyInstaller exited with code {code}")
        # Confirm no source/weight mutation happened during package analysis.
        if verify_upstream(source) != evidence["weights_sha256"]:
            raise ValueError("Upstream changed during the build")
        package = output / "dist" / PACKAGE_NAME
        executable = package / f"{PACKAGE_NAME}.exe"
        if not executable.is_file():
            raise ValueError("Frozen entry executable was not produced")
        evidence.update(package_inventory(package))
        evidence["entry_executable"] = str(executable)
        evidence["status"] = "built"
        return 0
    except Exception as exc:
        evidence["error"] = f"{type(exc).__name__}: {exc}"[:12000]
        if evidence["status"] != "timed_out":
            evidence["status"] = "failed"
        if created_output:
            try:
                shutil.rmtree(output)
                evidence["failed_output_removed"] = True
            except OSError as cleanup_error:
                evidence["failed_output_removed"] = False
                evidence["cleanup_error"] = str(cleanup_error)[:2000]
        return 2
    finally:
        evidence["elapsed_seconds"] = time.perf_counter() - started
        write_evidence(evidence_path, evidence)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args(argv)
    return build(args.source, args.output_directory, args.evidence)


if __name__ == "__main__":
    raise SystemExit(main())
