"""A3 — Per-read quality filter + amplicon length auto-detection.

Filters FASTQ reads by:
1. Mean Q-score (from sequencing_summary if available; else inferred from FASTQ
   quality string via Phred-33 decoding).
2. Read length — either a dynamic window (target_length ± length_tolerance_bp)
   or a fixed [length_min, length_max] range (fallback).
3. MinKNOW barcode_score (sequencing_summary only).

When ``sequencing_summary`` is provided, metadata is joined to reads by
``read_id``. When it is ``None``, Q-score is inferred from the FASTQ quality
string; barcode_score filtering is skipped (set ``min_barcode_score=0``).

Q-score defaults
----------------
- ``min_qscore = 8.0`` — ONT MinKNOW default pass threshold (R9.4.1 / R10.4.1).
  Q≥8 excludes the lowest-quality basecalls without being overly aggressive.
- ``length_min = 800`` — target amplicon lower bound (typical SDM amplicon ≥800 bp).
- ``length_max = 3000`` — target amplicon upper bound (SDM products rarely >3 kb).
- ``min_barcode_score = 60.0`` — ONT recommended minimum for reliable barcode
  assignment (values <60 indicate ambiguous classification).

References
----------
- ONT Community: "Understanding Guppy basecall quality scores"
- MinKNOW barcode_score column: 0–100 scale, ≥60 recommended.
"""

from __future__ import annotations

import gzip
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class QualityFilterParams:
    min_qscore: float = 8.0           # mean Q-score per read (Phred scale)
    length_min: int = 800             # fallback min length when target_length is None
    length_max: int = 3000            # fallback max length when target_length is None
    min_barcode_score: float = 60.0   # MinKNOW barcode_score column
    target_length: int | None = None  # modal amplicon length; overrides length_min/max when set
    length_tolerance_bp: int = 30     # ± window around target_length (bp)


@dataclass
class AmpliconLengthEstimate:
    """Result of detect_amplicon_length."""

    detected_length: int   # modal peak in bp (bin centre)
    n_sample_reads: int    # number of reads sampled
    confidence: str        # "high" | "medium" | "low"
    distribution_summary: dict  # min, median, max, peak_count, peak_ratio


@dataclass
class QualityFilterResult:
    n_input: int
    n_passed: int
    n_failed_qscore: int
    n_failed_length: int
    n_failed_barcode: int


# ---------------------------------------------------------------------------
# Phred Q-score helpers
# ---------------------------------------------------------------------------

# Phred+33 encoding (Illumina 1.8+ / ONT Guppy / Dorado).
_PHRED_OFFSET = 33


def _mean_qscore_from_qual(qual_string: str) -> float:
    """Compute mean Q-score from a FASTQ quality string.

    Uses the Phred error probability average:
        mean_error = mean(10 ^ (-Q/10))
        mean_Q = -10 * log10(mean_error)

    This matches ONT / Dorado computation more closely than the simple
    arithmetic mean of Q values.

    Returns 0.0 for empty quality strings.
    """
    if not qual_string:
        return 0.0
    total_prob = sum(
        10 ** (-(ord(ch) - _PHRED_OFFSET) / 10.0)
        for ch in qual_string
    )
    mean_prob = total_prob / len(qual_string)
    if mean_prob <= 0:
        return float("inf")
    return -10.0 * math.log10(mean_prob)


# ---------------------------------------------------------------------------
# Amplicon length auto-detection
# ---------------------------------------------------------------------------


def _iter_fastq_lengths(path: Path) -> Iterator[int]:
    """Yield sequence lengths from a FASTQ (or .fastq.gz) file."""
    opener = (
        gzip.open(path, "rt", encoding="utf-8")
        if path.suffix.lower() == ".gz"
        else open(path, "r", encoding="utf-8")  # noqa: WPS515
    )
    with opener as fh:
        while True:
            header = fh.readline()
            if not header:
                break
            seq = fh.readline().rstrip("\r\n")
            fh.readline()  # '+'
            fh.readline()  # quality
            if seq:
                yield len(seq)


def detect_amplicon_length(
    fastq_dir: Path,
    sample_size: int = 5000,
    bin_size_bp: int = 10,
) -> AmpliconLengthEstimate | None:
    """Histogram fastq read lengths and find the modal peak.

    Strategy
    --------
    1. Iterate .fastq / .fastq.gz files under fastq_dir (sorted order, first file
       first) and collect up to ``sample_size`` read lengths — stops as soon as
       the cap is reached to avoid scanning the full 7+ GB run folder.
    2. Bin lengths in ``bin_size_bp`` chunks; each bin's label is its lower bound.
    3. Pick the bin with the highest count; modal length = bin centre
       (lower_bound + bin_size_bp // 2).
    4. Confidence based on peak_ratio (peak_count / total):
       - ≥ 0.30 → "high"
       - ≥ 0.15 → "medium"
       - else   → "low"
    5. Return None if fewer than 100 reads were collected or peak_ratio < 0.05
       (distribution too flat to be useful).

    Parameters
    ----------
    fastq_dir:
        Directory containing *.fastq or *.fastq.gz files.
    sample_size:
        Maximum number of reads to sample (speed cap).
    bin_size_bp:
        Histogram bin width in base pairs.

    Returns
    -------
    AmpliconLengthEstimate or None.
    """
    if not fastq_dir.is_dir():
        return None

    fastq_files = sorted(
        list(fastq_dir.glob("*.fastq")) + list(fastq_dir.glob("*.fastq.gz"))
    )
    if not fastq_files:
        return None

    lengths: list[int] = []
    for fq_path in fastq_files:
        for length in _iter_fastq_lengths(fq_path):
            lengths.append(length)
            if len(lengths) >= sample_size:
                break
        if len(lengths) >= sample_size:
            break

    n_reads = len(lengths)
    if n_reads < 100:
        return None

    # Build histogram.
    bins: dict[int, int] = {}
    for ln in lengths:
        bin_key = (ln // bin_size_bp) * bin_size_bp  # lower bound of bin
        bins[bin_key] = bins.get(bin_key, 0) + 1

    peak_bin = max(bins, key=lambda k: bins[k])
    peak_count = bins[peak_bin]
    peak_ratio = peak_count / n_reads

    if peak_ratio < 0.05:
        return None

    modal_length = peak_bin + bin_size_bp // 2

    if peak_ratio >= 0.30:
        confidence = "high"
    elif peak_ratio >= 0.15:
        confidence = "medium"
    else:
        confidence = "low"

    median_length = int(statistics.median(lengths))

    return AmpliconLengthEstimate(
        detected_length=modal_length,
        n_sample_reads=n_reads,
        confidence=confidence,
        distribution_summary={
            "min": min(lengths),
            "median": median_length,
            "max": max(lengths),
            "peak_count": peak_count,
            "peak_ratio": round(peak_ratio, 4),
        },
    )


# ---------------------------------------------------------------------------
# sequencing_summary parser
# ---------------------------------------------------------------------------


def _parse_sequencing_summary(
    summary_path: Path,
) -> dict[str, dict[str, str | float]]:
    """Parse a MinKNOW sequencing_summary*.txt into a dict keyed by read_id.

    Follows the pattern in ``run_meta.py``: reads key=value TSV lines,
    absorbs OSError silently, and handles missing columns gracefully.

    Extracted columns: ``read_id``, ``mean_qscore_template``,
    ``sequence_length_template``, ``barcode_score``.

    Returns
    -------
    ``{read_id: {"qscore": float, "length": int, "barcode_score": float}}``
    """
    result: dict[str, dict[str, str | float]] = {}
    try:
        opener = (
            gzip.open(summary_path, "rt", encoding="utf-8", errors="replace")
            if summary_path.suffix.lower() == ".gz"
            else open(summary_path, "r", encoding="utf-8", errors="replace")  # noqa: WPS515
        )
        with opener as fh:
            header_line = fh.readline().rstrip("\r\n")
            if not header_line:
                return result
            headers = header_line.split("\t")
            col_idx = {name: i for i, name in enumerate(headers)}

            rid_col = col_idx.get("read_id")
            qscore_col = col_idx.get("mean_qscore_template")
            length_col = col_idx.get("sequence_length_template")
            bscore_col = col_idx.get("barcode_score")

            if rid_col is None:
                return result

            for line in fh:
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) <= rid_col:
                    continue
                read_id = parts[rid_col].strip()
                if not read_id:
                    continue

                entry: dict[str, str | float] = {}

                if qscore_col is not None and qscore_col < len(parts):
                    try:
                        entry["qscore"] = float(parts[qscore_col])
                    except ValueError:
                        pass

                if length_col is not None and length_col < len(parts):
                    try:
                        entry["length"] = int(parts[length_col])
                    except ValueError:
                        pass

                if bscore_col is not None and bscore_col < len(parts):
                    try:
                        entry["barcode_score"] = float(parts[bscore_col])
                    except ValueError:
                        pass

                result[read_id] = entry
    except OSError:
        pass
    return result


# ---------------------------------------------------------------------------
# FASTQ reading (shared with demux.py pattern)
# ---------------------------------------------------------------------------


def _open_fastq(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")  # noqa: WPS515


def _iter_fastq_records(
    path: Path,
) -> Iterator[tuple[str, str, str]]:
    """Yield (read_id, sequence, quality) triples from a FASTQ file."""
    with _open_fastq(path) as fh:
        while True:
            header = fh.readline()
            if not header:
                break
            seq = fh.readline().rstrip("\r\n")
            fh.readline()  # '+'
            qual = fh.readline().rstrip("\r\n")
            read_id = header.lstrip("@").split()[0].rstrip("\r\n")
            yield read_id, seq.upper(), qual


# ---------------------------------------------------------------------------
# Length window resolution
# ---------------------------------------------------------------------------

# The ONT read-length spread scales with amplicon length, so a fixed +/-30 bp
# window (~+/-1.7% of a 1.8 kb amplicon) discards genuine full-length reads and
# under-counts per-well depth. The effective window is at least +/- this fraction
# of the target length; length_tolerance_bp remains an explicit floor/override.
_LENGTH_TOLERANCE_FRACTION = 0.10


def _resolve_length_window(params: QualityFilterParams) -> tuple[int, int]:
    """Return (effective_min, effective_max) for length filtering.

    When ``target_length`` is set, the window is ``target_length +/- tol`` where
    ``tol = max(length_tolerance_bp, round(target_length * _LENGTH_TOLERANCE_FRACTION))``.
    The proportional term keeps long amplicons from being over-filtered while the
    absolute ``length_tolerance_bp`` still acts as a floor (and an override when a
    caller sets it larger than the proportional window). Otherwise falls back to
    ``(length_min, length_max)``.
    """
    if params.target_length is not None:
        tol = max(
            params.length_tolerance_bp,
            round(params.target_length * _LENGTH_TOLERANCE_FRACTION),
        )
        lo = max(0, params.target_length - tol)
        hi = params.target_length + tol
        return lo, hi
    return params.length_min, params.length_max


# ---------------------------------------------------------------------------
# Core filter
# ---------------------------------------------------------------------------


def filter_reads_by_summary(
    fastq_path: Path,
    sequencing_summary: Path | None,
    params: QualityFilterParams,
) -> tuple[Path, QualityFilterResult]:
    """Filter a FASTQ file and write passing reads to a temporary FASTA.

    Parameters
    ----------
    fastq_path:
        Input FASTQ (or ``.fastq.gz``) file.
    sequencing_summary:
        Path to a MinKNOW ``sequencing_summary_*.txt`` file. When ``None``,
        Q-score is computed from the FASTQ quality string; barcode_score
        filtering is skipped.
    params:
        Filter thresholds. When ``params.target_length`` is set, the length
        window is ``[target_length - length_tolerance_bp,
        target_length + length_tolerance_bp]``; otherwise ``length_min /
        length_max`` are used.

    Returns
    -------
    ``(filtered_fasta_path, QualityFilterResult)``

    The returned FASTA file is written to the system temp directory with a
    deterministic name ``<stem>_filtered.fasta`` relative to the FASTQ file
    parent. Callers are responsible for cleanup.
    """
    import tempfile

    if not fastq_path.exists():
        raise FileNotFoundError(f"FASTQ file not found: {fastq_path}")

    len_min, len_max = _resolve_length_window(params)

    # Load summary metadata if available.
    summary_meta: dict[str, dict[str, str | float]] = {}
    if sequencing_summary is not None:
        if not sequencing_summary.exists():
            raise FileNotFoundError(
                f"sequencing_summary not found: {sequencing_summary}"
            )
        summary_meta = _parse_sequencing_summary(sequencing_summary)

    # Output file: sibling of FASTQ in a tempdir to avoid modifying input dir.
    stem = fastq_path.stem.replace(".fastq", "")
    tmp_dir = tempfile.mkdtemp(prefix="mame_qfilt_")
    out_path = Path(tmp_dir) / f"{stem}_filtered.fasta"

    n_input = 0
    n_passed = 0
    n_failed_qscore = 0
    n_failed_length = 0
    n_failed_barcode = 0

    with open(out_path, "w", encoding="utf-8") as out_fh:
        for read_id, seq, qual in _iter_fastq_records(fastq_path):
            n_input += 1
            length = len(seq)

            # ── Length filter ────────────────────────────────────────────
            if length < len_min or length > len_max:
                n_failed_length += 1
                continue

            # ── Barcode score filter (summary only) ──────────────────────
            if summary_meta and params.min_barcode_score > 0:
                meta = summary_meta.get(read_id, {})
                bscore = meta.get("barcode_score")
                if bscore is not None and float(bscore) < params.min_barcode_score:
                    n_failed_barcode += 1
                    continue

            # ── Q-score filter ────────────────────────────────────────────
            if summary_meta:
                meta = summary_meta.get(read_id, {})
                qscore_raw = meta.get("qscore")
                if qscore_raw is not None:
                    qscore = float(qscore_raw)
                else:
                    # read_id not in summary — infer from quality string.
                    qscore = _mean_qscore_from_qual(qual)
            else:
                qscore = _mean_qscore_from_qual(qual)

            if qscore < params.min_qscore:
                n_failed_qscore += 1
                continue

            # ── Pass ────────────────────────────────────────────────────
            out_fh.write(f">{read_id}\n{seq}\n")
            n_passed += 1

    result = QualityFilterResult(
        n_input=n_input,
        n_passed=n_passed,
        n_failed_qscore=n_failed_qscore,
        n_failed_length=n_failed_length,
        n_failed_barcode=n_failed_barcode,
    )
    return out_path, result


__all__ = [
    "AmpliconLengthEstimate",
    "QualityFilterParams",
    "QualityFilterResult",
    "detect_amplicon_length",
    "filter_reads_by_summary",
]
