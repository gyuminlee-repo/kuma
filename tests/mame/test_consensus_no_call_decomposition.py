"""No-call decomposition, and the deletion channel that feeds translation.

The consensus writes one ``N`` for four different reasons and an operator has a
different job for each: a coverage shortfall is re-sequencing, a deletion is a
real molecule, an instrument no-call is a basecalling limit, and a split vote is
a mixed colony. ``consensus_n_fraction`` collapses all four into one number, and
that number is what ``max_consensus_n_fraction`` gates on.

These tests fix two things:

1. The four counts PARTITION the no-call positions inside the covered amplicon.
   Exclusivity and exhaustiveness are pinned by a sum identity whose right-hand
   side is read off the OUTPUT STRING rather than off the counting code, so the
   test cannot agree with a bug by sharing it.
2. The stored sequence separates the two kinds of no-call. A
   deletion-majority position is written ``-`` because the called molecule does
   not have that base; every other no-call stays ``N``. The separate
   ``del_majority_positions`` channel still travels in the header and still
   names exactly the gapped coordinates, so a legacy file that carries ``N``
   there keeps translating the way it always did.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import (
    Alignment,
    _CIGAR_D,
    _CIGAR_M,
    _QUERY_CONSUMING,
    _REF_CONSUMING,
)
from kuma_core.mame.ingest.consensus import (
    DEL_MAJORITY_FRACTION,
    DEL_RUN_REPORT_BUDGET,
    call_consensus_with_metrics,
)
from kuma_core.mame.ingest.consensus_metadata import (
    ConsensusMetadata,
    format_consensus_fasta_record,
    format_position_runs,
    parse_position_runs,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file
from kuma_core.mame.models import BarcodeRecord
from kuma_core.mame.translate.aa_translator import translate_and_diff

# A reference whose length is a multiple of three so a CDS spans it exactly.
# One RNG drawn once: a fresh ``Random(7)`` per character yields the same letter
# every time, and a homopolymer reference silently disarms every split-vote
# fixture below (a "minor" allele that happens to equal the reference joins the
# reference count instead of opposing it).
_RNG = random.Random(7)
REF = "".join(_RNG.choice("ACGT") for _ in range(180))
assert len(set(REF)) == 4


def _alts(pos: int) -> tuple[str, str]:
    """Two bases that differ from the reference at *pos*, and from each other."""
    others = [b for b in "ACGT" if b != REF[pos]]
    return others[0], others[1]


def _aln(read_seq: str, cigar: list[list[int]]) -> Alignment:
    r_en = q_en = 0
    for length, op in cigar:
        if op in _REF_CONSUMING:
            r_en += length
        if op in _QUERY_CONSUMING:
            q_en += length
    return Alignment(
        read_id="t",
        read_seq=read_seq,
        mapq=60,
        cigar=cigar,
        r_st=0,
        r_en=r_en,
        q_st=0,
        q_en=q_en,
        strand=1,
        reference_length=len(REF),
    )


def _full(seq: str = REF) -> Alignment:
    return _aln(seq, [[len(seq), _CIGAR_M]])


def _deleted(pos: int, length: int) -> Alignment:
    """A read carrying a *length* bp deletion starting at 0-based *pos*."""
    query = REF[:pos] + REF[pos + length :]
    return _aln(
        query,
        [
            [pos, _CIGAR_M],
            [length, _CIGAR_D],
            [len(REF) - pos - length, _CIGAR_M],
        ],
    )


def _sub(pos: int, base: str) -> Alignment:
    return _full(REF[:pos] + base + REF[pos + 1 :])


# Each case isolates one cause, except the two ``*_vs_split`` cases, which are
# the overlaps. Those exist because two categories that never co-occur cannot
# detect a missing exclusion term or a flipped priority: the sum and the
# per-cause counts come out the same either way.
_A70, _G70 = _alts(70)
_A90, _G90 = _alts(90)
_A110, _G110 = _alts(110)

CASES: dict[str, list[Alignment]] = {
    "wt": [_full()] * 20,
    "del1": [_deleted(60, 1)] * 18 + [_full()] * 2,
    "del3": [_deleted(60, 3)] * 18 + [_full()] * 2,
    "del_plurality": [_deleted(60, 1)] * 8 + [_full()] * 12,
    "ambiguous": [_sub(40, "N")] * 18 + [_full()] * 2,
    "no_majority": [_sub(70, _A70)] * 4 + [_sub(70, _G70)] * 3 + [_full()] * 3,
    # Deletion wins the token vote at 0.4 while nothing reaches a majority.
    "del_vs_split": [_deleted(90, 1)] * 4
    + [_sub(90, _A90)] * 3
    + [_sub(90, _G90)] * 3,
    # Same shape with the ambiguous token winning.
    "ambig_vs_split": [_sub(110, "N")] * 4
    + [_sub(110, _A110)] * 3
    + [_sub(110, _G110)] * 3,
    "empty": [],
}


def _covered_no_call_from_output(call) -> int:
    """No-call positions inside the covered amplicon, read off the output.

    Independent of the counting code under test. Both no-call characters are
    counted: the four buckets partition the no-call MASK, and writing ``-`` at
    the deletion-majority subset of it moved no position out of that mask.
    ``fasta_parser._recover_covered_n_fraction`` counts ``N`` alone because it
    reads LEGACY headers, whose files predate the gap character.
    """
    return (
        call.consensus_seq.count("N")
        + call.consensus_seq.count("-")
        - call.n_low_depth_positions
    )


# ---------------------------------------------------------------------------
# 1. Sum identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CASES))
def test_no_call_counts_partition_the_covered_no_calls(name: str) -> None:
    call = call_consensus_with_metrics(CASES[name], REF)
    total = (
        call.n_no_call_zero_depth
        + call.n_no_call_deletion
        + call.n_no_call_ambiguous
        + call.n_no_call_no_majority
    )
    assert total == _covered_no_call_from_output(call), name


def _composite(base_at_70: str) -> Alignment:
    """A read carrying a 2 bp deletion, an ambiguous base and a vote at pos 70.

    Every cause has to ride on the SAME reads, because a well has one read set.
    Splitting the vote at position 70 across otherwise identical reads is what
    puts a no-majority position in the same well as a deletion majority.
    """
    chars = list(REF)
    chars[40] = "N"
    chars[70] = base_at_70
    seq = "".join(chars)
    return _aln(
        seq[:60] + seq[62:],
        [[60, _CIGAR_M], [2, _CIGAR_D], [len(REF) - 62, _CIGAR_M]],
    )


def test_sum_identity_holds_on_a_well_carrying_every_cause_at_once() -> None:
    """One well, three causes, so a double count cannot cancel an omission."""
    alns = [_composite(_A70)] * 7 + [_composite(_G70)] * 7 + [_full()] * 6
    call = call_consensus_with_metrics(alns, REF)
    # All three causes are actually present, otherwise this proves nothing.
    assert call.n_no_call_deletion == 2
    assert call.n_no_call_ambiguous == 1
    assert call.n_no_call_no_majority == 1
    assert call.n_no_call_zero_depth == 0
    assert (
        call.n_no_call_zero_depth
        + call.n_no_call_deletion
        + call.n_no_call_ambiguous
        + call.n_no_call_no_majority
    ) == _covered_no_call_from_output(call)


def test_zero_depth_bucket_holds_the_min_depth_zero_edge() -> None:
    """``min_depth <= 0`` calls an unread position covered; it lands in bucket 1.

    This is the only way a covered position can have no evidence at all. At the
    production ``min_depth`` of 1 the bucket is always 0 and the shortfall is
    reported as ``n_low_depth_positions`` instead.
    """
    partial = _aln(REF[:100], [[100, _CIGAR_M]])
    call = call_consensus_with_metrics([partial] * 20, REF, min_depth=0)
    assert call.n_low_depth_positions == 0
    assert call.n_no_call_zero_depth == 80
    assert call.n_no_call_deletion == 0
    assert call.n_no_call_ambiguous == 0
    assert call.n_no_call_no_majority == 0
    assert (
        call.n_no_call_zero_depth
        + call.n_no_call_deletion
        + call.n_no_call_ambiguous
        + call.n_no_call_no_majority
    ) == _covered_no_call_from_output(call)


def test_the_sum_is_also_the_n_fraction_numerator() -> None:
    """The decomposition explains the number the N-fraction gate reads."""
    call = call_consensus_with_metrics(CASES["del3"], REF)
    n_covered = len(REF) - call.n_low_depth_positions
    total = (
        call.n_no_call_zero_depth
        + call.n_no_call_deletion
        + call.n_no_call_ambiguous
        + call.n_no_call_no_majority
    )
    assert call.consensus_n_fraction == pytest.approx(total / n_covered)


# ---------------------------------------------------------------------------
# 2. One cause at a time
# ---------------------------------------------------------------------------


def test_clean_well_has_no_no_calls_at_all() -> None:
    call = call_consensus_with_metrics(CASES["wt"], REF)
    assert (
        call.n_no_call_zero_depth,
        call.n_no_call_deletion,
        call.n_no_call_ambiguous,
        call.n_no_call_no_majority,
    ) == (0, 0, 0, 0)
    assert call.n_del_majority_positions == 0
    assert call.del_majority_positions == ()


def test_deletion_well_raises_only_the_deletion_count() -> None:
    call = call_consensus_with_metrics(CASES["del3"], REF)
    assert call.n_no_call_deletion == 3
    assert call.n_no_call_zero_depth == 0
    assert call.n_no_call_ambiguous == 0
    assert call.n_no_call_no_majority == 0
    # A deletion is a coverage-independent signal: the reads are all there.
    assert call.n_low_depth_positions == 0


def test_ambiguous_well_raises_only_the_ambiguous_count() -> None:
    call = call_consensus_with_metrics(CASES["ambiguous"], REF)
    assert call.n_no_call_ambiguous == 1
    assert call.n_no_call_deletion == 0
    assert call.n_no_call_no_majority == 0
    assert call.n_no_call_zero_depth == 0


def test_split_vote_well_raises_only_the_no_majority_count() -> None:
    call = call_consensus_with_metrics(CASES["no_majority"], REF)
    assert call.n_no_call_no_majority == 1
    assert call.n_no_call_deletion == 0
    assert call.n_no_call_ambiguous == 0
    assert call.n_no_call_zero_depth == 0


def test_deletion_outranks_no_majority_when_both_apply() -> None:
    """The overlap case. Deletion wins the token vote at 0.4 with no majority.

    Priority puts it in the deletion bucket: a deletion with a plurality behind
    it names a molecule, and reporting it as undifferentiated noise hides the
    one cause an operator can act on biologically.
    """
    call = call_consensus_with_metrics(CASES["del_vs_split"], REF)
    assert call.n_no_call_deletion == 1
    assert call.n_no_call_no_majority == 0
    # Below the majority rule, so it is NOT part of the called molecule and
    # carries no gap. The counter and the deletion channel disagree on purpose.
    assert call.del_majority_positions == ()
    assert call.n_del_majority_positions == 0
    assert call.consensus_net_indel_bp == 0


def test_ambiguous_outranks_no_majority_when_both_apply() -> None:
    call = call_consensus_with_metrics(CASES["ambig_vs_split"], REF)
    assert call.n_no_call_ambiguous == 1
    assert call.n_no_call_no_majority == 0


def test_uncovered_positions_are_not_in_the_decomposition() -> None:
    """They are outside the numerator and are reported as low depth instead."""
    partial = _aln(REF[:100], [[100, _CIGAR_M]])
    call = call_consensus_with_metrics([partial] * 20, REF)
    assert call.n_low_depth_positions == 80
    assert (
        call.n_no_call_zero_depth
        + call.n_no_call_deletion
        + call.n_no_call_ambiguous
        + call.n_no_call_no_majority
    ) == 0
    assert _covered_no_call_from_output(call) == 0


# ---------------------------------------------------------------------------
# 3. The deletion channel
# ---------------------------------------------------------------------------


def test_deletion_positions_are_one_based_and_match_the_majority_rule() -> None:
    call = call_consensus_with_metrics(CASES["del3"], REF)
    assert call.del_majority_positions == (61, 62, 63)
    assert call.n_del_majority_positions == 3
    # Same term the net indel is built from, so the two cannot disagree.
    assert call.consensus_net_indel_bp == -3


def test_the_majority_rule_is_the_named_constant() -> None:
    assert DEL_MAJORITY_FRACTION == 0.5
    # Strictly above, not at: an exact tie is not a majority.
    tie = [_deleted(60, 1)] * 10 + [_full()] * 10
    call = call_consensus_with_metrics(tie, REF)
    assert call.del_majority_positions == ()
    assert call.n_del_majority_positions == 0


def test_stored_gaps_are_exactly_the_deletion_majority_positions() -> None:
    """The promise this whole design rests on, in its current form.

    A gap is never written anywhere else. In particular ``del_vs_split``, whose
    deletion leads the vote at 0.4 without reaching a majority, keeps its ``N``:
    that position is a genuine no-call, not a missing base.
    """
    for name, alns in CASES.items():
        call = call_consensus_with_metrics(alns, REF)
        assert set(call.consensus_seq) <= set("ACGTN-"), name
        gaps = {i + 1 for i, c in enumerate(call.consensus_seq) if c == "-"}
        assert gaps == set(call.del_majority_positions), name
        assert len(gaps) == call.n_del_majority_positions, name


def test_position_run_encoding_round_trips() -> None:
    for positions in ((), (5,), (5, 6, 7, 20), (1, 2, 3), (3, 9, 10, 11, 40)):
        assert parse_position_runs(format_position_runs(positions)) == positions


def test_malformed_run_list_is_discarded_whole() -> None:
    """Half a deletion picture scored as the whole one is the failure mode."""
    assert parse_position_runs("5-3") == ()
    assert parse_position_runs("7,x,9") == ()
    assert parse_position_runs("9,4") == ()


def test_budget_omits_the_list_rather_than_truncating_it() -> None:
    """Past the budget the count still tells the truth and the list is absent."""
    alns = [
        _aln(
            "".join(
                REF[i] for i in range(len(REF)) if i % 2 or i >= 2 * (DEL_RUN_REPORT_BUDGET + 2)
            ),
            [
                op
                for i in range(DEL_RUN_REPORT_BUDGET + 2)
                for op in ([1, _CIGAR_D], [1, _CIGAR_M])
            ]
            + [[len(REF) - 2 * (DEL_RUN_REPORT_BUDGET + 2), _CIGAR_M]],
        )
    ] * 20
    call = call_consensus_with_metrics(alns, REF)
    assert call.n_del_majority_positions == DEL_RUN_REPORT_BUDGET + 2
    assert call.del_majority_positions == ()


# ---------------------------------------------------------------------------
# 4. FASTA header round trip
# ---------------------------------------------------------------------------


def _metadata(**kw) -> ConsensusMetadata:
    base = dict(
        depth=20,
        input_reads=20,
        aligned_reads=20,
        mapq_failed=0,
        span_failed=0,
        mixed_positions=0,
        max_minor_allele_fraction=0.0,
        low_depth_positions=0,
        consensus_n_fraction=0.0,
        low_quality_bases=0,
    )
    base.update(kw)
    return ConsensusMetadata(**base)  # type: ignore[arg-type]


def test_deletion_channel_round_trips_through_the_fasta_header(
    tmp_path: Path,
) -> None:
    call = call_consensus_with_metrics(CASES["del3"], REF)
    record = format_consensus_fasta_record(
        "1_1",
        call.consensus_seq,
        _metadata(
            del_majority_positions=call.del_majority_positions,
            n_del_majority_positions=call.n_del_majority_positions,
            n_no_call_zero_depth=call.n_no_call_zero_depth,
            n_no_call_deletion=call.n_no_call_deletion,
            n_no_call_ambiguous=call.n_no_call_ambiguous,
            n_no_call_no_majority=call.n_no_call_no_majority,
        ),
    )
    path = tmp_path / "1_1.fasta"
    path.write_text(record, encoding="utf-8")

    # The sequence line is the stored artifact and it carries the gaps.
    seq_line = path.read_text(encoding="utf-8").splitlines()[1]
    assert seq_line == call.consensus_seq
    assert seq_line[60:63] == "---"
    assert seq_line.count("-") == 3

    parsed = parse_fasta_file(path, native_barcode="NB01")
    assert parsed.del_majority_positions == (61, 62, 63)
    assert parsed.n_del_majority_positions == 3
    assert parsed.n_no_call_deletion == 3
    assert parsed.n_no_call_ambiguous == 0
    assert parsed.n_no_call_no_majority == 0
    assert parsed.n_no_call_zero_depth == 0


def test_legacy_header_without_the_new_keys_parses_to_the_old_behaviour(
    tmp_path: Path,
) -> None:
    path = tmp_path / "1_2.fasta"
    path.write_text(f">1_2 depth=10\n{REF}\n", encoding="utf-8")
    parsed = parse_fasta_file(path, native_barcode="NB01")
    assert parsed.del_majority_positions == ()
    assert parsed.n_del_majority_positions == 0
    assert parsed.n_no_call_deletion == 0
    assert parsed.n_no_call_zero_depth == 0
    assert parsed.n_no_call_ambiguous == 0
    assert parsed.n_no_call_no_majority == 0


# ---------------------------------------------------------------------------
# 5. Translation reads the channel
# ---------------------------------------------------------------------------


def _legacy_seq(consensus_seq: str) -> str:
    """The same consensus as a pre-gap-character release stored it.

    Those releases wrote ``N`` at deletion-majority positions too, so this is
    what every consensus FASTA already on disk looks like. The tests that pin
    backward compatibility have to read one of those rather than the sequence
    the current caller emits.
    """
    return consensus_seq.replace("-", "N")


def _record(consensus_seq: str, del_positions: tuple[int, ...]) -> BarcodeRecord:
    return BarcodeRecord(
        native_barcode="NB01",
        custom_barcode="1_1",
        consensus_seq=consensus_seq,
        file_size_kb=1.0,
        source_path=Path("1_1.fasta"),
        read_count=20,
        del_majority_positions=del_positions,
        n_del_majority_positions=len(del_positions),
    )


def test_one_bp_deletion_becomes_a_del_marker_instead_of_a_fake_substitution() -> None:
    call = call_consensus_with_metrics(CASES["del1"], REF)
    assert call.del_majority_positions == (61,)

    # Before: a legacy file writes the deleted base as an 'N' like any other, so
    # the NT diff calls it a substitution to N and the codon translates to the
    # ambiguous 'X', which is counted as a no-call rather than reported as a
    # change.
    old = translate_and_diff(
        _record(_legacy_seq(call.consensus_seq), ()), REF, 0, len(REF)
    )
    assert f"{REF[60]}61N" in old.observed_nt_changes
    assert not any(c.endswith("del") for c in old.observed_nt_changes)
    assert not any(c.endswith("del") for c in old.observed_aa_changes)
    assert old.n_no_call_aa == 1

    # After: the same stored sequence, plus the channel, reports a deletion.
    new = translate_and_diff(
        _record(call.consensus_seq, call.del_majority_positions), REF, 0, len(REF)
    )
    assert f"{REF[60]}61del" in new.observed_nt_changes
    assert f"{REF[60]}61N" not in new.observed_nt_changes
    deletions = [c for c in new.observed_aa_changes if c.endswith("del")]
    assert len(deletions) == 1 and deletions[0].endswith("21del")
    assert new.aa_sequence[20] == "-"
    assert new.n_no_call_aa == 0
    # The stored sequence says the same thing on its own.
    assert call.consensus_seq[60] == "-"


def test_in_frame_three_bp_deletion_reports_exactly_one_deleted_residue() -> None:
    call = call_consensus_with_metrics(CASES["del3"], REF)
    # Positions 61-63 are codon 21 exactly, so the frame is preserved.
    assert call.del_majority_positions == (61, 62, 63)
    assert call.consensus_net_indel_bp % 3 == 0

    new = translate_and_diff(
        _record(call.consensus_seq, call.del_majority_positions), REF, 0, len(REF)
    )
    deletions = [c for c in new.observed_aa_changes if c.endswith("del")]
    assert len(deletions) == 1
    assert deletions[0].endswith("21del")
    assert new.aa_sequence[20] == "-"
    # Every other residue is unchanged: no frame slip.
    assert [c for c in new.observed_aa_changes if not c.endswith("del")] == []


def test_empty_channel_reproduces_the_previous_behaviour_exactly() -> None:
    """Backward compatibility for every consensus file already on disk."""
    for name in ("wt", "del1", "ambiguous", "no_majority"):
        call = call_consensus_with_metrics(CASES[name], REF)
        record = _record(_legacy_seq(call.consensus_seq), ())
        result = translate_and_diff(record, REF, 0, len(REF))
        assert "-" not in result.aa_sequence, name
        assert not any(c.endswith("del") for c in result.observed_nt_changes), name


# ---------------------------------------------------------------------------
# 6. The two FRAMESHIFT paths do not start double-judging the same well
# ---------------------------------------------------------------------------


def test_del_markers_do_not_wake_the_second_frameshift_path() -> None:
    """``_has_frameshift`` matches ``{pos}_INDEL`` only, never ``{REF}{pos}del``.

    Two frameshift paths exist. The integer path reads
    ``consensus_net_indel_bp`` and is the one the gate was built on. The marker
    path scans ``observed_nt_changes``. Feeding deletions into the comparison
    adds ``{REF}{pos}del`` entries, and the question is whether that wakes the
    marker path and judges the same well twice. It does not: the regex requires
    a bare numeric position followed by ``_INDEL``, which only
    ``extract_nt_changes`` emits for a query LONGER than the reference. A
    reference-length consensus never produces one. No adjustment is needed, and
    widening the regex would be the change that creates the double judgement.
    """
    from kuma_core.mame.compare.verdict import _NT_INDEL_RE, _has_frameshift
    from kuma_core.mame.models import CompareParams

    assert _NT_INDEL_RE.match("A61del") is None
    assert _NT_INDEL_RE.match("61_INDEL") is not None

    call = call_consensus_with_metrics(CASES["del1"], REF)
    translated = translate_and_diff(
        _record(call.consensus_seq, call.del_majority_positions), REF, 0, len(REF)
    )
    assert any(c.endswith("del") for c in translated.observed_nt_changes)
    assert not _has_frameshift(translated, CompareParams().frameshift_window_bp)


def test_the_integer_frameshift_path_is_untouched_by_the_channel() -> None:
    """The gate input is computed from the same majority rule, before and after."""
    for name in ("wt", "del1", "del3"):
        call = call_consensus_with_metrics(CASES[name], REF)
        assert call.consensus_net_indel_bp == -call.n_del_majority_positions or (
            call.n_del_majority_positions == 0
            and call.consensus_net_indel_bp == 0
        )


# ---------------------------------------------------------------------------
# 7. Where the channel does and does not move a verdict class
# ---------------------------------------------------------------------------


def _confirmed_design_plus_deletion():
    """A well that reproduces its designed substitution and also lost a codon."""
    del_at, del_len = 120, 3  # codon 41 exactly, so the frame survives

    def read(alt: str) -> Alignment:
        chars = list(REF)
        chars[28] = alt
        seq = "".join(chars)
        return _aln(
            seq[:del_at] + seq[del_at + del_len :],
            [
                [del_at, _CIGAR_M],
                [del_len, _CIGAR_D],
                [len(REF) - del_at - del_len, _CIGAR_M],
            ],
        )

    for alt in (b for b in "ACGT" if b != REF[28]):
        alns = [read(alt)] * 18 + [_full()] * 2
        call = call_consensus_with_metrics(alns, REF)
        labels = translate_and_diff(
            _record(_legacy_seq(call.consensus_seq), ()), REF, 0, len(REF)
        ).observed_aa_changes
        # A stop would be judged as nonsense rather than by the label comparison.
        if len(labels) == 1 and "*" not in labels[0]:
            return call, labels
    raise AssertionError("no non-stop substitution available at this position")


def _verdicts(call, expected, params):
    from kuma_core.mame.compare.verdict import classify_verdict

    def record(dels, seq=None):
        return BarcodeRecord(
            native_barcode="NB",
            custom_barcode="1_1",
            consensus_seq=call.consensus_seq if seq is None else seq,
            file_size_kb=100.0,
            source_path=Path("x.fasta"),
            read_count=200,
            consensus_net_indel_bp=call.consensus_net_indel_bp,
            max_indel_event_fraction=call.max_indel_event_fraction,
            max_del_run_length=call.max_del_run_length,
            consensus_n_fraction=call.consensus_n_fraction,
            n_low_depth_positions=call.n_low_depth_positions,
            del_majority_positions=dels,
            n_del_majority_positions=len(dels),
        )

    # "before" is a LEGACY well: the deletion is an 'N' in the sequence and no
    # channel names it, which is every consensus file written before either
    # carrier existed.
    before = classify_verdict(
        translate_and_diff(
            record((), _legacy_seq(call.consensus_seq)), REF, 0, len(REF)
        ),
        expected,
        params,
    )
    after = classify_verdict(
        translate_and_diff(record(call.del_majority_positions), REF, 0, len(REF)),
        expected,
        params,
    )
    return before, after


def test_shipped_defaults_do_not_move_the_class() -> None:
    """Under the shipped gates an earlier gate always claims the well first.

    This is structural rather than evidence that the label is inert: a
    deletion-majority position pushes ``max_indel_event_fraction`` past 0.5, so
    the indel gate returns before the expected/observed comparison is reached,
    and ``max_consensus_n_fraction`` defaults to 0.0, so any surviving no-call
    routes to NO_CALL. Both were already true before the channel existed.
    """
    from kuma_core.mame.models import CompareParams

    call, expected = _confirmed_design_plus_deletion()
    before, after = _verdicts(call, expected, CompareParams())
    assert before.verdict == after.verdict
    assert "W41del" not in " ".join(
        c for c in expected
    )  # the label is new, the class is not


def test_the_deletion_moves_the_class_once_the_earlier_gates_stand_down() -> None:
    """With the indel gate off and the N gate tolerant, the deletion decides.

    Reported rather than hidden: this is the regime a caller enters by relaxing
    ``max_indel_event_fraction``, and there the well stops being a clean PASS
    because a codon it did not design for is missing.

    The legacy well stays PASS because neither carrier exists in it. A well
    called today reaches the same verdict through the gap in the sequence
    alone, which is what the third assertion pins: the channel is no longer the
    only way the deletion is seen.
    """
    from kuma_core.mame.models import CompareParams, VerdictClass

    call, expected = _confirmed_design_plus_deletion()
    params = CompareParams(
        max_indel_event_fraction=None, max_consensus_n_fraction=0.1
    )
    before, after = _verdicts(call, expected, params)
    assert before.verdict == VerdictClass.PASS
    assert after.verdict == VerdictClass.WRONG_AA
    assert "41del" in after.verdict_notes or "41-" in after.verdict_notes

    from kuma_core.mame.compare.verdict import classify_verdict

    no_channel = classify_verdict(
        translate_and_diff(
            BarcodeRecord(
                native_barcode="NB",
                custom_barcode="1_1",
                consensus_seq=call.consensus_seq,
                file_size_kb=100.0,
                source_path=Path("x.fasta"),
                read_count=200,
                consensus_net_indel_bp=call.consensus_net_indel_bp,
                max_indel_event_fraction=call.max_indel_event_fraction,
                max_del_run_length=call.max_del_run_length,
                consensus_n_fraction=call.consensus_n_fraction,
                n_low_depth_positions=call.n_low_depth_positions,
            ),
            REF,
            0,
            len(REF),
        ),
        expected,
        params,
    )
    assert no_channel.verdict == VerdictClass.WRONG_AA


# ---------------------------------------------------------------------------
# 8. The CDS offset arithmetic
# ---------------------------------------------------------------------------


def test_gaps_land_correctly_when_the_cds_does_not_start_at_zero() -> None:
    """A plasmid-style reference: the CDS is a window, not the whole record.

    ``_apply_deletion_gaps`` converts a REFERENCE position into an index inside
    the CDS slice, and this is the only new off-by-one surface. Every other test
    runs ``cds_start=0``, where the conversion is the identity.
    """
    flank = "TTTTTTTTTTTTTTTTTTTTTTTTTTTTTT"  # 30 bp, keeps the frame simple
    assert len(flank) == 30
    padded_ref = flank + REF
    cds_start, cds_end = 30, 30 + len(REF)

    call = call_consensus_with_metrics(CASES["del3"], REF)
    padded_consensus = flank + call.consensus_seq
    shifted = tuple(p + 30 for p in call.del_majority_positions)
    assert shifted == (91, 92, 93)

    result = translate_and_diff(
        _record(padded_consensus, shifted), padded_ref, cds_start, cds_end
    )
    deletions = [c for c in result.observed_aa_changes if c.endswith("del")]
    assert len(deletions) == 1
    assert deletions[0].endswith("21del")
    assert result.aa_sequence[20] == "-"
    # The flank is untouched and contributes no change.
    assert all("del" not in c for c in result.observed_nt_changes[:0] or [])
    assert f"{padded_ref[60]}61del" not in result.observed_nt_changes
    assert f"{padded_ref[90]}91del" in result.observed_nt_changes
