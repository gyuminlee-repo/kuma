# ruff: noqa: S101
"""Unit tests for the mame.run_combinatorial_demux RPC handler.

Coverage
--------
- CombinatorialDemuxParams validation: required fields, path existence,
  range constraints, path-traversal rejection, PR-B field rejection
- handle_run_combinatorial_demux: success path (mocked core), return schema
- Dispatcher registration: method name + _ASYNC_METHODS membership

Test strategy
-------------
``run_combinatorial_demux`` (core) is monkeypatched to avoid mappy/edlib
dependencies in unit tests.  The handler fixture (fastq_pass, xlsx, fasta)
uses real on-disk files so that path-existence validators pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from sidecar_mame.models import CombinatorialDemuxParams


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"

_F_BARCODES = [
    "AATCCCACTAC",  # F1 (11 bp)
    "TGAACTGAGCG",  # F2 (11 bp)
    "TATCTGACCTT",  # F3 (11 bp)
    "ATATGAGACG",   # F4 (10 bp)
    "CGCTCATTAG",   # F5 (10 bp)
    "TAATCTCGTC",   # F6 (10 bp)
    "GCGCGATTTT",   # F7 (10 bp)
    "AGAGCACTAG",   # F8 (10 bp)
    "TGCCTTGATC",   # F9 (10 bp)
    "CTACTCAGTC",   # F10 (10 bp)
    "TCGTCTGACT",   # F11 (10 bp)
    "GAACATACGG",   # F12 (10 bp)
]

_R_BARCODES = [
    "CCCTATGACA",  # R1 (10 bp)
    "TAATGGCAAG",  # R2 (10 bp)
    "AACAAGGCGT",  # R3 (10 bp)
    "GTATGTAGAA",  # R4 (10 bp)
    "TTCTATGGGG",  # R5 (10 bp)
    "CCTCGCAACC",  # R6 (10 bp)
    "TGGATGCTTA",  # R7 (10 bp)
    "AGAGTGCGGC",  # R8 (10 bp)
]

_REF_SEQ = "ATGGCTTGCTCTGTATCCACTGAGAACGTATCTTTCACTGAGACTGAAACTGAGACCCGT"


# ---------------------------------------------------------------------------
# File fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    """Minimal MinKNOW run directory with one FASTQ in fastq_pass/."""
    fastq_pass = tmp_path / "fastq_pass"
    fastq_pass.mkdir()
    fq = fastq_pass / "reads.fastq"
    fq.write_text("@read1\nACGT\n+\nIIII\n")
    return tmp_path


@pytest.fixture()
def barcodes_xlsx(tmp_path: Path) -> Path:
    """Minimal barcodes xlsx with F and R barcode rows."""
    try:
        import openpyxl
    except ImportError:
        pytest.skip("openpyxl not available")

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None

    for i, bc in enumerate(_F_BARCODES, start=1):
        ws.append([f"isps_f_{i}", bc.lower() + _F_TAIL])
    for i, bc in enumerate(_R_BARCODES, start=1):
        ws.append([f"isps_r_{i}", bc.lower() + _R_TAIL])

    path = tmp_path / "barcodes.xlsx"
    wb.save(path)
    return path


@pytest.fixture()
def reference_fasta(tmp_path: Path) -> Path:
    fasta = tmp_path / "reference.fasta"
    fasta.write_text(f">sispS_test\n{_REF_SEQ}\n")
    return fasta


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    return out  # not yet created; handler creates it


# ---------------------------------------------------------------------------
# Mock DemuxResult returned by core
# ---------------------------------------------------------------------------


@dataclass
class _MockDemuxStats:
    total_reads: int = 10
    passed_mapq: int = 8
    passed_coverage: int = 7
    assigned_reads: int = 6
    ambiguous_dropped: int = 1
    chimera_splits: int = 0
    wells_with_reads: int = 3
    wells_with_min_reads: int = 1


@dataclass
class _MockDemuxResult:
    stats: _MockDemuxStats = field(default_factory=_MockDemuxStats)
    per_well_reads: dict[str, list[tuple[str, str]]] = field(
        default_factory=lambda: {
            "1_1": [("r1", "ACGT"), ("r2", "ACGT"), ("r3", "ACGT")],
            "2_3": [("r4", "ACGT"), ("r5", "ACGT")],
            "4_7": [("r6", "ACGT")],
        }
    )
    per_well_consensus: dict[str, str] = field(
        default_factory=lambda: {
            "1_1": "ATGGCT",
            "2_3": "ATGGCC",
            "4_7": "NNNNNN",
        }
    )


# ---------------------------------------------------------------------------
# Params validation tests
# ---------------------------------------------------------------------------


class TestCombinatorialDemuxParamsValidation:
    """Tests for CombinatorialDemuxParams Pydantic model."""

    def test_valid_params_pass(
        self, run_dir: Path, barcodes_xlsx: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "out"
        p = CombinatorialDemuxParams.model_validate(
            {
                "minknow_run_dir": str(run_dir),
                "custom_barcodes_xlsx": str(barcodes_xlsx),
                "reference_fasta": str(reference_fasta),
                "output_dir": str(out),
            }
        )
        assert p.mapq_threshold == 25
        assert p.coverage_fraction == 0.98
        assert p.edit_dist_ratio == 0.25
        assert p.chimera_split is True
        assert p.trim_flank_bp == 30

    def test_missing_required_raises(self) -> None:
        with pytest.raises(Exception):  # pydantic ValidationError
            CombinatorialDemuxParams.model_validate(
                {"minknow_run_dir": "/nonexistent"}
            )

    def test_nonexistent_run_dir_raises(
        self, barcodes_xlsx: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception):
            CombinatorialDemuxParams.model_validate(
                {
                    "minknow_run_dir": "/nonexistent/run_dir",
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": str(tmp_path / "out"),
                }
            )

    def test_nonexistent_barcodes_xlsx_raises(
        self, run_dir: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception):
            CombinatorialDemuxParams.model_validate(
                {
                    "minknow_run_dir": str(run_dir),
                    "custom_barcodes_xlsx": str(tmp_path / "nofile.xlsx"),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": str(tmp_path / "out"),
                }
            )

    def test_nonexistent_reference_fasta_raises(
        self, run_dir: Path, barcodes_xlsx: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception):
            CombinatorialDemuxParams.model_validate(
                {
                    "minknow_run_dir": str(run_dir),
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(tmp_path / "noref.fasta"),
                    "output_dir": str(tmp_path / "out"),
                }
            )

    def test_output_dir_parent_missing_raises(
        self, run_dir: Path, barcodes_xlsx: Path, reference_fasta: Path
    ) -> None:
        with pytest.raises(Exception):
            CombinatorialDemuxParams.model_validate(
                {
                    "minknow_run_dir": str(run_dir),
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": "/nonexistent_parent/output",
                }
            )

    def test_mapq_threshold_out_of_range_raises(
        self, run_dir: Path, barcodes_xlsx: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception):
            CombinatorialDemuxParams.model_validate(
                {
                    "minknow_run_dir": str(run_dir),
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": str(tmp_path / "out"),
                    "mapq_threshold": 100,  # max is 60
                }
            )

    def test_coverage_fraction_out_of_range_raises(
        self, run_dir: Path, barcodes_xlsx: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception):
            CombinatorialDemuxParams.model_validate(
                {
                    "minknow_run_dir": str(run_dir),
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": str(tmp_path / "out"),
                    "coverage_fraction": 1.5,  # max is 1.0
                }
            )

    def test_edit_dist_ratio_out_of_range_raises(
        self, run_dir: Path, barcodes_xlsx: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception):
            CombinatorialDemuxParams.model_validate(
                {
                    "minknow_run_dir": str(run_dir),
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": str(tmp_path / "out"),
                    "edit_dist_ratio": 1.0,  # must be < 1.0
                }
            )

    def test_path_traversal_in_run_dir_raises(
        self, barcodes_xlsx: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        with pytest.raises(Exception):
            CombinatorialDemuxParams.model_validate(
                {
                    "minknow_run_dir": str(tmp_path / ".." / "traversal_target"),
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": str(tmp_path / "out"),
                }
            )

    def test_sample_map_xlsx_accepted(
        self, run_dir: Path, barcodes_xlsx: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        """PR-B: sample_map_xlsx is now accepted (no longer raises NotImplementedError)."""
        sample_map = tmp_path / "sample_map.xlsx"
        sample_map.touch()
        p = CombinatorialDemuxParams.model_validate(
            {
                "minknow_run_dir": str(run_dir),
                "custom_barcodes_xlsx": str(barcodes_xlsx),
                "reference_fasta": str(reference_fasta),
                "output_dir": str(tmp_path / "out"),
                "sample_map_xlsx": str(sample_map),
            }
        )
        assert p.sample_map_xlsx == str(sample_map)

    def test_kuro_xlsx_accepted(
        self, run_dir: Path, barcodes_xlsx: Path, reference_fasta: Path, tmp_path: Path
    ) -> None:
        """PR-B: kuro_xlsx is now accepted (no longer raises NotImplementedError)."""
        kuro = tmp_path / "kuro.xlsx"
        kuro.touch()
        p = CombinatorialDemuxParams.model_validate(
            {
                "minknow_run_dir": str(run_dir),
                "custom_barcodes_xlsx": str(barcodes_xlsx),
                "reference_fasta": str(reference_fasta),
                "output_dir": str(tmp_path / "out"),
                "kuro_xlsx": str(kuro),
            }
        )
        assert p.kuro_xlsx == str(kuro)


# ---------------------------------------------------------------------------
# Handler success test (mocked core)
# ---------------------------------------------------------------------------


class TestHandleRunCombinatorialDemuxSuccess:
    """Tests for handle_run_combinatorial_demux with mocked core call."""

    def _run(
        self,
        run_dir: Path,
        barcodes_xlsx: Path,
        reference_fasta: Path,
        output_dir: Path,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from sidecar_mame.handlers.combinatorial_demux import (
            handle_run_combinatorial_demux,
        )

        params: dict[str, Any] = {
            "minknow_run_dir": str(run_dir),
            "custom_barcodes_xlsx": str(barcodes_xlsx),
            "reference_fasta": str(reference_fasta),
            "output_dir": str(output_dir),
        }
        if extra_params:
            params.update(extra_params)

        mock_result = _MockDemuxResult()
        with (
            patch(
                "kuma_core.mame.ingest.combinatorial_demux.run_combinatorial_demux",
                return_value=mock_result,
            ),
            patch("sidecar_mame.handlers.combinatorial_demux._send"),
        ):
            return handle_run_combinatorial_demux(params)

    def test_returns_expected_keys(
        self,
        run_dir: Path,
        barcodes_xlsx: Path,
        reference_fasta: Path,
        output_dir: Path,
    ) -> None:
        result = self._run(run_dir, barcodes_xlsx, reference_fasta, output_dir)
        expected_keys = {
            "output_dir",
            "stats",
            "wells_with_reads",
            "assigned_reads",
            "chimera_splits",
            "per_well_consensus",
            "per_well_read_counts",
        }
        assert expected_keys <= result.keys()

    def test_stats_contains_expected_keys(
        self,
        run_dir: Path,
        barcodes_xlsx: Path,
        reference_fasta: Path,
        output_dir: Path,
    ) -> None:
        result = self._run(run_dir, barcodes_xlsx, reference_fasta, output_dir)
        stats = result["stats"]
        for key in (
            "total_reads",
            "passed_mapq",
            "passed_coverage",
            "assigned_reads",
            "ambiguous_dropped",
            "chimera_splits",
            "wells_with_reads",
            "wells_with_min_reads",
        ):
            assert key in stats, f"Missing stats key: {key}"

    def test_stats_values_match_mock(
        self,
        run_dir: Path,
        barcodes_xlsx: Path,
        reference_fasta: Path,
        output_dir: Path,
    ) -> None:
        result = self._run(run_dir, barcodes_xlsx, reference_fasta, output_dir)
        assert result["stats"]["total_reads"] == 10
        assert result["stats"]["assigned_reads"] == 6
        assert result["wells_with_reads"] == 3
        assert result["assigned_reads"] == 6
        assert result["chimera_splits"] == 0

    def test_per_well_read_counts_derived(
        self,
        run_dir: Path,
        barcodes_xlsx: Path,
        reference_fasta: Path,
        output_dir: Path,
    ) -> None:
        result = self._run(run_dir, barcodes_xlsx, reference_fasta, output_dir)
        counts = result["per_well_read_counts"]
        assert counts["1_1"] == 3
        assert counts["2_3"] == 2
        assert counts["4_7"] == 1

    def test_per_well_consensus_passed_through(
        self,
        run_dir: Path,
        barcodes_xlsx: Path,
        reference_fasta: Path,
        output_dir: Path,
    ) -> None:
        result = self._run(run_dir, barcodes_xlsx, reference_fasta, output_dir)
        assert result["per_well_consensus"]["1_1"] == "ATGGCT"
        assert result["per_well_consensus"]["2_3"] == "ATGGCC"

    def test_output_dir_is_str(
        self,
        run_dir: Path,
        barcodes_xlsx: Path,
        reference_fasta: Path,
        output_dir: Path,
    ) -> None:
        result = self._run(run_dir, barcodes_xlsx, reference_fasta, output_dir)
        assert isinstance(result["output_dir"], str)

    def test_chimera_split_false_passed_to_core(
        self,
        run_dir: Path,
        barcodes_xlsx: Path,
        reference_fasta: Path,
        output_dir: Path,
    ) -> None:
        """chimera_split=False must be forwarded to the core function."""
        from sidecar_mame.handlers.combinatorial_demux import (
            handle_run_combinatorial_demux,
        )

        params = {
            "minknow_run_dir": str(run_dir),
            "custom_barcodes_xlsx": str(barcodes_xlsx),
            "reference_fasta": str(reference_fasta),
            "output_dir": str(output_dir),
            "chimera_split": False,
        }
        mock_result = _MockDemuxResult()
        with (
            patch(
                "kuma_core.mame.ingest.combinatorial_demux.run_combinatorial_demux",
                return_value=mock_result,
            ) as mock_core,
            patch("sidecar_mame.handlers.combinatorial_demux._send"),
        ):
            handle_run_combinatorial_demux(params)
            _, call_kwargs = mock_core.call_args
            assert call_kwargs.get("chimera_split") is False


# ---------------------------------------------------------------------------
# Dispatcher registration tests
# ---------------------------------------------------------------------------


class TestDispatcherRegistration:
    """Verify the dispatcher _METHODS and _ASYNC_METHODS entries."""

    def test_method_registered_in_methods(self) -> None:
        from sidecar_mame.dispatcher import _METHODS

        assert "mame.run_combinatorial_demux" in _METHODS

    def test_method_in_async_methods(self) -> None:
        from sidecar_mame.dispatcher import _ASYNC_METHODS

        assert "mame.run_combinatorial_demux" in _ASYNC_METHODS

    def test_handler_callable(self) -> None:
        from sidecar_mame.dispatcher import _METHODS

        handler = _METHODS["mame.run_combinatorial_demux"]
        assert callable(handler)


# ---------------------------------------------------------------------------
# Heartbeat thread tests
# ---------------------------------------------------------------------------


class TestHeartbeat:
    """Verify heartbeat keep-alive emits during run_combinatorial_demux.

    Strategy: monkeypatch _HEARTBEAT_INTERVAL_S to 0.05 s and make the
    core sleep for 0.2 s.  The heartbeat thread must fire at least once
    during that window, emitting a progress notification with stage="demux"
    and value=50 (initial holder state, alignment phase).
    """

    def test_heartbeat_emits_during_alignment(
        self,
        run_dir: "Path",
        barcodes_xlsx: "Path",
        reference_fasta: "Path",
        output_dir: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        import time
        from unittest.mock import MagicMock, call, patch

        import sidecar_mame.handlers.combinatorial_demux as hb_mod

        # Speed up heartbeat interval so test completes in < 1 s.
        monkeypatch.setattr(hb_mod, "_HEARTBEAT_INTERVAL_S", 0.05)

        mock_result = _MockDemuxResult()

        def _slow_demux(**kwargs):
            """Simulate a long-running alignment with no progress callbacks."""
            time.sleep(0.25)
            return mock_result

        emitted: list[dict] = []

        def _capture_send(obj: dict) -> None:
            emitted.append(obj)

        with (
            patch(
                "kuma_core.mame.ingest.combinatorial_demux.run_combinatorial_demux",
                side_effect=_slow_demux,
            ),
            patch("sidecar_mame.handlers.combinatorial_demux._send", side_effect=_capture_send),
        ):
            from sidecar_mame.handlers.combinatorial_demux import (
                handle_run_combinatorial_demux,
            )

            handle_run_combinatorial_demux(
                {
                    "minknow_run_dir": str(run_dir),
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": str(output_dir),
                }
            )

        # Filter progress notifications (method == "progress")
        progress_events = [
            obj for obj in emitted
            if obj.get("method") == "progress"
        ]
        # At least the initial emit (value=50) + 1 heartbeat re-emit must exist.
        # With 0.05 s interval and 0.25 s sleep we expect ~4-5 heartbeats.
        heartbeat_events = [
            e for e in progress_events
            if e.get("params", {}).get("value") == 50
            and e.get("params", {}).get("stage") == "demux"
        ]
        assert len(heartbeat_events) >= 2, (
            f"Expected >= 2 demux/50 progress events (initial + heartbeat), "
            f"got {len(heartbeat_events)}. All events: {progress_events}"
        )

    def test_heartbeat_stops_after_completion(
        self,
        run_dir: "Path",
        barcodes_xlsx: "Path",
        reference_fasta: "Path",
        output_dir: "Path",
        monkeypatch: "pytest.MonkeyPatch",
    ) -> None:
        """Heartbeat thread must stop after run_combinatorial_demux returns."""
        import time
        from unittest.mock import patch

        import sidecar_mame.handlers.combinatorial_demux as hb_mod
        import threading

        monkeypatch.setattr(hb_mod, "_HEARTBEAT_INTERVAL_S", 0.05)

        mock_result = _MockDemuxResult()
        thread_ref: list = []

        original_thread_cls = threading.Thread

        def _capturing_thread(target=None, daemon=None, name=None):
            t = original_thread_cls(target=target, daemon=daemon, name=name)
            if name == "demux-heartbeat":
                thread_ref.append(t)
            return t

        with (
            patch(
                "kuma_core.mame.ingest.combinatorial_demux.run_combinatorial_demux",
                return_value=mock_result,
            ),
            patch("sidecar_mame.handlers.combinatorial_demux._send"),
            patch("sidecar_mame.handlers.combinatorial_demux.threading.Thread",
                  side_effect=_capturing_thread),
        ):
            from sidecar_mame.handlers.combinatorial_demux import (
                handle_run_combinatorial_demux,
            )

            handle_run_combinatorial_demux(
                {
                    "minknow_run_dir": str(run_dir),
                    "custom_barcodes_xlsx": str(barcodes_xlsx),
                    "reference_fasta": str(reference_fasta),
                    "output_dir": str(output_dir),
                }
            )

        # Thread must be captured and must have stopped.
        assert len(thread_ref) == 1, "Expected exactly one demux-heartbeat thread"
        hb = thread_ref[0]
        # Allow a short grace period for join.
        hb.join(timeout=0.5)
        assert not hb.is_alive(), "Heartbeat thread still alive after handler returned"
