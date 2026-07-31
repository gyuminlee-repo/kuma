"""``export_run_report`` refusals (handlers/report.py).

A run report that opens but says nothing is worse than one that was not written:
it reads as a finished run. These tests pin the two states that must be refused
rather than rendered.
"""

from __future__ import annotations

import pytest

from sidecar_mame import core
from sidecar_mame.handlers.report import handle_export_run_report


@pytest.fixture(autouse=True)
def _clean_state():
    core.reset_state()
    yield
    core.reset_state()


def test_no_prior_analyze_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="No prior analyze result"):
        handle_export_run_report({"output": str(tmp_path / "report.html")})


def test_an_empty_verdict_list_is_refused_instead_of_rendering_a_blank_report(tmp_path):
    # analyze ran but matched no wells. The renderer would happily produce a full
    # scaffold with every count at zero, which is the "report file blank" symptom.
    core.set_last_analyze(verdicts=[], replicates=[], output_path=str(tmp_path))

    with pytest.raises(RuntimeError, match="blank"):
        handle_export_run_report({"output": str(tmp_path / "report.html")})

    assert not (tmp_path / "report.html").exists()


def test_refusal_names_what_to_check(tmp_path):
    core.set_last_analyze(verdicts=[], replicates=[], output_path=str(tmp_path))

    with pytest.raises(RuntimeError) as excinfo:
        handle_export_run_report({"output": str(tmp_path / "report.html")})

    # 사용자가 다음에 무엇을 볼지 알 수 있어야 한다.
    message = str(excinfo.value)
    assert "barcode" in message and "run-folder" in message
