from __future__ import annotations

import subprocess
import builtins
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TypedDict, cast

from kuma_core.evolvepro.runner import RunHandle, _stream_stdout
from kuma_core.evolvepro import runner
from sidecar_evolvepro import dispatcher
from sidecar_evolvepro.handlers.evolvepro import handle_evolvepro_run_result


@dataclass
class _FakeProcess:
    stdout: Iterable[str]
    returncode: int = 0

    def wait(self) -> int:
        return self.returncode


@dataclass
class _FakeHandle:
    run_id: str
    process: _FakeProcess
    start_time: float = 0.0
    cancelled: bool = False


class _PopenCapture(TypedDict):
    cmd: list[str]
    kwargs: dict[str, object]


def test_stream_stdout_reports_loading_and_failure_without_result(tmp_path: Path):
    handle = _FakeHandle(
        run_id="run",
        process=_FakeProcess(stdout=["loading input\n"], returncode=1),
    )
    calls: list[tuple[object, ...]] = []

    def _capture_progress(
        run_id: str,
        stage: str,
        current: int,
        total: int,
        message: str,
        result: runner.RunResult | None = None,
    ) -> None:
        calls.append((run_id, stage, current, total, message, result))

    result = _stream_stdout(
        cast(RunHandle, handle), _capture_progress, 1, tmp_path
    )

    assert calls[0][:5] == (
        "run",
        "loading",
        0,
        1,
        "Starting EVOLVEpro subprocess (conda activate + Python startup, 30-90s)",
    )
    assert calls[1][:5] == ("run", "loading", 0, 1, "loading input")
    assert calls[-1][1] == "error"
    assert calls[-1][5] is None
    assert "result" not in result


def test_stream_stdout_reports_cancel_without_raw_exit_code(tmp_path: Path):
    handle = _FakeHandle(
        run_id="run",
        process=_FakeProcess(stdout=["loading embeddings\n"], returncode=3221225786),
        cancelled=True,
    )
    calls: list[tuple[object, ...]] = []

    def _capture_progress(
        run_id: str,
        stage: str,
        current: int,
        total: int,
        message: str,
        result: runner.RunResult | None = None,
    ) -> None:
        calls.append((run_id, stage, current, total, message, result))

    result = _stream_stdout(
        cast(RunHandle, handle), _capture_progress, 1, tmp_path
    )

    assert calls[-1][:5] == ("run", "error", 0, 1, "EVOLVEpro run cancelled")
    assert "3221225786" not in str(calls[-1][4])
    assert result["returncode"] == 3221225786
    assert "result" not in result


def test_stream_stdout_success_should_parse_result_files(tmp_path: Path):
    (tmp_path / "df_test.csv").write_text("rank,variant,y_predicted\n1,A1V,1.0\n")
    (tmp_path / "top_variants.csv").write_text("rank,variant,y_predicted\n1,A1V,1.0\n")
    handle = _FakeHandle(
        run_id="run",
        process=_FakeProcess(stdout=["done\n"], returncode=0),
    )
    calls: list[tuple[object, ...]] = []

    def _capture_progress(
        run_id: str,
        stage: str,
        current: int,
        total: int,
        message: str,
        result: runner.RunResult | None = None,
    ) -> None:
        calls.append((run_id, stage, current, total, message, result))

    result = _stream_stdout(
        cast(RunHandle, handle), _capture_progress, 1, tmp_path
    )

    assert calls[-1][:5] == ("run", "done", 1, 1, "EVOLVEpro run finished")
    assert isinstance(calls[-1][5], runner.RunResult)
    assert calls[-1][5].output_csv == tmp_path / "df_test.csv"
    assert calls[-1][5].top_variants == ["A1V"]
    assert calls[-1][5].elapsed_sec >= 0
    assert "result" in result
    assert result["result"].output_csv == tmp_path / "df_test.csv"
    assert result["result"].top_variants == ["A1V"]
    assert result["result"].elapsed_sec >= 0


def test_stream_stdout_embedding_progress_keeps_batch_counter(tmp_path: Path):
    handle = _FakeHandle(
        run_id="run",
        process=_FakeProcess(
            stdout=[
                "throughput: 2607.7 tok/s\n",
                "eta: 12 s\n",
                "  batch 14/152 done (39 seqs)\n",
            ],
            returncode=0,
        ),
    )
    calls: list[tuple[object, ...]] = []

    def _capture_progress(
        run_id: str,
        stage: str,
        current: int,
        total: int,
        message: str,
        result: runner.RunResult | None = None,
    ) -> None:
        calls.append((run_id, stage, current, total, message, result))

    _stream_stdout(cast(RunHandle, handle), _capture_progress, 1, tmp_path)

    embedding_calls = [call for call in calls if call[1] == "embedding"]
    assert embedding_calls
    assert embedding_calls[-1][:4] == ("run", "embedding", 14, 152)
    assert "batch 14/152" in str(embedding_calls[-1][4])
    assert "2607.7 tok/s" in str(embedding_calls[-1][4])
    assert "ETA 12s" in str(embedding_calls[-1][4])


def test_send_evolvepro_progress_serializes_result_only_on_done(monkeypatch):
    messages: list[dict] = []

    monkeypatch.setattr(dispatcher, "_send", lambda payload: messages.append(payload))

    dispatcher._send_evolvepro_progress("run", "loading", 1, 3, "working")

    result = runner.RunResult(
        run_id="run",
        output_csv=Path("/tmp/output.csv"),
        top_variants=["A1V", "B2C"],
        elapsed_sec=12.5,
    )

    dispatcher._send_evolvepro_progress(
        "run",
        "done",
        3,
        3,
        "finished",
        result,
    )

    assert messages[0] == {
        "jsonrpc": "2.0",
        "method": "progress",
        "params": {
            "type": "evolvepro_progress",
            "run_id": "run",
            "stage": "loading",
            "current": 1,
            "total": 3,
            "message": "working",
        },
    }
    assert messages[1] == {
        "jsonrpc": "2.0",
        "method": "progress",
        "params": {
            "type": "evolvepro_progress",
            "run_id": "run",
            "stage": "done",
            "current": 3,
            "total": 3,
            "message": "finished",
            "result": {
                "run_id": "run",
                "output_csv": "/tmp/output.csv",
                "top_variants": ["A1V", "B2C"],
                "elapsed_sec": 12.5,
            },
        },
    }


def test_run_starts_conda_subprocess_with_closed_stdin(monkeypatch, tmp_path: Path):
    captured: _PopenCapture = {"cmd": [], "kwargs": {}}

    def fake_popen(cmd: list[str], **kwargs: object) -> _FakeProcess:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProcess(stdout=[], returncode=0)

    monkeypatch.setattr(runner, "_find_conda_exe", lambda: "/opt/conda/bin/conda")
    monkeypatch.setattr(runner, "_adapter_path", lambda: tmp_path / "adapter.py")
    monkeypatch.setattr(runner.embedding_cache, "resolve_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(runner.subprocess, "Popen", fake_popen)

    handle = runner.run(
        input_csv=str(tmp_path / "round.csv"),
        round_files=[str(tmp_path / "round.csv")],
        wt_sequence="AC",
        wt_fasta=None,
        n_rounds=1,
        output_dir=str(tmp_path / "out"),
        top_n=3,
        esm2_model_id="esm2_t6_8M_UR50D",
    )

    assert handle.process.returncode == 0
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL


def test_cancel_uses_windows_process_tree_kill(monkeypatch):
    calls: list[list[str]] = []

    class _FakeRunningProcess:
        pid = 1234

        def poll(self) -> None:
            return None

        def send_signal(self, sig: int) -> None:  # noqa: ARG002
            raise AssertionError("Windows cancel should use taskkill for the process tree")

    def fake_run(cmd: list[str], **kwargs: object) -> object:
        calls.append(cmd)

        class _Completed:
            returncode = 0

        return _Completed()

    monkeypatch.setattr(runner.sys, "platform", "win32")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    handle = runner.RunHandle(
        run_id="run",
        process=cast(subprocess.Popen, _FakeRunningProcess()),
        start_time=0.0,
    )

    assert runner.cancel(handle) is True
    assert handle.cancelled is True
    assert calls == [["taskkill", "/PID", "1234", "/T", "/F"]]


def test_run_result_reads_csv_without_pandas(monkeypatch, tmp_path: Path):
    (tmp_path / "top_variants.csv").write_text(
        "rank,variant,y_predicted\n1,A1C,1.2\n2,C2A,0.8\n",
        encoding="utf-8",
    )
    (tmp_path / "df_test.csv").write_text(
        "rank,variant,y_predicted\n1,A1C,1.2\n2,C2A,0.8\n3,A1G,0.7\n",
        encoding="utf-8",
    )

    real_import = builtins.__import__

    def import_without_pandas(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "pandas":
            raise ModuleNotFoundError("No module named 'pandas'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", import_without_pandas)

    result = handle_evolvepro_run_result({"output_dir": str(tmp_path)})

    assert result == {
        "output_csv": str(tmp_path / "df_test.csv"),
        "top_variants": [
            {"rank": "1", "variant": "A1C", "y_predicted": "1.2"},
            {"rank": "2", "variant": "C2A", "y_predicted": "0.8"},
        ],
        "n_predictions": 3,
        "elapsed_sec": None,
    }
