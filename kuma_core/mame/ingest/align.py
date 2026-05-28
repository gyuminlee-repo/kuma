"""A4: minimap2 alignment via mappy Python bindings.

Wraps ``mappy.Aligner`` to provide alignment of per-well reads against a
reference sequence.  Applies alignment filters:

- MAPQ >= 25
- 100% reference span: aligned region must cover the full reference length
  (``r_st == 0 and r_en == reference_length``).

samtools/pysam are NOT used (POSIX-only, unavailable as Windows wheels).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol, TYPE_CHECKING, cast


class _MappyHit(Protocol):
    """Structural type for mappy alignment hit objects.

    mappy ships no PEP 561 stubs; attributes are defined by the underlying
    minimap2 C extension and documented at
    https://github.com/lh3/minimap2/blob/master/python/mappy.pyx
    """

    mapq: int
    cigar: Iterable[tuple[int, int]]
    r_st: int
    r_en: int
    q_st: int
    q_en: int
    strand: int


if TYPE_CHECKING:
    pass  # mappy imported at call-site to allow ImportError surface

# CIGAR operation codes (BAM spec, as returned by mappy)
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
    mapq:
        Mapping quality (0-60).
    cigar:
        CIGAR operations as list of ``[length, op]`` pairs (mappy format).
        Op codes follow the BAM spec (0=M, 1=I, 2=D, 4=S, 7==, 8=X).
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


def align_reads(
    reads: Iterable[tuple[str, str]],
    reference_fasta: Path,
    preset: str = "map-ont",
    min_mapq: int = 25,
    require_full_span: bool = True,
) -> list[Alignment]:
    """Align reads to a reference using mappy (minimap2 Python bindings).

    Parameters
    ----------
    reads:
        Iterable of ``(read_id, sequence)`` pairs.
    reference_fasta:
        Path to reference FASTA file (must have exactly one record).
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
    input order.

    Raises
    ------
    ImportError
        If ``mappy`` is not installed.
    FileNotFoundError
        If ``reference_fasta`` does not exist.
    ValueError
        If the reference FASTA contains no sequences.
    """
    try:
        import mappy  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "mappy is required for alignment. Install with: pip install mappy"
        ) from exc

    if not reference_fasta.exists():
        raise FileNotFoundError(f"Reference FASTA not found: {reference_fasta}")

    aligner = mappy.Aligner(str(reference_fasta), preset=preset)
    if not aligner:
        raise ValueError(f"mappy.Aligner initialisation failed for: {reference_fasta}")

    # Determine reference length from the first sequence in the FASTA.
    ref_len = _get_reference_length(reference_fasta)

    results: list[Alignment] = []
    reads_iter = iter(reads)

    for read_id, seq in reads_iter:
        if not seq:
            continue

        # mappy.map() returns zero or more hits; take the primary (first) hit.
        best: _MappyHit | None = None
        for _hit in aligner.map(seq):
            # mappy returns hits sorted by score descending; take first.
            best = cast(_MappyHit, _hit)
            break

        if best is None:
            continue

        h: _MappyHit = best

        # MAPQ filter: discard reads below minimum mapping quality
        if h.mapq < min_mapq:
            continue

        # Full-span filter: alignment must cover the full reference length
        if require_full_span and not (h.r_st == 0 and h.r_en == ref_len):
            continue

        results.append(
            Alignment(
                read_id=read_id,
                read_seq=seq,
                mapq=h.mapq,
                cigar=[list(op) for op in h.cigar],
                r_st=h.r_st,
                r_en=h.r_en,
                q_st=h.q_st,
                q_en=h.q_en,
                strand=h.strand,
                reference_length=ref_len,
            )
        )

    return results


def align_reads_multi(
    reads: Iterable[tuple[str, str]],
    reference_fasta: Path,
    preset: str = "map-ont",
    min_mapq: int = 25,
    coverage_fraction: float = 0.98,
    best_n: int = 20,
) -> list[tuple[str, str, list[Alignment]]]:
    """Align reads and return ALL passing hits per read (chimeric/concatemer support).

    Unlike :func:`align_reads` which takes only the primary (first) hit,
    this function iterates all hits mappy returns for each read.  Hits that
    pass MAPQ and coverage-fraction filters are returned.  This allows
    chimeric reads or concatemers carrying two distinct amplicons to be
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
        Maximum number of secondary/supplementary alignments mappy reports
        per read.  Increase for high-copy concatemers (default 20).

    Returns
    -------
    List of ``(read_id, read_seq, hits)`` tuples where ``hits`` is a
    non-empty list of :class:`Alignment` objects for that read.  Reads with
    no passing hits are omitted.

    Notes
    -----
    Caller is responsible for deduplicating (read_id, well) assignments
    to avoid counting the same physical read twice in one well.
    """
    try:
        import mappy  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "mappy is required for alignment. Install with: pip install mappy"
        ) from exc

    if not reference_fasta.exists():
        raise FileNotFoundError(f"Reference FASTA not found: {reference_fasta}")

    aligner = mappy.Aligner(str(reference_fasta), preset=preset, best_n=best_n)
    if not aligner:
        raise ValueError(f"mappy.Aligner initialisation failed for: {reference_fasta}")

    ref_len = _get_reference_length(reference_fasta)

    results: list[tuple[str, str, list[Alignment]]] = []

    for read_id, seq in reads:
        if not seq:
            continue

        passing: list[Alignment] = []
        for raw_hit in aligner.map(seq):
            h = cast(_MappyHit, raw_hit)

            if h.mapq < min_mapq:
                continue

            ref_span = h.r_en - h.r_st
            if ref_len > 0 and ref_span / ref_len < coverage_fraction:
                continue

            passing.append(
                Alignment(
                    read_id=read_id,
                    read_seq=seq,
                    mapq=h.mapq,
                    cigar=[list(op) for op in h.cigar],
                    r_st=h.r_st,
                    r_en=h.r_en,
                    q_st=h.q_st,
                    q_en=h.q_en,
                    strand=h.strand,
                    reference_length=ref_len,
                )
            )

        if passing:
            results.append((read_id, seq, passing))

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


__all__ = ["Alignment", "align_reads", "align_reads_multi", "_get_reference_length"]
