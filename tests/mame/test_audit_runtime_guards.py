"""Regression tests for alignment IO and interrupted-run marker contracts."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from kuma_core.mame.ingest import align
from kuma_core.mame.ingest.stage_marker import (
    MARKER_FILENAME, is_unit_complete, read_stage_marker, validate_marker, write_stage_marker,
)


@pytest.mark.parametrize("cigar", ["bad10M", "10Mbad20M", "10M?20M", "10M?"])
def test_cigar_rejects_unparsed_characters(cigar: str) -> None:
    with pytest.raises(ValueError, match="Malformed CIGAR"):
        align._parse_cigar(cigar)


def test_valid_cigar_and_absent_cigar_are_unchanged() -> None:
    assert align._parse_cigar("2H3S10M1I7M2D4=1X") == [
        [2, 5], [3, 4], [10, 0], [1, 1], [7, 0], [2, 2], [4, 7], [1, 8],
    ]
    assert align._parse_cigar("*") == []
    assert align._parse_cigar("") == []


def test_alignment_refuses_multiple_reference_records(tmp_path: Path) -> None:
    ref = tmp_path / "ref.fasta"
    ref.write_text(">first\nAAAA\n>second\nTTTTTTTT\n", encoding="utf-8")
    with pytest.raises(ValueError, match="single molecule"):
        align._get_reference_length(ref)


def test_alignment_keeps_single_record_length(tmp_path: Path) -> None:
    ref = tmp_path / "ref.fasta"
    ref.write_text(">single\nAAAA\nTTTT\n", encoding="utf-8")
    assert align._get_reference_length(ref) == 8


def _run_child(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, source: str):
    """Use a real process and bounded watchdog; never leave a failed child alive."""
    real_popen = subprocess.Popen
    children: list[subprocess.Popen[str]] = []

    def start(_cmd: list[str], **kwargs: Any) -> subprocess.Popen[str]:
        child: subprocess.Popen[str] = real_popen([sys.executable, "-c", source], **kwargs)
        children.append(child)
        return child

    def stop() -> None:
        for child in children:
            if child.poll() is None:
                child.kill()

    monkeypatch.setattr(align, "_resolve_minimap2", lambda: "test-minimap2")
    monkeypatch.setattr(align.subprocess, "Popen", start)
    watchdog = threading.Timer(15.0, stop)
    watchdog.daemon = True
    watchdog.start()
    try:
        return align._run_minimap2(tmp_path / "ref.fa", tmp_path / "reads.fa", "map-ont"), children
    finally:
        watchdog.cancel()
        stop()
        for child in children:
            child.wait(timeout=5)


def test_stderr_larger_than_pipe_capacity_cannot_deadlock_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    source = (
        "import sys\n"
        "sys.stderr.write('diagnostic ' * 100000); sys.stderr.flush()\n"
        "sys.stdout.write('0\\t0\\tref\\t1\\t60\\t8M\\t*\\t0\\t0\\tACGTACGT\\t*\\n'); sys.stdout.flush()\n"
    )
    records, _ = _run_child(monkeypatch, tmp_path, source)
    assert records == [(0, 0, 1, 60, "8M")]


def test_nonzero_alignment_exit_reports_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="test diagnostic"):
        _run_child(monkeypatch, tmp_path, "import sys; sys.stderr.write('test diagnostic'); sys.exit(3)")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("wells", None), ("wells", 1), ("wells", ["1_1", "1_1"]),
        ("schema_version", 999), ("schema_version", True),
        ("stage", "some_other_stage"), ("unit", "another_barcode"),
        ("consensus", "false"), ("per_well_counts", None),
        ("per_well_counts", {"1_1": -1}), ("per_well_counts", {"1_1": True}),
        ("per_well_counts", {"1_1": "12"}), ("per_well_counts", {}),
        ("n_input_reads", float("inf")), ("stats", {"total_reads": -1}),
    ],
)
def test_malformed_marker_is_incomplete_not_a_crash_or_success(
    tmp_path: Path, key: str, value: Any,
) -> None:
    unit = tmp_path / "NB01"
    unit.mkdir()
    (unit / "1_1.fasta").write_text(">1_1 depth=12\nACGT\n", encoding="utf-8")
    write_stage_marker(unit, per_well_counts={"1_1": 12}, consensus=True)
    marker = read_stage_marker(unit)
    assert marker is not None
    marker[key] = value
    ok, reason = validate_marker(marker, unit)
    assert not ok
    assert reason
    (unit / MARKER_FILENAME).write_text(json.dumps(marker), encoding="utf-8")
    assert not is_unit_complete(unit)


def test_a_directory_is_not_a_completed_consensus_file(tmp_path: Path) -> None:
    unit = tmp_path / "NB01"
    unit.mkdir()
    (unit / "1_1.fasta").mkdir()
    write_stage_marker(unit, per_well_counts={"1_1": 12}, consensus=True)
    assert not is_unit_complete(unit)


def test_schema_one_and_empty_completed_unit_remain_supported(tmp_path: Path) -> None:
    unit = tmp_path / "NB01"
    unit.mkdir()
    write_stage_marker(unit, per_well_counts={}, consensus=False)
    marker = read_stage_marker(unit)
    assert marker is not None
    assert validate_marker(marker, unit) == (True, "")
    marker["schema_version"] = 1
    assert validate_marker(marker, unit) == (True, "")
