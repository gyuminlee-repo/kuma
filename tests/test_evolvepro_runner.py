"""Unit tests for kuma_core.kuro.evolvepro_runner.

Mocking-based; never invokes real conda or EVOLVEpro.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from kuma_core.kuro import evolvepro_runner


def _eq(actual: object, expected: object) -> None:
    if actual != expected:
        raise AssertionError(f"{actual!r} != {expected!r}")  # noqa: S101


def _is(actual: object, expected: object) -> None:
    if actual is not expected:
        raise AssertionError(f"{actual!r} is not {expected!r}")  # noqa: S101


def _truthy(actual: object) -> None:
    if not actual:
        raise AssertionError(f"expected truthy, got {actual!r}")  # noqa: S101


def _contains(haystack: object, needle: object) -> None:
    if needle not in haystack:  # type: ignore[operator]
        raise AssertionError(f"{needle!r} not in {haystack!r}")  # noqa: S101


def test_detect_env_not_found_without_conda(monkeypatch):
    """When conda executable cannot be located, env_found is False."""
    monkeypatch.setattr(evolvepro_runner, "_find_conda_exe", lambda: None)
    status = evolvepro_runner.detect_env()
    _is(status.env_found, False)
    _is(status.env_path, None)
    _is(status.conda_exe, None)


def test_detect_env_found(monkeypatch, tmp_path):
    """When `conda env list` returns a matching row, env_path is extracted."""
    fake_conda = str(tmp_path / "conda")
    fake_env_path = str(tmp_path / "envs" / "evolvepro")
    base_path = str(tmp_path / "base_env")

    monkeypatch.setattr(evolvepro_runner, "_find_conda_exe", lambda: fake_conda)

    list_result = MagicMock()
    list_result.stdout = (
        "# conda environments:\n"
        "#\n"
        f"base                     {base_path}\n"
        f"evolvepro                {fake_env_path}\n"
    )
    list_result.returncode = 0

    version_result = MagicMock()
    version_result.stdout = "0.1.0\n"
    version_result.returncode = 0

    def fake_run(cmd, **kwargs):
        if cmd[:3] == [fake_conda, "env", "list"]:
            return list_result
        return version_result

    monkeypatch.setattr(evolvepro_runner.subprocess, "run", fake_run)

    status = evolvepro_runner.detect_env()
    _is(status.env_found, True)
    _eq(status.env_path, fake_env_path)
    _eq(status.evolvepro_version, "0.1.0")
    _eq(status.conda_exe, fake_conda)


def test_run_spawn_signature(monkeypatch, tmp_path):
    """run() spawns conda subprocess with expected argv structure."""
    fake_conda = str(tmp_path / "conda")
    monkeypatch.setattr(evolvepro_runner, "_find_conda_exe", lambda: fake_conda)

    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    fake_proc.pid = 4242

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return fake_proc

    monkeypatch.setattr(evolvepro_runner.subprocess, "Popen", fake_popen)

    input_csv = str(tmp_path / "input.csv")
    out_dir = str(tmp_path / "out")

    handle = evolvepro_runner.run(
        input_csv=input_csv,
        wt_sequence="MKT",
        n_rounds=2,
        output_dir=out_dir,
        top_n=5,
    )

    _is(handle.process, fake_proc)
    cmd = captured["cmd"]
    _eq(cmd[0], fake_conda)
    _eq(cmd[1:5], ["run", "-n", "evolvepro", "--no-capture-output"])
    _eq(cmd[5], "evolvepro")
    _contains(cmd, "--input")
    _contains(cmd, input_csv)
    _contains(cmd, "--wt-sequence")
    _contains(cmd, "MKT")
    _contains(cmd, "--rounds")
    _contains(cmd, "2")
    _contains(cmd, "--output-dir")
    _contains(cmd, out_dir)
    _contains(cmd, "--top-n")
    _contains(cmd, "5")


def test_cancel_kills_running_process(monkeypatch):
    """cancel() sends termination signal when process still running."""
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None
    fake_proc.pid = 9999

    handle = evolvepro_runner.RunHandle(
        run_id="abc", process=fake_proc, start_time=0.0
    )

    monkeypatch.setattr(evolvepro_runner.sys, "platform", "linux")
    killed = {"n": 0}

    def fake_killpg(pgid, sig):
        killed["n"] += 1

    monkeypatch.setattr(evolvepro_runner.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(evolvepro_runner.os, "killpg", fake_killpg)

    _is(evolvepro_runner.cancel(handle), True)
    _is(handle.cancelled, True)
    _eq(killed["n"], 1)


def test_cancel_already_exited_returns_false():
    fake_proc = MagicMock()
    fake_proc.poll.return_value = 0
    handle = evolvepro_runner.RunHandle(
        run_id="abc", process=fake_proc, start_time=0.0
    )
    _is(evolvepro_runner.cancel(handle), False)


def test_run_ids_are_unique(monkeypatch, tmp_path):
    """Two consecutive run() calls produce distinct run_ids."""
    fake_conda = str(tmp_path / "conda")
    monkeypatch.setattr(evolvepro_runner, "_find_conda_exe", lambda: fake_conda)

    def fake_popen(cmd, **kwargs):
        m = MagicMock()
        m.poll.return_value = None
        return m

    monkeypatch.setattr(evolvepro_runner.subprocess, "Popen", fake_popen)

    h1 = evolvepro_runner.run(
        input_csv=str(tmp_path / "a.csv"),
        wt_sequence="M",
        n_rounds=1,
        output_dir=str(tmp_path / "o1"),
        top_n=1,
    )
    h2 = evolvepro_runner.run(
        input_csv=str(tmp_path / "b.csv"),
        wt_sequence="M",
        n_rounds=1,
        output_dir=str(tmp_path / "o2"),
        top_n=1,
    )
    if h1.run_id == h2.run_id:
        raise AssertionError("run_ids should differ")  # noqa: S101
    _truthy(len(h1.run_id) > 0)


def test_classify_error_buckets():
    """Internal _classify_error maps stderr fragments to ErrorKind."""
    _eq(evolvepro_runner._classify_error("No space left on device", 1), "disk_full")
    _eq(evolvepro_runner._classify_error("Permission denied", 1), "permission")
    _eq(evolvepro_runner._classify_error("Connection timeout", 1), "network")
    _eq(evolvepro_runner._classify_error("No module named evolvepro", 1), "env_not_found")
    _eq(evolvepro_runner._classify_error("traceback ...", 1), "runtime_error")
