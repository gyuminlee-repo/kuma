"""Tests for kuma_core.mame.health (A8 — run health panel)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kuma_core.mame.health import RunHealthData, build_run_health


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_verdict(native: str, verdict_val: str, size_kb: float = 200.0) -> MagicMock:
    barcode = MagicMock()
    barcode.native_barcode = native
    barcode.file_size_kb = size_kb
    translated = MagicMock()
    translated.barcode = barcode
    vr = MagicMock()
    vr.translated = translated
    vr.verdict = MagicMock()
    vr.verdict.value = verdict_val
    return vr


def _make_replicate(
    mutant_id: str,
    selected_plate: str | None,
    is_fallback: bool = False,
) -> MagicMock:
    rr = MagicMock()
    rr.mutant_id = mutant_id
    rr.selected_plate = selected_plate
    rr.failed = selected_plate is None
    rr.is_fallback = is_fallback
    return rr


def _make_run_meta(raw_run_dir: str | None = None) -> MagicMock:
    meta = MagicMock()
    meta.instrument = "MinION"
    meta.raw_run_dir = raw_run_dir
    return meta


def _sample_verdicts() -> list:
    return [
        _make_verdict("NB01", "PASS", 250.0),
        _make_verdict("NB01", "PASS", 230.0),
        _make_verdict("NB01", "AMBIGUOUS", 180.0),
        _make_verdict("NB01", "LOWDEPTH", 40.0),
        _make_verdict("NB02", "PASS", 260.0),
        _make_verdict("NB02", "AMBIGUOUS", 190.0),
        _make_verdict("NB02", "FRAMESHIFT", 30.0),
    ]


def _sample_replicates() -> list:
    return [
        _make_replicate("V5F", "NB01"),
        _make_replicate("K53N", "NB02", is_fallback=True),
        _make_replicate("G12V", None),
    ]


# ── core build_run_health tests ───────────────────────────────────────────────


class TestBuildRunHealth:
    def test_returns_run_health_data(self) -> None:
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        assert isinstance(data, RunHealthData)

    def test_per_plate_keys(self) -> None:
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        assert "NB01" in data.per_plate_summary
        assert "NB02" in data.per_plate_summary

    def test_per_plate_counts_nb01(self) -> None:
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        nb01 = data.per_plate_summary["NB01"]
        assert nb01["total"] == 4
        assert nb01["pass"] == 2
        assert nb01["ambiguous"] == 1
        assert nb01["fail"] == 1

    def test_per_plate_counts_nb02(self) -> None:
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        nb02 = data.per_plate_summary["NB02"]
        assert nb02["total"] == 3
        assert nb02["pass"] == 1
        assert nb02["ambiguous"] == 1
        assert nb02["fail"] == 1

    def test_fallback_tracked(self) -> None:
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        # K53N is_fallback=True on NB02
        assert data.per_plate_summary["NB02"]["fallback"] == 1

    def test_fallback_not_double_counted(self) -> None:
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        assert data.per_plate_summary["NB01"]["fallback"] == 0

    def test_distribution_stats_present(self) -> None:
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        assert "median" in data.file_size_distribution
        assert data.suggested_cutoff_kb >= 50.0
        assert isinstance(data.bimodal, bool)

    def test_no_run_meta_all_none(self) -> None:
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        assert data.pore_yield_pct is None
        assert data.throughput_timeline is None
        assert data.barcode_distribution is None

    def test_run_meta_none_raw_run_dir(self) -> None:
        meta = _make_run_meta(raw_run_dir=None)
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.pore_yield_pct is None
        assert data.throughput_timeline is None
        assert data.barcode_distribution is None

    def test_empty_verdicts_safe(self) -> None:
        data = build_run_health([], [], None)
        assert data.per_plate_summary == {}
        assert data.file_size_distribution == {}
        assert data.suggested_cutoff_kb >= 50.0

    def test_precomputed_dist_stats_used(self) -> None:
        from kuma_core.mame.distribution import DistributionStats

        mock_dist = DistributionStats(
            n_files=5,
            file_size_kb={"min": 100.0, "p05": 105.0, "p25": 110.0, "median": 150.0,
                          "p75": 200.0, "p95": 250.0, "max": 300.0, "mean": 160.0, "std": 50.0},
            suggested_cutoff_kb=100.0,
            suggested_method="kneedle",
            bimodal=True,
        )
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None, mock_dist)
        assert data.bimodal is True
        assert data.suggested_method == "kneedle"
        assert data.file_size_distribution["median"] == 150.0


# ── MinKNOW CSV parsing tests ─────────────────────────────────────────────────


class TestPoreActivityParsing:
    def test_pore_yield_parsed(self, tmp_path: Path) -> None:
        csv_content = "experiment_time (min),pore_active_%\n0,92.5\n30,85.3\n60,78.1\n"
        csv_file = tmp_path / "pore_activity_PAX12345.csv"
        csv_file.write_text(csv_content, encoding="utf-8")
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.pore_yield_pct == pytest.approx(78.1)

    def test_pore_yield_missing_file(self, tmp_path: Path) -> None:
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.pore_yield_pct is None

    def test_pore_yield_unknown_columns(self, tmp_path: Path) -> None:
        csv_content = "time,some_other_col\n0,92.5\n"
        csv_file = tmp_path / "pore_activity_PAX12345.csv"
        csv_file.write_text(csv_content, encoding="utf-8")
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.pore_yield_pct is None


class TestThroughputParsing:
    def test_throughput_timeline_parsed(self, tmp_path: Path) -> None:
        csv_content = "experiment_time (min),reads_per_second\n0,0.0\n30,12345.0\n60,9876.5\n"
        csv_file = tmp_path / "throughput_PAX12345.csv"
        csv_file.write_text(csv_content, encoding="utf-8")
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.throughput_timeline is not None
        assert len(data.throughput_timeline) == 3
        first = data.throughput_timeline[0]
        assert first["time_h"] == pytest.approx(0.0)
        assert first["reads_per_sec"] == pytest.approx(0.0)
        second = data.throughput_timeline[1]
        assert second["time_h"] == pytest.approx(0.5)  # 30 min / 60
        assert second["reads_per_sec"] == pytest.approx(12345.0)

    def test_throughput_missing_file(self, tmp_path: Path) -> None:
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.throughput_timeline is None

    def test_throughput_bad_rows_skipped(self, tmp_path: Path) -> None:
        csv_content = "experiment_time (min),reads_per_second\n0,100.0\nbad,data\n60,200.0\n"
        csv_file = tmp_path / "throughput_PAX12345.csv"
        csv_file.write_text(csv_content, encoding="utf-8")
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        # 2 valid rows (bad row skipped)
        assert data.throughput_timeline is not None
        assert len(data.throughput_timeline) == 2


class TestBarcodeAlignmentParsing:
    def test_barcode_distribution_parsed(self, tmp_path: Path) -> None:
        tsv_content = "barcode_arrangement\tnum_reads\nbarcode01\t12400\nbarcode02\t9850\nunclassified\t1234\n"
        tsv_file = tmp_path / "barcode_alignment_passed.tsv"
        tsv_file.write_text(tsv_content, encoding="utf-8")
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.barcode_distribution is not None
        assert data.barcode_distribution["barcode01"] == 12400
        assert data.barcode_distribution["barcode02"] == 9850

    def test_barcode_alignment_missing_file(self, tmp_path: Path) -> None:
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.barcode_distribution is None

    def test_barcode_alignment_prefers_passed_variant(self, tmp_path: Path) -> None:
        # Both exist; passed variant should win
        tsv_all = "barcode_arrangement\tnum_reads\nbarcode01\t1\n"
        tsv_passed = "barcode_arrangement\tnum_reads\nbarcode01\t999\n"
        (tmp_path / "barcode_alignment.tsv").write_text(tsv_all, encoding="utf-8")
        (tmp_path / "barcode_alignment_passed.tsv").write_text(tsv_passed, encoding="utf-8")
        meta = _make_run_meta(raw_run_dir=str(tmp_path))
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.barcode_distribution is not None
        assert data.barcode_distribution["barcode01"] == 999


class TestGracefulOnNonexistentDir:
    def test_nonexistent_raw_run_dir(self) -> None:
        meta = _make_run_meta(raw_run_dir="/absolutely/nonexistent/path/xyz")
        data = build_run_health(_sample_verdicts(), _sample_replicates(), meta)
        assert data.pore_yield_pct is None
        assert data.throughput_timeline is None
        assert data.barcode_distribution is None
