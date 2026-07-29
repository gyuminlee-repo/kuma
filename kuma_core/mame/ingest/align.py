"""A4: minimap2 alignment via the minimap2 command-line binary.

Spawns the ``minimap2`` CLI as a subprocess (``minimap2 -a``) and parses the
SAM output to provide alignment of per-well reads against a reference
sequence.  Applies alignment filters:

- MAPQ >= 25
- 100% reference span: aligned region must cover the full reference length
  (``r_st == 0 and r_en == reference_length``).

The CLI path is used on every platform.  mappy (the minimap2 Python binding)
ships no Windows wheel, so the in-process binding broke Windows desktop builds
(raw_run returned JSON-RPC -32603).  samtools/pysam are NOT used (POSIX-only,
unavailable as Windows wheels).

Coordinate conventions are matched byte-for-byte to the prior mappy path:

- ``read_seq`` holds the original input read, never the SAM SEQ field (for a
  reverse hit SAM SEQ is the reverse complement of the input).
- ``r_st`` = SAM POS - 1 (1-based to 0-based); ``r_en`` advances by
  reference-consuming op lengths.
- ``q_st`` = sum of leading clip lengths (S and H); ``q_en`` = ``q_st`` plus
  query-consuming aligned op lengths (M/I/=/X).  Strand-agnostic and
  SEQ-independent, so it reproduces mappy forward-oriented coordinates for both
  primary and supplementary records.
- ``strand`` = -1 when SAM FLAG bit 0x10 is set, otherwise +1.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# CIGAR operation codes (BAM spec)
_CIGAR_M = 0   # match or mismatch
_CIGAR_I = 1   # insertion to reference
_CIGAR_D = 2   # deletion from reference
_CIGAR_N = 3   # skipped region from reference
_CIGAR_S = 4   # soft clip (bases present in query, not aligned)
_CIGAR_H = 5   # hard clip (bases absent from query SEQ)
_CIGAR_P = 6   # padding
_CIGAR_EQ = 7  # sequence match (=)
_CIGAR_X = 8   # sequence mismatch (X)

# Ops that consume the reference position
_REF_CONSUMING = frozenset({_CIGAR_M, _CIGAR_D, _CIGAR_N, _CIGAR_EQ, _CIGAR_X})
# Ops that consume the query (read) position
_QUERY_CONSUMING = frozenset({_CIGAR_M, _CIGAR_I, _CIGAR_S, _CIGAR_EQ, _CIGAR_X})

# Ops that consume the query in the aligned region (clips excluded)
_QUERY_ALIGNED = frozenset({_CIGAR_M, _CIGAR_I, _CIGAR_EQ, _CIGAR_X})

# SAM FLAG bits
_FLAG_REVERSE = 0x10
_FLAG_UNMAPPED = 0x4
_FLAG_SECONDARY = 0x100
_FLAG_SUPPLEMENTARY = 0x800

# Map SAM CIGAR letters to BAM op codes.
_CIGAR_LETTER_TO_OP = {
    "M": _CIGAR_M,
    "I": _CIGAR_I,
    "D": _CIGAR_D,
    "N": _CIGAR_N,
    "S": _CIGAR_S,
    "H": _CIGAR_H,
    "P": _CIGAR_P,
    "=": _CIGAR_EQ,
    "X": _CIGAR_X,
}

_CIGAR_TOKEN_RE = re.compile(r"(\d+)([MIDNSHP=X])")


@dataclass
class Alignment:
    """Single read alignment result.

    Attributes
    ----------
    read_id:
        Original read identifier from the FASTA/FASTQ header.
    read_seq:
        Full read sequence (as provided; not reverse-complemented).
        Callers should respect ``strand`` when iterating bases.
    read_qual:
        Optional FASTQ quality string matching ``read_seq``.  ``None`` when
        reads came from FASTA or a legacy path that has already dropped quality.
    mapq:
        Mapping quality (0-60).
    cigar:
        CIGAR operations as list of ``[length, op]`` pairs.
        Op codes follow the BAM spec (0=M, 1=I, 2=D, 4=S, 5=H, 7==, 8=X).
    r_st:
        Alignment start on reference (0-based, inclusive).
    r_en:
        Alignment end on reference (0-based, exclusive).
    q_st:
        Alignment start on query (0-based, inclusive).
    q_en:
        Alignment end on query (0-based, exclusive).
    strand:
        +1 for forward, -1 for reverse complement.
    reference_length:
        Full reference sequence length (for span-filter bookkeeping).
    """

    read_id: str
    read_seq: str
    mapq: int
    cigar: list[list[int]]  # [[length, op], ...]
    r_st: int
    r_en: int
    q_st: int
    q_en: int
    strand: int
    reference_length: int
    read_qual: str | None = None


@dataclass(frozen=True)
class AlignmentStats:
    """Read-level alignment pass/fail counters for consensus diagnostics."""

    n_input_reads: int
    n_primary_alignments: int
    n_unaligned: int
    n_failed_mapq: int
    n_failed_span: int
    n_passed_filter: int


def _resolve_minimap2() -> str:
    """Locate the minimap2 binary.

    Priority order:

    1. ``KURO_MINIMAP2`` environment variable.
    2. The sidecar resource directory next to the frozen executable
       (PyInstaller ``sys._MEIPASS`` or the executable directory).
    3. ``minimap2`` on PATH.

    Returns
    -------
    Path string to an executable minimap2 binary.

    Raises
    ------
    RuntimeError
        If no minimap2 binary can be located.
    """
    exe_name = "minimap2.exe" if sys.platform.startswith("win") else "minimap2"

    # 1. Explicit override.
    env_path = os.environ.get("KURO_MINIMAP2")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return str(candidate)
        raise RuntimeError(
            f"KURO_MINIMAP2 points to a missing file: {env_path}"
        )

    # 2. Sidecar resource directory (bundled binary, Phase 2).
    resource_dirs: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        resource_dirs.append(Path(meipass))
    if getattr(sys, "frozen", False):
        resource_dirs.append(Path(sys.executable).parent)
    for base in resource_dirs:
        for candidate in (base / exe_name, base / "bin" / exe_name):
            if candidate.is_file():
                return str(candidate)

    # 3. PATH.
    found = shutil.which("minimap2")
    if found:
        return found

    raise RuntimeError(
        "minimap2 binary not found. Set the KURO_MINIMAP2 environment variable "
        "to its path, place it on PATH, or install it (e.g. "
        "'conda install -c bioconda minimap2' or download a release binary from "
        "https://github.com/lh3/minimap2/releases)."
    )


def _parse_cigar(cigar_str: str) -> list[list[int]]:
    """Parse a SAM CIGAR string into ``[[length, op_int], ...]``.

    ``"*"`` (no CIGAR) yields an empty list.
    """
    if cigar_str == "*" or not cigar_str:
        return []
    ops: list[list[int]] = []
    pos = 0
    for match in _CIGAR_TOKEN_RE.finditer(cigar_str):
        ops.append([int(match.group(1)), _CIGAR_LETTER_TO_OP[match.group(2)]])
        pos = match.end()
    if pos != len(cigar_str):
        raise ValueError(f"Malformed CIGAR string: {cigar_str!r}")
    return ops


def _coords_from_cigar(
    cigar: list[list[int]], pos_1based: int, reverse: bool
) -> tuple[int, int, int, int]:
    """Derive (r_st, r_en, q_st, q_en) from a CIGAR and 1-based SAM POS.

    - r_st = pos - 1 (0-based); r_en = r_st + reference-consuming op lengths.
    - SAM clips are relative to the SEQ as written. For reverse-strand records
      SEQ is the reverse complement of the input read, so the SAM-oriented
      q_st/q_en are flipped back to the original (as-input) read orientation to
      match mappy's forward query coordinates that downstream code expects.
    """
    r_st = pos_1based - 1
    ref_span = 0
    lead_clip = 0
    q_aligned = 0
    total_query = 0
    seen_aligned = False
    for length, op in cigar:
        if op in _REF_CONSUMING:
            ref_span += length
        if op in (_CIGAR_S, _CIGAR_H):
            total_query += length
            if not seen_aligned:
                lead_clip += length
        elif op in _QUERY_ALIGNED:
            seen_aligned = True
            q_aligned += length
            total_query += length
        else:
            # Deletion / skip / padding consume neither query clip nor aligned
            # query bases; mark the aligned region as started for clip logic.
            seen_aligned = True
    r_en = r_st + ref_span
    q_st_sam = lead_clip
    q_en_sam = lead_clip + q_aligned
    if reverse:
        q_st = total_query - q_en_sam
        q_en = total_query - q_st_sam
    else:
        q_st = q_st_sam
        q_en = q_en_sam
    return r_st, r_en, q_st, q_en


def _strip_clips(cigar: list[list[int]]) -> list[list[int]]:
    """Drop soft/hard-clip ops to match mappy's clip-free ``.cigar``.

    Clipping is conveyed by q_st/q_en; consensus walking starts at q_st and must
    not re-advance over a leading clip op (which double-offsets the query).
    """
    return [[length, op] for length, op in cigar if op not in (_CIGAR_S, _CIGAR_H)]


def _normalise_read_tuple(read: tuple[str, ...]) -> tuple[str, str, str | None]:
    if len(read) >= 3:
        return str(read[0]), str(read[1]), str(read[2])
    return str(read[0]), str(read[1]), None


def _write_reads_fasta(
    reads: Iterable[tuple[str, ...]], fasta_path: Path
) -> list[tuple[str, str, str | None]]:
    """Write reads to a FASTA with synthetic integer QNAMEs.

    Returns an index map:
    ``index_map[i] == (original_read_id, original_seq, original_qual_or_none)``.
    Empty reads are skipped (not written, not indexed).
    """
    index_map: list[tuple[str, str, str | None]] = []
    with fasta_path.open("w", encoding="utf-8") as fh:
        for raw_read in reads:
            read_id, seq, qual = _normalise_read_tuple(raw_read)
            if not seq:
                continue
            idx = len(index_map)
            index_map.append((read_id, seq, qual))
            fh.write(f">{idx}\n{seq}\n")
    return index_map


# Default thread count for the main minimap2 alignment.  KUMA_MINIMAP2_THREADS
# env var takes priority; otherwise auto-detect from the host CPU, reserving one
# core for the UI / sidecar.  (Previously capped at min(8, cpu), which under-used
# machines with more than 8 cores.)  Per-well consensus alignment passes an
# explicit threads=1 instead, so concurrent wells do not oversubscribe.
_MINIMAP2_THREADS: int = int(
    os.environ.get("KUMA_MINIMAP2_THREADS", "")
    or str(max(1, (os.cpu_count() or 4) - 1))
)


def build_minimap2_index(reference_fasta: Path, mmi_path: Path) -> Path:
    """Pre-build a minimap2 ``.mmi`` index with the ``map-ont`` preset.

    Equivalent to ``minimap2 -x map-ont -d mmi_path reference_fasta``.  The
    preset MUST match the on-the-fly alignment preset (``map-ont``) so that an
    alignment run against the prebuilt index reproduces byte-identical output:
    minimap2 stores k/w/H in the index and ignores runtime ``-k``/``-w`` when a
    prebuilt index is supplied, but re-applies all alignment-time parameters at
    align time.  Using the same preset both places keeps results identical.

    Returns ``mmi_path`` on success; raises RuntimeError on a non-zero exit.
    """
    binary = _resolve_minimap2()
    cmd = [binary, "-x", "map-ont", "-d", str(mmi_path), str(reference_fasta)]
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"minimap2 index build failed (exit {proc.returncode}): "
            f"{(proc.stderr or '').strip()[:500]}"
        )
    return mmi_path


def _run_minimap2(
    reference: Path,
    reads_fasta: Path,
    preset: str,
    best_n: int | None = None,
    threads: int | None = None,
) -> list[tuple[int, int, int, int, str]]:
    """Run minimap2 -a, parsing SAM records straight off stdout.

    ``reference`` is the positional reference argument: either a FASTA path or a
    prebuilt ``.mmi`` index.  minimap2 accepts both in the same slot.

    stdout is consumed from a pipe instead of being written to a SAM file, so
    the full alignment output is never materialised on disk.  stderr is captured
    in memory only (never written to a file path).

    Returns the parsed records; raises RuntimeError on a non-zero exit.
    """
    binary = _resolve_minimap2()
    n_threads = threads if threads is not None else _MINIMAP2_THREADS
    cmd = [binary, "-a", "-x", preset, "-t", str(n_threads)]
    if best_n is not None:
        # -N caps secondary alignments reported per read.
        cmd += ["-N", str(best_n)]
    cmd += [str(reference), str(reads_fasta)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
    )
    if proc.stdout is None:
        raise RuntimeError("minimap2 stdout pipe unavailable")
    records = list(_iter_sam_records_stream(proc.stdout))
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"minimap2 failed (exit {proc.returncode}): "
            f"{(err or '').strip()[:500]}"
        )
    return records


def _iter_sam_records_stream(
    fh: Iterable[str],
) -> Iterable[tuple[int, int, int, int, str]]:
    """Yield (read_index, flag, pos_1based, mapq, cigar_str) per SAM line.

    Parses an iterable of SAM text lines (a file or a subprocess stdout pipe).
    Header lines (starting with '@') and unmapped records (FLAG & 0x4) are
    skipped.  ``read_index`` is parsed from the synthetic integer QNAME.
    """
    for line in fh:
        line = line.rstrip("\n")
        if not line or line.startswith("@"):
            continue
        fields = line.split("\t")
        if len(fields) < 6:
            continue
        flag = int(fields[1])
        if flag & _FLAG_UNMAPPED:
            continue
        read_index = int(fields[0])
        pos = int(fields[3])
        mapq = int(fields[4])
        cigar_str = fields[5]
        yield read_index, flag, pos, mapq, cigar_str


def align_reads(
    reads: Iterable[tuple[str, ...]],
    reference_fasta: Path,
    preset: str = "map-ont",
    min_mapq: int = 25,
    require_full_span: bool = True,
    threads: int | None = None,
    reference_index: Path | None = None,
    coverage_fraction: float | None = None,
) -> list[Alignment]:
    """Align reads to a reference using the minimap2 CLI.

    Parameters
    ----------
    reads:
        Iterable of ``(read_id, sequence)`` pairs or
        ``(read_id, sequence, quality)`` triples.
    reference_fasta:
        Path to reference FASTA file (must have exactly one record).  Always
        used to read the reference length; also passed to minimap2 as the
        positional reference unless ``reference_index`` is given.
    reference_index:
        Optional prebuilt minimap2 ``.mmi`` index (see
        :func:`build_minimap2_index`).  When set, it replaces
        ``reference_fasta`` as the positional reference argument to minimap2,
        skipping per-call index construction.  ``reference_fasta`` is still
        read for its length.  The index MUST be built with the same preset as
        ``preset`` (``map-ont``) to keep alignment output byte-identical.
    preset:
        minimap2 preset; ``"map-ont"`` for Oxford Nanopore reads.
    min_mapq:
        Minimum mapping quality (MAPQ).  Reads below this threshold are
        discarded.
    require_full_span:
        When True, only accept alignments that span the full reference
        (``r_st == 0 and r_en == reference_length``).  Equivalent to
        bedtools intersect -f 1.0.

    Returns
    -------
    List of :class:`Alignment` objects that passed all filters, in
    input order (one primary hit per read at most).

    Raises
    ------
    RuntimeError
        If the minimap2 binary cannot be located or fails to run.
    FileNotFoundError
        If ``reference_fasta`` does not exist.
    ValueError
        If the reference FASTA contains no sequences.
    """
    if not reference_fasta.exists():
        raise FileNotFoundError(f"Reference FASTA not found: {reference_fasta}")

    ref_len = _get_reference_length(reference_fasta)

    with tempfile.TemporaryDirectory(prefix="kuro_align_") as tmpdir:
        reads_fasta = Path(tmpdir) / "reads.fasta"
        index_map = _write_reads_fasta(reads, reads_fasta)
        if not index_map:
            return []

        positional_ref = reference_index if reference_index is not None else reference_fasta
        records = _run_minimap2(positional_ref, reads_fasta, preset, threads=threads)

        # Collect the single primary alignment per read index.
        primary: dict[int, Alignment] = {}
        for read_index, flag, pos, mapq, cigar_str in records:
            if flag & (_FLAG_SECONDARY | _FLAG_SUPPLEMENTARY):
                continue
            if read_index in primary:
                continue
            cigar = _parse_cigar(cigar_str)
            r_st, r_en, q_st, q_en = _coords_from_cigar(cigar, pos, bool(flag & _FLAG_REVERSE))
            strand = -1 if (flag & _FLAG_REVERSE) else 1
            read_id, read_seq, read_qual = index_map[read_index]
            primary[read_index] = Alignment(
                read_id=read_id,
                read_seq=read_seq,
                read_qual=read_qual,
                mapq=mapq,
                cigar=_strip_clips(cigar),
                r_st=r_st,
                r_en=r_en,
                q_st=q_st,
                q_en=q_en,
                strand=strand,
                reference_length=ref_len,
            )

    # Emit in input (index) order, applying filters.
    results: list[Alignment] = []
    for idx in range(len(index_map)):
        aln = primary.get(idx)
        if aln is None:
            continue
        if aln.mapq < min_mapq:
            continue
        if require_full_span and not (aln.r_st == 0 and aln.r_en == ref_len):
            continue
        if (
            coverage_fraction is not None
            and ref_len > 0
            and (aln.r_en - aln.r_st) / ref_len < coverage_fraction
        ):
            continue
        results.append(aln)

    return results


def align_reads_with_stats(
    reads: Iterable[tuple[str, ...]],
    reference_fasta: Path,
    preset: str = "map-ont",
    min_mapq: int = 25,
    require_full_span: bool = True,
    threads: int | None = None,
) -> tuple[list[Alignment], AlignmentStats]:
    """Align reads and return passing alignments plus drop-reason counters."""
    if not reference_fasta.exists():
        raise FileNotFoundError(f"Reference FASTA not found: {reference_fasta}")

    ref_len = _get_reference_length(reference_fasta)

    with tempfile.TemporaryDirectory(prefix="kuro_align_") as tmpdir:
        reads_fasta = Path(tmpdir) / "reads.fasta"
        index_map = _write_reads_fasta(reads, reads_fasta)
        if not index_map:
            stats = AlignmentStats(
                n_input_reads=0,
                n_primary_alignments=0,
                n_unaligned=0,
                n_failed_mapq=0,
                n_failed_span=0,
                n_passed_filter=0,
            )
            return [], stats

        records = _run_minimap2(reference_fasta, reads_fasta, preset, threads=threads)

        primary: dict[int, Alignment] = {}
        for read_index, flag, pos, mapq, cigar_str in records:
            if flag & (_FLAG_SECONDARY | _FLAG_SUPPLEMENTARY):
                continue
            if read_index in primary:
                continue
            cigar = _parse_cigar(cigar_str)
            r_st, r_en, q_st, q_en = _coords_from_cigar(cigar, pos, bool(flag & _FLAG_REVERSE))
            strand = -1 if (flag & _FLAG_REVERSE) else 1
            read_id, read_seq, read_qual = index_map[read_index]
            primary[read_index] = Alignment(
                read_id=read_id,
                read_seq=read_seq,
                read_qual=read_qual,
                mapq=mapq,
                cigar=_strip_clips(cigar),
                r_st=r_st,
                r_en=r_en,
                q_st=q_st,
                q_en=q_en,
                strand=strand,
                reference_length=ref_len,
            )

    results: list[Alignment] = []
    n_unaligned = 0
    n_failed_mapq = 0
    n_failed_span = 0
    for idx in range(len(index_map)):
        aln = primary.get(idx)
        if aln is None:
            n_unaligned += 1
            continue
        if aln.mapq < min_mapq:
            n_failed_mapq += 1
            continue
        if require_full_span and not (aln.r_st == 0 and aln.r_en == ref_len):
            n_failed_span += 1
            continue
        results.append(aln)

    stats = AlignmentStats(
        n_input_reads=len(index_map),
        n_primary_alignments=len(primary),
        n_unaligned=n_unaligned,
        n_failed_mapq=n_failed_mapq,
        n_failed_span=n_failed_span,
        n_passed_filter=len(results),
    )
    return results, stats


def align_reads_multi(
    reads: Iterable[tuple[str, ...]],
    reference_fasta: Path,
    preset: str = "map-ont",
    min_mapq: int = 25,
    coverage_fraction: float = 0.98,
    best_n: int = 20,
    threads: int | None = None,
) -> list[tuple[str, str, list[Alignment]]]:
    """Align reads and return ALL passing hits per read (chimera/concatemer support).

    Unlike :func:`align_reads` which takes only the primary hit, this function
    keeps the primary and supplementary alignments minimap2 reports for each
    read.  Hits that pass MAPQ and coverage-fraction filters are returned.  This
    allows chimeric reads or concatemers carrying two distinct amplicons to be
    demultiplexed into separate wells.

    Parameters
    ----------
    reads:
        Iterable of ``(read_id, sequence)`` pairs.
    reference_fasta:
        Path to reference FASTA file (must have exactly one record).
    preset:
        minimap2 preset; ``"map-ont"`` for Oxford Nanopore reads.
    min_mapq:
        Minimum mapping quality per hit (default 25).
    coverage_fraction:
        Minimum fraction of reference covered by each hit
        (default 0.98 = 98%; replaces strict require_full_span==True).
    best_n:
        Maximum number of secondary alignments minimap2 reports per read
        (passed as -N).  Increase for high-copy concatemers (default 20).

    Returns
    -------
    List of ``(read_id, read_seq, hits)`` tuples where ``hits`` is a
    non-empty list of :class:`Alignment` objects for that read.  Reads with
    no passing hits are omitted.  Output order follows input order.

    Notes
    -----
    Caller is responsible for deduplicating (read_id, well) assignments
    to avoid counting the same physical read twice in one well.  Secondary
    alignments (FLAG 0x100) are skipped: minimap2 emits SEQ=* and MAPQ=0 for
    them, so the min_mapq filter would discard them in any case.
    """
    if not reference_fasta.exists():
        raise FileNotFoundError(f"Reference FASTA not found: {reference_fasta}")

    ref_len = _get_reference_length(reference_fasta)

    with tempfile.TemporaryDirectory(prefix="kuro_align_") as tmpdir:
        reads_fasta = Path(tmpdir) / "reads.fasta"
        index_map = _write_reads_fasta(reads, reads_fasta)
        if not index_map:
            return []

        records = _run_minimap2(
            reference_fasta, reads_fasta, preset, best_n=best_n,
            threads=threads,
        )

        # Collect passing hits per read index (primary + supplementary).
        hits_by_index: dict[int, list[Alignment]] = {}
        for read_index, flag, pos, mapq, cigar_str in records:
            if flag & _FLAG_SECONDARY:
                continue
            if mapq < min_mapq:
                continue
            cigar = _parse_cigar(cigar_str)
            r_st, r_en, q_st, q_en = _coords_from_cigar(cigar, pos, bool(flag & _FLAG_REVERSE))
            ref_span = r_en - r_st
            if ref_len > 0 and ref_span / ref_len < coverage_fraction:
                continue
            strand = -1 if (flag & _FLAG_REVERSE) else 1
            read_id, read_seq, read_qual = index_map[read_index]
            hits_by_index.setdefault(read_index, []).append(
                Alignment(
                    read_id=read_id,
                    read_seq=read_seq,
                    read_qual=read_qual,
                    mapq=mapq,
                    cigar=_strip_clips(cigar),
                    r_st=r_st,
                    r_en=r_en,
                    q_st=q_st,
                    q_en=q_en,
                    strand=strand,
                    reference_length=ref_len,
                )
            )

    results: list[tuple[str, str, list[Alignment]]] = []
    for idx in range(len(index_map)):
        passing = hits_by_index.get(idx)
        if passing:
            read_id, read_seq, _read_qual = index_map[idx]
            results.append((read_id, read_seq, passing))

    return results


def _get_reference_length(reference_fasta: Path) -> int:
    """Return the total length of the first sequence in a FASTA file."""
    length = 0
    in_seq = False
    with reference_fasta.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if line.startswith(">"):
                if in_seq:
                    # Second header found -- stop; use length of first sequence.
                    break
                in_seq = True
            elif in_seq:
                length += len(line.strip())
    if length == 0:
        raise ValueError(f"Reference FASTA contains no sequence data: {reference_fasta}")
    return length


__all__ = [
    "Alignment",
    "AlignmentStats",
    "align_reads",
    "align_reads_multi",
    "align_reads_with_stats",
    "_get_reference_length",
]
