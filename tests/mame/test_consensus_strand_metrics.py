# ruff: noqa: S101
"""Strand and position evidence behind the minor allele.

These fields MEASURE, they do not classify.  Nothing here is a threshold, no
verdict reads any of it, and the pre-existing consensus fields must come out
bit-identical (see :class:`TestAdditiveOnly`).

Two label-free signals separate a real per-clone mixture from a
sequence-context artifact:

* the weak-strand share of the minor allele, ``min(plus, minus) / (plus +
  minus)``.  An artifact is read off one strand and sits near 0; a mixture is
  read off both and sits near 0.4.  The both-strands principle is the
  acceptance rule in ampliCan's ``amplicanConsensus`` (Labun et al. 2019,
  Genome Res 29(5), doi:10.1101/gr.244293.118).
* which reference positions carry a minor allele at all, which is what
  ``noisy_positions`` reports per well.

Fixture convention
------------------
``_aln`` takes the sequence a read contributes to the pileup, i.e. in
REFERENCE orientation, and builds the ``Alignment`` around it.  A minus-strand
read stores the reverse complement of that (the as-input orientation) and has
``q_st``/``q_en`` flipped, matching
``kuma_core.mame.ingest.align._coords_from_cigar``.  Hand-building the read in
the wrong orientation moves every vote to ``len - 1 - pos`` and reads as an
implementation bug.
"""

from __future__ import annotations

import numpy as np
import pytest

from kuma_core.mame.ingest.align import Alignment, _CIGAR_D, _CIGAR_M
from kuma_core.mame.ingest import consensus as consensus_mod
from kuma_core.mame.ingest.consensus import (
    NoisyPosition,
    _NOISY_POSITION_REPORT_BUDGET,
    _reverse_complement,
    call_consensus_with_metrics,
)

_REF = "ACGTTGCAACGGATCCTTAGCCATGAACTG"


def _aln(
    read_id: str,
    ref_oriented_seq: str,
    strand: int,
    ref_len: int | None = None,
    cigar: list[list[int]] | None = None,
) -> Alignment:
    """Full-length alignment voting ``ref_oriented_seq`` from ``strand``."""
    ref_len = len(_REF) if ref_len is None else ref_len
    n = len(ref_oriented_seq)
    read_seq = _reverse_complement(ref_oriented_seq) if strand == -1 else ref_oriented_seq
    span = (
        sum(length for length, op in cigar if op in (_CIGAR_M, _CIGAR_D))
        if cigar is not None
        else n
    )
    return Alignment(
        read_id=read_id,
        read_seq=read_seq,
        mapq=60,
        cigar=cigar if cigar is not None else [[n, _CIGAR_M]],
        r_st=0,
        r_en=span,
        q_st=0,
        q_en=n,
        strand=strand,
        reference_length=ref_len,
    )


def _alt(base: str) -> str:
    """A fixed non-reference base, so every fixture is deterministic."""
    return {"A": "C", "C": "A", "G": "T", "T": "G"}[base]


def _mutated(ref: str, edits: dict[int, str]) -> str:
    seq = list(ref)
    for pos, base in edits.items():
        seq[pos] = base
    return "".join(seq)


def _well(
    n_reads: int,
    minor: dict[int, tuple[int, int]],
    ref: str = _REF,
) -> list[Alignment]:
    """Build a well of ``n_reads`` full-length reads.

    ``minor`` maps a 0-based reference position to ``(n_plus, n_minus)``: how
    many plus- and minus-strand reads carry the alternate base there.  Reads are
    laid out plus-strand first so a position's carriers are a prefix of each
    strand block, which keeps every count in the assertions readable.
    """
    n_plus = (n_reads + 1) // 2
    reads: list[Alignment] = []
    for i in range(n_reads):
        strand = 1 if i < n_plus else -1
        rank = i if strand == 1 else i - n_plus
        edits = {
            pos: _alt(ref[pos])
            for pos, (want_plus, want_minus) in minor.items()
            if rank < (want_plus if strand == 1 else want_minus)
        }
        reads.append(_aln(f"r{i}", _mutated(ref, edits), strand))
    return reads


class TestWeakStrandShare:
    def test_minor_allele_on_one_strand_only_scores_zero(self) -> None:
        """Six minus-strand carriers, no plus-strand carrier: share 0.0.

        0.0 here is a MEASUREMENT, not a missing value: the minor allele exists
        and every read carrying it aligned on the same strand.
        """
        call = call_consensus_with_metrics(
            _well(20, {4: (0, 6)}), _REF, min_depth=1
        )
        assert call.max_minor_allele_strand_share == 0.0
        assert call.max_minor_allele_plus_count == 0
        assert call.max_minor_allele_minus_count == 6
        assert call.max_minor_allele_fraction == pytest.approx(6 / 20)

    def test_evenly_split_minor_allele_scores_one_half(self) -> None:
        call = call_consensus_with_metrics(
            _well(20, {4: (3, 3)}), _REF, min_depth=1
        )
        assert call.max_minor_allele_strand_share == pytest.approx(0.5)
        assert call.max_minor_allele_plus_count == 3
        assert call.max_minor_allele_minus_count == 3

    def test_lopsided_split_scores_the_weak_strand(self) -> None:
        """The share is the WEAK strand, so 5 plus and 1 minus give 1/6."""
        call = call_consensus_with_metrics(
            _well(20, {4: (5, 1)}), _REF, min_depth=1
        )
        assert call.max_minor_allele_strand_share == pytest.approx(1 / 6)
        assert call.max_minor_allele_plus_count == 5
        assert call.max_minor_allele_minus_count == 1

    def test_no_eligible_position_reports_unknown_not_zero(self) -> None:
        """A clean well: ``None`` (unknown), never 0.0 (one-strand artifact).

        Conflating the two would make every unanimous well look like the
        strongest possible artifact.
        """
        call = call_consensus_with_metrics(_well(20, {}), _REF, min_depth=1)
        assert call.max_minor_allele_strand_share is None
        assert call.noisy_positions == ()
        assert call.max_minor_allele_plus_count == 0
        assert call.max_minor_allele_minus_count == 0

    def test_shallow_well_below_mix_min_depth_is_unknown(self) -> None:
        """Under ``mix_min_depth`` nothing is eligible, so the share is unknown.

        This is the case the plus/minus counters exist for: a share alone cannot
        distinguish "no strand information" from "one strand only".
        """
        call = call_consensus_with_metrics(
            _well(4, {4: (0, 2)}), _REF, min_depth=1, mix_min_depth=10
        )
        assert call.max_minor_allele_strand_share is None
        assert call.noisy_positions == ()


class TestNoisyPositionRecord:
    def test_position_is_one_based(self) -> None:
        """0-based pileup index 7 is reported as 8.

        Matches ``extract_nt_changes`` in translate/aa_translator.py, the
        repository's user-facing nucleotide coordinate convention.
        """
        call = call_consensus_with_metrics(
            _well(20, {7: (2, 4)}), _REF, min_depth=1
        )
        assert [p.position for p in call.noisy_positions] == [8]
        (record,) = call.noisy_positions
        assert record.plus_count == 2
        assert record.minus_count == 4
        assert record.depth == 20
        assert record.minor_fraction == pytest.approx(6 / 20)
        assert record.weak_strand_share == pytest.approx(2 / 6)

    def test_weak_strand_share_is_none_without_support(self) -> None:
        """Unreachable through the pileup, still must not read as 0.0."""
        assert (
            NoisyPosition(
                position=1, minor_fraction=0.0, depth=20, plus_count=0, minus_count=0
            ).weak_strand_share
            is None
        )

    def test_top_record_agrees_with_the_scalar_fields(self) -> None:
        """``noisy_positions[0]`` is the position the scalars were read off.

        Both use "highest minor fraction, lowest position on a tie", so a
        disagreement means the two code paths drifted apart.
        """
        call = call_consensus_with_metrics(
            _well(20, {3: (1, 1), 7: (4, 2), 11: (0, 3)}), _REF, min_depth=1
        )
        top = call.noisy_positions[0]
        assert top.minor_fraction == pytest.approx(call.max_minor_allele_fraction)
        assert top.plus_count == call.max_minor_allele_plus_count
        assert top.minus_count == call.max_minor_allele_minus_count
        assert top.weak_strand_share == pytest.approx(
            call.max_minor_allele_strand_share
        )


class TestRankingAndBudget:
    """Fourteen eligible positions, strictly decreasing minor fractions."""

    _COUNTS = [14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]

    def _call(self) -> object:
        # 40 reads, position i carrying _COUNTS[i] alternate reads split as
        # evenly as the count allows, so no position is accidentally one-strand.
        minor = {
            i: ((c + 1) // 2, c // 2) for i, c in enumerate(self._COUNTS)
        }
        return call_consensus_with_metrics(_well(40, minor), _REF, min_depth=1)

    def test_exactly_the_budget_is_returned(self) -> None:
        call = self._call()
        assert len(self._COUNTS) > _NOISY_POSITION_REPORT_BUDGET, (
            "fixture stopped exceeding the budget; truncation is untested"
        )
        assert len(call.noisy_positions) == _NOISY_POSITION_REPORT_BUDGET

    def test_ranked_by_minor_fraction_descending(self) -> None:
        call = self._call()
        fractions = [p.minor_fraction for p in call.noisy_positions]
        assert fractions == sorted(fractions, reverse=True)
        # Strictly decreasing counts mean the ranking is exactly plate order
        # here, 1-based.
        assert [p.position for p in call.noisy_positions] == list(
            range(1, _NOISY_POSITION_REPORT_BUDGET + 1)
        )

    def test_mixed_count_is_the_untruncated_total(self) -> None:
        """The budget truncates the REPORT, never the count over the gate."""
        call = self._call()
        over_gate = sum(1 for c in self._COUNTS if c / 40 >= 0.20)
        assert over_gate == 7
        assert call.n_mixed_positions == over_gate
        # And the truncated report is larger than the over-gate set, which is
        # the point: positions below the gate are exactly what this surfaces.
        assert len(call.noisy_positions) > over_gate

    def test_mixed_count_survives_truncation(self) -> None:
        """More over-gate positions than the budget: the count must not truncate.

        The fixture above cannot catch this. It has 7 over-gate positions and a
        budget of 10, so an implementation that counted the mixed positions off
        the TRUNCATED report would return 7 as well, and correct and broken code
        would be indistinguishable. Here 12 positions clear the gate, so the two
        answers differ: 12 if ``n_mixed_positions`` is read off the eligible
        pool, 10 if it is read off the report.
        """
        counts = [19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6]
        over_gate = sum(1 for c in counts if c / 40 >= 0.20)
        assert over_gate == 12
        assert over_gate > _NOISY_POSITION_REPORT_BUDGET, (
            "fixture no longer separates the two implementations"
        )
        call = call_consensus_with_metrics(
            _well(40, {i: ((c + 1) // 2, c // 2) for i, c in enumerate(counts)}),
            _REF,
            min_depth=1,
        )
        assert call.n_mixed_positions == over_gate
        assert len(call.noisy_positions) == _NOISY_POSITION_REPORT_BUDGET

    def test_ties_break_on_ascending_position(self) -> None:
        call = call_consensus_with_metrics(
            _well(20, {12: (2, 2), 5: (2, 2), 9: (3, 3)}), _REF, min_depth=1
        )
        assert [p.position for p in call.noisy_positions] == [10, 6, 13]

    def test_fewer_than_the_budget_when_fewer_are_eligible(self) -> None:
        call = call_consensus_with_metrics(
            _well(20, {2: (1, 1), 6: (2, 2)}), _REF, min_depth=1
        )
        assert len(call.noisy_positions) == 2


class TestTieColumnIsDeterministic:
    def test_three_way_tie_picks_the_stable_argsort_column(self) -> None:
        """Equal C/G/T counts must name the same minor allele on every machine.

        ``kind="stable"`` keeps tied columns in A < C < G < T order, so among a
        three-way tie rank -1 is the highest tied column and rank -2 the next
        one down.  Here the A/C/G/T row is [0, 5, 5, 5], so the major is T and
        the minor is G.  WHICH tied column gets named is arbitrary; that it is
        the same column on every numpy version is not, and that is what this
        pins.

        Only the G carriers are minus-strand, so the reported counts identify
        the column unambiguously: G gives (0, 5) while C or T would give (5, 0).
        """
        ref_pos = 4
        assert _REF[ref_pos] == "T"
        reads: list[Alignment] = []
        # 5 plus-strand reads voting the reference base (T) ...
        for i in range(5):
            reads.append(_aln(f"ref{i}", _REF, 1))
        # ... 5 plus-strand reads voting C ...
        for i in range(5):
            reads.append(_aln(f"c{i}", _mutated(_REF, {ref_pos: "C"}), 1))
        # ... and 5 minus-strand reads voting G.
        for i in range(5):
            reads.append(_aln(f"g{i}", _mutated(_REF, {ref_pos: "G"}), -1))

        call = call_consensus_with_metrics(reads, _REF, min_depth=1)
        (record,) = [p for p in call.noisy_positions if p.position == ref_pos + 1]
        assert record.minor_fraction == pytest.approx(5 / 15)
        assert (record.plus_count, record.minus_count) == (0, 5)

    def test_numpy_stable_argsort_tie_order_is_what_the_code_assumes(self) -> None:
        """Pins the numpy behaviour the comment in consensus.py relies on."""
        row = np.array([[5, 5, 5, 0]], dtype=np.int64)
        order = np.argsort(row, axis=1, kind="stable")[0]
        assert list(order) == [3, 0, 1, 2]


class TestBatchInvariance:
    """The minus accumulator is merged across batches; prove that merge.

    At the shipped budget these wells are a single batch, so the per-batch
    ``is_minus`` masking would otherwise never be exercised on more than one
    batch.  A budget of 1 puts every read in its own batch, the worst case.
    """

    def test_every_new_field_survives_one_read_per_batch(self) -> None:
        reads = _well(
            40,
            {i: ((c + 1) // 2, c // 2) for i, c in enumerate([14, 11, 9, 6, 3, 1])},
        )
        original = consensus_mod._BATCH_BASE_BUDGET
        try:
            results = []
            for budget in (original, 1, 7):
                consensus_mod._BATCH_BASE_BUDGET = budget
                results.append(
                    call_consensus_with_metrics(reads, _REF, min_depth=1)
                )
        finally:
            consensus_mod._BATCH_BASE_BUDGET = original

        assert len(consensus_mod._batch_bounds(reads)) == 1, (
            "shipped budget already splits this fixture; the comparison is not "
            "between one batch and many"
        )
        base = results[0]
        assert base.noisy_positions, "fixture produced no eligible position"
        for budget, got in zip((1, 7), results[1:]):
            assert got.max_minor_allele_strand_share == (
                base.max_minor_allele_strand_share
            ), f"budget {budget}"
            assert got.max_minor_allele_plus_count == (
                base.max_minor_allele_plus_count
            ), f"budget {budget}"
            assert got.max_minor_allele_minus_count == (
                base.max_minor_allele_minus_count
            ), f"budget {budget}"
            assert got.noisy_positions == base.noisy_positions, f"budget {budget}"

    def test_batching_actually_splits_this_fixture(self) -> None:
        reads = _well(40, {4: (3, 3)})
        original = consensus_mod._BATCH_BASE_BUDGET
        try:
            consensus_mod._BATCH_BASE_BUDGET = 1
            assert len(consensus_mod._batch_bounds(reads)) == len(reads)
        finally:
            consensus_mod._BATCH_BASE_BUDGET = original


# ---------------------------------------------------------------------------
# The change is additive: nothing that existed before moves.
# ---------------------------------------------------------------------------

_DESIGNED_POS = 10
_MIXED_POS = 20
_DEL_START, _DEL_LEN = 5, 2


def _regression_well() -> list[Alignment]:
    """One well exercising every pre-existing field this change could touch.

    18 of 20 reads carry a designed substitution at ``_DESIGNED_POS`` (so the
    consensus calls a variant and ``min_variant_support`` is measurable), 6
    carry an unrelated minor allele at ``_MIXED_POS`` (over the mixed gate), and
    12 carry a 2 bp deletion (so ``consensus_net_indel_bp`` is negative).
    """
    designed = _alt(_REF[_DESIGNED_POS])
    mixed = _alt(_REF[_MIXED_POS])
    reads: list[Alignment] = []
    for i in range(20):
        edits: dict[int, str] = {}
        if i < 18:
            edits[_DESIGNED_POS] = designed
        if i < 6:
            edits[_MIXED_POS] = mixed
        seq = _mutated(_REF, edits)
        strand = 1 if i % 2 == 0 else -1
        if i < 12:
            cigar = [
                [_DEL_START, _CIGAR_M],
                [_DEL_LEN, _CIGAR_D],
                [len(_REF) - _DEL_START - _DEL_LEN, _CIGAR_M],
            ]
            seq = seq[:_DEL_START] + seq[_DEL_START + _DEL_LEN:]
            reads.append(_aln(f"d{i}", seq, strand, cigar=cigar))
        else:
            reads.append(_aln(f"r{i}", seq, strand))
    return reads


class TestAdditiveOnly:
    """Literals below were read off the pre-change module at HEAD.

    They are hardcoded rather than recomputed so this test cannot drift with the
    implementation it guards.
    """

    def test_preexisting_fields_are_unchanged(self) -> None:
        call = call_consensus_with_metrics(
            _regression_well(), _REF, min_depth=1
        )
        expected_seq = (
            _REF[:_DEL_START]
            + "N" * _DEL_LEN
            + _mutated(_REF, {_DESIGNED_POS: _alt(_REF[_DESIGNED_POS])})[
                _DEL_START + _DEL_LEN:
            ]
        )
        assert call.consensus_seq == expected_seq
        assert call.n_mixed_positions == 1
        assert call.max_minor_allele_fraction == pytest.approx(6 / 20)
        assert call.median_minor_allele_fraction == pytest.approx(0.2)
        assert call.min_variant_support == pytest.approx(18 / 20)
        assert call.n_variant_positions == 1
        assert call.min_variant_support_depth == 20
        assert call.consensus_net_indel_bp == -_DEL_LEN
        assert call.max_del_run_length == _DEL_LEN
        assert call.n_low_depth_positions == 0
        assert call.consensus_n_fraction == pytest.approx(_DEL_LEN / len(_REF))

    def test_the_regression_well_still_exercises_every_field(self) -> None:
        """Guards the test above: a fixture that stopped producing a variant, a
        mixed position or a deletion would pass it vacuously."""
        call = call_consensus_with_metrics(
            _regression_well(), _REF, min_depth=1
        )
        assert call.n_mixed_positions > 0
        assert call.n_variant_positions > 0
        assert call.consensus_net_indel_bp < 0
        assert "N" in call.consensus_seq
