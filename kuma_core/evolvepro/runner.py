"""EVOLVEpro GUI wrapper runner.

KUMA does not bundle or redistribute EVOLVEpro. Users install EVOLVEpro
in a conda environment themselves (accepting MIT TLO Internal Research
EULA directly). This module detects the user installation and shells out
to it via subprocess.
"""
from __future__ import annotations

import os
import re
import json
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable
from typing import Literal, Optional

from . import embedding_cache

ProgressStage = Literal["detect", "loading", "scoring", "selecting", "done", "error"]
ErrorKind = Literal[
    "env_not_found", "network", "disk_full", "permission", "runtime_error"
]
ProgressCallback = Callable[[str, ProgressStage, int, int, str], None]

CONDA_ENV_NAME_DEFAULT = "evolvepro"

_ESM2_MODEL_IDS = (
    "esm2_t6_8M_UR50D",
    "esm2_t12_35M_UR50D",
    "esm2_t30_150M_UR50D",
    "esm2_t33_650M_UR50D",
    "esm2_t36_3B_UR50D",
    "esm2_t48_15B_UR50D",
)

_REQUIRED_RUNTIME_MODULES = (
    "evolvepro",
    "esm",
    "Bio",
    "numpy",
    "pandas",
    "openpyxl",
    "sklearn",
    "sklearn_extra",
    "scipy",
    "xgboost",
    "matplotlib",
    "seaborn",
    "torch",
)

# stdout patterns (best-effort; CLI output unverified)
_RE_ROUND = re.compile(r"round\s+(\d+)\s*/\s*(\d+)", re.IGNORECASE)
_RE_LOADING = re.compile(r"loading\s+(?:model|esm)", re.IGNORECASE)
_RE_SCORING = re.compile(r"(?:scoring|computing|inference)", re.IGNORECASE)
_RE_SELECTING = re.compile(r"(?:selecting|sampling)\s+(?:top|variants?)", re.IGNORECASE)
_RE_DONE = re.compile(r"(?:complete|done|finished)", re.IGNORECASE)
_RE_THROUGHPUT = re.compile(r"throughput:\s*([\d.]+)\s*tok/s", re.IGNORECASE)
_RE_ETA = re.compile(r"eta:\s*([\d.]+)\s*s", re.IGNORECASE)


def _adapter_path() -> Path:
    return Path(__file__).resolve().with_name("adapter.py")


@dataclass
class EvolveProEnvStatus:
    env_found: bool
    env_path: Optional[str] = None
    evolvepro_version: Optional[str] = None
    weights_cached: bool = False
    weights_path: Optional[str] = None
    conda_exe: Optional[str] = None
    cached_models: dict[str, str] = field(default_factory=dict)


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
            home / "miniforge3" / "Scripts" / "conda.exe",
            home / "miniforge3" / "condabin" / "conda.bat",
            home / "miniconda3" / "Scripts" / "conda.exe",
            home / "miniconda3" / "condabin" / "conda.bat",
            home / "anaconda3" / "Scripts" / "conda.exe",
            home / "anaconda3" / "condabin" / "conda.bat",
            Path("C:/ProgramData/miniforge3/Scripts/conda.exe"),
            Path("C:/ProgramData/miniforge3/condabin/conda.bat"),
            Path("C:/ProgramData/miniconda3/Scripts/conda.exe"),
            Path("C:/ProgramData/miniconda3/condabin/conda.bat"),
            Path("C:/ProgramData/Anaconda3/Scripts/conda.exe"),
            Path("C:/ProgramData/Anaconda3/condabin/conda.bat"),
        ]
    else:
        candidates += [
            home / "miniforge3" / "bin" / "conda",
            home / "miniconda3" / "bin" / "conda",
            home / "anaconda3" / "bin" / "conda",
            Path("/opt/miniforge3/bin/conda"),
            Path("/opt/conda/bin/conda"),
        ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _conda_cmd(conda_exe: str, *args: str) -> list[str]:
    """Build a subprocess argv for conda, including Windows batch shims."""
    if sys.platform == "win32" and Path(conda_exe).suffix.lower() in {".bat", ".cmd"}:
        return ["cmd.exe", "/d", "/c", conda_exe, *args]
    return [conda_exe, *args]


def _find_env_path_from_conda_list(stdout: str, env_name: str) -> Optional[str]:
    """Extract an env path from `conda env list` JSON or text output."""
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        for raw_path in data.get("envs", []):
            path = Path(str(raw_path))
            if path.name == env_name:
                return str(path)

    for line in stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if "*" in parts:
            parts.remove("*")
        if parts and parts[0] == env_name and len(parts) >= 2:
            return parts[-1]
    return None


def _runtime_probe_script() -> str:
    imports = ", ".join(_REQUIRED_RUNTIME_MODULES)
    return (
        "import sys\n"
        f"import {imports}\n"
        "print(f'__prefix__={sys.prefix}')\n"
        "print(getattr(evolvepro, '__version__', 'unknown'))\n"
    )


def _python_c(script: str) -> str:
    """Wrap multi-line Python for `python -c` without literal newlines."""
    return f"exec({script!r})"


def _scan_cached_models() -> dict[str, str]:
    """Return {model_id: file_path} for each ESM2 weight file present on disk."""
    cache = Path(
        os.environ.get("TORCH_HOME", str(Path.home() / ".cache" / "torch"))
    ) / "hub" / "checkpoints"
    result: dict[str, str] = {}
    for model_id in _ESM2_MODEL_IDS:
        pt = cache / f"{model_id}.pt"
        if pt.exists():
            result[model_id] = str(pt)
    return result


def detect_env(env_name: str = CONDA_ENV_NAME_DEFAULT) -> EvolveProEnvStatus:
    """Detect user's EVOLVEpro conda environment.

    Returns EvolveProEnvStatus. Never raises -- failures map to env_found=False.
    """
    conda = _find_conda_exe()
    if not conda:
        return EvolveProEnvStatus(env_found=False)
    env_path: Optional[str] = None
    try:
        result = subprocess.run(  # noqa: S603
            _conda_cmd(conda, "env", "list", "--json"),
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
        )
        env_path = _find_env_path_from_conda_list(result.stdout, env_name)
    except (subprocess.TimeoutExpired, OSError):
        env_path = None

    version: Optional[str] = None
    try:
        v_result = subprocess.run(  # noqa: S603
            _conda_cmd(
                conda,
                "run",
                "-n",
                env_name,
                "python",
                "-c",
                _python_c(_runtime_probe_script()),
            ),
            capture_output=True,
            text=True,
            timeout=15,
            shell=False,
        )
        if v_result.returncode == 0:
            lines = [line.strip() for line in v_result.stdout.splitlines() if line.strip()]
            for line in lines:
                if line.startswith("__prefix__="):
                    env_path = line.split("=", 1)[1] or env_path
            version_lines = [line for line in lines if not line.startswith("__prefix__=")]
            version = version_lines[-1] if version_lines else "unknown"
        else:
            return EvolveProEnvStatus(env_found=False, env_path=env_path, conda_exe=conda)
    except (subprocess.TimeoutExpired, OSError):
        return EvolveProEnvStatus(env_found=False, env_path=env_path, conda_exe=conda)
    cached_models = _scan_cached_models()
    preferred = cached_models.get("esm2_t33_650M_UR50D")
    first_path = preferred or (next(iter(cached_models.values()), None))
    return EvolveProEnvStatus(
        env_found=True,
        env_path=env_path,
        evolvepro_version=version,
        weights_cached=bool(cached_models),
        weights_path=first_path,
        conda_exe=conda,
        cached_models=cached_models,
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
    last_throughput: float | None = None
    last_eta: float | None = None
    progress_cb(
        handle.run_id,
        "loading",
        0,
        n_rounds_expected,
        "Starting EVOLVEpro subprocess (conda activate + Python startup, 30-90s)",
    )
    if proc.stdout is None:
        raise RuntimeError("subprocess stdout pipe is unexpectedly closed")
    for raw in proc.stdout:
        if handle.cancelled:
            break
        line = raw.rstrip()
        if not line:
            continue
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
        elif m := _RE_THROUGHPUT.search(line):
            last_throughput = float(m.group(1))
            parts = [f"{last_throughput:.1f} tok/s"]
            if last_eta is not None:
                parts.append(f"ETA {last_eta:.0f}s")
            progress_cb(
                handle.run_id,
                last_stage,
                current_round,
                n_rounds_expected,
                " | ".join(parts),
            )
        elif m := _RE_ETA.search(line):
            last_eta = float(m.group(1))
            parts = []
            if last_throughput is not None:
                parts.append(f"{last_throughput:.1f} tok/s")
            parts.append(f"ETA {last_eta:.0f}s")
            progress_cb(
                handle.run_id,
                last_stage,
                current_round,
                n_rounds_expected,
                " | ".join(parts),
            )
        else:
            progress_cb(
                handle.run_id,
                last_stage,
                current_round,
                n_rounds_expected,
                line[:240],
            )
    proc.wait()
    if proc.returncode == 0:
        progress_cb(handle.run_id, "done", n_rounds_expected, n_rounds_expected, "EVOLVEpro run finished")
    else:
        detail = next(
            (
                line
                for line in reversed(output_lines)
                if "EVOLVEpro and ESM-2 require a protein FASTA" in line
                or "ValueError:" in line
                or "RuntimeError:" in line
            ),
            "",
        )
        if detail.startswith("ValueError: "):
            detail = detail.removeprefix("ValueError: ")
        message = f"EVOLVEpro run failed with exit code {proc.returncode}"
        if detail:
            message = f"{message}: {detail}"
        progress_cb(
            handle.run_id,
            "error",
            current_round,
            n_rounds_expected,
            message,
        )
    return {"stdout_lines": output_lines, "returncode": proc.returncode}


def run(
    *,
    input_csv: str,
    round_files: Optional[list[str]] = None,
    wt_sequence: str,
    wt_fasta: Optional[str] = None,
    n_rounds: int,
    output_dir: str,
    top_n: int,
    env_name: str = CONDA_ENV_NAME_DEFAULT,
    esm2_model_id: str,
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
    cli = os.environ.get("EVOLVEPRO_CLI")
    if cli:
        cmd = _conda_cmd(
            conda, "run", "-n", env_name, "--no-capture-output", cli,
            "--input", input_csv,
            "--rounds", str(n_rounds),
            "--output-dir", output_dir,
            "--top-n", str(top_n),
        )
    else:
        files = round_files if round_files else [input_csv]
        cmd = _conda_cmd(
            conda, "run", "-n", env_name, "--no-capture-output",
            "python", str(_adapter_path()),
            "--rounds", str(n_rounds),
            "--output-dir", output_dir,
            "--top-n", str(top_n),
            "--model-id", esm2_model_id,
        )
        for file in files:
            cmd.extend(["--round-file", file])
        if wt_fasta:
            cmd.extend(["--wt-fasta", wt_fasta])
        else:
            cmd.extend(["--wt-sequence", wt_sequence])
        embeddings_csv = os.environ.get("EVOLVEPRO_EMBEDDINGS_CSV")
        if embeddings_csv:
            cmd.extend(["--embeddings-csv", embeddings_csv])
        # Resolve embedding cache directory: env var overrides default.
        _cache_dir_env = os.environ.get("EVOLVEPRO_EMBEDDINGS_CACHE_DIR")
        _cache_dir = _cache_dir_env if _cache_dir_env else str(embedding_cache.resolve_cache_dir())
        cmd.extend(["--embeddings-cache-dir", _cache_dir])
    if cli:
        if wt_fasta:
            cmd.extend(["--wt-fasta", wt_fasta])
        else:
            cmd.extend(["--wt-sequence", wt_sequence])
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
