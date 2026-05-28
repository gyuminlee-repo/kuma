"""Combinatorial barcode demux pipeline for 96-well nanopore amplicon screening.

Algorithm (minimap2 align + alignment-anchored fuzzy barcode matching):
----------------------------------------------------------------------
1. Align all raw FASTQ reads to reference using mappy (map-ont preset).
2. MAPQ >= 25 filter.
3. Coverage filter: each alignment must cover >= coverage_fraction of reference
   (default 0.98; replaces strict 100% filter to recover reads with 1-2 bp clip).
4. Chimera/concatemer splitting: ALL passing hits per read are evaluated.
   A single raw read may yield assignments to multiple wells if it contains
   two distinct amplicon copies (chimeric or concatemer read).
   Duplicate (read_id, well) pairs within the same read are deduplicated.
5. For each passing hit, extract alignment-anchored slice +/-trim_flank_bp,
   then run alignment-anchored fuzzy barcode matching on that slice.
   Strand normalisation is done inside _demux_read_anchored.
6. Barcode demux using edlib HW (infix) edit-distance search:
   Library structure (sense strand of read):
     5-[F_barcode + F_anneal]-[insert]-[RC(R_anneal) + RC(R_barcode)]-3
   - F-barcode window (5 end): [max(0, q_st - window_bp - max_f_len), q_st + window_bp]
   - R-barcode window (3 end): [max(0, q_en - window_bp), min(L, q_en + window_bp + max_r_len)]
     R barcode prefixes are reverse-complemented before searching (RC form in read).
   - For each barcode, best infix edit distance is computed; only accept if
     edit_distance <= int(len(bc) * edit_dist_ratio)  (floor, conservative).
   - Ambiguity: if best == second-best edit distance -> drop (ambiguous).
   - Exactly 1 R + 1 F unambiguous match required; otherwise dropped.
7. Per-well consensus: majority-vote per position (N if depth < min_depth).

Barcode loading:
- Annealing tails stripped; only prefix portion used for fuzzy matching.
- F tail: 'cacaggaggttaaacc' (16 bp), R tail: 'tgcgttgcgctctag' (15 bp).
- Fallback prefix length if tail absent: 11 bp (F) / 10 bp (R).

Assumptions:
- Reference FASTA has exactly one sequence record.
- Barcodes xlsx rows: isps_f_1..12 then isps_r_1..8.
- mappy and edlib available (pyproject.toml restricts mappy to Linux).
- Edit-distance threshold uses floor(len * ratio), not ceil, to stay
  conservative on 10 bp barcodes (floor gives max 2 edits at ratio=0.20).
"""

from __future__ import annotations

import gzip
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from kuma_core.mame.ingest.align import (
    align_reads,
    align_reads_multi,
    _get_reference_length,
    Alignment,
)
from kuma_core.mame.ingest.consensus import call_consensus
from kuma_core.mame.ingest.well_consensus import _read_reference_seq

log = logging.getLogger(__name__)

_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"

_F_FALLBACK_LEN = 11  # prefix length if F tail absent
_R_FALLBACK_LEN = 10  # prefix length if R tail absent

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
    ambiguous_dropped: int = 0
    chimera_splits: int = 0   # extra well assignments from multi-hit reads
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
    """Return the prefix before the annealing tail.

    Fallback: first 11 bp if tail absent.  Public for external callers and
    backward compatibility.
    """
    idx = seq.lower().find(tail.lower())
    if idx >= 0:
        return seq[:idx]
    return seq[:11]


def load_barcode_prefixes(
    barcodes_xlsx: Path,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Load F and R barcode *prefix* sequences from xlsx (annealing tail stripped).

    Returns
    -------
    (r_barcodes, f_barcodes)
        r_barcodes: 8-element list of (name, prefix_seq) tuples (index 0 = R1).
        f_barcodes: 12-element list of (name, prefix_seq) tuples (index 0 = F1).

    The prefix is the barcode-unique region only (tail excluded).  Prefix lengths
    are typically 10 bp (R and most F) or 11 bp (F1-F3 in the standard plate).
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

    f_entries: list[tuple[int, str, str]] = []  # (idx, name, prefix)
    r_entries: list[tuple[int, str, str]] = []

    for row in ws.iter_rows(values_only=True):
        if not row or row[0] is None:
            continue
        name = str(row[0]).strip().lower()
        seq_val = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if not seq_val:
            continue

        if name.startswith("isps_f_"):
            try:
                idx = int(name.split("_")[-1])
            except ValueError:
                log.warning("Skipping F barcode row with non-integer index: %s", name)
                continue
            prefix = _extract_f_prefix(seq_val)
            f_entries.append((idx, name, prefix.upper()))

        elif name.startswith("isps_r_"):
            try:
                idx = int(name.split("_")[-1])
            except ValueError:
                log.warning("Skipping R barcode row with non-integer index: %s", name)
                continue
            prefix = _extract_r_prefix(seq_val)
            r_entries.append((idx, name, prefix.upper()))

    wb.close()

    f_entries.sort(key=lambda x: x[0])
    r_entries.sort(key=lambda x: x[0])

    f_barcodes = [(name, prefix) for _, name, prefix in f_entries]
    r_barcodes = [(name, prefix) for _, name, prefix in r_entries]

    if len(f_barcodes) != 12:
        log.warning("Expected 12 F barcodes, got %d", len(f_barcodes))
    if len(r_barcodes) != 8:
        log.warning("Expected 8 R barcodes, got %d", len(r_barcodes))

    return r_barcodes, f_barcodes


def _extract_f_prefix(seq: str) -> str:
    """Strip F annealing tail; fallback to first _F_FALLBACK_LEN bases."""
    idx = seq.lower().find(_F_TAIL.lower())
    return seq[:idx] if idx >= 0 else seq[:_F_FALLBACK_LEN]


def _extract_r_prefix(seq: str) -> str:
    """Strip R annealing tail; fallback to first _R_FALLBACK_LEN bases."""
    idx = seq.lower().find(_R_TAIL.lower())
    return seq[:idx] if idx >= 0 else seq[:_R_FALLBACK_LEN]


def load_barcodes(barcodes_xlsx: Path) -> tuple[list[str], list[str]]:
    """Load F and R barcode full sequences from xlsx (legacy, full seq).

    Returns
    -------
    (f_barcodes, r_barcodes)
        f_barcodes: 12-element list, uppercase full sequences (index 0 = F1).
        r_barcodes: 8-element list, uppercase full sequences (index 0 = R1).

    .. note::
        This function is kept for backward compatibility.  The main pipeline
        now uses :func:`load_barcode_prefixes` which strips annealing tails.
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
            continue
        name = str(row[0]).strip().lower()
        seq_val = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if not seq_val:
            continue

        if name.startswith("isps_f_"):
            try:
                idx = int(name.split("_")[-1])
            except ValueError:
                log.warning("Skipping F barcode row with non-integer index: %s", name)
                continue
            f_entries.append((idx, seq_val.upper()))

        elif name.startswith("isps_r_"):
            try:
                idx = int(name.split("_")[-1])
            except ValueError:
                log.warning("Skipping R barcode row with non-integer index: %s", name)
                continue
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
# Alignment-anchored fuzzy barcode matching
# ---------------------------------------------------------------------------


def _best_infix_match(
    query: str,
    window: str,
    max_edit: int,
) -> int | None:
    """Return the best infix edit distance of *query* inside *window*.

    Uses edlib HW mode (infix / semi-global on query).  Returns the edit
    distance if <= max_edit, otherwise None.
    """
    try:
        import edlib  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "edlib is required for fuzzy barcode matching. "
            "Install with: pip install edlib"
        ) from exc

    if not window or not query:
        return None

    result = edlib.align(query, window, mode="HW", task="distance", k=max_edit)
    dist = result["editDistance"]
    if dist < 0 or dist > max_edit:
        return None
    return dist


def _find_best_barcode(
    barcodes: list[tuple[str, str]],
    window: str,
    edit_dist_ratio: float,
) -> tuple[int, int] | None:
    """Find the unambiguous best-matching barcode in *window*.

    Parameters
    ----------
    barcodes:
        List of (name, prefix_seq) tuples (1-indexed position = list index + 1).
    window:
        Sequence window extracted from the read.
    edit_dist_ratio:
        Max allowed edit distance = int(len(bc) * edit_dist_ratio).

    Returns
    -------
    (1-based index, edit_distance) if exactly one barcode is unambiguously
    best, None otherwise (no match or ambiguous).
    """
    best_dist: int = 10**6
    best_idx: int = -1
    second_best_dist: int = 10**6

    for i, (_, prefix) in enumerate(barcodes):
        max_edit = int(len(prefix) * edit_dist_ratio)
        dist = _best_infix_match(prefix, window, max_edit)
        if dist is None:
            continue
        if dist < best_dist:
            second_best_dist = best_dist
            best_dist = dist
            best_idx = i
        elif dist < second_best_dist:
            second_best_dist = dist

    if best_idx < 0:
        return None  # no match within threshold

    # Ambiguity guard: if best == second_best, result is ambiguous -> drop
    if best_dist == second_best_dist:
        return None

    return best_idx + 1, best_dist  # 1-based index


def _demux_read_anchored(
    read_seq: str,
    q_st: int,
    q_en: int,
    strand: int,
    r_barcodes: list[tuple[str, str]],
    f_barcodes: list[tuple[str, str]],
    window_bp: int = 30,
    edit_dist_ratio: float = 0.20,
) -> tuple[int, int] | None:
    """Demux one read using alignment anchors and edlib fuzzy matching.

    Parameters
    ----------
    read_seq:
        Full read sequence as returned by the FASTQ parser (not RC'd).
    q_st, q_en:
        Alignment start/end on the read (from mappy, 0-based half-open).
    strand:
        +1 or -1 from mappy.
    r_barcodes, f_barcodes:
        (name, prefix) tuples as returned by load_barcode_prefixes.
    window_bp:
        Window radius around anchor points (default 30 bp).
    edit_dist_ratio:
        Max allowed edit distance fraction of barcode length (default 0.20).
        Threshold = floor(len(bc) * ratio).  At ratio=0.20: 10 bp -> 2 edits,
        11 bp -> 2 edits, 15 bp -> 3 edits.

    Returns
    -------
    (r_idx_1based, f_idx_1based) or None if demux fails.

    Notes
    -----
    Strand normalisation:
      strand +1: use read_seq as-is.
      strand -1: work on RC(read_seq) and remap anchor coords via
                 norm_q_st = L - q_en, norm_q_en = L - q_st.
    Biological window layout (after normalisation to +1 orientation):
      F barcode is 5' of the amplicon -> search before norm_q_st.
      R barcode is 3' of the amplicon in RC form -> search RC(r_prefix) after norm_q_en.

    Library structure on sense strand of read (strand +1):
      5'-[F_barcode + F_anneal]-[insert]-[RC(R_anneal) + RC(R_barcode)]-3'
    So the 5' window contains F_barcode (as-is) and the 3' window contains
    RC(R_barcode). R barcode prefixes are reverse-complemented before searching.
    """
    seq = read_seq.upper()
    L = len(seq)

    if strand == -1:
        # Normalise to forward orientation so window math is uniform.
        seq = _reverse_complement(seq)
        norm_q_st = L - q_en
        norm_q_en = L - q_st
    else:
        norm_q_st = q_st
        norm_q_en = q_en

    max_r_len = max((len(p) for _, p in r_barcodes), default=10)
    max_f_len = max((len(p) for _, p in f_barcodes), default=11)

    # F barcode: 5' of alignment start (F_barcode + F_anneal tail)
    f_win_start = max(0, norm_q_st - window_bp - max_f_len)
    f_win_end = min(L, norm_q_st + window_bp)
    f_window = seq[f_win_start:f_win_end]

    # R barcode: 3' of alignment end, appears as RC(R_barcode) in the read
    r_win_start = max(0, norm_q_en - window_bp)
    r_win_end = min(L, norm_q_en + window_bp + max_r_len)
    r_window = seq[r_win_start:r_win_end]

    # RC the R barcode prefixes: on the read the R barcode is reverse-complemented
    r_barcodes_rc = [(name, _reverse_complement(prefix)) for name, prefix in r_barcodes]

    f_result = _find_best_barcode(f_barcodes, f_window, edit_dist_ratio)
    r_result = _find_best_barcode(r_barcodes_rc, r_window, edit_dist_ratio)

    if r_result is None or f_result is None:
        return None

    r_idx, _ = r_result
    f_idx, _ = f_result
    return r_idx, f_idx


def _demux_read(
    trimmed_seq: str,
    f_barcodes: list[str],
    r_barcodes: list[str],
) -> tuple[int, int] | None:
    """Exact substring demux (legacy, no alignment context).

    Kept for backward compatibility with existing tests.  The main pipeline
    uses :func:`_demux_read_anchored`.

    Returns (r_idx_1based, f_idx_1based) or None.
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
# Core pipeline
# ---------------------------------------------------------------------------


def run_combinatorial_demux(
    raw_fastq_paths: list[Path],
    reference_fasta: Path,
    barcodes_xlsx: Path,
    output_dir: Path,
    mapq_threshold: int = 25,
    coverage_fraction: float = 0.98,
    trim_flank_bp: int = 30,
    min_depth: int = 3,
    window_bp: int = 30,
    edit_dist_ratio: float = 0.25,
    chimera_split: bool = True,
) -> DemuxResult:
    """MAPQ-filtered alignment-anchored fuzzy per-well demux with chimera splitting.

    Aligns pooled reads to a single reference, applies coverage filter,
    assigns each read (or each hit within a chimeric/concatemer read) to an
    R x F well by alignment-anchored edlib fuzzy barcode matching, and calls
    majority-vote consensus per well.

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
        Minimum MAPQ per alignment hit (default 25).
    coverage_fraction:
        Minimum fraction of reference covered by each hit (default 0.98).
        Replaces the former strict 100%-span filter; recovers reads with
        1-2 bp end-clip while keeping spurious partial alignments out.
    trim_flank_bp:
        Bases to include on each side of each hit's aligned region when
        extracting the slice written to FASTA (default 30).
    min_depth:
        Minimum read depth per position for consensus call (default 3).
    window_bp:
        Search window radius around alignment anchors for barcode matching
        (default 30 bp).
    edit_dist_ratio:
        Max allowed edit distance fraction of barcode length (default 0.25).
        Threshold = floor(len(bc) * ratio).
    chimera_split:
        When True (default), iterate ALL passing alignment hits per read and
        attempt demux for each hit independently.  A chimeric read carrying
        two different amplicon copies may contribute to two wells.
        When False, only the first passing hit is used (legacy behaviour).

    Returns
    -------
    DemuxResult with stats, per_well_reads, per_well_consensus.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "consensus").mkdir(exist_ok=True)

    stats = DemuxStats()

    r_barcodes, f_barcodes = load_barcode_prefixes(barcodes_xlsx)
    log.info(
        "Loaded %d R barcodes, %d F barcodes (prefix-only, annealing tail stripped)",
        len(r_barcodes),
        len(f_barcodes),
    )

    ref_len = _get_reference_length(reference_fasta)
    log.info("Reference length: %d bp", ref_len)

    all_reads: list[tuple[str, str]] = list(_iter_fastq(raw_fastq_paths))
    stats.total_reads = len(all_reads)
    log.info("Total reads: %d", stats.total_reads)

    per_well: dict[tuple[int, int], list[tuple[str, str]]] = defaultdict(list)

    if chimera_split:
        # --- multi-hit path: chimera / concatemer splitting ----------------
        multi_results = align_reads_multi(
            reads=all_reads,
            reference_fasta=reference_fasta,
            preset="map-ont",
            min_mapq=mapq_threshold,
            coverage_fraction=coverage_fraction,
        )

        reads_with_hits = len(multi_results)
        total_hit_count = sum(len(hits) for _, _, hits in multi_results)
        stats.passed_coverage = reads_with_hits
        stats.passed_mapq = reads_with_hits
        log.info(
            "Passed MAPQ+coverage filter: %d reads / %d total hits",
            reads_with_hits,
            total_hit_count,
        )

        for read_id, read_seq, hits in multi_results:
            # Track which wells this read has already been assigned to
            # to prevent double-counting the same read in the same well.
            assigned_wells_this_read: set[tuple[int, int]] = set()
            is_first_hit = True

            for hit in hits:
                # Extract aligned slice + flanks from the raw read.
                # Coordinates are in read (query) space; no strand flip here.
                slice_start = max(0, hit.q_st - trim_flank_bp)
                slice_end = min(len(read_seq), hit.q_en + trim_flank_bp)
                slice_seq = read_seq[slice_start:slice_end]

                # Alignment anchors within the slice coordinate space.
                # q_st/q_en are absolute positions in read_seq.
                q_st_in_slice = hit.q_st - slice_start
                q_en_in_slice = hit.q_en - slice_start

                result = _demux_read_anchored(
                    read_seq=slice_seq,
                    q_st=q_st_in_slice,
                    q_en=q_en_in_slice,
                    strand=hit.strand,
                    r_barcodes=r_barcodes,
                    f_barcodes=f_barcodes,
                    window_bp=window_bp,
                    edit_dist_ratio=edit_dist_ratio,
                )
                if result is None:
                    stats.ambiguous_dropped += 1
                    is_first_hit = False
                    continue

                r_idx, f_idx = result
                well = (r_idx, f_idx)

                if well in assigned_wells_this_read:
                    # Already assigned to this well from an earlier hit: skip.
                    is_first_hit = False
                    continue

                assigned_wells_this_read.add(well)
                per_well[well].append((read_id, slice_seq))

                if is_first_hit:
                    stats.assigned_reads += 1
                else:
                    stats.chimera_splits += 1
                is_first_hit = False

    else:
        # --- legacy single-hit path ----------------------------------------
        alignments = align_reads(
            reads=all_reads,
            reference_fasta=reference_fasta,
            preset="map-ont",
            min_mapq=mapq_threshold,
            require_full_span=(coverage_fraction >= 1.0),
        )
        stats.passed_coverage = len(alignments)
        stats.passed_mapq = len(alignments)
        log.info(
            "Passed MAPQ+coverage filter: %d / %d",
            stats.passed_coverage,
            stats.total_reads,
        )

        for aln in alignments:
            trimmed = _trim_read(aln, aln.read_seq, trim_flank_bp)
            result = _demux_read_anchored(
                read_seq=aln.read_seq,
                q_st=aln.q_st,
                q_en=aln.q_en,
                strand=aln.strand,
                r_barcodes=r_barcodes,
                f_barcodes=f_barcodes,
                window_bp=window_bp,
                edit_dist_ratio=edit_dist_ratio,
            )
            if result is None:
                stats.ambiguous_dropped += 1
                continue
            r_idx, f_idx = result
            per_well[(r_idx, f_idx)].append((aln.read_id, trimmed))
            stats.assigned_reads += 1

    log.info(
        "Barcode-assigned reads: %d  chimera splits: %d  (ambiguous/no-match dropped: %d)",
        stats.assigned_reads,
        stats.chimera_splits,
        stats.ambiguous_dropped,
    )

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
    stats.wells_with_min_reads = sum(
        1 for v in per_well.values() if len(v) >= min_depth
    )
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


# ---------------------------------------------------------------------------
# Helpers for per-alignment processing
# ---------------------------------------------------------------------------


def _trim_read(aln: Alignment, original_seq: str, flank_bp: int) -> str:
    """Return the aligned region of a read with +/-flank_bp flanks."""
    start = max(0, aln.q_st - flank_bp)
    end = min(len(original_seq), aln.q_en + flank_bp)
    return original_seq[start:end]


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
        log.debug(
            "Well %s: 0 alignments from %d trimmed reads", well_name, len(reads)
        )
        return "N" * ref_len, 0

    consensus_seq = call_consensus(well_alignments, ref_seq, min_depth=min_depth)
    return consensus_seq, len(well_alignments)


__all__ = [
    # Public types
    "DemuxResult",
    "DemuxStats",
    # Public entry points
    "load_barcodes",
    "load_barcode_prefixes",
    "run_combinatorial_demux",
    # Semi-private helpers exported for tests and diagnostic scripts
    "_extract_barcode_prefix",
    "_extract_f_prefix",
    "_extract_r_prefix",
    "_find_best_barcode",
    "_demux_read_anchored",
    "_demux_read",
]
