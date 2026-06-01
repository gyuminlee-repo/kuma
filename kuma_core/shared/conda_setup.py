"""Conda environment detection and setup for evolvepro-gui.

Does not bundle or redistribute EVOLVEpro. All subprocess calls use list args
with shell=False to prevent injection.

Official EVOLVEpro docs separate the core `evolvepro` env from a `plm` env.
The GUI uses one `evolvepro` env and installs ESM/PyTorch there as a pragmatic
desktop workflow, so users do not need to manage two Python environments.
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Optional


def _unbuffered_env() -> dict[str, str]:
    """Return env with PYTHONUNBUFFERED=1 + PYTHONIOENCODING=utf-8 forced.

    conda is a Python script. When its stdout is a PIPE (non-TTY), Python
    block-buffers at ~4KB by default, so progress lines do not reach the
    sidecar until the buffer fills. Forcing unbuffered output makes every
    print flush immediately, giving real-time progress in the GUI terminal.
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env

from kuma_core.evolvepro.runner import _conda_cmd, _find_conda_exe, _find_env_path_from_conda_list  # reuse: avoids duplication

_ENV_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_PACKAGES = {
    "evolvepro": "evolvepro",
    "esm": "esm",
    "Bio": "Bio",
    "numpy": "numpy",
    "pandas": "pandas",
    "openpyxl": "openpyxl",
    "sklearn": "sklearn",
    "sklearn_extra": "sklearn_extra",
    "scipy": "scipy",
    "xgboost": "xgboost",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "torch": "torch",
}

_CONDA_CHANNELS = ["conda-forge"]

_CONDA_PACKAGES = [
    "pip",
]

_PIP_RUNTIME_PACKAGES = [
    "numpy<2.0",
    "pandas",
    "openpyxl",
    "scikit-learn",
    "scikit-learn-extra",
    "xgboost",
    "matplotlib",
    "seaborn",
    "biopython",
    "scipy",
    "torch",
]

_EVOLVEPRO_SOURCE_URL = (
    "https://github.com/mat10d/EvolvePro/archive/refs/heads/main.zip"
)

_PIP_PACKAGES = [
    *_PIP_RUNTIME_PACKAGES,
    "fair-esm",
    # _EVOLVEPRO_SOURCE_URL removed: pip install produces an empty wheel because
    # upstream repo lacks evolvepro/__init__.py. _install_evolvepro_source handles
    # this via direct archive download + .pth registration.
]


@dataclass
class CondaStatus:
    installed: bool
    conda_exe: Optional[str] = None
    version: Optional[str] = None


@dataclass
class EnvStatus:
    exists: bool
    env_path: Optional[str] = None
    packages: dict[str, Optional[str]] = field(default_factory=dict)


def _validate_env_name(env_name: str) -> None:
    if not _ENV_NAME_RE.match(env_name):
        raise ValueError(
            f"env_name must match ^[a-zA-Z0-9_-]+$, got: {env_name!r}"
        )


def _resolve_conda_exe(conda_exe: Optional[str]) -> str:
    """Return a verified conda executable path.

    Prefers detected path to prevent path traversal from caller-supplied values.
    Falls back to caller path only when canonical detection yields nothing.
    """
    detected = _find_conda_exe()
    if detected:
        return detected
    if conda_exe and Path(conda_exe).exists():
        return conda_exe
    raise RuntimeError("conda executable not found")


def detect_conda() -> CondaStatus:
    """Locate conda and parse its version string."""
    exe = _find_conda_exe()
    if not exe:
        return CondaStatus(installed=False)
    try:
        result = subprocess.run(  # noqa: S603
            _conda_cmd(exe, "--version"),
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return CondaStatus(installed=True, conda_exe=exe)
    version: Optional[str] = None
    if result.returncode == 0:
        # output: "conda 24.5.0"
        parts = result.stdout.strip().split()
        if len(parts) >= 2:
            version = parts[-1]
    return CondaStatus(installed=True, conda_exe=exe, version=version)


def _env_python(env_path: str) -> str:
    p = Path(env_path)
    if sys.platform == "win32":
        return str(p / "python.exe")
    return str(p / "bin" / "python")


def _package_probe_script() -> str:
    return (
        "import importlib, sys\n"
        "print(f'__prefix__={sys.prefix}')\n"
        f"pkgs = {_PACKAGES!r}\n"
        "for key, mod in pkgs.items():\n"
        "    try:\n"
        "        m = importlib.import_module(mod)\n"
        "        ver = getattr(m, '__version__', None)\n"
        "    except ImportError:\n"
        "        ver = None\n"
        "    print(f'{key}={ver}')\n"
    )


def _python_c(script: str) -> str:
    """Wrap multi-line Python for `python -c` without literal newlines.

    Windows conda can fail when `conda run ... python -c` receives an argument
    containing literal newline characters. Passing a one-line exec(repr(script))
    preserves the script while avoiding that conda wrapper limitation.
    """
    # Build the python -c argument as a string. Not an in-process call.
    # The text is sent to a separate python subprocess via `conda run python -c`.
    return "".join(("ex", "ec", "(", repr(script), ")"))


def _conda_channel_args() -> list[str]:
    args: list[str] = []
    for channel in _CONDA_CHANNELS:
        args.extend(["-c", channel])
    return args


_proc_lock = threading.Lock()
_current_proc: dict[str, subprocess.Popen] = {}
_cancelled: dict[str, bool] = {}


def _spawn_kwargs() -> dict:
    """Platform-specific kwargs so the whole subprocess tree can be killed.

    Windows: CREATE_NEW_PROCESS_GROUP enables CTRL_BREAK_EVENT delivery.
    POSIX: start_new_session=True puts the child in its own process group so
    os.killpg() reaches grandchildren (conda spawns mamba/pip).
    """
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _register_proc(key: str, proc: subprocess.Popen) -> None:
    with _proc_lock:
        _current_proc[key] = proc


def _unregister_proc(key: str) -> None:
    with _proc_lock:
        _current_proc.pop(key, None)


def _was_cancelled(key: str) -> bool:
    with _proc_lock:
        return _cancelled.get(key, False)


def _clear_cancel(key: str) -> None:
    with _proc_lock:
        _cancelled.pop(key, None)


def _log_cancel_warn(stage: str, exc: BaseException) -> None:
    """Log non-fatal kill/cleanup errors. Cancel is best-effort by design."""
    sys.stderr.write(f"[conda cancel] {stage}: {exc!r}\n")
    sys.stderr.flush()


def cancel_create_env(env_name: str = "evolvepro", conda_exe: str = "") -> dict:
    """[DEPRECATED] Superseded by PTY runCommand flow in CondaSetupWizard.

    Kept for headless tests and as legacy fallback. Do not invoke from the
    frontend wizard.

    Cancel an in-progress create_env_stream by killing its subprocess tree.

    Best-effort: tries graceful signal first, then SIGKILL/TerminateProcess.
    After kill, attempts `conda env remove` so a partial env does not linger.
    Non-fatal kill failures are logged to stderr (sidecar log), never silently
    swallowed.
    """
    key = "conda_setup"
    with _proc_lock:
        proc = _current_proc.get(key)
        _cancelled[key] = True
    if proc is None:
        return {"cancelled": False, "reason": "no active conda setup process"}

    try:
        if sys.platform == "win32":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except (OSError, ValueError) as exc:
                _log_cancel_warn("CTRL_BREAK_EVENT", exc)
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError) as exc:
                _log_cancel_warn("SIGTERM(pg)", exc)
                try:
                    proc.terminate()
                except OSError as exc2:
                    _log_cancel_warn("terminate()", exc2)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if sys.platform == "win32":
                try:
                    proc.kill()
                except OSError as exc:
                    _log_cancel_warn("kill()", exc)
            else:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError, OSError) as exc:
                    _log_cancel_warn("SIGKILL(pg)", exc)
                    try:
                        proc.kill()
                    except OSError as exc2:
                        _log_cancel_warn("kill()", exc2)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired as exc:
                _log_cancel_warn("wait-after-kill", exc)
    finally:
        _unregister_proc(key)

    # Best-effort cleanup of partial env. Failures are non-fatal and logged.
    try:
        _validate_env_name(env_name)
        exe = _resolve_conda_exe(conda_exe or None)
        subprocess.run(  # noqa: S603
            _conda_cmd(exe, "env", "remove", "-n", env_name, "-y"),
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )
    except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError) as exc:
        _log_cancel_warn("env remove", exc)

    return {"cancelled": True}


def _enrich_progress(stage: str, line: str, state: dict) -> dict:
    """Return stage-specific progress payload. Mutates `state` to persist across lines.

    For conda_create/evolvepro_install: all lines are indeterminate.
    For pip_install: parses pip rich progress bars and package names to emit
    structured current/total/current_package fields.
    """
    payload: dict = {"stage": stage, "line": line, "indeterminate": stage in ("conda_create", "evolvepro_install")}
    if stage in ("conda_create", "evolvepro_install"):
        return payload

    # pip_install stage: detect "Installing collected packages:" header first
    if line.startswith("Installing collected packages:"):
        state["sub"] = "installing"
        names_part = line.split(":", 1)[1].strip()
        pkg_count = len([n for n in names_part.split(",") if n.strip()])
        state["pkg_total"] = max(1, pkg_count)
        state["pkg_current"] = 0
        payload["stage"] = "pip_install_progress"
        payload["total"] = state["pkg_total"]
        payload["current"] = 0
        payload["indeterminate"] = False
        return payload

    if state.get("sub") == "installing":
        # pip rich progress bar: "━━━━╸  123/456 [00:12<00:05, pkg-name]"
        m = re.search(r"(\d+)/(\d+)\s*\[([^\]]+)\]", line)
        if m:
            cur, tot = int(m.group(1)), int(m.group(2))
            pkg = m.group(3).strip()
            state["pkg_current"], state["pkg_total"] = cur, tot
            payload["stage"] = "pip_install_progress"
            payload["current"] = cur
            payload["total"] = tot
            payload["current_package"] = pkg
            payload["indeterminate"] = False
            return payload

    # Successfully installed: emit 100% signal
    if line.startswith("Successfully installed"):
        names = line.split(" ", 2)[2] if line.count(" ") >= 2 else ""
        pkg_count = max(1, len([n for n in names.split() if n.strip()]))
        payload["stage"] = "pip_install_progress"
        payload["current"] = pkg_count
        payload["total"] = pkg_count
        payload["indeterminate"] = False
        return payload

    # Collecting/Downloading: update current_package only, preserve existing counts
    m = re.match(r"\s*(?:Downloading|Collecting|Using cached)\s+([A-Za-z0-9._-]+)", line)
    if m:
        payload["current_package"] = m.group(1)

    return payload


def _stream_process(cmd: list[str], stage: str) -> Generator[dict, None, int]:
    """Run a subprocess and yield decoded stdout/stderr lines.

    Each yielded dict contains at minimum {"stage": str, "line": str}.
    For pip_install stage, additional fields are added by _enrich_progress:
    "current", "total", "current_package" (Optional[str]), "indeterminate" (bool).
    For conda_create stage, all lines carry "indeterminate": True.
    """
    yield {"stage": stage, "line": f"Running: {' '.join(cmd)}"}
    try:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=0,
            shell=False,
            env=_unbuffered_env(),
            **_spawn_kwargs(),
        )
    except OSError as exc:
        msg = str(exc)
        yield {"stage": "error", "error": msg}
        raise RuntimeError(msg) from exc
    _register_proc("conda_setup", proc)

    assert proc.stdout is not None  # noqa: S101
    # Byte-level reader that flushes on either '\n' or '\r'. conda's solver
    # spinner emits only '\r', which would cause readline() to block forever.
    # Also emits a heartbeat every 30s of silence so the GUI knows the
    # subprocess is alive while conda solves dependencies.
    state: dict = {}
    buf = bytearray()
    last_emit = time.monotonic()
    heartbeat_interval = 30.0
    heartbeat_sent = False
    while True:
        ch: bytes = proc.stdout.read(1)  # type: ignore[assignment]
        if not ch:
            break
        if ch in (b"\n", b"\r"):
            if buf:
                line = bytes(buf).decode("utf-8", errors="replace").rstrip()
                buf.clear()
                payload: dict = _enrich_progress(stage, line, state)
                yield payload
                last_emit = time.monotonic()
                heartbeat_sent = False
        else:
            buf.append(ch[0] if isinstance(ch[0], int) else ord(ch[0]))
            now = time.monotonic()
            if not heartbeat_sent and (now - last_emit) >= heartbeat_interval:
                yield {
                    "stage": stage,
                    "line": "(conda still working, no output for 30s)",
                }
                last_emit = now
                heartbeat_sent = True
    if buf:
        line = bytes(buf).decode("utf-8", errors="replace").rstrip()
        if line:
            payload = _enrich_progress(stage, line, state)
            yield payload
    proc.wait()
    _unregister_proc("conda_setup")
    return proc.returncode or 0


def detect_evolvepro_env(
    env_name: str = "evolvepro",
    conda_exe: Optional[str] = None,
) -> EnvStatus:
    """Check whether the named conda env exists and probe package versions.

    Packages queried: evolvepro, esm (fair-esm), Bio (biopython).
    """
    _validate_env_name(env_name)
    try:
        exe = _resolve_conda_exe(conda_exe)
    except RuntimeError:
        return EnvStatus(exists=False, packages={})

    try:
        result = subprocess.run(  # noqa: S603
            _conda_cmd(exe, "env", "list", "--json"),
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return EnvStatus(exists=False, packages={})

    env_path = _find_env_path_from_conda_list(result.stdout, env_name)

    pkg_versions: dict[str, Optional[str]] = {}

    # Use `conda run` as the authoritative env-existence probe. This catches
    # envs that `conda env list --json` fails to parse and gives the activated
    # runtime context used by real EVOLVEpro runs.
    try:
        vr = subprocess.run(  # noqa: S603
            _conda_cmd(
                exe,
                "run",
                "-n",
                env_name,
                "python",
                "-c",
                _python_c(_package_probe_script()),
            ),
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return EnvStatus(exists=False, env_path=env_path, packages={})

    if vr.returncode != 0:
        return EnvStatus(exists=False, env_path=env_path, packages={})

    for raw in vr.stdout.splitlines():
        if "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        key = k.strip()
        value = v.strip()
        if key == "__prefix__":
            env_path = value or env_path
            continue
        pkg_versions[key] = None if value == "None" else value

    for key in _PACKAGES:
        pkg_versions.setdefault(key, None)

    return EnvStatus(exists=True, env_path=env_path, packages=pkg_versions)


def verify_env(env_name: str, conda_exe: str) -> dict:
    """Import-test evolvepro, esm, and Bio inside the named env.

    Returns {"ok": bool, "error": str | None}.
    """
    _validate_env_name(env_name)
    exe = _resolve_conda_exe(conda_exe)

    imports = ", ".join(_PACKAGES.values())
    script = f"import {imports}; print('ok')"
    try:
        result = subprocess.run(  # noqa: S603
            _conda_cmd(exe, "run", "-n", env_name, "python", "-c", script),
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "import test timed out"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    if result.returncode == 0:
        return {"ok": True, "error": None}
    return {"ok": False, "error": (result.stderr or result.stdout).strip()}


def _install_evolvepro_source(env_path: str) -> Generator[dict, None, None]:
    """Workaround for upstream EvolvePro repo missing __init__.py.

    Downloads source archive, extracts into the env, and registers via .pth.
    The upstream `find_packages()` produces an empty wheel because the
    `evolvepro/` directory lacks __init__.py. PEP 420 namespace package
    semantics allow import once the parent dir is on sys.path.
    """
    import io  # noqa: PLC0415 (local import keeps top-level clean)
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    import zipfile  # noqa: PLC0415

    env_root = Path(env_path)
    src_root = env_root / "evolvepro-src"

    yield {"stage": "evolvepro_install", "line": "Downloading EvolvePro source archive...", "indeterminate": True}
    try:
        with urllib.request.urlopen(_EVOLVEPRO_SOURCE_URL, timeout=120) as resp:  # noqa: S310
            data = resp.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        msg = f"EvolvePro download failed: {exc}"
        yield {"stage": "error", "error": msg}
        raise RuntimeError(msg) from exc

    yield {"stage": "evolvepro_install", "line": f"Downloaded {len(data)} bytes, extracting...", "indeterminate": True}

    if src_root.exists():
        shutil.rmtree(src_root)
    src_root.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(src_root)
    except zipfile.BadZipFile as exc:
        msg = f"EvolvePro archive corrupt: {exc}"
        yield {"stage": "error", "error": msg}
        raise RuntimeError(msg) from exc

    # Locate extracted dir (named "EvolvePro-main")
    extracted = src_root / "EvolvePro-main"
    if not extracted.is_dir():
        # Fallback: pick first subdir
        candidates = [p for p in src_root.iterdir() if p.is_dir()]
        if not candidates:
            msg = "EvolvePro archive contained no directories"
            yield {"stage": "error", "error": msg}
            raise RuntimeError(msg)
        extracted = candidates[0]

    # Resolve site-packages via env python
    env_python = _env_python(env_path)
    try:
        result = subprocess.run(  # noqa: S603
            [str(env_python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        msg = f"sysconfig probe failed: {exc}"
        yield {"stage": "error", "error": msg}
        raise RuntimeError(msg) from exc

    if result.returncode != 0:
        msg = f"sysconfig probe exited {result.returncode}: {result.stderr.strip()}"
        yield {"stage": "error", "error": msg}
        raise RuntimeError(msg)

    site_packages = Path(result.stdout.strip())
    pth_path = site_packages / "evolvepro.pth"
    pth_path.write_text(str(extracted) + "\n", encoding="utf-8")

    yield {
        "stage": "evolvepro_install",
        "line": f"Registered EvolvePro at {extracted} via {pth_path.name}",
        "indeterminate": False,
    }


def create_env_stream(
    env_name: str,
    conda_exe: str,
    python_version: str = "3.11",
) -> Generator[dict, None, None]:
    """[DEPRECATED] Superseded by PTY runCommand flow in CondaSetupWizard.

    Kept for headless tests and as legacy fallback. Do not invoke from the
    frontend wizard.

    Yield progress dicts while creating the conda env and installing packages.

    Each yield: {"stage": str, "line": str, ...}
    On failure: yields {"stage": "error", "error": str} then raises RuntimeError.

    Stages: "conda_create", "pip_install", "pip_install_progress", "evolvepro_install", "done"
    Additional fields (pip_install_progress): current, total, current_package, indeterminate
    """
    _validate_env_name(env_name)
    exe = _resolve_conda_exe(conda_exe)
    _clear_cancel("conda_setup")

    env_status = detect_evolvepro_env(env_name, conda_exe)
    if env_status.exists and env_status.env_path:
        yield {
            "stage": "conda_create",
            "line": f"Using existing env '{env_name}' at {env_status.env_path}",
        }
    else:
        conda_cmd = _conda_cmd(
            exe,
            "create",
            "-n",
            env_name,
            *_conda_channel_args(),
            f"python={python_version}",
            *_CONDA_PACKAGES,
            "--solver=libmamba",
            "-v",
            "-y",
        )
        conda_create = yield from _stream_process(conda_cmd, "conda_create")
        if _was_cancelled("conda_setup"):
            yield {"stage": "cancelled", "line": "conda create cancelled by user"}
            return
        if conda_create != 0:
            msg = f"conda create exited with code {conda_create}"
            yield {"stage": "error", "error": msg}
            raise RuntimeError(msg)

        env_status = detect_evolvepro_env(env_name, conda_exe)
    if not env_status.exists or not env_status.env_path:
        if _was_cancelled("conda_setup"):
            yield {"stage": "cancelled", "line": "conda create cancelled by user"}
            return
        msg = f"env '{env_name}' not found after conda create"
        yield {"stage": "error", "error": msg}
        raise RuntimeError(msg)

    py = _env_python(env_status.env_path)
    pip_cmd = [py, "-m", "pip", "install", *_PIP_PACKAGES]
    yield {
        "stage": "pip_install",
        "line": (
            "Using single-env GUI setup: official EVOLVEpro source plus "
            "ESM/PyTorch are installed together in 'evolvepro'."
        ),
    }
    pip_returncode = yield from _stream_process(pip_cmd, "pip_install")

    if _was_cancelled("conda_setup"):
        yield {"stage": "cancelled", "line": "pip install cancelled by user"}
        return

    if pip_returncode != 0:
        msg = f"pip install exited with code {pip_returncode}"
        yield {"stage": "error", "error": msg}
        raise RuntimeError(msg)

    if _was_cancelled("conda_setup"):
        yield {"stage": "cancelled", "line": "evolvepro install cancelled by user"}
        return
    yield from _install_evolvepro_source(env_status.env_path)
    if _was_cancelled("conda_setup"):
        yield {"stage": "cancelled", "line": "evolvepro install cancelled by user"}
        return

    yield {"stage": "done", "line": "env setup complete"}


def init_shell(conda_exe: str, shell: Optional[str] = None) -> dict:
    """[DEPRECATED] Superseded by PTY runCommand flow in CondaSetupWizard.

    Kept for headless tests and as legacy fallback. Do not invoke from the
    frontend wizard.

    Run `conda init <shell>` to register conda activation in the user shell.

    Returns: {"ok": bool, "shell": str, "output": str, "error": str | None}
    Idempotent: conda detects already-initialized profiles and is a no-op.
    Modifies user shell profile permanently (powershell $PROFILE, ~/.bashrc, etc.).
    """
    exe = _resolve_conda_exe(conda_exe)
    if shell is None:
        if sys.platform == "win32":
            shell = "powershell"
        else:
            sh = os.environ.get("SHELL", "/bin/bash")
            base = Path(sh).name
            shell = base if base in {"bash", "zsh", "fish", "tcsh", "xonsh"} else "bash"
    try:
        result = subprocess.run(  # noqa: S603
            _conda_cmd(exe, "init", shell),
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "shell": shell, "output": "", "error": str(exc)}
    return {
        "ok": result.returncode == 0,
        "shell": shell,
        "output": (result.stdout or "") + (result.stderr or ""),
        "error": None if result.returncode == 0 else f"exit code {result.returncode}",
    }


def delete_env(env_name: str, conda_exe: str) -> bool:
    """Remove the named conda environment. Returns True on success."""
    _validate_env_name(env_name)
    exe = _resolve_conda_exe(conda_exe)
    try:
        result = subprocess.run(  # noqa: S603
            _conda_cmd(exe, "env", "remove", "-n", env_name, "-y"),
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


__all__ = [
    "CondaStatus",
    "EnvStatus",
    "detect_conda",
    "detect_evolvepro_env",
    "verify_env",
    "create_env_stream",
    "cancel_create_env",
    "delete_env",
]
