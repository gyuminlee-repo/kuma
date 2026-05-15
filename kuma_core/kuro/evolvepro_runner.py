"""EVOLVEpro GUI wrapper runner.

KUMA does not bundle or redistribute EVOLVEpro. Users install EVOLVEpro
in a conda environment themselves (accepting MIT TLO Internal Research
EULA directly). This module detects the user installation and shells out
to it via subprocess.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Literal, Optional

ProgressStage = Literal["detect", "loading", "scoring", "selecting", "done"]
ErrorKind = Literal[
    "env_not_found", "network", "disk_full", "permission", "runtime_error"
]
ProgressCallback = Callable[[str, ProgressStage, int, int, str], None]

CONDA_ENV_NAME_DEFAULT = "evolvepro"

# stdout patterns (best-effort; CLI output unverified)
_RE_ROUND = re.compile(r"round\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_RE_LOADING = re.compile(r"loading\s+(?:model|esm)", re.IGNORECASE)
_RE_SCORING = re.compile(r"(?:scoring|computing|inference)", re.IGNORECASE)
_RE_SELECTING = re.compile(r"(?:selecting|sampling)\s+(?:top|variants?)", re.IGNORECASE)
_RE_DONE = re.compile(r"(?:complete|done|finished)", re.IGNORECASE)


@dataclass
class EvolveProEnvStatus:
    env_found: bool
    env_path: Optional[str] = None
    evolvepro_version: Optional[str] = None
    weights_cached: bool = False
    weights_path: Optional[str] = None
    conda_exe: Optional[str] = None


@dataclass
class RunHandle:
    run_id: str
    process: subprocess.Popen
    start_time: float
    cancelled: bool = False
    thread: Optional[threading.Thread] = None


def _find_conda_exe() -> Optional[str]:
    """Locate conda executable across OS. Returns None if not found."""
    env = os.environ.get("CONDA_EXE")
    if env and Path(env).exists():
        return env
    found = shutil.which("conda")
    if found:
        return found
    candidates: list[Path] = []
    home = Path.home()
    if sys.platform == "win32":
        candidates += [
            home / "miniconda3" / "Scripts" / "conda.exe",
            home / "anaconda3" / "Scripts" / "conda.exe",
            Path("C:/ProgramData/miniconda3/Scripts/conda.exe"),
        ]
    else:
        candidates += [
            home / "miniconda3" / "bin" / "conda",
            home / "anaconda3" / "bin" / "conda",
            Path("/opt/conda/bin/conda"),
        ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def detect_env(env_name: str = CONDA_ENV_NAME_DEFAULT) -> EvolveProEnvStatus:
    """Detect user's EVOLVEpro conda environment.

    Returns EvolveProEnvStatus. Never raises -- failures map to env_found=False.
    """
    conda = _find_conda_exe()
    if not conda:
        return EvolveProEnvStatus(env_found=False)
    try:
        result = subprocess.run(  # noqa: S603
            [conda, "env", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return EvolveProEnvStatus(env_found=False, conda_exe=conda)
    env_path: Optional[str] = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts and parts[0] == env_name and len(parts) >= 2:
            env_path = parts[-1]
            break
    if not env_path:
        return EvolveProEnvStatus(env_found=False, conda_exe=conda)
    version: Optional[str] = None
    try:
        v_result = subprocess.run(  # noqa: S603
            [
                conda, "run", "-n", env_name, "python", "-c",
                "import evolvepro; print(getattr(evolvepro, '__version__', 'unknown'))",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
        if v_result.returncode == 0:
            version = v_result.stdout.strip() or "unknown"
    except (subprocess.TimeoutExpired, OSError):
        pass
    cache = Path(
        os.environ.get("TORCH_HOME", str(Path.home() / ".cache" / "torch"))
    ) / "hub" / "checkpoints"
    weight_file = cache / "esm2_t33_650M_UR50D.pt"
    return EvolveProEnvStatus(
        env_found=True,
        env_path=env_path,
        evolvepro_version=version,
        weights_cached=weight_file.exists(),
        weights_path=str(weight_file) if weight_file.exists() else None,
        conda_exe=conda,
    )


def _classify_error(stderr: str, returncode: int) -> ErrorKind:
    s = stderr.lower()
    if "no space left" in s or "disk full" in s:
        return "disk_full"
    if "permission denied" in s or "access denied" in s:
        return "permission"
    if "connection" in s or "network" in s or "timeout" in s or "resolve" in s:
        return "network"
    if "no module named" in s or "command not found" in s:
        return "env_not_found"
    return "runtime_error"


def _stream_stdout(
    handle: RunHandle,
    progress_cb: ProgressCallback,
    n_rounds_expected: int,
) -> dict:
    """Background thread: parse subprocess stdout, emit progress, collect result."""
    proc = handle.process
    output_lines: list[str] = []
    current_round = 0
    last_stage: ProgressStage = "loading"
    progress_cb(handle.run_id, "loading", 0, n_rounds_expected, "Loading ESM-2 model")
    if proc.stdout is None:
        raise RuntimeError("subprocess stdout pipe is unexpectedly closed")
    for raw in proc.stdout:
        if handle.cancelled:
            break
        line = raw.rstrip()
        output_lines.append(line)
        if m := _RE_ROUND.search(line):
            current_round = int(m.group(1))
            total = int(m.group(2))
            last_stage = "scoring"
            progress_cb(handle.run_id, "scoring", current_round, total, line[:120])
        elif _RE_LOADING.search(line) and last_stage == "loading":
            progress_cb(
                handle.run_id, "loading", 0, n_rounds_expected, line[:120]
            )
        elif _RE_SELECTING.search(line):
            last_stage = "selecting"
            progress_cb(
                handle.run_id,
                "selecting",
                current_round,
                n_rounds_expected,
                line[:120],
            )
        elif _RE_DONE.search(line):
            last_stage = "done"
    proc.wait()
    return {"stdout_lines": output_lines, "returncode": proc.returncode}


def run(
    *,
    input_csv: str,
    wt_sequence: str,
    n_rounds: int,
    output_dir: str,
    top_n: int,
    env_name: str = CONDA_ENV_NAME_DEFAULT,
    progress_callback: Optional[ProgressCallback] = None,
) -> RunHandle:
    """Spawn EVOLVEpro CLI as subprocess. Returns RunHandle immediately.

    The caller is responsible for waiting on the background thread (handle.thread).
    """
    conda = _find_conda_exe()
    if not conda:
        raise RuntimeError("env_not_found: conda executable not located")
    run_id = uuid.uuid4().hex
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    cli = os.environ.get("EVOLVEPRO_CLI", "evolvepro")
    cmd = [
        conda, "run", "-n", env_name, "--no-capture-output",
        cli,
        "--input", input_csv,
        "--wt-sequence", wt_sequence,
        "--rounds", str(n_rounds),
        "--output-dir", output_dir,
        "--top-n", str(top_n),
    ]
    popen_kwargs: dict = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        shell=False,
    )
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(cmd, **popen_kwargs)  # noqa: S603
    handle = RunHandle(run_id=run_id, process=process, start_time=time.time())
    if progress_callback:
        thread = threading.Thread(
            target=_stream_stdout,
            args=(handle, progress_callback, n_rounds),
            daemon=True,
        )
        handle.thread = thread
        thread.start()
    return handle


def cancel(handle: RunHandle) -> bool:
    """Terminate the running subprocess group. Returns True if signal sent."""
    if handle.process.poll() is not None:
        return False
    handle.cancelled = True
    try:
        if sys.platform == "win32":
            handle.process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(os.getpgid(handle.process.pid), signal.SIGTERM)
        return True
    except (OSError, ProcessLookupError):
        return False


__all__ = [
    "ProgressStage",
    "ErrorKind",
    "ProgressCallback",
    "EvolveProEnvStatus",
    "RunHandle",
    "detect_env",
    "run",
    "cancel",
    "CONDA_ENV_NAME_DEFAULT",
]
