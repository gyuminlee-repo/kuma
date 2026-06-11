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
import threading
import multiprocessing
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import os
import sys
import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Callable, Iterator

from kuma_core.mame.ingest.align import (
    align_reads,
    align_reads_multi,
    build_minimap2_index,
    _get_reference_length,
    Alignment,
)
from kuma_core.mame.ingest.consensus import call_consensus_with_metrics
from kuma_core.mame.ingest.consensus_metadata import (
    ConsensusMetadata,
    format_consensus_fasta_record,
)
from kuma_core.mame.ingest.stage_marker import (
    is_unit_complete,
    read_stage_marker,
    write_stage_marker,
)
from kuma_core.mame.ingest.well_consensus import _read_reference_seq
from kuma_core.shared.atomic_write import atomic_write_text

log = logging.getLogger(__name__)

def _is_frozen_win() -> bool:
    """True only on a frozen (PyInstaller) Windows build.

    PyInstaller --onefile + multiprocessing "spawn" deadlocks on Windows: each
    spawned worker re-extracts the whole onefile archive, so the per-NB and
    per-read ProcessPools never make progress. Linux/macOS frozen demux is fine
    (fork / no re-extraction); only the Windows frozen sidecar hangs. Callers
    fall back to serial demux when this is True; dev/test and Linux/macOS keep
    full parallelism.
    """
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


_F_TAIL = "cacaggaggttaaacc"
_R_TAIL = "tgcgttgcgctctag"

_F_FALLBACK_LEN = 11  # prefix length if F tail absent
_R_FALLBACK_LEN = 10  # prefix length if R tail absent

# Gene-agnostic barcode row-name patterns (mirror sort_barcode.py).
# Match any "<prefix>_f_<int>" / "<prefix>_r_<int>" — not limited to "isps".
_FWD_ROW_RE = re.compile(r"^(?P<prefix>.+?)_f_(?P<n>\d+)$")
_REV_ROW_RE = re.compile(r"^(?P<prefix>.+?)_r_(?P<n>\d+)$")

_COMP = str.maketrans("ACGTacgtNn", "TGCAtgcaNn")

# Default worker count for per-well consensus ThreadPool.
# KUMA_MAME_CONSENSUS_WORKERS env var takes priority.
_CONSENSUS_WORKERS: int = int(
    os.environ.get("KUMA_MAME_CONSENSUS_WORKERS", "")
    or str(max(1, (os.cpu_count() or 4) - 1))
)

# Filename for the combined single-file consensus FASTA (all wells in one
# multi-record file), written in output_dir alongside the per-well consensus/
# directory. Mirrors the Aporva pipeline's final/<...>_consensus_dna.fasta so
# downstream tools that expect one multi-record FASTA keep working.
_COMBINED_CONSENSUS_FILENAME = "consensus_all_dna.fasta"


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

        m_f = _FWD_ROW_RE.match(name)
        m_r = _REV_ROW_RE.match(name)
        if m_f is not None:
            idx = int(m_f.group("n"))
            prefix = _extract_f_prefix(seq_val)
            f_entries.append((idx, name, prefix.upper()))

        elif m_r is not None:
            idx = int(m_r.group("n"))
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

        m_f = _FWD_ROW_RE.match(name)
        m_r = _REV_ROW_RE.match(name)
        if m_f is not None:
            idx = int(m_f.group("n"))
            f_entries.append((idx, seq_val.upper()))

        elif m_r is not None:
            idx = int(m_r.group("n"))
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
# Per-read chimera-path matching (extracted for optional ProcessPool fan-out)
# ---------------------------------------------------------------------------

# Default read-count threshold above which the chimera-path per-read matching
# loop is fanned out to a ProcessPool (only when this run owns the cores, i.e.
# n_nb == 1). Read at call time via os.environ so tests can lower it; a
# module-level constant bound at import could not be overridden by monkeypatch.
_PERREAD_THRESHOLD_DEFAULT = 10000

# Default read-chunk size for the alignment stage. Reads are loaded and aligned
# in chunks of this size instead of materialising the whole FASTQ in memory, so
# the per-chunk minimap2 input/SAM and the per-chunk Alignment lists are dropped
# between chunks (lowers alignment-stage peak RAM only; per_well accumulates to
# consensus as before). Read at call time via os.environ (KUMA_MAME_READ_CHUNK)
# so tests can lower it; a module-level constant bound at import could not be
# overridden by monkeypatch. Identity is preserved because minimap2 maps each
# query independently (per-read MAPQ, no cross-read normalisation), so a chunk's
# per-read hits equal the whole-load's, and chunks are processed in input order
# with per-chunk read_index re-sort -> global per_well append order is unchanged.
_READ_CHUNK_DEFAULT = 50000


def _iter_chunks(
    it: Iterator[tuple[str, str]], size: int
) -> Iterator[list[tuple[str, str]]]:
    """Yield successive ``size``-length lists from *it* (last may be shorter)."""
    chunk: list[tuple[str, str]] = []
    for item in it:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _match_reads_chunk(
    chunk: list[tuple[int, str, str, list[Alignment]]],
    r_barcodes: list[tuple[str, str]],
    f_barcodes: list[tuple[str, str]],
    window_bp: int,
    edit_dist_ratio: float,
    trim_flank_bp: int,
) -> list[tuple[int, list[tuple[int, int, str]], int, int, int]]:
    """Pure per-read barcode matching for the chimera (multi-hit) path.

    Module-level (no closure) so it is picklable for a ``spawn`` ProcessPool.
    Mirrors the serial loop body in :func:`run_combinatorial_demux` exactly
    (slice extraction, per-hit ``_demux_read_anchored``, read-local dedup,
    first-hit vs chimera-split classification). The matching logic itself is
    unchanged; only the accumulation is returned to the caller instead of
    mutating shared ``per_well``/``stats``.

    Parameters
    ----------
    chunk:
        ``(read_index, read_id, read_seq, hits)`` tuples. ``read_index`` is the
        position in the original ``multi_results`` list, used by the caller to
        re-sort results into input order before appending.

    Returns
    -------
    One tuple per input read: ``(read_index, appends, assigned_delta,
    chimera_delta, ambiguous_delta)`` where ``appends`` is the ordered list of
    ``(r_idx, f_idx, slice_seq)`` to push onto ``per_well[(r_idx, f_idx)]`` and
    the three deltas are this read's contribution to the matching stats.
    """
    out: list[tuple[int, list[tuple[int, int, str]], int, int, int]] = []
    for read_index, _read_id, read_seq, hits in chunk:
        assigned_wells_this_read: set[tuple[int, int]] = set()
        is_first_hit = True
        appends: list[tuple[int, int, str]] = []
        assigned_delta = 0
        chimera_delta = 0
        ambiguous_delta = 0

        for hit in hits:
            slice_start = max(0, hit.q_st - trim_flank_bp)
            slice_end = min(len(read_seq), hit.q_en + trim_flank_bp)
            slice_seq = read_seq[slice_start:slice_end]

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
                ambiguous_delta += 1
                is_first_hit = False
                continue

            r_idx, f_idx = result
            well = (r_idx, f_idx)

            if well in assigned_wells_this_read:
                is_first_hit = False
                continue

            assigned_wells_this_read.add(well)
            appends.append((r_idx, f_idx, slice_seq))

            if is_first_hit:
                assigned_delta += 1
            else:
                chimera_delta += 1
            is_first_hit = False

        out.append(
            (read_index, appends, assigned_delta, chimera_delta, ambiguous_delta)
        )
    return out


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
    well_consensus_at_root: bool = False,
    minimap2_threads: int | None = None,
    consensus_workers: int | None = None,
    per_read_parallel: bool = False,
    progress_callback: Callable[[int, int, str], None] | None = None,
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
    well_consensus_at_root:
        When True, write single-record per-well consensus FASTA files at the
        top level of ``output_dir`` (so a non-recursive top-level ``*.fasta``
        glob sees only consensus files), the multi-record per-well reads under
        ``output_dir/reads/``, and the combined consensus FASTA under
        ``output_dir/final/``.  When False (default), keep the legacy layout
        (reads at root, consensus under ``output_dir/consensus/``, combined at
        root).
    minimap2_threads:
        Thread count passed through to the alignment minimap2 invocation.
        ``None`` (default) keeps the module-level auto-detected default.
    consensus_workers:
        Worker count for the per-well consensus ThreadPool.  ``None`` (default)
        keeps the module-level ``_CONSENSUS_WORKERS`` default.

    Returns
    -------
    DemuxResult with stats, per_well_reads, per_well_consensus.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    if well_consensus_at_root:
        reads_dir = output_dir / "reads"
        reads_dir.mkdir(exist_ok=True)
        final_dir = output_dir / "final"
        final_dir.mkdir(exist_ok=True)
        consensus_dir = output_dir
        combined_path = final_dir / _COMBINED_CONSENSUS_FILENAME
    else:
        consensus_dir = output_dir / "consensus"
        consensus_dir.mkdir(exist_ok=True)
        reads_dir = output_dir
        combined_path = output_dir / _COMBINED_CONSENSUS_FILENAME

    stats = DemuxStats()

    r_barcodes, f_barcodes = load_barcode_prefixes(barcodes_xlsx)
    log.info(
        "Loaded %d R barcodes, %d F barcodes (prefix-only, annealing tail stripped)",
        len(r_barcodes),
        len(f_barcodes),
    )

    ref_len = _get_reference_length(reference_fasta)
    log.info("Reference length: %d bp", ref_len)

    per_well: dict[tuple[int, int], list[tuple[str, str]]] = defaultdict(list)

    # Chunk-stream read loading: load + align in N-read chunks instead of
    # materialising the whole FASTQ. Each chunk's minimap2 input/SAM and its
    # Alignment lists are dropped between iterations, lowering alignment-stage
    # peak RAM only (per_well still accumulates across chunks to consensus).
    # Identity is preserved because minimap2 maps each query independently
    # (per-read MAPQ, no cross-read normalisation), so a chunk's per-read hits
    # equal the whole-load's; chunks run in input order and the per-read pool
    # re-sorts each chunk by read_index, so the global per_well append order
    # (and thus consensus tie-break) is unchanged. stats are accumulated across
    # chunks (total_reads/passed_*/per-read deltas all use +=).
    _chunk_size = int(
        os.environ.get("KUMA_MAME_READ_CHUNK", str(_READ_CHUNK_DEFAULT))
    )
    _chunk_size = max(1, _chunk_size)
    _read_chunks = _iter_chunks(_iter_fastq(raw_fastq_paths), _chunk_size)

    for chunk_reads in _read_chunks:
        stats.total_reads += len(chunk_reads)

        if chimera_split:
            # --- multi-hit path: chimera / concatemer splitting ------------
            multi_results = align_reads_multi(
                reads=chunk_reads,
                reference_fasta=reference_fasta,
                preset="map-ont",
                min_mapq=mapq_threshold,
                coverage_fraction=coverage_fraction,
                threads=minimap2_threads,
            )

            reads_with_hits = len(multi_results)
            total_hit_count = sum(len(hits) for _, _, hits in multi_results)
            stats.passed_coverage += reads_with_hits
            stats.passed_mapq += reads_with_hits
            log.info(
                "Passed MAPQ+coverage filter (chunk): %d reads / %d total hits",
                reads_with_hits,
                total_hit_count,
            )

            _demux_total = len(multi_results)
            _threshold = int(
                os.environ.get(
                    "KUMA_MAME_PERREAD_THRESHOLD", str(_PERREAD_THRESHOLD_DEFAULT)
                )
            )
            # Per-read ProcessPool fan-out is only safe/beneficial when this run
            # owns the cores (n_nb == 1, signalled by per_read_parallel) and the
            # dataset clears the spawn/pickle overhead break-even threshold. Below
            # the threshold, or when n_nb > 1 (the per-NB pool already saturates
            # cores), stay on the serial path. Both paths produce byte-identical
            # per_well/stats: parallel results are re-sorted to input (read_index)
            # order before append, and the matching logic is shared verbatim via
            # _match_reads_chunk.
            _use_perread_pool = (
                per_read_parallel and _demux_total >= _threshold
                and _demux_total > 0 and not _is_frozen_win()
            )

            if _use_perread_pool:
                # oversubscription guard: the per-NB pool is 1 here (n_nb == 1)
                # and the consensus ThreadPool runs after this loop, so the
                # per-read pool may use all cores.
                cpu = os.cpu_count() or 4
                _env_w = os.environ.get("KUMA_MAME_PERREAD_WORKERS", "").strip()
                if _env_w.isdigit() and int(_env_w) > 0:
                    pool_workers = min(int(_env_w), cpu)
                else:
                    pool_workers = cpu
                pool_workers = max(1, min(pool_workers, _demux_total))

                indexed = [
                    (i, rid, rseq, hits)
                    for i, (rid, rseq, hits) in enumerate(multi_results)
                ]
                chunk_size = max(1, (_demux_total + pool_workers - 1) // pool_workers)
                chunks = [
                    indexed[i : i + chunk_size]
                    for i in range(0, _demux_total, chunk_size)
                ]

                collected: list[
                    tuple[int, list[tuple[int, int, str]], int, int, int]
                ] = []
                ctx = multiprocessing.get_context("spawn")
                with ProcessPoolExecutor(
                    max_workers=pool_workers, mp_context=ctx
                ) as ex:
                    futs = [
                        ex.submit(
                            _match_reads_chunk,
                            chunk,
                            r_barcodes,
                            f_barcodes,
                            window_bp,
                            edit_dist_ratio,
                            trim_flank_bp,
                        )
                        for chunk in chunks
                    ]
                    _done = 0
                    for fut in as_completed(futs):
                        collected.extend(fut.result())
                        _done += 1
                        if progress_callback is not None:
                            progress_callback(_done, len(futs), "demux")

                # Re-sort to input order so per_well append order (and thus
                # consensus tie-break) matches the serial path exactly.
                collected.sort(key=lambda r: r[0])
                id_by_index = {i: rid for i, rid, _, _ in indexed}
                for (
                    read_index,
                    appends,
                    assigned_d,
                    chimera_d,
                    ambiguous_d,
                ) in collected:
                    read_id = id_by_index[read_index]
                    for r_idx, f_idx, slice_seq in appends:
                        per_well[(r_idx, f_idx)].append((read_id, slice_seq))
                    stats.assigned_reads += assigned_d
                    stats.chimera_splits += chimera_d
                    stats.ambiguous_dropped += ambiguous_d
            else:
                _demux_step = max(1, _demux_total // 100)  # ~1% interval throttle
                for _demux_i, (read_id, read_seq, hits) in enumerate(multi_results):
                    if progress_callback is not None and _demux_i % _demux_step == 0:
                        progress_callback(_demux_i, _demux_total, "demux")
                    # Track which wells this read has already been assigned to
                    # to prevent double-counting the same read in the same well.
                    assigned_wells_this_read: set[tuple[int, int]] = set()
                    is_first_hit = True

                    for hit in hits:
                        # Extract aligned slice + flanks from the raw read.
                        # Coordinates are in read (query) space; no strand flip.
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
                            # Already assigned to this well from an earlier hit.
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
            # --- legacy single-hit path ------------------------------------
            alignments = align_reads(
                reads=chunk_reads,
                reference_fasta=reference_fasta,
                preset="map-ont",
                min_mapq=mapq_threshold,
                require_full_span=(coverage_fraction >= 1.0),
                threads=minimap2_threads,
            )
            stats.passed_coverage += len(alignments)
            stats.passed_mapq += len(alignments)
            log.info(
                "Passed MAPQ+coverage filter (chunk): %d / %d",
                len(alignments),
                len(chunk_reads),
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

    log.info("Total reads: %d", stats.total_reads)
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
        fasta_path = reads_dir / f"{well_name}.fasta"
        atomic_write_text(
            fasta_path,
            "".join(f">{read_id}\n{trimmed}\n" for read_id, trimmed in reads),
        )

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

    # Per-well consensus — parallel across wells (each well is independent)
    ref_seq = _read_reference_seq(reference_fasta)
    per_well_consensus: dict[str, str] = {}

    _consensus_total = len(per_well_reads)

    # Build the reference minimap2 index once (map-ont preset, identical to the
    # per-well alignment preset) so every well reuses it instead of rebuilding
    # the index on each of the (up to 96) align_reads calls. The .mmi lives in a
    # tempdir that spans the whole consensus loop below.
    _index_tmp = tempfile.TemporaryDirectory(prefix="kuma_mame_idx_")
    well_index: Path | None
    try:
        well_index = build_minimap2_index(
            reference_fasta, Path(_index_tmp.name) / "reference.mmi"
        )
    except Exception as exc:  # noqa: BLE001
        # Index prebuild is a pure performance optimisation. On any failure,
        # fall back to per-well on-the-fly indexing (reference_index=None) so
        # alignment output stays identical.
        log.warning(
            "minimap2 index prebuild failed (%s); per-well alignment will "
            "index the reference FASTA on the fly", exc
        )
        well_index = None

    def _run_well(
        well_name: str,
        reads: list[tuple[str, str]],
    ) -> tuple[str, str, int, int, float, int, float, int, int, int, int, int]:
        """Worker: returns consensus sequence, depth, and mix metrics."""
        (
            seq,
            depth,
            mixed_positions,
            max_minor_fraction,
            low_depth_positions,
            n_fraction,
            low_quality_bases,
            input_reads,
            aligned_reads,
            mapq_failed,
            span_failed,
        ) = _compute_well_consensus(
            well_name, reads, reference_fasta, ref_seq, ref_len, min_depth,
            reference_index=well_index,
        )
        return (
            well_name,
            seq,
            depth,
            mixed_positions,
            max_minor_fraction,
            low_depth_positions,
            n_fraction,
            low_quality_bases,
            input_reads,
            aligned_reads,
            mapq_failed,
            span_failed,
        )

    _consensus_done = 0
    n_workers = consensus_workers if consensus_workers is not None else _CONSENSUS_WORKERS
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_run_well, wn, rds): wn
            for wn, rds in per_well_reads.items()
        }
        for fut in as_completed(futures):
            (
                wn,
                seq,
                depth,
                mixed_positions,
                max_minor_fraction,
                low_depth_positions,
                n_fraction,
                low_quality_bases,
                input_reads,
                aligned_reads,
                mapq_failed,
                span_failed,
            ) = fut.result()
            per_well_consensus[wn] = seq
            atomic_write_text(
                consensus_dir / f"{wn}.fasta",
                format_consensus_fasta_record(
                    wn,
                    seq,
                    ConsensusMetadata(
                        depth=depth,
                        input_reads=input_reads,
                        aligned_reads=aligned_reads,
                        mapq_failed=mapq_failed,
                        span_failed=span_failed,
                        mixed_positions=mixed_positions,
                        max_minor_allele_fraction=max_minor_fraction,
                        low_depth_positions=low_depth_positions,
                        consensus_n_fraction=n_fraction,
                        low_quality_bases=low_quality_bases,
                    ),
                ),
            )
            _consensus_done += 1
            if progress_callback is not None:
                progress_callback(_consensus_done, _consensus_total, "consensus")

    # All wells finished aligning against the prebuilt index; drop the tempdir.
    _index_tmp.cleanup()

    # Combined single-file consensus FASTA (all wells, sorted by R then F),
    # mirroring the Aporva pipeline's final/<...>_consensus_dna.fasta output.
    # The per-well consensus/ files above are still written.
    _combined_order = sorted(
        per_well_consensus,
        key=lambda w: tuple(int(part) for part in w.split("_")),
    )
    atomic_write_text(
        combined_path,
        "".join(f">{wn}\n{per_well_consensus[wn]}\n" for wn in _combined_order),
    )

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
    reference_index: Path | None = None,
) -> tuple[str, int, int, float, int, float, int, int, int, int, int]:
    """Align reads and return consensus sequence, depth, and mix metrics."""
    if not reads:
        return (
            "N" * ref_len,
            0,
            0,
            0.0,
            ref_len,
            1.0 if ref_len > 0 else 0.0,
            0,
            0,
            0,
            0,
            0,
        )

    well_alignments = align_reads(
        reads=reads,
        reference_fasta=reference_fasta,
        preset="map-ont",
        min_mapq=0,           # trimmed reads; already filtered upstream
        require_full_span=False,
        # One thread per well: parallelism comes from the consensus
        # ThreadPoolExecutor across wells, so per-well minimap2 must stay
        # single-threaded to avoid workers x threads oversubscription.
        threads=1,
        # Reuse the reference .mmi prebuilt once for the whole consensus loop
        # (map-ont preset), skipping a fresh per-well index build. None falls
        # back to indexing reference_fasta on the fly.
        reference_index=reference_index,
    )

    if not well_alignments:
        log.debug(
            "Well %s: 0 alignments from %d trimmed reads", well_name, len(reads)
        )
        return (
            "N" * ref_len,
            0,
            0,
            0.0,
            ref_len,
            1.0 if ref_len > 0 else 0.0,
            0,
            len(reads),
            0,
            0,
            0,
        )

    consensus_call = call_consensus_with_metrics(
        well_alignments,
        ref_seq,
        min_depth=min_depth,
    )
    return (
        consensus_call.consensus_seq,
        len(well_alignments),
        consensus_call.n_mixed_positions,
        consensus_call.max_minor_allele_fraction,
        consensus_call.n_low_depth_positions,
        consensus_call.consensus_n_fraction,
        consensus_call.n_low_quality_bases,
        len(reads),
        len(well_alignments),
        0,
        0,
    )


# ---------------------------------------------------------------------------
# Per-native-barcode parallel orchestration
# ---------------------------------------------------------------------------

# The 8 DemuxStats counters carried in each per-NB summary and summed into
# merged_stats. Single source of truth so the worker summary, the resume-seed
# from a marker, and the merge step all agree on the key set.
_DEMUX_NB_STAT_KEYS: tuple[str, ...] = (
    "total_reads", "passed_mapq", "passed_coverage", "assigned_reads",
    "ambiguous_dropped", "chimera_splits", "wells_with_reads",
    "wells_with_min_reads",
)


class _DirectProgressSink:
    """In-process stand-in for a multiprocessing progress queue (serial demux).

    Mirrors the ``put_nowait((nb_name, fraction))`` contract so the worker uses a
    single code path; forwards straight to the aggregate callback.
    """

    __slots__ = ("_cb",)

    def __init__(self, cb: Callable[[str, float], None]) -> None:
        self._cb = cb

    def put_nowait(self, item: tuple[str, float]) -> None:
        try:
            self._cb(item[0], item[1])
        except Exception:
            pass


def _demux_one_nb(payload: dict) -> dict:
    """ProcessPool worker: run one native barcode, return a picklable summary."""
    fastq = [Path(s) for s in payload["fastq_paths"]]
    q = payload.get("progress_queue")
    nb_name = payload["nb_name"]
    inner_cb = None
    if q is not None:
        _last = [0.0]

        def inner_cb(done: int, total: int, stage: str) -> None:
            if total <= 0:
                return
            frac = done / total
            # Fold the two inner sub-phases into one 0..1 fraction for this NB:
            # read demux fills 0..0.85, per-well consensus 0.85..1.0.
            nb_f = 0.85 * frac if stage == "demux" else 0.85 + 0.15 * frac
            nb_f = max(0.0, min(1.0, nb_f))
            if nb_f - _last[0] >= 0.01 or nb_f >= 1.0:
                _last[0] = nb_f
                try:
                    q.put_nowait((nb_name, nb_f))
                except Exception:
                    pass

    result = run_combinatorial_demux(
        raw_fastq_paths=fastq, reference_fasta=Path(payload["reference_fasta"]),
        barcodes_xlsx=Path(payload["barcodes_xlsx"]), output_dir=Path(payload["output_dir"]),
        mapq_threshold=payload["mapq_threshold"], coverage_fraction=payload["coverage_fraction"],
        trim_flank_bp=payload["trim_flank_bp"], edit_dist_ratio=payload["edit_dist_ratio"],
        chimera_split=payload["chimera_split"], well_consensus_at_root=True,
        minimap2_threads=payload["minimap2_threads"], consensus_workers=payload["consensus_workers"],
        per_read_parallel=payload.get("per_read_parallel", False),
        progress_callback=inner_cb)
    s = result.stats
    return {"nb_name": payload["nb_name"], "sort_barcode_name": payload["sort_barcode_name"],
            "output_dir": str(Path(payload["output_dir"]).resolve()),
            "stats": {k: getattr(s, k) for k in _DEMUX_NB_STAT_KEYS},
            "per_well_read_counts": {w: len(r) for w, r in result.per_well_reads.items()}}


def _summary_from_marker(sort_barcode_name: str, nb_out: Path, marker: dict) -> dict:
    """Reconstruct a per-NB summary dict from a completed unit's stage marker.

    Mirrors the picklable dict returned by :func:`_demux_one_nb` so a skipped
    (already-complete) native barcode contributes identically to ``per_nb`` and
    ``merged_stats`` as a freshly-processed one.  ``per_well_read_counts`` is the
    marker's recorded ``per_well_counts``; the 8 DemuxStats counters come from
    the marker's optional ``stats`` block (absent in older/foreign markers, in
    which case those counters seed 0, never a crash).

    ``nb_name`` is left as the sort_barcode name here; the caller overwrites it
    with the real input nb_name before ordering so resume ordering matches.
    """
    marker_stats = marker.get("stats") or {}
    stats = {k: int(marker_stats.get(k, 0)) for k in _DEMUX_NB_STAT_KEYS}
    per_well = {
        str(w): int(c) for w, c in (marker.get("per_well_counts") or {}).items()
    }
    return {
        "nb_name": sort_barcode_name,
        "sort_barcode_name": sort_barcode_name,
        "output_dir": str(nb_out.resolve()),
        "stats": stats,
        "per_well_read_counts": per_well,
    }


def run_combinatorial_demux_per_nb(
    nb_to_fastq: dict[str, list[Path]],
    reference_fasta: Path,
    barcodes_xlsx: Path,
    output_dir: Path,
    *,
    mapq_threshold: int = 25,
    coverage_fraction: float = 0.98,
    trim_flank_bp: int = 30,
    edit_dist_ratio: float = 0.25,
    chimera_split: bool = True,
    parallel: bool = True,
    max_workers: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    """Run combinatorial demux per native barcode, in parallel across barcodes.

    Each native barcode in *nb_to_fastq* is demuxed into its own
    ``output_dir/sort_barcode{NN}/`` subdir (well_consensus_at_root layout),
    optionally across worker processes.  Iterates *nb_to_fastq* in dict order
    (insertion order = caller order).

    Returns a dict with ``merged_stats`` (8 stat keys summed across barcodes),
    ``per_nb`` (per-barcode summaries in input order), ``parallel`` (whether the
    parallel path was used), and ``workers`` (process count).
    """
    from kuma_core.mame.ingest.sort_barcode import _nb_to_sort_barcode_name

    cpu = os.cpu_count() or 4
    n = len(nb_to_fastq)
    env_off = os.environ.get("KUMA_MAME_NB_PARALLEL", "1") == "0"
    use_parallel = parallel and n > 1 and not env_off and not _is_frozen_win()
    if use_parallel:
        _env_workers = os.environ.get("KUMA_MAME_NB_WORKERS", "").strip()
        if max_workers:
            P = max_workers
        elif _env_workers.isdigit() and int(_env_workers) > 0:
            P = int(_env_workers)
        else:
            P = min(n, cpu)
        P = max(1, min(P, n, cpu))
    else:
        P = 1
    threads_per = max(1, cpu // P)
    # n_nb == 1: this single NB runs in the main process (no per-NB pool), so
    # the per-read matching loop may fan out to its own ProcessPool. With n>1
    # the per-NB pool already owns the cores, so per-read stays serial (and
    # nesting a pool inside a worker is illegal anyway).
    per_read_parallel = n == 1 and not _is_frozen_win()

    payloads: list[dict] = []
    for nb_name, paths in nb_to_fastq.items():
        sort_barcode_name = _nb_to_sort_barcode_name(nb_name)
        payloads.append({
            "nb_name": nb_name,
            "sort_barcode_name": sort_barcode_name,
            "output_dir": str(output_dir / sort_barcode_name),
            "fastq_paths": [str(p) for p in paths],
            "reference_fasta": str(reference_fasta),
            "barcodes_xlsx": str(barcodes_xlsx),
            "mapq_threshold": mapq_threshold,
            "coverage_fraction": coverage_fraction,
            "trim_flank_bp": trim_flank_bp,
            "edit_dist_ratio": edit_dist_ratio,
            "chimera_split": chimera_split,
            "minimap2_threads": threads_per,
            "consensus_workers": threads_per,
            "per_read_parallel": per_read_parallel,
        })

    # Fail fast if two entries map to the same sort_barcode output dir
    # (e.g. both "barcode06" and "NB06"), which would silently overwrite.
    _sort_names = [pl["sort_barcode_name"] for pl in payloads]
    if len(set(_sort_names)) != len(_sort_names):
        raise ValueError(
            f"Native barcodes map to colliding sort_barcode output dirs: {_sort_names}"
        )

    # ── Resume: which per-NB units are already complete? ─────────────────
    # A unit (one output_dir/sort_barcode{NN}/ dir) is "done" ONLY when it
    # carries a valid completion marker whose recorded inventory matches the
    # consensus FASTA on disk.  Directory existence alone never counts.  Each
    # completed unit's summary is reconstructed from its marker (mirroring the
    # _demux_one_nb dict) so it is NOT re-demuxed/aligned, yet still seeds
    # merged_stats and per_nb identically to a freshly-processed one.
    completed_summaries: dict[str, dict] = {}  # nb_name -> summary dict
    for pl in payloads:
        nb_out = output_dir / pl["sort_barcode_name"]
        if is_unit_complete(nb_out):
            marker = read_stage_marker(nb_out)
            if marker is not None:
                summ = _summary_from_marker(pl["sort_barcode_name"], nb_out, marker)
                summ["nb_name"] = pl["nb_name"]  # real input nb_name for ordering
                completed_summaries[pl["nb_name"]] = summ

    # Only dispatch payloads for units that are NOT already complete.
    pending = [pl for pl in payloads if pl["nb_name"] not in completed_summaries]

    def _commit_marker(summ: dict) -> None:
        """Write the unit's completion marker LAST (atomic commit point).

        Called only after the unit's consensus FASTA are all on disk (worker
        returned).  Records per_well_counts (= read counts), the 8 DemuxStats
        counters under ``stats`` so a full resume can reseed merged_stats, and
        consensus=True since the per-NB path always runs consensus.  A failure
        to write the marker must not lose the completed work, but here a write
        failure is unexpected (atomic temp+replace) and should surface, so it is
        not swallowed.
        """
        nb_out = output_dir / summ["sort_barcode_name"]
        # The worker (run_combinatorial_demux) already created nb_out; mkdir here
        # is an idempotent guard so the marker write never fails on a missing
        # parent.  An empty/interrupted unit whose consensus FASTA never landed
        # stays "not complete" (validate_marker inventory mismatch), so this does
        # not falsely mark an empty dir done.
        nb_out.mkdir(parents=True, exist_ok=True)
        write_stage_marker(
            nb_out,
            per_well_counts={
                str(w): int(c) for w, c in summ["per_well_read_counts"].items()
            },
            consensus=True,
            stats={k: int(summ["stats"][k]) for k in _DEMUX_NB_STAT_KEYS},
        )

    summaries: list[dict] = list(completed_summaries.values())

    # ── Smooth aggregate progress across barcodes ─────────────────────────
    # Each pending NB contributes a 0..1 fraction (streamed from the worker via
    # progress_q); resume-skipped units count as 1.0. The bar reported to the
    # caller = (completed + sum(in-flight fractions)) / n as parts-per-1000, so
    # the demux phase advances continuously instead of only at NB boundaries.
    nb_frac: dict[str, float] = {pl["nb_name"]: 0.0 for pl in pending}
    n_seed_done = len(completed_summaries)
    _agg_lock = threading.Lock()
    _agg_last = [-1.0]

    def _emit_agg(force: bool = False) -> None:
        if progress_callback is None:
            return
        with _agg_lock:
            agg = (n_seed_done + sum(nb_frac.values())) / n if n else 1.0
            agg = max(0.0, min(1.0, agg))
            if not force and abs(agg - _agg_last[0]) < 0.003:
                return
            _agg_last[0] = agg
            done_ct = n_seed_done + sum(1 for f in nb_frac.values() if f >= 1.0)
        progress_callback(int(round(agg * 1000)), 1000, f"{done_ct}/{n} barcodes")

    def _note_frac(nb_name: str, frac: float) -> None:
        with _agg_lock:
            if nb_name in nb_frac and frac > nb_frac[nb_name]:
                nb_frac[nb_name] = frac
        _emit_agg()

    _emit_agg(force=True)  # tick past resume-skipped units immediately

    if P > 1 and pending:
        mp_ctx = multiprocessing.get_context("spawn")
        manager = None
        progress_q = None
        try:
            manager = mp_ctx.Manager()
            progress_q = manager.Queue()
        except Exception:  # Manager unavailable — degrade to per-NB completion only
            manager = None
            progress_q = None
        if progress_q is not None:
            for pl in pending:
                pl["progress_queue"] = progress_q
        _drain_stop = threading.Event()

        def _drainer() -> None:
            while not _drain_stop.is_set():
                try:
                    nb_name, frac = progress_q.get(timeout=0.4)
                except Exception:
                    continue
                _note_frac(nb_name, frac)

        _drain_thread = None
        if progress_q is not None:
            _drain_thread = threading.Thread(target=_drainer, daemon=True)
            _drain_thread.start()
        try:
            with ProcessPoolExecutor(max_workers=P, mp_context=mp_ctx) as ex:
                futs = {ex.submit(_demux_one_nb, pl): pl["nb_name"] for pl in pending}
                for fut in as_completed(futs):
                    summ = fut.result()  # propagate worker exceptions (fail-fast)
                    _commit_marker(summ)  # commit point: unit files all on disk now
                    with _agg_lock:
                        nb_frac[summ["nb_name"]] = 1.0
                    _emit_agg(force=True)
                    summaries.append(summ)
        finally:
            _drain_stop.set()
            if _drain_thread is not None:
                _drain_thread.join(timeout=1.5)
            if manager is not None:
                try:
                    manager.shutdown()
                except Exception:
                    pass
    else:
        for pl in pending:
            # Serial path: forward inner progress in-process via a queue-shaped
            # shim so _demux_one_nb uses one code path.
            pl["progress_queue"] = _DirectProgressSink(_note_frac)
            summ = _demux_one_nb(pl)
            _commit_marker(summ)  # commit point: unit files all on disk now
            summaries.append(summ)
            with _agg_lock:
                nb_frac[pl["nb_name"]] = 1.0
            _emit_agg(force=True)

    # Order summaries by input nb order.
    by_name = {s["nb_name"]: s for s in summaries}
    ordered_summaries = [by_name[pl["nb_name"]] for pl in payloads]

    # Merge stats: sum each of the 8 stat keys across summaries (processed +
    # resume-seeded units alike).
    merged = {
        k: sum(s["stats"][k] for s in ordered_summaries) for k in _DEMUX_NB_STAT_KEYS
    }

    return {"merged_stats": merged, "per_nb": ordered_summaries,
            "parallel": P > 1, "workers": P}


__all__ = [
    # Public types
    "DemuxResult",
    "DemuxStats",
    # Public entry points
    "load_barcodes",
    "load_barcode_prefixes",
    "run_combinatorial_demux",
    "run_combinatorial_demux_per_nb",
    "_demux_one_nb",
    # Semi-private helpers exported for tests and diagnostic scripts
    "_extract_barcode_prefix",
    "_extract_f_prefix",
    "_extract_r_prefix",
    "_find_best_barcode",
    "_demux_read_anchored",
    "_demux_read",
]
