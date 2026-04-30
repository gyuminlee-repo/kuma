"""Tests for kuma_core.mame.health (A8/A9 — run health panel + cross-talk detection)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kuma_core.mame.health import (
    CrossTalkCandidate,
    RunHealthData,
    _well_neighbors,
    build_run_health,
    detect_cross_talk,
)


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


# ── A9: _well_neighbors tests ─────────────────────────────────────────────────


class TestWellNeighbors:
    def test_corner_a1(self) -> None:
        neighbors = _well_neighbors("A1")
        assert set(neighbors) == {"B1", "A2"}

    def test_corner_h12(self) -> None:
        neighbors = _well_neighbors("H12")
        assert set(neighbors) == {"G12", "H11"}

    def test_corner_a12(self) -> None:
        neighbors = _well_neighbors("A12")
        assert set(neighbors) == {"B12", "A11"}

    def test_corner_h1(self) -> None:
        neighbors = _well_neighbors("H1")
        assert set(neighbors) == {"G1", "H2"}

    def test_edge_a6(self) -> None:
        # Top edge — only down and left/right
        neighbors = _well_neighbors("A6")
        assert set(neighbors) == {"B6", "A5", "A7"}

    def test_interior_d6(self) -> None:
        neighbors = _well_neighbors("D6")
        assert set(neighbors) == {"C6", "E6", "D5", "D7"}

    def test_invalid_well_empty(self) -> None:
        assert _well_neighbors("") == []
        assert _well_neighbors("Z1") == []
        assert _well_neighbors("A0") == []
        assert _well_neighbors("A13") == []

    def test_lowercase_row(self) -> None:
        # Should work case-insensitively
        assert set(_well_neighbors("a1")) == {"B1", "A2"}


# ── A9: detect_cross_talk tests ───────────────────────────────────────────────


def _flat_distribution(n: int = 20, base: int = 1000) -> dict[str, int]:
    """Build a uniform distribution for 96-well wells A1..B(n//8+1)."""
    rows = "ABCDEFGH"
    dist: dict[str, int] = {}
    for i in range(n):
        row = rows[i % 8]
        col = i // 8 + 1
        dist[f"{row}{col}"] = base
    return dist


class TestDetectCrossTalk:
    def test_none_returns_empty(self) -> None:
        assert detect_cross_talk(None) == []

    def test_too_few_entries_returns_empty(self) -> None:
        dist = {"A1": 100, "A2": 100, "A3": 100, "A4": 100}
        assert detect_cross_talk(dist) == []

    def test_uniform_distribution_no_candidates(self) -> None:
        dist = _flat_distribution(24, base=5000)
        result = detect_cross_talk(dist)
        assert result == []

    def test_spike_well_detected(self) -> None:
        # Build flat dist and spike one well to a very high count
        dist = _flat_distribution(24, base=1000)
        dist["A1"] = 50_000  # extreme outlier (A1 is always present in flat dist)
        result = detect_cross_talk(dist)
        wells = [c.well for c in result]
        assert "A1" in wells

    def test_spike_well_severity_high(self) -> None:
        dist = _flat_distribution(24, base=1000)
        dist["A1"] = 50_000
        result = detect_cross_talk(dist)
        a1 = next(c for c in result if c.well == "A1")
        assert a1.severity == "high"

    def test_spike_well_z_score_positive(self) -> None:
        dist = _flat_distribution(24, base=1000)
        dist["A1"] = 50_000
        result = detect_cross_talk(dist)
        a1 = next(c for c in result if c.well == "A1")
        assert a1.z_score > 2.5

    def test_sorted_by_z_desc(self) -> None:
        dist = _flat_distribution(24, base=1000)
        dist["A1"] = 20_000
        dist["B1"] = 30_000
        result = detect_cross_talk(dist)
        z_scores = [c.z_score for c in result]
        assert z_scores == sorted(z_scores, reverse=True)

    def test_neighbor_avg_populated(self) -> None:
        # Use a larger flat dist so neighbors of B2 (A2, C2, B1, B3) are all present
        dist = _flat_distribution(48, base=1000)
        dist["B2"] = 50_000  # extreme spike; neighbors are A2, C2, B1, B3 — all 1000
        result = detect_cross_talk(dist)
        b2 = next(c for c in result if c.well == "B2")
        # All 4 neighbors exist in the 48-entry flat dist and have count 1000
        assert b2.neighbor_avg == pytest.approx(1000.0, rel=0.01)

    def test_candidate_is_dataclass(self) -> None:
        dist = _flat_distribution(24, base=1000)
        dist["D6"] = 50_000
        result = detect_cross_talk(dist)
        assert all(isinstance(c, CrossTalkCandidate) for c in result)

    def _build_spread_dist(self) -> dict[str, int]:
        """80 wells with counts 500, 550, 600, … 4450 (step 50).

        mean ≈ 2475, std ≈ 1162 — sufficient spread for severity threshold tests.
        """
        base_vals = list(range(500, 500 + 80 * 50, 50))
        dist: dict[str, int] = {}
        rows = "ABCDEFGH"
        idx = 0
        for col in range(1, 11):
            for row in rows:
                if idx < len(base_vals):
                    dist[f"{row}{col}"] = base_vals[idx]
                    idx += 1
        return dist

    def test_medium_severity(self) -> None:
        """Spike producing z ≈ 3.5 → severity == "medium".

        Spike value 6926 was computed via binary search against the spread dist
        (mean≈2475, std≈1162). Verified: actual z ≈ 3.4998.
        """
        import statistics

        dist = self._build_spread_dist()
        spike_well = "H12"
        spike = 6926  # gives z ≈ 3.5 after insertion
        dist[spike_well] = spike
        # Sanity check: z must be in (3.0, 4.0]
        vals = list(dist.values())
        z_actual = (spike - statistics.mean(vals)) / statistics.stdev(vals)
        assert 3.0 < z_actual <= 4.0, f"Test setup error: z={z_actual:.4f}"
        result = detect_cross_talk(dist)
        candidate = next((c for c in result if c.well == spike_well), None)
        assert candidate is not None
        assert candidate.severity == "medium"

    def test_low_severity(self) -> None:
        """Spike producing z ≈ 2.75 → severity == "low".

        Spike value 5855 was computed via binary search against the spread dist.
        Verified: actual z ≈ 2.7495.
        """
        import statistics

        dist = self._build_spread_dist()
        spike_well = "H12"
        spike = 5855  # gives z ≈ 2.75 after insertion
        dist[spike_well] = spike
        vals = list(dist.values())
        z_actual = (spike - statistics.mean(vals)) / statistics.stdev(vals)
        assert 2.5 < z_actual <= 3.0, f"Test setup error: z={z_actual:.4f}"
        result = detect_cross_talk(dist)
        candidate = next((c for c in result if c.well == spike_well), None)
        assert candidate is not None
        assert candidate.severity == "low"

    def test_build_run_health_includes_cross_talk_field(self) -> None:
        """Regression: cross_talk_candidates must be present and default-empty."""
        data = build_run_health(_sample_verdicts(), _sample_replicates(), None)
        assert hasattr(data, "cross_talk_candidates")
        assert isinstance(data.cross_talk_candidates, list)
