"""Non-finite cells in MinKNOW report files must not crash or silently zero.

Contract under test, in the repo's own terms: a value that could not be measured
is ``None``, never ``0``. ``inf`` / ``nan`` in a report json or a MinKNOW csv is
an unmeasurable value, so it must leave the metric absent rather than crash the
run or contribute a fabricated number.

Every case below is paired with a control that feeds an ordinary value through
the same call, so a test failing here means the non-finite path broke, not that
the parser stopped working.
"""

from __future__ import annotations

import math
from pathlib import Path

from kuma_core.mame import health
from kuma_core.mame.ingest import read_length


# ---------------------------------------------------------------------------
# read_length._as_int / _as_float
# ---------------------------------------------------------------------------


def test_as_int_rejects_non_finite_without_raising() -> None:
    """int(float('inf')) raises OverflowError; int(float('nan')) raises ValueError."""
    assert read_length._as_int(float("inf")) is None
    assert read_length._as_int(float("-inf")) is None
    assert read_length._as_int(float("nan")) is None
    # The same values arriving as strings, which is how MinKNOW writes buckets.
    assert read_length._as_int("inf") is None
    assert read_length._as_int("-Infinity") is None
    assert read_length._as_int("nan") is None


def test_as_int_control_ordinary_values_still_parse() -> None:
    assert read_length._as_int(1500) == 1500
    assert read_length._as_int(1500.9) == 1500
    assert read_length._as_int("1500") == 1500
    assert read_length._as_int("1500.9") == 1500
    assert read_length._as_int("not a number") is None
    assert read_length._as_int(True) is None


def test_as_int_distinguishes_measured_zero_from_absent() -> None:
    assert read_length._as_int(0) == 0
    assert read_length._as_int("0") == 0
    assert read_length._as_int(0.0) == 0
    assert read_length._as_int(None) is None


def test_as_float_rejects_non_finite() -> None:
    assert read_length._as_float(float("inf")) is None
    assert read_length._as_float(float("-inf")) is None
    assert read_length._as_float(float("nan")) is None
    assert read_length._as_float("inf") is None
    assert read_length._as_float("NaN") is None


def test_as_float_control_ordinary_values_still_parse() -> None:
    assert read_length._as_float(12.5) == 12.5
    assert read_length._as_float("12.5") == 12.5
    assert read_length._as_float(12) == 12.0
    assert read_length._as_float("junk") is None


def test_as_float_distinguishes_measured_zero_from_absent() -> None:
    assert read_length._as_float(0) == 0.0
    assert read_length._as_float("0.0") == 0.0
    assert read_length._as_float(None) is None


# ---------------------------------------------------------------------------
# read_length._read_buckets -> _bin_midpoints
# ---------------------------------------------------------------------------


def _bucket_section(ranges: list[dict[str, object]], values: list[object]) -> dict[str, object]:
    return {
        "bucket_ranges": ranges,
        "histogram_data": [{"bucket_values": values}],
    }


def test_read_buckets_drops_non_finite_bins_and_midpoints_stay_finite() -> None:
    section = _bucket_section(
        [
            {"start": 0, "end": 128},
            {"start": 128, "end": "inf"},
            {"start": "inf", "end": 512},
            {"start": 512, "end": 640},
        ],
        [10, 20, 30, 40],
    )
    buckets = read_length._read_buckets(section)
    assert buckets is not None
    # Only the two well-formed bins survive; neither a non-finite end nor a
    # non-finite start may be quietly rewritten to 0.
    assert buckets.starts == [0, 512]
    assert buckets.ends == [128, 640]
    assert buckets.values == [10, 40]
    mids = read_length._bin_midpoints(buckets)
    assert all(math.isfinite(m) for m in mids)
    assert mids == [64.0, 576.0]


def test_read_buckets_control_missing_start_still_opens_at_zero() -> None:
    """A first bucket with no 'start' key legitimately opens at 0 (documented)."""
    section = _bucket_section([{"end": 128}, {"start": 128, "end": 256}], [10, 20])
    buckets = read_length._read_buckets(section)
    assert buckets is not None
    assert buckets.starts == [0, 128]
    assert buckets.ends == [128, 256]
    assert buckets.values == [10, 20]


def test_read_buckets_control_all_finite_survives_intact() -> None:
    section = _bucket_section(
        [{"start": 0, "end": 128}, {"start": 128, "end": 256}], ["10", "20"]
    )
    buckets = read_length._read_buckets(section)
    assert buckets is not None
    assert buckets.values == [10, 20]


def test_read_buckets_returns_none_when_every_bin_is_non_finite() -> None:
    """Absent, not an empty distribution: no bin was readable."""
    section = _bucket_section([{"start": 0, "end": "inf"}], ["inf"])
    assert read_length._read_buckets(section) is None


def test_read_qscore_drops_non_finite_edges() -> None:
    entry = {
        "bucket_ranges": [
            {"start": 0, "end": 10},
            {"start": "inf", "end": 20},
            {"start": 20, "end": "inf"},
        ],
        "histogram_data": [{"bucket_values": [1, 2, 3]}],
    }
    parsed = read_length._read_qscore(entry)
    assert parsed is not None
    assert parsed.starts == [0.0]
    assert parsed.ends == [10.0]


def test_read_qscore_control_missing_start_opens_at_zero() -> None:
    entry = {
        "bucket_ranges": [{"end": 10}, {"start": 10, "end": 20}],
        "histogram_data": [{"bucket_values": [1, 2]}],
    }
    parsed = read_length._read_qscore(entry)
    assert parsed is not None
    assert parsed.starts == [0.0, 10.0]
    assert parsed.ends == [10.0, 20.0]


# ---------------------------------------------------------------------------
# health._parse_pore_activity
# ---------------------------------------------------------------------------


def _write_pore_activity(tmp_path: Path, body: str) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "pore_activity_abc123.csv").write_text(body, encoding="utf-8")
    return run_dir


def test_pore_activity_wide_layout_non_finite_is_absent(tmp_path: Path) -> None:
    run_dir = _write_pore_activity(
        tmp_path, "Experiment Time (minutes),% Active Pores\n1,nan\n"
    )
    assert health._parse_pore_activity(run_dir) is None


def test_pore_activity_wide_layout_inf_is_absent(tmp_path: Path) -> None:
    run_dir = _write_pore_activity(
        tmp_path, "Experiment Time (minutes),% Active Pores\n1,inf\n"
    )
    assert health._parse_pore_activity(run_dir) is None


def test_pore_activity_wide_layout_control_value_parses(tmp_path: Path) -> None:
    run_dir = _write_pore_activity(
        tmp_path, "Experiment Time (minutes),% Active Pores\n1,72.5\n"
    )
    assert health._parse_pore_activity(run_dir) == 72.5


def test_pore_activity_wide_layout_measured_zero_is_not_absent(tmp_path: Path) -> None:
    run_dir = _write_pore_activity(
        tmp_path, "Experiment Time (minutes),% Active Pores\n1,0.0\n"
    )
    result = health._parse_pore_activity(run_dir)
    assert result == 0.0
    assert result is not None


def test_pore_activity_long_layout_non_finite_cell_is_dropped(tmp_path: Path) -> None:
    """An inf state-time must not poison the ratio into nan."""
    run_dir = _write_pore_activity(
        tmp_path,
        "Channel State,Experiment Time (minutes),State Time (samples)\n"
        "strand,1,inf\n"
        "strand,2,300\n"
        "unavailable,3,100\n",
    )
    result = health._parse_pore_activity(run_dir)
    assert result is not None
    assert math.isfinite(result)
    assert result == 75.0


def test_pore_activity_long_layout_control(tmp_path: Path) -> None:
    run_dir = _write_pore_activity(
        tmp_path,
        "Channel State,Experiment Time (minutes),State Time (samples)\n"
        "strand,1,300\n"
        "unavailable,2,100\n",
    )
    assert health._parse_pore_activity(run_dir) == 75.0


# ---------------------------------------------------------------------------
# health._parse_barcode_alignment
# ---------------------------------------------------------------------------


def _write_barcode_alignment(tmp_path: Path, body: str) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "barcode_alignment_passed_abc.tsv").write_text(body, encoding="utf-8")
    return run_dir


def test_barcode_alignment_inf_count_does_not_raise(tmp_path: Path) -> None:
    """int(float('inf')) raises OverflowError, outside every except here."""
    run_dir = _write_barcode_alignment(
        tmp_path,
        "barcode\tcount\nbarcode01\tinf\nbarcode02\t120\n",
    )
    dist = health._parse_barcode_alignment(run_dir)
    assert dist == {"barcode02": 120}


def test_barcode_alignment_nan_count_is_dropped(tmp_path: Path) -> None:
    run_dir = _write_barcode_alignment(
        tmp_path,
        "barcode\tcount\nbarcode01\tnan\nbarcode02\t120\n",
    )
    assert health._parse_barcode_alignment(run_dir) == {"barcode02": 120}


def test_barcode_alignment_control_counts_parse(tmp_path: Path) -> None:
    run_dir = _write_barcode_alignment(
        tmp_path,
        "barcode\tcount\nbarcode01\t100\nbarcode02\t120.0\n",
    )
    assert health._parse_barcode_alignment(run_dir) == {
        "barcode01": 100,
        "barcode02": 120,
    }


def test_barcode_alignment_measured_zero_is_kept(tmp_path: Path) -> None:
    """0 reads on a lane is a measurement, not a missing value."""
    run_dir = _write_barcode_alignment(
        tmp_path,
        "barcode\tcount\nbarcode01\t0\nbarcode02\t120\n",
    )
    dist = health._parse_barcode_alignment(run_dir)
    assert dist is not None
    assert dist["barcode01"] == 0


def test_barcode_alignment_all_non_finite_returns_none(tmp_path: Path) -> None:
    run_dir = _write_barcode_alignment(
        tmp_path,
        "barcode\tcount\nbarcode01\tinf\n",
    )
    assert health._parse_barcode_alignment(run_dir) is None
