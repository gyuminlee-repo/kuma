"""Compare the MAME consensus caller against ``samtools consensus``.

Why this file exists
--------------------
``kuma_core/mame/ingest/consensus.py`` is a 1,100-line consensus caller whose
only checks were self-consistency ones: the majority base at a position agrees
with the base the same code called at that position.  That cannot detect a
systematically wrong rule.  ``tests/mame/test_well_consensus_regression.py``
states the gap itself ("samtools binary-level comparison is NOT performed").
This module closes it by calling an established tool on the SAME reads and
comparing outputs.  samtools stays a test-only oracle: nothing here is vendored
or bundled, and the tests skip when the binary is absent
(``tests/mame/samtools_support.py``).

Making the comparison fair
--------------------------
Two callers only compare if they are fed the same evidence.  Three asymmetries
are removed explicitly:

1. **Read set.**  MAME filters on MAPQ >= 25 AND a full-span alignment
   (``align.py``: ``_alignment_passes``).  samtools sees every record.  A
   ``samtools view -q 25`` does not align the two: on a single-record reference
   minimap2 hands out MAPQ 60 almost universally and that gate fires on
   nothing, while the span gate discards 4-12% of reads (measured 2026-09-13,
   vault note ``260913_MAME_samtools_도입여부와_homopolymer_커버리지``).  So the
   oracle feeds samtools exactly the read ids ``align_reads`` returned.  The
   fixtures deliberately include truncated reads so that set is a strict subset
   and the restriction is exercised rather than vacuous.
2. **Flags.**  MAME skips SECONDARY (0x100) and SUPPLEMENTARY (0x800).  The
   ``samtools consensus`` default ``--ff`` is UNMAP,SECONDARY,QCFAIL,DUP, which
   keeps supplementary records.  ``--ff 0x904`` (UNMAP|SECONDARY|SUPPLEMENTARY)
   matches MAME.  Note ``-F`` is not accepted by this subcommand (verified with
   samtools 1.24: the usage text lists ``--ff/--excl-flags`` only), so the task
   of excluding flags is done with ``--ff``.
3. **Mode.**  ``-m simple --show-ins no --show-del no`` is the samtools mode
   that corresponds to the MAME design.  The default mode is bayesian and the
   ``--show-ins`` default is yes, neither of which MAME implements.

Two differences remain and cannot be removed by flags:

(a) ``-c/--call-fract`` defaults to 0.75 in simple mode while MAME adopts a
    base at >= 0.5 of depth.  ``-c 0.5`` is passed to align them.
(b) MAME drops bases below ``min_base_quality=10`` before voting; samtools
    simple mode has no equivalent (``-q/--use-qual`` weights, it does not
    gate).  The fixtures here are FASTA (no quality strings), so the MAME gate
    is inert and the difference disappears instead of being papered over.

Assumptions
-----------
* ``align_reads`` is called with its defaults (``min_mapq=25``,
  ``require_full_span=True``), i.e. the sorted-barcode path.  The analyze path
  passes ``require_full_span=False``; the oracle does not depend on which is
  used, only on comparing against the read set the call actually returned.
* Reads are error-free apart from the engineered variant, so agreement must be
  exact.  A disagreement means one of the two callers is wrong, not that a
  tolerance was too tight.
* ``minimap2`` is invoked with the same arguments as ``align._run_minimap2``
  (``-a -x map-ont``), with ``-t 1`` for determinism.
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import Alignment, _resolve_minimap2, align_reads
from kuma_core.mame.ingest.consensus import ConsensusCall, call_consensus_with_metrics
from tests.mame.minimap2_support import requires_minimap2
from tests.mame.samtools_support import requires_samtools, resolve_samtools

pytestmark = [requires_minimap2, requires_samtools]

# ---------------------------------------------------------------------------
# Fixture sequences (seeded, so a failure is reproducible)
# ---------------------------------------------------------------------------

_RNG = random.Random(20260913)
_REF = "".join(_RNG.choice("ACGT") for _ in range(250))

_SNV_POS = 120
_SNV_ALT = "T" if _REF[_SNV_POS] != "T" else "A"
_SNV_SEQ = _REF[:_SNV_POS] + _SNV_ALT + _REF[_SNV_POS + 1 :]

_MIX_POS = 80
_MIX_ALT = "T" if _REF[_MIX_POS] != "T" else "A"
_MIX_SEQ = _REF[:_MIX_POS] + _MIX_ALT + _REF[_MIX_POS + 1 :]

_DEL_POS = 150
_DEL_LEN = 3
_DEL_SEQ = _REF[:_DEL_POS] + _REF[_DEL_POS + _DEL_LEN :]

_N_READS = 24
_N_TRUNCATED = 3

_COMP = str.maketrans("ACGT", "TGCA")


def _rc(seq: str) -> str:
    return seq.translate(_COMP)[::-1]


def _well_reads(seq: str, prefix: str = "r") -> list[tuple[str, str]]:
    """Half forward, half reverse-complement, first ``_N_TRUNCATED`` clipped.

    The clipped reads lose 20 bp off one end, so the full-span gate rejects
    them and ``align_reads`` returns a strict subset of the input.
    """
    reads: list[tuple[str, str]] = []
    for i in range(_N_READS):
        body = seq[20:] if i < _N_TRUNCATED else seq
        reads.append((f"{prefix}{i}", body if i % 2 == 0 else _rc(body)))
    return reads


@pytest.fixture(scope="module")
def ref_fasta(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("samtools_oracle") / "ref.fasta"
    path.write_text(f">ref\n{_REF}\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The two callers
# ---------------------------------------------------------------------------


def _mame_consensus(
    reads: list[tuple[str, str]], ref_fasta: Path
) -> tuple[list[Alignment], ConsensusCall]:
    alignments = align_reads(reads, ref_fasta)
    return alignments, call_consensus_with_metrics(alignments, _REF)


def _samtools_consensus(reads: list[tuple[str, str]], ref_fasta: Path, tmp: Path) -> str:
    """``minimap2 -a | samtools sort -O sam | samtools consensus``.

    ``samtools consensus`` requires coordinate-sorted input (an unsorted SAM
    aborts with "BAM/SAM file is not sorted by position"), but needs neither
    BAM nor an index, so the whole chain runs through pipes.  ``-a`` keeps
    uncovered reference ends in the output, so a length difference can only
    come from indels.
    """
    reads_fasta = tmp / "oracle_reads.fasta"
    reads_fasta.write_text(
        "".join(f">{rid}\n{seq}\n" for rid, seq in reads), encoding="utf-8"
    )
    samtools = resolve_samtools()
    aligned = subprocess.run(
        [_resolve_minimap2(), "-a", "-x", "map-ont", "-t", "1",
         str(ref_fasta), str(reads_fasta)],
        capture_output=True, text=True, check=True,
    )
    sorted_sam = subprocess.run(
        [samtools, "sort", "-O", "sam", "-"],
        input=aligned.stdout, capture_output=True, text=True, check=True,
    )
    called = subprocess.run(
        [samtools, "consensus",
         "-m", "simple",        # default is bayesian, which MAME does not implement
         "-c", "0.5",           # default 0.75; MAME adopts a base at >= 0.5
         "--show-ins", "no",    # default yes; MAME drops insertions
         "--show-del", "no",
         "--ff", "0x904",       # UNMAP|SECONDARY|SUPPLEMENTARY, matching MAME
         "-a", "-f", "fasta", "-"],
        input=sorted_sam.stdout, capture_output=True, text=True, check=True,
    )
    return "".join(
        line.strip() for line in called.stdout.splitlines() if not line.startswith(">")
    ).upper()


def _oracle(
    reads: list[tuple[str, str]], ref_fasta: Path, tmp: Path
) -> tuple[ConsensusCall, str, list[Alignment]]:
    """Run both callers over the read set MAME's gates admitted."""
    alignments, call = _mame_consensus(reads, ref_fasta)
    passed_ids = {aln.read_id for aln in alignments}
    passed = [(rid, seq) for rid, seq in reads if rid in passed_ids]
    assert len(passed) == len(alignments)
    return call, _samtools_consensus(passed, ref_fasta, tmp), alignments


# ---------------------------------------------------------------------------
# Axis 1 — the two callers must agree exactly
# ---------------------------------------------------------------------------


def test_gates_drop_reads_so_the_read_set_restriction_is_live(
    ref_fasta: Path, tmp_path: Path
) -> None:
    """Guard for the fairness argument itself.

    If every read passed, feeding samtools "the ids that passed" would be the
    same as feeding it everything, and the alignment of the two inputs would be
    untested.  The truncated reads make the subset strict.
    """
    reads = _well_reads(_REF)
    alignments = align_reads(reads, ref_fasta)
    assert len(alignments) == _N_READS - _N_TRUNCATED


def test_error_free_well_matches_samtools(ref_fasta: Path, tmp_path: Path) -> None:
    call, samtools_seq, _ = _oracle(_well_reads(_REF), ref_fasta, tmp_path)
    assert call.consensus_seq == _REF
    assert call.consensus_seq == samtools_seq


def test_single_snv_well_matches_samtools(ref_fasta: Path, tmp_path: Path) -> None:
    call, samtools_seq, _ = _oracle(_well_reads(_SNV_SEQ), ref_fasta, tmp_path)
    assert call.consensus_seq[_SNV_POS] == _SNV_ALT
    assert call.consensus_seq == _SNV_SEQ
    assert call.consensus_seq == samtools_seq


def test_majority_well_matches_samtools(ref_fasta: Path, tmp_path: Path) -> None:
    """A well where the variant is carried by a majority, not by everyone.

    Roughly 87% variant.  Kept clear of both thresholds on purpose: 0.5 exactly
    would compare MAME's ``>=`` against whatever samtools means by
    "at least INT portion", and a minor fraction above ``-H`` (0.15 by default)
    would put samtools in its heterozygous branch.  What this exercises is the
    vote itself, which a broken majority rule cannot survive.
    """
    reads: list[tuple[str, str]] = []
    for i in range(_N_READS):
        seq = _REF if i in (5, 13, 21) else _MIX_SEQ
        body = seq[20:] if i < _N_TRUNCATED else seq
        reads.append((f"m{i}", body if i % 2 == 0 else _rc(body)))

    call, samtools_seq, alignments = _oracle(reads, ref_fasta, tmp_path)
    variant_support = sum(
        1 for aln in alignments if aln.read_id not in {"m5", "m13", "m21"}
    )
    assert 0.8 < variant_support / len(alignments) < 0.9
    assert call.consensus_seq[_MIX_POS] == _MIX_ALT
    assert call.consensus_seq == samtools_seq


# ---------------------------------------------------------------------------
# Axis 2 — the one difference that is intended, pinned so a change is noticed
# ---------------------------------------------------------------------------


def test_deletion_well_difference_is_representation_not_signal_loss(
    ref_fasta: Path, tmp_path: Path
) -> None:
    """MAME keeps reference length and writes ``N``; samtools gets shorter.

    This is a MAME design choice (codon-wise comparison against the expected
    workbook needs reference-fixed coordinates), not an accident, so it is
    asserted rather than tolerated: should MAME ever start emitting a
    variable-length consensus, this test says so.

    The second half is the point.  The deleted bases are absent from the MAME
    string, yet ``consensus_net_indel_bp`` carries the same number samtools
    expresses by shortening, and removing the ``N`` runs reproduces the
    samtools sequence exactly.  The representation limit costs no signal.
    """
    call, samtools_seq, _ = _oracle(_well_reads(_DEL_SEQ), ref_fasta, tmp_path)

    assert len(call.consensus_seq) == len(_REF)
    assert len(samtools_seq) == len(_REF) - _DEL_LEN
    assert call.consensus_seq.count("N") == _DEL_LEN
    # The N run may sit a base or two off _DEL_POS: minimap2 left-aligns a
    # deletion inside a repeat, so the position is asserted as a window.
    n_start = call.consensus_seq.index("N")
    assert abs(n_start - _DEL_POS) <= _DEL_LEN
    assert call.consensus_seq[n_start : n_start + _DEL_LEN] == "N" * _DEL_LEN

    assert call.consensus_net_indel_bp == len(samtools_seq) - len(_REF)
    assert call.consensus_seq.replace("N", "") == samtools_seq
