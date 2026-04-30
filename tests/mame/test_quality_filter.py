"""Tests for A3 per-read quality filter (kuma_core.mame.ingest.quality_filter)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from kuma_core.mame.ingest.quality_filter import (
    QualityFilterParams,
    QualityFilterResult,
    _mean_qscore_from_qual,
    _parse_sequencing_summary,
    filter_reads_by_summary,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _phred(q: int) -> str:
    """Return a single Phred+33 character for Q-score *q*."""
    return chr(q + 33)


def _qual_string(q: int, length: int) -> str:
    return _phred(q) * length


def _make_fastq(path: Path, reads: list[tuple[str, str, int]]) -> None:
    """Write a FASTQ. reads: (read_id, sequence, mean_q_int)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for read_id, seq, q in reads:
            qual = _qual_string(q, len(seq))
            fh.write(f"@{read_id}\n{seq}\n+\n{qual}\n")


def _make_seq(length: int) -> str:
    return ("ACGT" * (length // 4 + 1))[:length]


def _make_summary(
    path: Path,
    rows: list[dict],
) -> None:
    """Write a minimal sequencing_summary_*.txt."""
    # Columns: read_id, mean_qscore_template, sequence_length_template, barcode_score.
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("read_id\tmean_qscore_template\tsequence_length_template\tbarcode_score\n")
        for row in rows:
            fh.write(
                f"{row['read_id']}\t{row.get('qscore', 10.0)}"
                f"\t{row.get('length', 1000)}\t{row.get('bscore', 80.0)}\n"
            )


# ---------------------------------------------------------------------------
# Unit tests: _mean_qscore_from_qual
# ---------------------------------------------------------------------------


def test_mean_qscore_exact_q10() -> None:
    """Uniform Q10 string should yield Q close to 10."""
    qual = _qual_string(10, 100)
    q = _mean_qscore_from_qual(qual)
    assert abs(q - 10.0) < 0.01


def test_mean_qscore_empty_returns_zero() -> None:
    assert _mean_qscore_from_qual("") == 0.0


def test_mean_qscore_high_quality() -> None:
    """Q30 string should yield Q close to 30."""
    qual = _qual_string(30, 200)
    q = _mean_qscore_from_qual(qual)
    assert abs(q - 30.0) < 0.1


def test_mean_qscore_mixed() -> None:
    """Mix of Q10 and Q20 should yield a value between 10 and 20."""
    # Q10 + Q20 mix (50/50).
    qual = _phred(10) * 50 + _phred(20) * 50
    q = _mean_qscore_from_qual(qual)
    assert 10.0 < q < 20.0


# ---------------------------------------------------------------------------
# Unit tests: _parse_sequencing_summary
# ---------------------------------------------------------------------------


def test_parse_summary_extracts_columns(tmp_path: Path) -> None:
    summary = tmp_path / "sequencing_summary.txt"
    _make_summary(
        summary,
        [
            {"read_id": "r1", "qscore": 12.5, "length": 1000, "bscore": 75.0},
            {"read_id": "r2", "qscore": 6.0, "length": 500, "bscore": 55.0},
        ],
    )
    meta = _parse_sequencing_summary(summary)
    assert "r1" in meta
    assert abs(float(meta["r1"]["qscore"]) - 12.5) < 0.01
    assert abs(float(meta["r2"]["qscore"]) - 6.0) < 0.01


def test_parse_summary_missing_file_returns_empty() -> None:
    meta = _parse_sequencing_summary(Path("/nonexistent/summary.txt"))
    assert meta == {}


def test_parse_summary_missing_columns_are_skipped(tmp_path: Path) -> None:
    summary = tmp_path / "s.txt"
    # No barcode_score column.
    summary.write_text("read_id\tmean_qscore_template\tsequence_length_template\nr1\t10.0\t900\n")
    meta = _parse_sequencing_summary(summary)
    assert "r1" in meta
    assert "barcode_score" not in meta["r1"]


# ---------------------------------------------------------------------------
# Integration: filter_reads_by_summary — without summary (FASTQ-only)
# ---------------------------------------------------------------------------


def test_filter_qscore_fastq_only_pass(tmp_path: Path) -> None:
    """Reads with Q≥8 and correct length pass; low-Q reads fail."""
    fastq = tmp_path / "reads.fastq"
    seq_ok = _make_seq(1000)
    seq_low_q = _make_seq(1000)

    reads = [
        ("pass_r1", seq_ok, 12),   # Q12 → passes Q≥8
        ("pass_r2", seq_ok, 9),    # Q9  → passes Q≥8
        ("fail_q",  seq_low_q, 5), # Q5  → fails
    ]
    _make_fastq(fastq, reads)

    params = QualityFilterParams(min_qscore=8.0, length_min=800, length_max=3000)
    out_path, result = filter_reads_by_summary(fastq, sequencing_summary=None, params=params)

    assert isinstance(result, QualityFilterResult)
    assert result.n_input == 3
    assert result.n_passed == 2
    assert result.n_failed_qscore == 1
    assert result.n_failed_length == 0
    assert result.n_failed_barcode == 0
    assert out_path.exists()

    # Verify FASTA output contains exactly 2 records.
    lines = out_path.read_text().splitlines()
    headers = [l for l in lines if l.startswith(">")]
    assert len(headers) == 2


def test_filter_length_min_max(tmp_path: Path) -> None:
    """Reads outside length range are rejected."""
    fastq = tmp_path / "reads.fastq"
    seq_short = _make_seq(300)   # < 800 → fail length
    seq_ok = _make_seq(1200)
    seq_long = _make_seq(4000)   # > 3000 → fail length

    reads = [
        ("short", seq_short, 12),
        ("ok",    seq_ok, 12),
        ("long",  seq_long, 12),
    ]
    _make_fastq(fastq, reads)

    params = QualityFilterParams(min_qscore=8.0, length_min=800, length_max=3000)
    _, result = filter_reads_by_summary(fastq, sequencing_summary=None, params=params)

    assert result.n_passed == 1
    assert result.n_failed_length == 2


def test_filter_no_reads_pass_writes_empty_fasta(tmp_path: Path) -> None:
    fastq = tmp_path / "reads.fastq"
    seq = _make_seq(1000)
    _make_fastq(fastq, [("r1", seq, 2)])  # Q2 → always fails Q≥8

    params = QualityFilterParams(min_qscore=8.0)
    out_path, result = filter_reads_by_summary(fastq, sequencing_summary=None, params=params)

    assert result.n_passed == 0
    assert out_path.exists()
    assert out_path.read_text() == ""


def test_filter_missing_fastq_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="FASTQ file not found"):
        filter_reads_by_summary(
            fastq_path=tmp_path / "nonexistent.fastq",
            sequencing_summary=None,
            params=QualityFilterParams(),
        )


# ---------------------------------------------------------------------------
# Integration: filter_reads_by_summary — with sequencing_summary
# ---------------------------------------------------------------------------


def test_filter_uses_summary_qscore_over_fastq(tmp_path: Path) -> None:
    """Q-score from sequencing_summary overrides FASTQ quality string."""
    fastq = tmp_path / "reads.fastq"
    seq = _make_seq(1000)
    # FASTQ quality is Q12 (would pass), but summary says Q4 (should fail).
    _make_fastq(fastq, [("r1", seq, 12)])

    summary = tmp_path / "sequencing_summary.txt"
    _make_summary(summary, [{"read_id": "r1", "qscore": 4.0, "length": 1000, "bscore": 70.0}])

    params = QualityFilterParams(min_qscore=8.0, min_barcode_score=0.0)
    _, result = filter_reads_by_summary(fastq, sequencing_summary=summary, params=params)

    # Summary Q4 < threshold 8 → should fail.
    assert result.n_failed_qscore == 1
    assert result.n_passed == 0


def test_filter_barcode_score_threshold(tmp_path: Path) -> None:
    """Reads below min_barcode_score are rejected."""
    fastq = tmp_path / "reads.fastq"
    seq = _make_seq(1000)
    _make_fastq(
        fastq,
        [
            ("r_pass", seq, 12),
            ("r_fail_bc", seq, 12),
        ],
    )

    summary = tmp_path / "sequencing_summary.txt"
    _make_summary(
        summary,
        [
            {"read_id": "r_pass", "qscore": 12.0, "length": 1000, "bscore": 80.0},
            {"read_id": "r_fail_bc", "qscore": 12.0, "length": 1000, "bscore": 40.0},
        ],
    )

    params = QualityFilterParams(min_qscore=8.0, min_barcode_score=60.0)
    _, result = filter_reads_by_summary(fastq, sequencing_summary=summary, params=params)

    assert result.n_passed == 1
    assert result.n_failed_barcode == 1


def test_filter_summary_read_not_found_falls_back_to_fastq_qscore(
    tmp_path: Path,
) -> None:
    """Reads absent from summary fall back to FASTQ quality-string Q-score."""
    fastq = tmp_path / "reads.fastq"
    seq = _make_seq(1000)
    # r1 has Q10 in FASTQ quality string; NOT in summary.
    _make_fastq(fastq, [("r1", seq, 10)])

    summary = tmp_path / "sequencing_summary.txt"
    # Summary only has r2 (irrelevant).
    _make_summary(summary, [{"read_id": "r2", "qscore": 5.0, "length": 1000, "bscore": 70.0}])

    params = QualityFilterParams(min_qscore=8.0, min_barcode_score=0.0)
    _, result = filter_reads_by_summary(fastq, sequencing_summary=summary, params=params)

    # FASTQ Q10 ≥ 8 → should pass.
    assert result.n_passed == 1


def test_filter_missing_summary_raises(tmp_path: Path) -> None:
    fastq = tmp_path / "reads.fastq"
    seq = _make_seq(1000)
    _make_fastq(fastq, [("r1", seq, 10)])

    with pytest.raises(FileNotFoundError, match="sequencing_summary not found"):
        filter_reads_by_summary(
            fastq_path=fastq,
            sequencing_summary=tmp_path / "nonexistent_summary.txt",
            params=QualityFilterParams(),
        )


def test_filter_default_params_are_sensible() -> None:
    """Default QualityFilterParams values match the documented spec."""
    p = QualityFilterParams()
    assert p.min_qscore == 8.0
    assert p.length_min == 800
    assert p.length_max == 3000
    assert p.min_barcode_score == 60.0
    assert p.target_length is None
    assert p.length_tolerance_bp == 30


# ---------------------------------------------------------------------------
# R6.5: target_length dynamic window
# ---------------------------------------------------------------------------


def test_filter_target_length_window_pass(tmp_path: Path) -> None:
    """Reads within target_length ± tolerance pass; others fail."""
    fastq = tmp_path / "reads.fastq"
    seq_in = _make_seq(1735)      # exactly at target
    seq_hi = _make_seq(1766)      # 31 bp over → fail
    seq_lo = _make_seq(1704)      # 31 bp under → fail
    seq_edge = _make_seq(1765)    # exactly at upper edge (1735+30) → pass

    reads = [
        ("in",    seq_in,   12),
        ("hi",    seq_hi,   12),
        ("lo",    seq_lo,   12),
        ("edge",  seq_edge, 12),
    ]
    _make_fastq(fastq, reads)

    params = QualityFilterParams(
        min_qscore=8.0,
        target_length=1735,
        length_tolerance_bp=30,
    )
    _, result = filter_reads_by_summary(fastq, sequencing_summary=None, params=params)

    assert result.n_passed == 2      # "in" and "edge"
    assert result.n_failed_length == 2  # "hi" and "lo"


def test_filter_target_length_overrides_length_min_max(tmp_path: Path) -> None:
    """When target_length is set, length_min/max are ignored."""
    fastq = tmp_path / "reads.fastq"
    # Read length 900 would pass length_min=800 but is outside [1735±30].
    seq_old_pass = _make_seq(900)
    seq_new_pass = _make_seq(1735)

    reads = [
        ("old_pass", seq_old_pass, 12),
        ("new_pass", seq_new_pass, 12),
    ]
    _make_fastq(fastq, reads)

    params = QualityFilterParams(
        min_qscore=8.0,
        length_min=800,
        length_max=3000,
        target_length=1735,
        length_tolerance_bp=30,
    )
    _, result = filter_reads_by_summary(fastq, sequencing_summary=None, params=params)

    # Only the 1735-bp read passes.
    assert result.n_passed == 1
    assert result.n_failed_length == 1


def test_filter_target_length_none_uses_fallback(tmp_path: Path) -> None:
    """When target_length is None, length_min/max are used as fallback."""
    fastq = tmp_path / "reads.fastq"
    seq_ok = _make_seq(1000)
    seq_short = _make_seq(300)

    _make_fastq(fastq, [("ok", seq_ok, 12), ("short", seq_short, 12)])

    params = QualityFilterParams(
        min_qscore=8.0,
        length_min=800,
        length_max=3000,
        target_length=None,
    )
    _, result = filter_reads_by_summary(fastq, sequencing_summary=None, params=params)

    assert result.n_passed == 1
    assert result.n_failed_length == 1
