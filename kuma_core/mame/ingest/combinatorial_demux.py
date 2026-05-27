"""Combinatorial barcode demux pipeline for 96-well nanopore amplicon screening.

Algorithm (minimap2 align + 100% coverage filter + R×F combinatorial demux +
per-well majority-vote consensus):
------------------------------------------------------
1. Align all raw FASTQ reads to reference using mappy (map-ont preset).
2. MAPQ >= 25 filter.
3. 100% coverage filter: r_st == 0 and r_en == ref_len (equivalent to
   ``bedtools intersect -f 1.0``).
4. Trim +/- 30 bp flanks from read: ``read[q_st-30 : q_en+30]``.
5. Barcode demux on trimmed sequence:
   - 8 R barcodes + 12 F barcodes loaded from xlsx.
   - Full barcode sequence (including annealing tail) used as search pattern.
   - Substring search (exact match) in both orientations (fwd + RC).
   - Exactly 1 R + 1 F match required; otherwise dropped.
   - Written to ``{R_idx}_{F_idx}.fasta`` (1-indexed).
6. Per-well consensus: majority-vote per position (N if depth < min_depth).

Assumptions:
- Reference FASTA has exactly one sequence record.
- Barcodes xlsx rows: isps_f_1..12 then isps_r_1..8.
- Annealing tails: F='cacaggaggttaaacc', R='tgcgttgcgctctag'.
- mappy available on Linux (pyproject.toml restricts to Linux).
"""

from __future__ import annotations

import gzip
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from kuma_core.mame.ingest.align import align_reads, _get_reference_length, Alignment
from kuma_core.mame.ingest.consensus import call_consensus
from kuma_core.mame.ingest.well_consensus import _read_reference_seq

log = logging.getLogger(__name__)

_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"

_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")


def _reverse_complement(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class DemuxStats:
    """Summary counters from a single run_combinatorial_demux call."""

    total_reads: int = 0
    passed_mapq: int = 0
    passed_coverage: int = 0
    assigned_reads: int = 0
    wells_with_reads: int = 0
    wells_with_min_reads: int = 0


@dataclass
class DemuxResult:
    """Return value of run_combinatorial_demux."""

    stats: DemuxStats
    per_well_reads: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    per_well_consensus: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Barcode utilities
# ---------------------------------------------------------------------------


def _extract_barcode_prefix(seq: str, tail: str) -> str:
    """Return the prefix before the annealing tail (fallback: first 11 bp).

    .. deprecated::
        No longer called by load_barcodes. Full sequences are used for matching.
        Kept for backward compatibility / external callers.
    """
    idx = seq.lower().find(tail.lower())
    if idx >= 0:
        return seq[:idx]
    return seq[:11]


def load_barcodes(barcodes_xlsx: Path) -> tuple[list[str], list[str]]:
    """Load F and R barcode prefix sequences from xlsx.

    Returns
    -------
    (f_barcodes, r_barcodes)
        f_barcodes: 12-element list, uppercase full sequences (index 0 = F1).
        r_barcodes: 8-element list, uppercase full sequences (index 0 = R1).
    """
    try:
        import openpyxl  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "openpyxl is required for barcode loading. "
            "Install with: pip install openpyxl"
        ) from exc

    wb = openpyxl.load_workbook(barcodes_xlsx, read_only=True)
    ws = wb.active
    if ws is None:
        raise ValueError("Empty workbook: no active sheet in " + str(barcodes_xlsx))

    f_entries: list[tuple[int, str]] = []
    r_entries: list[tuple[int, str]] = []

    for row in ws.iter_rows(values_only=True):
        if not row or row[0] is None:
            continue  # skip empty rows in xlsx (not in exception block)
        name = str(row[0]).strip().lower()
        seq_val = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if not seq_val:
            continue  # skip rows with empty sequence (not in exception block)

        if name.startswith("isps_f_"):
            try:
                idx = int(name.split("_")[-1])
            except ValueError:
                log.warning("Skipping F barcode row with non-integer index: %s", name)
                continue  # skip malformed row names (after logging)
            f_entries.append((idx, seq_val.upper()))

        elif name.startswith("isps_r_"):
            try:
                idx = int(name.split("_")[-1])
            except ValueError:
                log.warning("Skipping R barcode row with non-integer index: %s", name)
                continue  # skip malformed row names (after logging)
            r_entries.append((idx, seq_val.upper()))

    wb.close()

    f_entries.sort(key=lambda x: x[0])
    r_entries.sort(key=lambda x: x[0])

    f_barcodes = [s for _, s in f_entries]
    r_barcodes = [s for _, s in r_entries]

    if len(f_barcodes) != 12:
        log.warning("Expected 12 F barcodes, got %d", len(f_barcodes))
    if len(r_barcodes) != 8:
        log.warning("Expected 8 R barcodes, got %d", len(r_barcodes))

    return f_barcodes, r_barcodes


# ---------------------------------------------------------------------------
# FASTQ parsing
# ---------------------------------------------------------------------------


def _iter_fastq(paths: list[Path]) -> Iterator[tuple[str, str]]:
    """Yield (read_id, sequence) from one or more FASTQ(.gz) files."""
    for path in paths:
        opener = gzip.open if str(path).endswith(".gz") else open
        with opener(path, "rt") as fh:
            while True:
                header = fh.readline()
                if not header:
                    break
                seq = fh.readline().rstrip("\n")
                fh.readline()   # '+'
                fh.readline()   # quality
                if seq:
                    read_id = header[1:].split()[0].rstrip("\n")
                    yield read_id, seq


# ---------------------------------------------------------------------------
# Barcode demux (single read)
# ---------------------------------------------------------------------------


def _demux_read(
    trimmed_seq: str,
    f_barcodes: list[str],
    r_barcodes: list[str],
) -> tuple[int, int] | None:
    """Return (r_idx_1based, f_idx_1based) or None if demux fails.

    Exact substring match in fwd + RC orientation.
    Exactly 1 R + 1 F required; 0 or 2+ in either axis -> None.
    """
    seq_upper = trimmed_seq.upper()
    seq_rc = _reverse_complement(seq_upper)

    matched_r = [
        i + 1
        for i, bc in enumerate(r_barcodes)
        if bc in seq_upper or bc in seq_rc
    ]
    matched_f = [
        i + 1
        for i, bc in enumerate(f_barcodes)
        if bc in seq_upper or bc in seq_rc
    ]

    if len(matched_r) == 1 and len(matched_f) == 1:
        return matched_r[0], matched_f[0]
    return None


# ---------------------------------------------------------------------------
# Helpers for per-alignment processing
# ---------------------------------------------------------------------------


def _trim_read(aln: Alignment, original_seq: str, flank_bp: int) -> str:
    """Return the aligned region of a read with +/-flank_bp flanks."""
    start = max(0, aln.q_st - flank_bp)
    end = min(len(original_seq), aln.q_en + flank_bp)
    return original_seq[start:end]


def _assign_alignment(
    aln: Alignment,
    read_seq_map: dict[str, str],
    f_barcodes: list[str],
    r_barcodes: list[str],
    trim_flank_bp: int,
) -> tuple[tuple[int, int], str] | None:
    """Trim + demux one alignment. Returns ((r_idx, f_idx), trimmed) or None."""
    seq = read_seq_map.get(aln.read_id, "")
    if not seq:
        return None
    trimmed = _trim_read(aln, seq, trim_flank_bp)
    result = _demux_read(trimmed, f_barcodes, r_barcodes)
    if result is None:
        return None
    return result, trimmed


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


def run_combinatorial_demux(
    raw_fastq_paths: list[Path],
    reference_fasta: Path,
    barcodes_xlsx: Path,
    output_dir: Path,
    mapq_threshold: int = 25,
    coverage_fraction: float = 1.0,
    trim_flank_bp: int = 30,
    min_depth: int = 3,
) -> DemuxResult:
    """MAPQ-filtered alignment-based per-well demux for nanopore amplicon screening.

    Aligns pooled reads to a single reference, applies 100% reference coverage
    filter, assigns each read to an R×F well by exact barcode substring match,
    and calls majority-vote consensus per well.

    Parameters
    ----------
    raw_fastq_paths:
        FASTQ(.gz) input files (all reads pooled before alignment).
    reference_fasta:
        Single-record DNA FASTA used as alignment reference.
    barcodes_xlsx:
        xlsx with isps_f_1..12 and isps_r_1..8 barcode sequences.
    output_dir:
        Directory for output files.
        Per-well FASTA: ``{output_dir}/{R_idx}_{F_idx}.fasta``
        Consensus FASTA: ``{output_dir}/consensus/{R_idx}_{F_idx}.fasta``
    mapq_threshold:
        Minimum MAPQ (default 25).
    coverage_fraction:
        1.0 for strict 100% reference coverage filter (default).
    trim_flank_bp:
        Bases to include on each side of aligned region (default 30).
    min_depth:
        Minimum read depth per position for consensus call (default 3).

    Returns
    -------
    DemuxResult with stats, per_well_reads, per_well_consensus.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "consensus").mkdir(exist_ok=True)

    stats = DemuxStats()

    f_barcodes, r_barcodes = load_barcodes(barcodes_xlsx)
    log.info("Loaded %d F barcodes, %d R barcodes", len(f_barcodes), len(r_barcodes))

    ref_len = _get_reference_length(reference_fasta)
    log.info("Reference length: %d bp", ref_len)

    all_reads: list[tuple[str, str]] = list(_iter_fastq(raw_fastq_paths))
    stats.total_reads = len(all_reads)
    log.info("Total reads: %d", stats.total_reads)

    alignments: list[Alignment] = align_reads(
        reads=all_reads,
        reference_fasta=reference_fasta,
        preset="map-ont",
        min_mapq=mapq_threshold,
        require_full_span=(coverage_fraction >= 1.0),
    )
    stats.passed_coverage = len(alignments)
    stats.passed_mapq = stats.passed_coverage
    log.info("Passed MAPQ+coverage filter: %d / %d", stats.passed_coverage, stats.total_reads)

    read_seq_map: dict[str, str] = {rid: seq for rid, seq in all_reads}

    per_well: dict[tuple[int, int], list[tuple[str, str]]] = defaultdict(list)
    for aln in alignments:
        assignment = _assign_alignment(aln, read_seq_map, f_barcodes, r_barcodes, trim_flank_bp)
        if assignment is not None:
            (r_idx, f_idx), trimmed = assignment
            per_well[(r_idx, f_idx)].append((aln.read_id, trimmed))
            stats.assigned_reads += 1

    log.info("Barcode-assigned reads: %d", stats.assigned_reads)

    # Write per-well FASTA files
    per_well_reads: dict[str, list[tuple[str, str]]] = {}
    for (r_idx, f_idx), reads in per_well.items():
        well_name = f"{r_idx}_{f_idx}"
        per_well_reads[well_name] = reads
        fasta_path = output_dir / f"{well_name}.fasta"
        with fasta_path.open("w") as fh:
            for read_id, trimmed in reads:
                fh.write(f">{read_id}\n{trimmed}\n")

    stats.wells_with_reads = sum(1 for v in per_well.values() if len(v) >= 1)
    stats.wells_with_min_reads = sum(1 for v in per_well.values() if len(v) >= min_depth)
    log.info(
        "Wells with >=1 read: %d/96, wells with >=%d reads: %d/96",
        stats.wells_with_reads,
        min_depth,
        stats.wells_with_min_reads,
    )

    # Per-well consensus
    ref_seq = _read_reference_seq(reference_fasta)
    per_well_consensus: dict[str, str] = {}

    for well_name, reads in per_well_reads.items():
        consensus_seq, depth = _compute_well_consensus(
            well_name, reads, reference_fasta, ref_seq, ref_len, min_depth
        )
        per_well_consensus[well_name] = consensus_seq
        with (output_dir / "consensus" / f"{well_name}.fasta").open("w") as fh:
            fh.write(f">{well_name} depth={depth}\n{consensus_seq}\n")

    return DemuxResult(
        stats=stats,
        per_well_reads=per_well_reads,
        per_well_consensus=per_well_consensus,
    )


def _compute_well_consensus(
    well_name: str,
    reads: list[tuple[str, str]],
    reference_fasta: Path,
    ref_seq: str,
    ref_len: int,
    min_depth: int,
) -> tuple[str, int]:
    """Align trimmed reads and call majority-vote consensus. Returns (seq, depth)."""
    if not reads:
        return "N" * ref_len, 0

    well_alignments = align_reads(
        reads=reads,
        reference_fasta=reference_fasta,
        preset="map-ont",
        min_mapq=0,           # trimmed reads; already filtered upstream
        require_full_span=False,
    )

    if not well_alignments:
        log.debug("Well %s: 0 alignments from %d trimmed reads", well_name, len(reads))
        return "N" * ref_len, 0

    consensus_seq = call_consensus(well_alignments, ref_seq, min_depth=min_depth)
    return consensus_seq, len(well_alignments)


__all__ = [
    "DemuxResult",
    "DemuxStats",
    "load_barcodes",
    "run_combinatorial_demux",
]
