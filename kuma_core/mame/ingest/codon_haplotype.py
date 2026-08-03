"""Per-codon read-level haplotype (3-mer) counting and its on-disk sidecar.

Why a haplotype and not a per-position base count
-------------------------------------------------
A saturation library puts many designed variants on ONE codon.  Per-position
base counts cannot separate them, because the variants share letters within the
codon.  Measured on the IspS R560 plate (reference codon CGC), counting each
reference position independently and taking the per-position minimum over the
three mutated positions over-reports the rarest variants the most::

    variant  codon   read-level count   per-position minimum   error
    R560L    CTG              9,446                  9,446     exact
    R560N    AAC              5,380                  5,380     exact
    R560D    GAC              4,181                  5,163     1.2x
    R560V    GTC                982                  5,163     5.3x

R560V shares ``G`` at codon offset 0 with GAC and ``T`` at offset 1 with CTG, so
a per-position estimate inherits the counts of its neighbours.  The error is
largest exactly where the measurement matters, on the rarest variant.  Counting
the three bases a single read carries, as one unit, removes the ambiguity.

What is counted
---------------
One vote per (read, codon) pair, and only when that read supplies all three
bases of the codon as unambiguous A/C/G/T calls that survived the pileup base
quality gate.  A read that carries a deletion, an ``N``, a low quality base, or
simply does not span the codon contributes nothing to that codon.  ``depth`` is
therefore the number of reads that produced a complete 3-mer at that codon and
is the correct denominator for a haplotype fraction.  It is smaller than the
pileup depth used by the consensus caller, which counts each position
separately.

Insertions are ignored, matching the consensus caller: the pileup is
reference-length and an inserted base has no reference coordinate.

Codon grid
----------
Codon ``i`` occupies reference positions ``3i``, ``3i+1``, ``3i+2``, i.e. the
grid is anchored at reference position ``frame_offset`` (currently always 0).
The consensus stage does not know the CDS coordinates, so the reader checks the
grid against ``cds_start`` and reports a mismatch rather than returning numbers
from the wrong frame.

Storage bound
-------------
A full table is ``n_codons`` x 64 counts per well and does not belong on disk.
The sidecar keeps, per well:

- ``depth``   one integer per codon (the denominator, always present),
- ``maj``     the majority 3-mer of every codon, concatenated,
- ``maj_n``   its count, one integer per codon,
- ``codons``  for codons that have them, the top ``top_k`` NON-majority 3-mers
  whose count reaches ``min_count``.

A 3-mer that is not retained still yields a usable answer rather than silence:
its count is at most ``min(smallest retained count, residual)``, where the
residual is ``depth`` minus everything retained.  Callers report that as an
upper bound.  See :meth:`WellCodonHaplotypes.lookup`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from kuma_core.shared.atomic_write import atomic_write_text

#: Sidecar file name, written into the same per-unit directory as the per-well
#: consensus FASTA.  The leading dot plus ``.json`` suffix keeps it out of the
#: ``*.fasta`` / ``*.fa`` / ``*.fas`` globs that drive the stage-marker
#: inventory guard, exactly like ``.demux_consensus_complete.json``.
SIDECAR_FILENAME = ".codon_haplotypes.json"
SCHEMA_VERSION = 1
STAGE_NAME = "codon_haplotype"

#: Bases that can take part in a haplotype.  ``N`` is deliberately absent: an
#: ambiguous call makes the whole codon incomplete for that read rather than
#: producing an ``N``-bearing 3-mer that no design can ever match.
_BASES = "ACGT"
_N_BASES = 4
_N_HAPLOTYPES = _N_BASES**3

#: ``index -> 3-mer`` for every unambiguous codon, in the order produced by
#: ``b0 * 16 + b1 * 4 + b2`` over ``_BASES``.
_HAPLOTYPE_SEQS: tuple[str, ...] = tuple(
    f"{a}{b}{c}" for a in _BASES for b in _BASES for c in _BASES
)
_HAPLOTYPE_INDEX: dict[str, int] = {
    seq: idx for idx, seq in enumerate(_HAPLOTYPE_SEQS)
}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_top_k() -> int:
    """Non-majority 3-mers retained per codon.

    See ``notes/perf/codon-haplotype.md`` for the measurement that fixes the
    default.  ``0`` keeps only the majority; a negative value retains every
    3-mer that reaches ``min_count`` and exists for calibration runs.
    """
    return _env_int("KUMA_MAME_CODON_TOP_K", 8)


def _default_min_count() -> int:
    """Smallest non-majority count worth writing down.

    A 3-mer seen once cannot be told apart from a single read error, so the
    default floor is 2.  Lowering it to 1 is what the calibration run does.
    """
    return max(1, _env_int("KUMA_MAME_CODON_MIN_COUNT", 2))


# ---------------------------------------------------------------------------
# Counting (vectorised, called from the consensus pileup)
# ---------------------------------------------------------------------------


def new_counts(n_codons: int) -> np.ndarray:
    """Return a zeroed ``(n_codons, 64)`` haplotype accumulator."""
    return np.zeros((max(0, n_codons), _N_HAPLOTYPES), dtype=np.int64)


def accumulate(
    counts: np.ndarray,
    ref_pos: np.ndarray,
    read_idx: np.ndarray,
    base_code: np.ndarray,
    n_reads: int,
) -> None:
    """Fold one batch of pileup votes into *counts*, in place.

    Parameters mirror what the consensus pileup already has in hand after it
    has applied the quality and alphabet filters:

    ``ref_pos``
        Reference position of each surviving aligned base.
    ``read_idx``
        Index of the read that contributed it, within this batch.
    ``base_code``
        Base as a column index into ``consensus._TOKENS`` (``A C G T N -``);
        anything at or above 4 (``N``) is dropped here, which is what makes an
        ambiguous base break the codon rather than corrupt it.
    ``n_reads``
        Number of reads in the batch, i.e. the range of ``read_idx``.

    A read votes at most once per reference position (reference-consuming CIGAR
    ops never overlap), so a (read, codon, offset) cell is written at most once
    and the scatter below cannot lose a vote to a duplicate index.
    """
    n_codons = counts.shape[0]
    if n_codons == 0 or n_reads == 0 or ref_pos.size == 0:
        return

    unambiguous = base_code < _N_BASES
    if not bool(unambiguous.any()):
        return
    rp = ref_pos[unambiguous]
    rd = read_idx[unambiguous]
    bc = base_code[unambiguous].astype(np.int64)

    codon = rp // 3
    in_grid = codon < n_codons
    if not bool(in_grid.all()):
        codon = codon[in_grid]
        rd = rd[in_grid]
        bc = bc[in_grid]
        rp = rp[in_grid]
    if codon.size == 0:
        return
    offset = rp - codon * 3

    # One (read, codon) cell per column, three offset planes.  255 marks "this
    # read supplied no usable base here", so a cell is complete only when all
    # three planes were written.
    n_cells = n_reads * n_codons
    planes = np.full((3, n_cells), 255, dtype=np.uint8)
    cell = rd * n_codons + codon
    planes[offset, cell] = bc.astype(np.uint8)

    # Completeness in one pass rather than three comparisons and two ANDs: a
    # written plane holds 0..3, so a complete cell sums to at most 9 while any
    # cell still carrying the 255 sentinel sums to at least 255. The widths are
    # chosen so the sum cannot wrap (3 * 255 = 765 < 32767).
    occupancy = planes.sum(axis=0, dtype=np.int16)
    filled = np.flatnonzero(occupancy < 255)
    if filled.size == 0:
        return
    hap = (
        planes[0][filled].astype(np.int64) * (_N_BASES * _N_BASES)
        + planes[1][filled].astype(np.int64) * _N_BASES
        + planes[2][filled].astype(np.int64)
    )
    flat = (filled % n_codons) * _N_HAPLOTYPES + hap
    # bincount already returns int64; an astype here would copy 35 KB per batch
    # for nothing.
    counts.reshape(-1)[:] += np.bincount(flat, minlength=n_codons * _N_HAPLOTYPES)


# ---------------------------------------------------------------------------
# Bounded summary (what actually reaches disk)
# ---------------------------------------------------------------------------


def summarize(
    counts: np.ndarray,
    top_k: int | None = None,
    min_count: int | None = None,
) -> dict[str, Any]:
    """Reduce a full ``(n_codons, 64)`` table to the bounded sidecar payload.

    The emitted ordering is fully determined by the counts (count descending,
    then 3-mer ascending), so two runs over the same reads produce
    byte-identical output and the harness tree hash stays meaningful.
    """
    k = _default_top_k() if top_k is None else top_k
    floor = _default_min_count() if min_count is None else max(1, min_count)
    n_codons = int(counts.shape[0])
    if n_codons == 0:
        return {"depth": [], "maj": "", "maj_n": [], "codons": {}}

    depth = counts.sum(axis=1)
    maj_idx = counts.argmax(axis=1)
    maj_n = counts[np.arange(n_codons), maj_idx]
    # A codon nobody covered has an all-zero row; argmax reports column 0, which
    # would advertise "AAA" as the majority of an empty codon.  Blank it out.
    empty = depth == 0

    maj_parts: list[str] = []
    for i in range(n_codons):
        maj_parts.append("NNN" if empty[i] else _HAPLOTYPE_SEQS[int(maj_idx[i])])

    codons: dict[str, list[list[Any]]] = {}
    # Only rows that actually hold a non-majority vote are worth inspecting.
    interesting = np.flatnonzero((depth - maj_n) >= floor)
    for i in interesting:
        row = counts[i]
        idx = int(maj_idx[i])
        candidates = [
            (int(row[j]), _HAPLOTYPE_SEQS[j])
            for j in np.flatnonzero(row >= floor)
            if j != idx
        ]
        if not candidates:
            continue
        candidates.sort(key=lambda item: (-item[0], item[1]))
        retained = candidates if k < 0 else candidates[:k]
        if not retained:
            continue
        codons[str(int(i))] = [[seq, cnt] for cnt, seq in retained]

    return {
        "depth": [int(v) for v in depth],
        "maj": "".join(maj_parts),
        "maj_n": [int(v) for v in maj_n],
        "codons": codons,
    }


def empty_summary(n_codons: int) -> dict[str, Any]:
    """Summary for a well with no usable reads: every codon at depth 0."""
    n = max(0, n_codons)
    return {
        "depth": [0] * n,
        "maj": "NNN" * n,
        "maj_n": [0] * n,
        "codons": {},
    }


# ---------------------------------------------------------------------------
# Sidecar I/O
# ---------------------------------------------------------------------------


def sidecar_path(unit_dir: Path) -> Path:
    return Path(unit_dir) / SIDECAR_FILENAME


def write_sidecar(
    unit_dir: Path,
    unit: str,
    per_well: Mapping[str, dict[str, Any]],
    n_codons: int,
    frame_offset: int = 0,
    top_k: int | None = None,
    min_count: int | None = None,
) -> Path:
    """Write the per-unit sidecar.

    Must be written BEFORE the stage completion marker: the marker is the
    commit point of the unit, so anything it implies has to already be on disk.
    """
    payload = {
        "schema_version": SCHEMA_VERSION,
        "stage": STAGE_NAME,
        "unit": str(unit),
        "frame_offset": int(frame_offset),
        "codon_count": int(n_codons),
        "top_k": _default_top_k() if top_k is None else int(top_k),
        "min_count": _default_min_count() if min_count is None else int(min_count),
        "wells": {str(w): v for w, v in sorted(per_well.items())},
    }
    return atomic_write_text(
        sidecar_path(unit_dir),
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False),
        fsync=False,
    )


@dataclass(frozen=True)
class CodonObservation:
    """What the sidecar can say about one (codon, 3-mer) question."""

    depth: int
    count: int
    #: True when *count* is the recorded number of reads, False when the 3-mer
    #: fell outside the retained set and *count* is only an upper bound.
    exact: bool
    majority_seq: str
    majority_count: int

    @property
    def fraction(self) -> float:
        return self.count / self.depth if self.depth else 0.0

    @property
    def majority_fraction(self) -> float:
        return self.majority_count / self.depth if self.depth else 0.0


@dataclass(frozen=True)
class WellCodonHaplotypes:
    """Parsed per-well haplotype evidence."""

    depth: tuple[int, ...]
    majority: str
    majority_count: tuple[int, ...]
    retained: Mapping[int, tuple[tuple[str, int], ...]]
    frame_offset: int = 0

    def lookup(self, codon_index: int, codon_seq: str) -> CodonObservation | None:
        """Return the evidence for *codon_seq* at *codon_index*.

        ``None`` means the codon is outside the recorded grid; the caller must
        report that as missing information rather than as a zero observation.
        """
        if codon_index < 0 or codon_index >= len(self.depth):
            return None
        depth = self.depth[codon_index]
        maj_seq = self.majority[codon_index * 3 : codon_index * 3 + 3]
        maj_n = self.majority_count[codon_index]
        query = codon_seq.upper()
        if query == maj_seq:
            return CodonObservation(depth, maj_n, True, maj_seq, maj_n)
        entries = self.retained.get(codon_index, ())
        for seq, count in entries:
            if seq == query:
                return CodonObservation(depth, count, True, maj_seq, maj_n)
        # Not retained.  Everything recorded is accounted for, so the query can
        # only live in the residual, and it cannot exceed the smallest count
        # that WAS worth retaining.
        residual = depth - maj_n - sum(count for _seq, count in entries)
        bound = residual
        if entries:
            bound = min(bound, entries[-1][1])
        bound = max(0, bound)
        # A zero bound is not a bound, it is a measurement: with no residual mass
        # left, every read at this codon has been attributed, so the query was
        # seen exactly zero times. Reporting that as "at most 0" would hide a
        # real negative result behind hedging.
        return CodonObservation(depth, bound, bound == 0, maj_seq, maj_n)


def _parse_well(raw: Mapping[str, Any], frame_offset: int) -> WellCodonHaplotypes:
    depth = tuple(int(v) for v in raw.get("depth", ()))
    maj = str(raw.get("maj", ""))
    maj_n = tuple(int(v) for v in raw.get("maj_n", ()))
    retained: dict[int, tuple[tuple[str, int], ...]] = {}
    for key, entries in (raw.get("codons") or {}).items():
        try:
            idx = int(key)
        except (TypeError, ValueError):
            continue
        retained[idx] = tuple(
            (str(seq).upper(), int(count)) for seq, count in entries
        )
    return WellCodonHaplotypes(
        depth=depth,
        majority=maj,
        majority_count=maj_n,
        retained=retained,
        frame_offset=frame_offset,
    )


def read_sidecar(unit_dir: Path) -> dict[str, WellCodonHaplotypes] | None:
    """Return ``{well: WellCodonHaplotypes}`` for *unit_dir*, or ``None``.

    ``None`` covers both "no sidecar" (a consensus tree produced before this
    stage existed) and "unreadable sidecar".  Both mean the same thing to a
    caller: this well carries no haplotype evidence, and that has to be said out
    loud rather than rendered as a zero.
    """
    path = sidecar_path(unit_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    wells = raw.get("wells")
    if not isinstance(wells, dict):
        return None
    frame_offset = int(raw.get("frame_offset", 0) or 0)
    out: dict[str, WellCodonHaplotypes] = {}
    for well, payload in wells.items():
        if isinstance(payload, dict):
            out[str(well)] = _parse_well(payload, frame_offset)
    return out


def codon_index_for_aa_position(
    aa_position: int, cds_start: int, frame_offset: int = 0
) -> int | None:
    """Map a 1-based AA position to a codon index on the recorded grid.

    The sidecar grid is anchored at reference position ``frame_offset`` and
    steps by 3, so it can only answer for a CDS that starts on the same grid.
    Returns ``None`` when it does not, which the caller must report as missing
    information: silently rounding would answer with a neighbouring codon.
    """
    if aa_position < 1:
        return None
    ref_offset = cds_start + (aa_position - 1) * 3
    if (ref_offset - frame_offset) % 3 != 0:
        return None
    index = (ref_offset - frame_offset) // 3
    return index if index >= 0 else None


def haplotype_index(codon_seq: str) -> int | None:
    """Column index of *codon_seq* in the accumulator, or None if ambiguous."""
    return _HAPLOTYPE_INDEX.get(codon_seq.upper())


def haplotype_seqs() -> Iterable[str]:
    return _HAPLOTYPE_SEQS


__all__ = [
    "SCHEMA_VERSION",
    "SIDECAR_FILENAME",
    "STAGE_NAME",
    "CodonObservation",
    "WellCodonHaplotypes",
    "accumulate",
    "codon_index_for_aa_position",
    "empty_summary",
    "haplotype_index",
    "haplotype_seqs",
    "new_counts",
    "read_sidecar",
    "sidecar_path",
    "summarize",
    "write_sidecar",
]
