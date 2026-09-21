"""The consensus caller writes '-' at deletion-majority positions only.

The alphabet split this file pins: '-' means "the called molecule is missing
this reference base", 'N' means "no call" (no coverage, below depth, ambiguous,
or no majority). The threshold that separates them is the SAME majority rule
``del_majority_positions`` is built from (``DEL_MAJORITY_FRACTION``, strictly
more than half the spanning depth), not the plurality the base call uses. A
deletion that wins the vote without winning a majority stays 'N' because it is
a genuine no-call.

The plurality band is not hypothetical. Two real ONT runs put PASS wells at
``del_frac`` 0.319 to 0.467 (vault note ``260918_MAME_indel게이트_무방비구간_
두런_특성화``), which is exactly the band ``test_deletion_plurality_stays_n``
reproduces.

Counters are asserted unchanged because they are computed off masks rather
than off the emitted characters: ``consensus_n_fraction`` and the four-way
no-call decomposition must be byte-identical to what the 'N'-only caller
produced, and ``compare/verdict.py`` already subtracts
``n_no_call_deletion_majority`` from the N gate.
"""

from __future__ import annotations

from kuma_core.mame.ingest.align import _CIGAR_D, _CIGAR_M
from kuma_core.mame.ingest.consensus import (
    DEL_RUN_REPORT_BUDGET,
    call_consensus_with_metrics,
)
from kuma_core.mame.models import BarcodeRecord
from kuma_core.mame.translate.aa_translator import build_length_true_nt

from tests.mame.test_consensus import _make_aln

_REF = "ATGCATGCATGCATGCATGC"


def _del_aln(ref: str, del_start: int, del_len: int):
    """One read carrying a ``del_len`` deletion starting at ``del_start``."""
    body = ref[:del_start] + ref[del_start + del_len :]
    return _make_aln(
        read_seq=body,
        ref_len=len(ref),
        cigar=[
            [del_start, _CIGAR_M],
            [del_len, _CIGAR_D],
            [len(ref) - del_start - del_len, _CIGAR_M],
        ],
    )


def test_deletion_majority_writes_gap_not_n() -> None:
    """3 of 4 reads deleted at 3..4: majority, so the two positions are '-'."""
    alns = [_del_aln(_REF, 3, 2) for _ in range(3)] + [_make_aln(_REF, len(_REF))]
    call = call_consensus_with_metrics(alns, _REF)

    assert call.consensus_seq[3] == "-"
    assert call.consensus_seq[4] == "-"
    assert "N" not in call.consensus_seq
    assert call.del_majority_positions == (4, 5)


def test_gap_positions_equal_del_majority_positions() -> None:
    """The gap set IS the reported deletion set, coordinate for coordinate."""
    alns = [_del_aln(_REF, 8, 3) for _ in range(4)] + [_make_aln(_REF, len(_REF))]
    call = call_consensus_with_metrics(alns, _REF)

    gaps = {i + 1 for i, c in enumerate(call.consensus_seq) if c == "-"}
    assert gaps == set(call.del_majority_positions)
    assert call.consensus_seq.count("-") == call.n_del_majority_positions


def test_deletion_plurality_stays_n() -> None:
    """4 deleted / 3 A / 3 G is a deletion PLURALITY, not a majority.

    ``del_frac`` is 0.4, inside the 0.319-0.467 band two real runs put PASS
    wells in. The position is a genuine no-call, so it stays 'N' and no
    deletion is reported for it. This is the assertion that fails if the gap
    character is driven by ``argmax`` instead of the majority rule.
    """
    pos = 5
    alt_a = _REF[:pos] + "A" + _REF[pos + 1 :]
    alt_g = _REF[:pos] + "G" + _REF[pos + 1 :]
    alns = (
        [_del_aln(_REF, pos, 1) for _ in range(4)]
        + [_make_aln(alt_a, len(_REF)) for _ in range(3)]
        + [_make_aln(alt_g, len(_REF)) for _ in range(3)]
    )
    call = call_consensus_with_metrics(alns, _REF)

    assert call.consensus_seq[pos] == "N"
    assert "-" not in call.consensus_seq
    assert call.del_majority_positions == ()
    assert call.n_del_majority_positions == 0
    assert call.n_no_call_deletion == 1


def test_counters_unchanged_by_gap_character() -> None:
    """Masks, not characters: the no-call decomposition still counts gaps."""
    alns = [_del_aln(_REF, 3, 2) for _ in range(3)] + [_make_aln(_REF, len(_REF))]
    call = call_consensus_with_metrics(alns, _REF)

    assert call.n_no_call_deletion == 2
    assert call.n_no_call_deletion_majority == 2
    assert call.n_no_call_zero_depth == 0
    assert call.n_no_call_ambiguous == 0
    assert call.n_no_call_no_majority == 0
    assert (
        call.n_no_call_zero_depth
        + call.n_no_call_deletion
        + call.n_no_call_ambiguous
        + call.n_no_call_no_majority
    ) == round(call.consensus_n_fraction * len(_REF))
    assert call.consensus_n_fraction == 2 / len(_REF)


def test_uncovered_positions_stay_n() -> None:
    """A read that covers only the first half leaves the rest 'N', not '-'."""
    half = len(_REF) // 2
    aln = _make_aln(
        read_seq=_REF[:half],
        ref_len=len(_REF),
        cigar=[[half, _CIGAR_M]],
    )
    call = call_consensus_with_metrics([aln], _REF)

    assert call.consensus_seq[half:] == "N" * (len(_REF) - half)
    assert "-" not in call.consensus_seq


def test_gaps_written_even_past_the_report_budget() -> None:
    """Past ``DEL_RUN_REPORT_BUDGET`` the list is omitted; the gaps are not.

    This is the defect the change fixes: those wells reported no deletion
    anywhere, so translation never saw one.
    """
    n_runs = DEL_RUN_REPORT_BUDGET + 2
    ref = "ACGT" * (n_runs + 1)
    del_starts = [4 * i + 1 for i in range(n_runs)]

    def _multi_del():
        cigar: list[list[int]] = []
        body_parts: list[str] = []
        cursor = 0
        for start in del_starts:
            cigar.append([start - cursor, _CIGAR_M])
            body_parts.append(ref[cursor:start])
            cigar.append([1, _CIGAR_D])
            cursor = start + 1
        cigar.append([len(ref) - cursor, _CIGAR_M])
        body_parts.append(ref[cursor:])
        return _make_aln(
            read_seq="".join(body_parts), ref_len=len(ref), cigar=cigar
        )

    call = call_consensus_with_metrics([_multi_del() for _ in range(3)], ref)

    assert call.n_del_majority_positions == n_runs
    assert call.del_majority_positions == ()
    assert call.consensus_seq.count("-") == n_runs


def test_build_length_true_nt_unchanged_on_gapped_input() -> None:
    """A query already carrying '-' restores to the same molecule as an 'N' one.

    ``_apply_deletion_gaps`` writes '-' at the same coordinates, so handing it
    a sequence that already has them there is idempotent.
    """
    positions = (4, 5)
    n_query = "ATG" + "NN" + _REF[5:]
    gap_query = "ATG" + "--" + _REF[5:]

    def _record(seq: str) -> BarcodeRecord:
        from pathlib import Path

        return BarcodeRecord(
            native_barcode="nb",
            custom_barcode="1_1",
            consensus_seq=seq,
            file_size_kb=1.0,
            source_path=Path("x.fasta"),
            del_majority_positions=positions,
            n_del_majority_positions=len(positions),
        )

    from_n = build_length_true_nt(_record(n_query), n_query, 0, len(_REF))
    from_gap = build_length_true_nt(_record(gap_query), gap_query, 0, len(_REF))

    assert from_n == from_gap
    assert from_gap is not None
    assert len(from_gap) == len(_REF) - len(positions)
