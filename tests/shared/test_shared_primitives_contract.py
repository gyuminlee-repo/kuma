"""Contract tests for the shared primitives every export path runs through.

Each test here was checked against the defect it describes: with the fix
reverted it fails. A test that passes both ways witnesses nothing, which is
what the audit found wrong with much of the existing suite.

The four defects, all of one shape: a quantity that could not be obtained
reported as an ordinary value, so nothing downstream can tell the two apart.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kuma_core.shared import memory_monitor
from kuma_core.shared.atomic_write import atomic_write_text
from kuma_core.shared.memory_monitor import memory_usage_ratio
from kuma_core.shared.output_hash import write_output_checksum
from kuma_core.shared.run_manifest import build_run_manifest

# ---------------------------------------------------------------------------
# The memory guard says when it cannot measure
# ---------------------------------------------------------------------------


def test_unreadable_total_is_none_not_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """A total of zero yields None, so no threshold comparison can succeed.

    Reverted to ``return 0.0`` this fails, because 0.0 compares below both
    thresholds and the guard sits silently open for the life of the process.
    """
    monkeypatch.setattr(memory_monitor, "get_system_total_bytes", lambda: 0)
    assert memory_usage_ratio() is None


def test_zero_usage_stays_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """A measured share of zero is still 0.0, and is not confused with None.

    Without this the previous test would pass on a function that returned None
    unconditionally, which measures nothing.
    """
    monkeypatch.setattr(memory_monitor, "get_system_total_bytes", lambda: 1 << 30)
    monkeypatch.setattr(memory_monitor, "get_self_rss_bytes", lambda: 0)
    assert memory_usage_ratio() == 0.0


# ---------------------------------------------------------------------------
# An input that could not be read is not an input that was never supplied
# ---------------------------------------------------------------------------


def _manifest_for(inputs: dict[str, Path]) -> dict:
    now = datetime.now(timezone.utc)
    return build_run_manifest(
        method="export", inputs=inputs, params={}, started_at=now, finished_at=now
    )


def test_unreadable_input_is_distinguishable_from_absent(tmp_path: Path) -> None:
    """A directory handed in where a file was expected keeps its key.

    A directory is used rather than a chmod, because mode 0000 does not deny
    root and the suite runs as root in containers. IsADirectoryError is an
    OSError on every platform, which is the branch under test.

    Reverted to ``continue`` this fails: both manifests come out as ``{}`` and
    a run that consumed a file it could not hash is indistinguishable from one
    the operator never supplied.
    """
    handed_in = tmp_path / "layout"
    handed_in.mkdir()

    never_supplied = _manifest_for({"layout": tmp_path / "absent.xlsx"})["inputs"]
    unreadable = _manifest_for({"layout": handed_in})["inputs"]

    assert never_supplied == {}
    assert "layout" in unreadable
    assert unreadable["layout"]["sha256"] is None
    assert unreadable["layout"]["path"] == str(handed_in)
    assert unreadable["layout"]["unreadable"]


def test_readable_input_records_a_digest(tmp_path: Path) -> None:
    """The control: an ordinary input still carries hash and size.

    Without it the test above would pass on a function that recorded every
    input as unreadable.
    """
    plate = tmp_path / "plate.xlsx"
    plate.write_bytes(b"payload")

    entry = _manifest_for({"layout": plate})["inputs"]["layout"]
    assert entry["sha256"] is not None
    assert entry["size_bytes"] == 7
    assert "unreadable" not in entry


# ---------------------------------------------------------------------------
# Two writers of one target do not collide on a shared staging name
# ---------------------------------------------------------------------------


def test_concurrent_writers_both_publish(tmp_path: Path) -> None:
    """Neither writer fails, and the published file is one of the two whole.

    Reverted to the fixed ``.tmp`` suffix this fails: measured over twenty
    rounds, one writer raised FileNotFoundError out of os.replace in eighteen
    of them, on a staging path the caller never named.
    """
    target = tmp_path / "manifest.json"
    a = "A" * 400_000
    b = "B" * 400_000
    errors: list[BaseException] = []

    def write(content: str) -> None:
        try:
            atomic_write_text(target, content, fsync=False)
        except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
            errors.append(exc)

    for _ in range(20):
        errors.clear()
        threads = [
            threading.Thread(target=write, args=(a,)),
            threading.Thread(target=write, args=(b,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"a writer failed: {errors[0]!r}"
        assert target.read_text(encoding="utf-8") in (a, b)


def test_staging_file_is_cleared_on_success(tmp_path: Path) -> None:
    """The per-call staging name still leaves nothing behind.

    The token would be a cheap way to make the test above pass while littering
    the output directory, which is what this rules out.
    """
    target = tmp_path / "out.txt"
    atomic_write_text(target, "hello")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.txt"]


# ---------------------------------------------------------------------------
# The checksum file is published the way its neighbour is
# ---------------------------------------------------------------------------


def test_checksum_publishes_nothing_when_the_write_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure before the rename leaves no file at the final name.

    The interruption is injected at the fsync, which is the last step the
    atomic primitive takes before publishing. That is a proxy for a crash
    mid-write rather than a reproduction of one, and it is enough to separate
    the two implementations: staged, the failure discards the staging file and
    the target is never created; written in place, the same failure point does
    not exist and the file appears.

    Reverted to ``Path.write_text`` this fails on the last two assertions,
    because that call publishes directly at the final name. shasum -c answers
    on a partial digest line rather than declining, so a truncated one reports
    an intact export as a mismatch.
    """
    exported = tmp_path / "primers.xlsx"
    exported.write_bytes(b"payload")

    def refuse(fd: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", refuse)

    with pytest.raises(OSError):
        write_output_checksum(exported)

    assert not (tmp_path / "primers.xlsx.sha256").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["primers.xlsx"]


def test_checksum_line_keeps_lf_on_every_platform(tmp_path: Path) -> None:
    """Routing through the atomic primitive must not reintroduce CRLF.

    A CR before the filename makes shasum -c look for a name that is not
    there, which is a Windows defect this repository already fixed once.
    """
    exported = tmp_path / "order.csv"
    exported.write_bytes(b"payload")

    checksum_path = write_output_checksum(exported)
    raw = checksum_path.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"  order.csv\n")
