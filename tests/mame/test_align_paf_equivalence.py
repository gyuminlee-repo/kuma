"""Differential test: SAM (``-a``) vs PAF minimap2 output for the demux path.

Why this file exists
--------------------
``align_reads_multi`` (the combinatorial-demux path) consumes only
``(r_st, r_en, q_st, q_en, strand, mapq)`` per hit; the CIGAR it stores is a
dead field there (only ``align_reads_grouped`` -> ``consensus`` reads it).  That
makes PAF look like a free win, because dropping ``-a`` also makes minimap2 skip
base-level DP alignment, which is roughly two thirds of its wall time.

It is not free.  This test pins down which PAF variant preserves output and
which does not:

* ``-c`` PAF (base-level alignment, PAF text) reproduces the SAM tuples exactly,
  in the same order, and maps ``tp:A:S`` 1:1 onto SAM ``FLAG 0x100``.  It is a
  safe drop-in, but it still pays for the DP, so it buys almost nothing.
* bare PAF (no ``-a``, no ``-c``) reports *chain* endpoints instead of
  DP-extended alignment endpoints.  The ends move by a few bases, which is
  invisible to a set comparison of read ids but decisive at the
  ``coverage_fraction`` gate, since that gate is a ratio of exactly those
  endpoints.  It also stops emitting secondary records altogether, so the
  ``FLAG 0x100`` <-> ``tp:A:S`` correspondence breaks.

The demux gate is applied to those endpoints, so the assertions below compare
the tuple lists *after* the real ``min_mapq`` / ``coverage_fraction`` filters,
not just the raw records.
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import (
    _coords_from_cigar,
    _parse_cigar,
    _resolve_minimap2,
)

_FLAG_UNMAPPED = 0x4
_FLAG_SECONDARY = 0x100
_FLAG_REVERSE = 0x10

# Demux defaults (see combinatorial_demux.demux_reads signature).
_MIN_MAPQ = 25
_COVERAGE_FRACTION = 0.98

_COMP = str.maketrans("ACGT", "TGCA")

# Reference length matches the real step-2 workload (ispS, 1683 bp) so the
# coverage gate sits at the same absolute distance from the read ends.
_REF_LEN = 1683
_ERROR_RATE = 0.06  # ONT-like substitution/indel mix
_N_READS = 400


def _rc(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _mutate(seq: str, rate: float, rng: random.Random) -> str:
    out: list[str] = []
    for base in seq:
        roll = rng.random()
        if roll < rate * 0.5:
            out.append(rng.choice("ACGT"))  # substitution
        elif roll < rate * 0.75:
            continue  # deletion
        elif roll < rate:
            out.append(base)
            out.append(rng.choice("ACGT"))  # insertion
        else:
            out.append(base)
    return "".join(out)


@pytest.fixture(scope="module")
def workload(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, int]:
    """A reference FASTA plus reads with barcode-like flanks and concatemers.

    Deterministic (fixed seeds).  Every fifth read is a two-copy concatemer, the
    shape that produces supplementary records in SAM and multiple primary chains
    in PAF; every third read is reverse-complemented.
    """
    rng = random.Random(20260801)
    ref_seq = "".join(rng.choice("ACGT") for _ in range(_REF_LEN))

    read_rng = random.Random(7)
    reads: list[str] = []
    for i in range(_N_READS):
        body = _mutate(ref_seq, _ERROR_RATE, read_rng)
        left = "".join(read_rng.choice("ACGT") for _ in range(read_rng.randint(20, 60)))
        right = "".join(read_rng.choice("ACGT") for _ in range(read_rng.randint(20, 60)))
        seq = left + body + right
        if i % 5 == 0:
            seq += _mutate(ref_seq, _ERROR_RATE, read_rng)
        if i % 3 == 0:
            seq = _rc(seq)
        reads.append(seq)

    tmp = tmp_path_factory.mktemp("paf_equiv")
    ref_fasta = tmp / "ref.fasta"
    ref_fasta.write_text(f">ref\n{ref_seq}\n", encoding="utf-8")
    reads_fasta = tmp / "reads.fasta"
    with reads_fasta.open("w", encoding="utf-8") as fh:
        for idx, seq in enumerate(reads):
            fh.write(f">{idx}\n{seq}\n")
    return ref_fasta, reads_fasta, len(ref_seq)


def _run(mode_flags: list[str], ref_fasta: Path, reads_fasta: Path) -> str:
    cmd = [
        _resolve_minimap2(),
        *mode_flags,
        "-x", "map-ont",
        "-t", "1",
        "-N", "20",
        str(ref_fasta),
        str(reads_fasta),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, shell=False)
    assert proc.returncode == 0, f"minimap2 failed: {proc.stderr[-500:]}"
    return proc.stdout


def _sam_hits(text: str) -> tuple[list[tuple[int, ...]], int]:
    """Return (hit tuples in output order, secondary-record count).

    Mirrors the filtering ``align_reads_multi`` applies to SAM: unmapped
    (0x4) and secondary (0x100) records are dropped, primary and supplementary
    are kept.
    """
    hits: list[tuple[int, ...]] = []
    n_secondary = 0
    for line in text.splitlines():
        if line.startswith("@") or not line:
            continue
        fields = line.split("\t")
        flag = int(fields[1])
        if flag & _FLAG_UNMAPPED:
            continue
        if flag & _FLAG_SECONDARY:
            n_secondary += 1
            continue
        reverse = bool(flag & _FLAG_REVERSE)
        r_st, r_en, q_st, q_en = _coords_from_cigar(
            _parse_cigar(fields[5]), int(fields[3]), reverse
        )
        hits.append(
            (int(fields[0]), r_st, r_en, q_st, q_en, -1 if reverse else 1, int(fields[4]))
        )
    return hits, n_secondary


def _paf_hits(text: str) -> tuple[list[tuple[int, ...]], int]:
    """Return (hit tuples in output order, non-primary record count).

    PAF columns used: 1 query name, 3/4 query start/end (always on the original
    forward strand, i.e. already what ``_coords_from_cigar`` flips reverse SAM
    records back to), 5 strand, 8/9 target start/end, 12 mapq.  ``tp:A:`` in the
    tag columns carries P (primary) / S (secondary) / I (inversion).
    """
    hits: list[tuple[int, ...]] = []
    n_non_primary = 0
    for line in text.splitlines():
        if not line:
            continue
        fields = line.split("\t")
        tags = [f[5:] for f in fields[12:] if f.startswith("tp:A:")]
        if tags and tags[0] != "P":
            n_non_primary += 1
            continue
        hits.append(
            (
                int(fields[0]),
                int(fields[7]),
                int(fields[8]),
                int(fields[2]),
                int(fields[3]),
                -1 if fields[4] == "-" else 1,
                int(fields[11]),
            )
        )
    return hits, n_non_primary


def _passing(hits: list[tuple[int, ...]], ref_len: int) -> list[tuple[int, ...]]:
    """Apply the demux gate (min_mapq + coverage_fraction) to hit tuples."""
    return [
        h for h in hits
        if h[6] >= _MIN_MAPQ and (h[2] - h[1]) / ref_len >= _COVERAGE_FRACTION
    ]


class TestPafEquivalence:
    def test_cigar_paf_is_a_drop_in_for_sam(
        self, workload: tuple[Path, Path, int]
    ) -> None:
        """``-c`` PAF reproduces the SAM demux tuples exactly, order included.

        Order matters, not just membership: ``is_first_hit`` in
        ``combinatorial_demux`` charges the first hit of a read to
        ``assigned_reads`` and every later one to ``chimera_splits``, so a
        reordering inside a read moves counters even when the set is equal.
        """
        ref_fasta, reads_fasta, ref_len = workload
        sam_hits, sam_secondary = _sam_hits(_run(["-a"], ref_fasta, reads_fasta))
        paf_hits, paf_secondary = _paf_hits(_run(["-c"], ref_fasta, reads_fasta))

        assert sam_hits, "SAM run produced no hits; fixture is not exercising minimap2"
        assert paf_hits == sam_hits, (
            "-c PAF diverges from SAM in the fields demux consumes"
        )
        assert _passing(paf_hits, ref_len) == _passing(sam_hits, ref_len)
        assert paf_secondary == sam_secondary, (
            "FLAG 0x100 and tp:A:S must be a 1:1 correspondence"
        )

    def test_bare_paf_moves_alignment_ends_and_fails_the_coverage_gate(
        self, workload: tuple[Path, Path, int]
    ) -> None:
        """Dropping ``-a`` without ``-c`` is NOT output-preserving.

        This is the blocking result, asserted rather than left as a comment so a
        future attempt at the same optimization sees it fail fast.  Bare PAF
        reports chain endpoints; the DP extension that ``-a``/``-c`` performs
        pushes ``r_en`` outward by a few bases, and ``coverage_fraction`` is a
        ratio of exactly those endpoints, so borderline hits flip.
        """
        ref_fasta, reads_fasta, ref_len = workload
        sam_hits, _ = _sam_hits(_run(["-a"], ref_fasta, reads_fasta))
        bare_hits, bare_secondary = _paf_hits(_run([], ref_fasta, reads_fasta))

        assert bare_hits != sam_hits, (
            "bare PAF unexpectedly matched SAM; re-measure before trusting this"
        )
        assert bare_secondary == 0, (
            "bare PAF is expected to report no tp:A:S records at all"
        )
        sam_pass = _passing(sam_hits, ref_len)
        bare_pass = _passing(bare_hits, ref_len)
        assert len(bare_pass) < len(sam_pass), (
            "bare PAF must lose hits at the coverage gate; if it no longer does, "
            "re-run the step-2 fingerprint before concluding anything"
        )

        # The loss is attributable to the span, not to mapq.
        sam_by_mapq = [h for h in sam_hits if h[6] >= _MIN_MAPQ]
        bare_by_mapq = [h for h in bare_hits if h[6] >= _MIN_MAPQ]
        assert len(bare_by_mapq) >= len(sam_by_mapq), (
            "bare PAF should not be losing hits at the mapq gate"
        )
