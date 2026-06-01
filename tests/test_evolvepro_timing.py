"""Tests for kuma_core.evolvepro.timing."""
from __future__ import annotations

import pytest

from kuma_core.evolvepro.timing import (
    SEED_THROUGHPUT,
    _seed_tok_per_sec,
    estimate_seconds,
    workload,
)


# ---------------------------------------------------------------------------
# workload: formula verification
# ---------------------------------------------------------------------------

class TestWorkload:
    def test_all_valid_aa_seq_len_10(self) -> None:
        # All 10 residues in _VALID_AA -> valid_count=10
        # n_variants = 1 + 10*19 = 191
        # total_tokens = 191 * (10 + 2) = 2292
        seq = "ACDEFGHIKL"  # 10 residues, all in VALID_AA
        result = workload(seq)
        assert result["n_variants"] == 191  # noqa: S101
        assert result["total_tokens"] == 191 * 12  # noqa: S101
        assert result["seq_len"] == 10  # noqa: S101

    def test_single_valid_aa(self) -> None:
        # seq = "A", valid_count=1
        # n_variants = 1 + 1*19 = 20
        # total_tokens = 20 * (1 + 2) = 60
        result = workload("A")
        assert result["n_variants"] == 20  # noqa: S101
        assert result["total_tokens"] == 60  # noqa: S101
        assert result["seq_len"] == 1  # noqa: S101

    def test_invalid_aa_not_counted(self) -> None:
        # "X" is not in _VALID_AA -> valid_count=0
        # n_variants = 1 + 0 = 1 (WT only)
        # total_tokens = 1 * (1 + 2) = 3
        result = workload("X")
        assert result["n_variants"] == 1  # noqa: S101
        assert result["total_tokens"] == 3  # noqa: S101

    def test_mixed_valid_invalid(self) -> None:
        # "AX": A is valid, X is not -> valid_count=1
        # n_variants = 1 + 1*19 = 20
        # total_tokens = 20 * (2 + 2) = 80
        result = workload("AX")
        assert result["n_variants"] == 20  # noqa: S101
        assert result["total_tokens"] == 80  # noqa: S101

    def test_empty_sequence_raises(self) -> None:
        with pytest.raises(ValueError, match="wt_sequence"):
            workload("")

    def test_returns_dict_with_required_keys(self) -> None:
        result = workload("ACDE")
        assert "n_variants" in result  # noqa: S101
        assert "total_tokens" in result  # noqa: S101
        assert "seq_len" in result  # noqa: S101


# ---------------------------------------------------------------------------
# estimate_seconds: basis branching
# ---------------------------------------------------------------------------

class TestEstimateSeconds:
    def test_measured_basis(self) -> None:
        wl = workload("ACDE")
        result = estimate_seconds(
            wl,
            model_id="esm2_t33_650M_UR50D",
            gpu=False,
            measured_tok_per_sec=500.0,
        )
        assert result["basis"] == "measured"  # noqa: S101
        assert result["tok_per_sec"] == pytest.approx(500.0)  # noqa: S101
        expected = wl["total_tokens"] / 500.0
        assert result["seconds"] == pytest.approx(expected)  # noqa: S101

    def test_spec_basis_when_no_measured(self) -> None:
        wl = workload("ACDE")
        result = estimate_seconds(
            wl,
            model_id="esm2_t33_650M_UR50D",
            gpu=False,
            measured_tok_per_sec=None,
        )
        assert result["basis"] == "spec"  # noqa: S101
        seed = _seed_tok_per_sec("esm2_t33_650M_UR50D", gpu=False)
        assert result["tok_per_sec"] == pytest.approx(seed)  # noqa: S101

    def test_gpu_uses_gpu_seed(self) -> None:
        wl = workload("ACDE")
        result_cpu = estimate_seconds(
            wl, model_id="esm2_t33_650M_UR50D", gpu=False, measured_tok_per_sec=None
        )
        result_gpu = estimate_seconds(
            wl, model_id="esm2_t33_650M_UR50D", gpu=True, measured_tok_per_sec=None
        )
        # GPU should be faster (higher tok_per_sec, lower seconds).
        assert result_gpu["tok_per_sec"] > result_cpu["tok_per_sec"]  # noqa: S101
        assert result_gpu["seconds"] < result_cpu["seconds"]  # noqa: S101

    def test_zero_measured_tok_per_sec_raises(self) -> None:
        wl = workload("ACDE")
        with pytest.raises(ValueError):
            estimate_seconds(
                wl,
                model_id="esm2_t33_650M_UR50D",
                gpu=False,
                measured_tok_per_sec=0.0,
            )

    def test_negative_measured_tok_per_sec_raises(self) -> None:
        wl = workload("ACDE")
        with pytest.raises(ValueError):
            estimate_seconds(
                wl,
                model_id="esm2_t33_650M_UR50D",
                gpu=False,
                measured_tok_per_sec=-100.0,
            )

    def test_empty_model_id_raises(self) -> None:
        wl = workload("ACDE")
        with pytest.raises(ValueError, match="model_id"):
            estimate_seconds(wl, model_id="", gpu=False, measured_tok_per_sec=None)

    def test_result_has_required_keys(self) -> None:
        wl = workload("A")
        result = estimate_seconds(
            wl, model_id="esm2_t33_650M_UR50D", gpu=False, measured_tok_per_sec=None
        )
        assert "seconds" in result  # noqa: S101
        assert "basis" in result  # noqa: S101
        assert "tok_per_sec" in result  # noqa: S101


# ---------------------------------------------------------------------------
# SEED_THROUGHPUT: sanity check
# ---------------------------------------------------------------------------

class TestSeedThroughput:
    def test_structure(self) -> None:
        assert "gpu" in SEED_THROUGHPUT  # noqa: S101
        assert "cpu" in SEED_THROUGHPUT  # noqa: S101
        for hw in ("gpu", "cpu"):
            assert "small" in SEED_THROUGHPUT[hw]  # noqa: S101
            assert "large" in SEED_THROUGHPUT[hw]  # noqa: S101

    def test_all_positive(self) -> None:
        for hw_vals in SEED_THROUGHPUT.values():
            for val in hw_vals.values():
                assert val > 0  # noqa: S101
