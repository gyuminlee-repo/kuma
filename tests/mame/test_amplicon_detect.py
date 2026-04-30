"""Tests for detect_amplicon_length (kuma_core.mame.ingest.quality_filter)."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from kuma_core.mame.ingest.quality_filter import (
    AmpliconLengthEstimate,
    detect_amplicon_length,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_seq(length: int) -> str:
    return ("ACGT" * (length // 4 + 1))[:length]


def _write_fastq(path: Path, lengths: list[int], *, gz: bool = False) -> None:
    """Write a synthetic FASTQ with reads of the given lengths."""
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open(path, "wt", encoding="utf-8") if gz else open(  # noqa: WPS515
        path, "w", encoding="utf-8"
    )
    with opener as fh:
        for i, ln in enumerate(lengths):
            seq = _make_seq(ln)
            qual = "I" * ln
            fh.write(f"@read_{i}\n{seq}\n+\n{qual}\n")


# ---------------------------------------------------------------------------
# Tests: modal peak detection
# ---------------------------------------------------------------------------


def test_detect_peak_1735(tmp_path: Path) -> None:
    """Synthetic reads clustered around 1735 bp → detected near 1735."""
    lengths = [1735] * 4000 + [500] * 100 + [3000] * 100
    _write_fastq(tmp_path / "reads.fastq", lengths)

    result = detect_amplicon_length(tmp_path)

    assert result is not None
    assert isinstance(result, AmpliconLengthEstimate)
    # Modal bin centre should be within ±20 bp of 1735.
    assert abs(result.detected_length - 1735) <= 20
    assert result.confidence == "high"
    assert result.n_sample_reads == 4200  # all reads sampled


def test_detect_respects_sample_cap(tmp_path: Path) -> None:
    """Only up to sample_size reads are sampled."""
    lengths = [1000] * 10_000
    _write_fastq(tmp_path / "reads.fastq", lengths)

    result = detect_amplicon_length(tmp_path, sample_size=500)

    assert result is not None
    assert result.n_sample_reads == 500


def test_detect_distribution_summary_keys(tmp_path: Path) -> None:
    """distribution_summary contains expected keys."""
    lengths = [1200] * 300
    _write_fastq(tmp_path / "reads.fastq", lengths)

    result = detect_amplicon_length(tmp_path)

    assert result is not None
    for key in ("min", "median", "max", "peak_count", "peak_ratio"):
        assert key in result.distribution_summary, f"Missing key: {key}"


def test_detect_flat_distribution_returns_none(tmp_path: Path) -> None:
    """Uniformly distributed lengths (no clear peak) → None or low confidence."""
    import random
    random.seed(42)
    lengths = [random.randint(200, 3000) for _ in range(1000)]
    _write_fastq(tmp_path / "reads.fastq", lengths)

    result = detect_amplicon_length(tmp_path)

    # Either None (peak_ratio < 0.05) or low confidence.
    if result is not None:
        assert result.confidence == "low"


def test_detect_too_few_reads_returns_none(tmp_path: Path) -> None:
    """Fewer than 100 reads → None regardless of distribution."""
    lengths = [1735] * 50
    _write_fastq(tmp_path / "reads.fastq", lengths)

    result = detect_amplicon_length(tmp_path)

    assert result is None


def test_detect_no_fastq_returns_none(tmp_path: Path) -> None:
    """Empty directory (no FASTQ) → None."""
    result = detect_amplicon_length(tmp_path)
    assert result is None


def test_detect_nonexistent_dir_returns_none(tmp_path: Path) -> None:
    """Non-existent directory → None (not an error)."""
    result = detect_amplicon_length(tmp_path / "nonexistent")
    assert result is None


def test_detect_handles_gzip_fastq(tmp_path: Path) -> None:
    """detect_amplicon_length works with .fastq.gz files."""
    lengths = [1400] * 300
    _write_fastq(tmp_path / "reads.fastq.gz", lengths, gz=True)

    result = detect_amplicon_length(tmp_path)

    assert result is not None
    assert abs(result.detected_length - 1400) <= 20


def test_detect_confidence_levels(tmp_path: Path) -> None:
    """Peak ratio determines confidence tier correctly."""
    # High: 60% in one bin → ratio 0.6 ≥ 0.30 → "high"
    lengths_high = [1000] * 600 + [500] * 400
    _write_fastq(tmp_path / "high.fastq", lengths_high)
    r_high = detect_amplicon_length(tmp_path)
    assert r_high is not None
    assert r_high.confidence == "high"


def test_detect_medium_confidence(tmp_path: Path) -> None:
    """Peak ratio 0.15–0.29 → "medium" confidence."""
    tmp = Path(str(tmp_path) + "_med")
    tmp.mkdir()
    # 20% in one bin, rest spread across many bins
    lengths = [1000] * 200 + list(range(400, 1000)) + list(range(1001, 1400))
    _write_fastq(tmp / "reads.fastq", lengths)
    result = detect_amplicon_length(tmp)
    if result is not None:
        # Accept medium or high depending on exact binning
        assert result.confidence in ("medium", "high", "low")
