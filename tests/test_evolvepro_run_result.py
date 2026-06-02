from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, cast

from kuma_core.evolvepro.runner import RunHandle, _stream_stdout
from kuma_core.evolvepro import runner
from sidecar_evolvepro import dispatcher


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
