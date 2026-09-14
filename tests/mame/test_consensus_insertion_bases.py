"""The insertion channel: keeping WHAT was inserted, not only how much.

MAME detects every length change. ``consensus_net_indel_bp`` carried the sign and
the size of all of them in the 3-arm measurement, real data and spike-in alike.
What it could not carry is the SEQUENCE, because the pileup counted inserting
reads (``insertion_events``) and summed their lengths (``insertion_bp``) and
stored the bases nowhere.

That gap has a name: a block substitution. minimap2 writes a swapped codon as an
insertion next to a deletion, so the deletion becomes an 'N' and the insertion is
dropped, and the net indel is 0. The length is reported correctly and the bases
are absent, which is the one case where a zero net indel does not mean nothing
happened.

These tests fix four things:

1. The majority insertion sequence is recovered, per anchor, by both the
   vectorized and the scalar accumulator, and the two agree.
2. The STORED sequence does not move. Insertions stay out of it, exactly as
   before, and the channel travels beside it.
3. A header round-trips, and a header written before the keys existed produces
   the same record a clean well produces.
4. The length-true sequence rebuilt at translation time equals the molecule,
   including the block-substitution case where neither the stored sequence nor
   the net indel can express it.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest

from kuma_core.mame.ingest.align import (
    Alignment,
    _CIGAR_D,
    _CIGAR_I,
    _CIGAR_M,
)
from kuma_core.mame.ingest.consensus import (
    DEL_MAJORITY_FRACTION,
    _accumulate,
    _accumulate_all,
    call_consensus_with_metrics,
)
from kuma_core.mame.ingest.consensus_metadata import (
    ConsensusMetadata,
    format_consensus_fasta_record,
    INS_MAJORITY_BASES,
    N_INS_MAJORITY_ANCHORS,
    format_insertion_bases,
    parse_insertion_bases,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file
from kuma_core.mame.models import BarcodeRecord
from kuma_core.mame.translate.aa_translator import (
    build_length_true_nt,
    translate_and_diff,
)

# A reference with no long homopolymer, so an inserted base has exactly one
# anchor and the tests are not asserting an aligner tie-break.
_RNG = random.Random(20260914)
REF = "".join(_RNG.choice("ACGT") for _ in range(180))
assert len(set(REF)) == 4


def _aln(read_seq: str, cigar: list[list[int]], strand: int = 1) -> Alignment:
    r_en = 0
    for length, op in cigar:
        if op in (_CIGAR_M, _CIGAR_D):
            r_en += length
    return Alignment(
        read_id="t",
        read_seq=read_seq,
        mapq=60,
        cigar=cigar,
        r_st=0,
        r_en=r_en,
        q_st=0,
        q_en=len(read_seq),
        strand=strand,
        reference_length=len(REF),
    )


def _full(seq: str = REF) -> Alignment:
    return _aln(seq, [[len(seq), _CIGAR_M]])


def _inserted(pos: int, bases: str) -> Alignment:
    """A read carrying *bases* inserted after 1-based reference position *pos*."""

    read = REF[:pos] + bases + REF[pos:]
    return _aln(
        read,
        [[pos, _CIGAR_M], [len(bases), _CIGAR_I], [len(REF) - pos, _CIGAR_M]],
    )


def _block_sub(del_pos: int, ins_pos: int, base: str) -> Alignment:
    """A read with one inserted base and one deleted base: net indel zero.

    ``ins_pos`` < ``del_pos``, which is how minimap2 lays out a codon swap: the
    insertion is anchored upstream and the deletion lands a few matched bases
    later. The two do NOT sit on the same position, which is why filling the
    deleted slot with the inserted base cannot reconstruct the molecule.
    """

    assert ins_pos < del_pos
    read = REF[:ins_pos] + base + REF[ins_pos : del_pos - 1] + REF[del_pos:]
    return _aln(
        read,
        [
            [ins_pos, _CIGAR_M],
            [1, _CIGAR_I],
            [del_pos - 1 - ins_pos, _CIGAR_M],
            [1, _CIGAR_D],
            [len(REF) - del_pos, _CIGAR_M],
        ],
    )


def _record(call, **over) -> BarcodeRecord:
    kw: dict[str, Any] = dict(
        native_barcode="nb01",
        custom_barcode="w1",
        consensus_seq=call.consensus_seq,
        read_count=10,
        file_size_kb=1.0,
        source_path=Path("w1.fasta"),
        del_majority_positions=call.del_majority_positions,
        n_del_majority_positions=call.n_del_majority_positions,
        ins_majority_bases=call.ins_majority_bases,
        n_ins_majority_anchors=call.n_ins_majority_anchors,
    )
    kw.update(over)
    return BarcodeRecord(**kw)


# ---------------------------------------------------------------------------
# 1. the accumulator recovers the bases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bases", ["A", "GT", "CCC", "ACGTACGT"])
def test_majority_insertion_sequence_is_recovered(bases: str) -> None:
    alns = [_inserted(70, bases) for _ in range(9)] + [_full()]
    call = call_consensus_with_metrics(alns, REF)
    assert call.ins_majority_bases == ((70, bases),)
    assert call.n_ins_majority_anchors == 1


def test_a_minority_insertion_wins_no_anchor() -> None:
    """Below the majority fraction the anchor is not reported at all.

    The threshold that decides this is the same ``DEL_MAJORITY_FRACTION`` the
    base call uses, so an insertion is admitted on exactly the evidence a
    substitution needs.
    """

    alns = [_inserted(70, "A") for _ in range(3)] + [_full() for _ in range(7)]
    call = call_consensus_with_metrics(alns, REF)
    assert 3 / 10 < DEL_MAJORITY_FRACTION
    assert call.ins_majority_bases == ()
    assert call.n_ins_majority_anchors == 0


def test_competing_sequences_resolve_to_the_more_common_one() -> None:
    alns = (
        [_inserted(70, "AA") for _ in range(7)]
        + [_inserted(70, "GG") for _ in range(2)]
        + [_full()]
    )
    call = call_consensus_with_metrics(alns, REF)
    assert call.ins_majority_bases == ((70, "AA"),)


def test_a_tie_reports_no_sequence_but_is_still_counted() -> None:
    """A tie is dropped from the list and kept in the count.

    Picking either candidate would present a coin flip with the same confidence
    as a real majority, and nothing downstream could tell the two apart. The
    count is what says a piece of the picture is missing.
    """

    alns = (
        [_inserted(70, "AA") for _ in range(4)]
        + [_inserted(70, "GG") for _ in range(4)]
        + [_full(), _full()]
    )
    call = call_consensus_with_metrics(alns, REF)
    assert call.ins_majority_bases == ()
    assert call.n_ins_majority_anchors == 1


def test_two_anchors_are_reported_ascending() -> None:
    reads = []
    for _ in range(9):
        read = REF[:40] + "TT" + REF[40:120] + "C" + REF[120:]
        reads.append(
            _aln(
                read,
                [
                    [40, _CIGAR_M],
                    [2, _CIGAR_I],
                    [80, _CIGAR_M],
                    [1, _CIGAR_I],
                    [len(REF) - 120, _CIGAR_M],
                ],
            )
        )
    call = call_consensus_with_metrics(reads + [_full()], REF)
    assert call.ins_majority_bases == ((40, "TT"), (120, "C"))


def test_a_minus_strand_read_contributes_reference_oriented_bases() -> None:
    """Strand is resolved before the tally, not after.

    ``read_seq`` is the read as input and the accumulator reverse-complements it
    into reference orientation before voting, so a plus and a minus read of the
    same molecule must produce the SAME inserted sequence. If they did not, a
    well sequenced in both directions would tie against itself.
    """

    comp = str.maketrans("ACGT", "TGCA")
    plus = _inserted(70, "GT")
    minus_read = plus.read_seq.translate(comp)[::-1]
    minus = _aln(minus_read, list(plus.cigar), strand=-1)
    call = call_consensus_with_metrics([plus] * 5 + [minus] * 4 + [_full()], REF)
    assert call.ins_majority_bases == ((70, "GT"),)
    assert call.n_ins_majority_anchors == 1


def test_scalar_and_vectorized_accumulators_agree() -> None:
    """The reference implementation and the fast path record the same tally.

    Two paths that are supposed to do the same thing are compared on the same
    input rather than each against its own expectation.
    """

    alns = [_inserted(70, "AA") for _ in range(6)] + [
        _inserted(70, "AG") for _ in range(2)
    ] + [_inserted(30, "C") for _ in range(5)]

    *_, batched, _, _ = _accumulate_all(alns, len(REF), min_base_quality=10)

    per_position: list[dict[str, int]] = [
        {k: 0 for k in "ACGTN-"} for _ in range(len(REF))
    ]
    events = [0] * len(REF)
    scalar: dict[int, dict[bytes, int]] = {}
    for aln in alns:
        _accumulate(aln, per_position, events, 10, scalar)

    assert scalar == batched
    assert scalar == {70 - 1: {b"AA": 6, b"AG": 2}, 30 - 1: {b"C": 5}}


# ---------------------------------------------------------------------------
# 2. the stored sequence does not move
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "make",
    [
        lambda: [_inserted(70, "A") for _ in range(9)] + [_full()],
        lambda: [_inserted(70, "ACGTACGT") for _ in range(9)] + [_full()],
        lambda: [_block_sub(80, 70, "G") for _ in range(9)] + [_full()],
    ],
)
def test_stored_sequence_stays_reference_length_and_drops_insertions(make) -> None:
    call = call_consensus_with_metrics(make(), REF)
    assert len(call.consensus_seq) == len(REF)
    assert set(call.consensus_seq) <= set("ACGTN")


def test_an_insertion_only_well_stores_exactly_the_reference() -> None:
    """The one output a reader could have mistaken for evidence of change.

    A clone whose only difference is an in-frame insertion reaches a
    reference-identical stored sequence. That was true before this channel
    existed and stays true; the channel is the only place the difference shows.
    """

    call = call_consensus_with_metrics(
        [_inserted(70, "GGG") for _ in range(9)] + [_full()], REF
    )
    assert call.consensus_seq == REF
    assert call.ins_majority_bases == ((70, "GGG"),)


# ---------------------------------------------------------------------------
# 3. the header
# ---------------------------------------------------------------------------


def test_insertion_record_round_trips() -> None:
    entries = ((12, "A"), (70, "GGT"), (155, "C"))
    assert parse_insertion_bases(format_insertion_bases(entries)) == entries


@pytest.mark.parametrize(
    "raw",
    [
        "70",              # no separator
        "70:",             # no bases
        "70:XY",           # not nucleotides
        "seventy:A",       # not a number
        "70:A,12:C",       # not ascending
        "0:A",             # not 1-based
    ],
)
def test_malformed_insertion_record_discards_the_whole_value(raw: str) -> None:
    """Half a splice scored as a whole one is the failure this avoids."""

    assert parse_insertion_bases(raw) == ()


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


def test_header_round_trips_through_a_file(tmp_path: Path) -> None:
    call = call_consensus_with_metrics(
        [_inserted(70, "GGG") for _ in range(9)] + [_full()], REF
    )
    record = format_consensus_fasta_record(
        "w1",
        call.consensus_seq,
        _metadata(
            ins_majority_bases=call.ins_majority_bases,
            n_ins_majority_anchors=call.n_ins_majority_anchors,
        ),
    )
    path = tmp_path / "w1.fasta"
    path.write_text(record, encoding="utf-8")

    # The sequence line is the stored artifact: reference length, no insertion.
    seq_line = path.read_text(encoding="utf-8").splitlines()[1]
    assert seq_line == call.consensus_seq == REF

    rec = parse_fasta_file(path, native_barcode="NB01")
    assert rec.ins_majority_bases == ((70, "GGG"),)
    assert rec.n_ins_majority_anchors == 1
    assert build_length_true_nt(rec, seq_line, 0, len(REF)) == (
        REF[:70] + "GGG" + REF[70:]
    )


def test_a_header_without_the_keys_reads_as_a_clean_well(tmp_path: Path) -> None:
    """Absence is the old behaviour exactly, not a new one.

    Every consensus file a user already has was written without these keys, and
    the value they produce has to be the value a well with no insertion produces.
    """

    path = tmp_path / "old.fasta"
    path.write_text(f">w1 depth=10\n{REF}\n", encoding="utf-8")
    rec = parse_fasta_file(path, native_barcode="NB01")
    assert rec.ins_majority_bases == ()
    assert rec.n_ins_majority_anchors == 0
    assert build_length_true_nt(rec, REF, 0, len(REF)) == REF


def test_an_empty_channel_omits_the_key_entirely() -> None:
    pairs = dict(_metadata().header_items())
    assert INS_MAJORITY_BASES not in pairs
    assert pairs[N_INS_MAJORITY_ANCHORS] == "0"


# ---------------------------------------------------------------------------
# 4. the length-true sequence
# ---------------------------------------------------------------------------


def test_insertion_only_well_rebuilds_the_inserted_molecule() -> None:
    call = call_consensus_with_metrics(
        [_inserted(70, "GGG") for _ in range(9)] + [_full()], REF
    )
    rec = _record(call)
    built = build_length_true_nt(rec, call.consensus_seq, 0, len(REF))
    assert built is not None
    assert built == REF[:70] + "GGG" + REF[70:]
    assert len(built) == len(REF) + call.consensus_net_indel_bp


def test_deletion_only_well_rebuilds_the_shortened_molecule() -> None:
    dels = [
        _aln(
            REF[:79] + REF[80:],
            [[79, _CIGAR_M], [1, _CIGAR_D], [len(REF) - 80, _CIGAR_M]],
        )
        for _ in range(9)
    ]
    call = call_consensus_with_metrics(dels + [_full()], REF)
    rec = _record(call)
    built = build_length_true_nt(rec, call.consensus_seq, 0, len(REF))
    assert built is not None
    assert built == REF[:79] + REF[80:]
    assert len(built) == len(REF) + call.consensus_net_indel_bp


def test_block_substitution_is_recovered_though_the_net_indel_is_zero() -> None:
    """The case the whole channel exists for.

    Insertion and deletion cancel, so the length is unchanged and
    ``consensus_net_indel_bp`` is 0. The stored sequence carries an 'N' where the
    deletion landed and carries no trace of the insertion at all, so the molecule
    appears in NEITHER. Only the rebuilt sequence has it.
    """

    alns = [_block_sub(80, 70, "G") for _ in range(9)] + [_full()]
    call = call_consensus_with_metrics(alns, REF)
    assert call.consensus_net_indel_bp == 0
    expected = REF[:70] + "G" + REF[70:79] + REF[80:]

    assert expected not in call.consensus_seq
    built = build_length_true_nt(_record(call), call.consensus_seq, 0, len(REF))
    assert built is not None
    assert built == expected
    assert len(built) == len(REF)


def test_filling_the_deleted_slot_would_not_have_worked() -> None:
    """Pins WHY the rebuild splices rather than substitutes.

    The obvious shortcut for a net-zero well is to write the inserted base into
    the deleted position. It gives a different molecule whenever the two are not
    the same position, which in a real block substitution they are not, and it
    would pass a length check while failing the sequence.
    """

    alns = [_block_sub(80, 70, "G") for _ in range(9)] + [_full()]
    call = call_consensus_with_metrics(alns, REF)
    filled = call.consensus_seq[:79] + "G" + call.consensus_seq[80:]
    built = build_length_true_nt(_record(call), call.consensus_seq, 0, len(REF))
    assert built is not None
    assert len(filled) == len(built)
    assert filled != built


def test_a_clean_well_rebuilds_to_itself() -> None:
    call = call_consensus_with_metrics([_full() for _ in range(10)], REF)
    assert build_length_true_nt(_record(call), call.consensus_seq, 0, len(REF)) == REF


def test_an_incomplete_channel_refuses_rather_than_guesses() -> None:
    """A count larger than its list means part of the picture is missing.

    Splicing what is present would produce a sequence that looks complete and is
    missing bases nobody could point at, so the rebuild declines instead.
    """

    call = call_consensus_with_metrics(
        [_inserted(70, "A") for _ in range(9)] + [_full()], REF
    )
    short_ins = _record(call, n_ins_majority_anchors=3)
    assert build_length_true_nt(short_ins, call.consensus_seq, 0, len(REF)) is None
    short_del = _record(call, n_del_majority_positions=3)
    assert build_length_true_nt(short_del, call.consensus_seq, 0, len(REF)) is None


def test_deletions_are_applied_before_insertions() -> None:
    """Order is load-bearing and is pinned against the other order.

    Writing '-' shifts no index, so after the deletion pass the string is still
    in reference coordinates and every insertion anchor is still valid. Splicing
    first shifts every later index and puts the deletion on the wrong base.
    """

    query = REF
    dels = (80,)
    ins = ((70, "GGG"),)
    rec = BarcodeRecord(
        native_barcode="nb01",
        custom_barcode="w1",
        consensus_seq=query,
        read_count=10,
        file_size_kb=1.0,
        source_path=Path("w1.fasta"),
        del_majority_positions=dels,
        n_del_majority_positions=1,
        ins_majority_bases=ins,
        n_ins_majority_anchors=1,
    )
    built = build_length_true_nt(rec, query, 0, len(REF))
    assert built == REF[:70] + "GGG" + REF[70:79] + REF[80:]

    # The other order, spelled out: splice first, then delete at the SAME
    # 1-based coordinate. It removes a base three positions off.
    chars = list(query)
    chars[70:70] = list("GGG")
    del chars[80 - 1]
    assert "".join(chars) != built


def test_translate_and_diff_reports_the_rebuild_without_moving_the_diff() -> None:
    """The new field is reported beside the verdict inputs, never into them.

    Deletion handling is #396's and stays exactly as #396 left it; the insertion
    channel adds a field and changes no existing one.
    """

    alns = [_inserted(69, "GGG") for _ in range(9)] + [_full()]
    call = call_consensus_with_metrics(alns, REF)
    with_ins = translate_and_diff(_record(call), REF, 0, len(REF))
    without = translate_and_diff(
        _record(call, ins_majority_bases=(), n_ins_majority_anchors=0),
        REF,
        0,
        len(REF),
    )
    assert with_ins.observed_nt_changes == without.observed_nt_changes
    assert with_ins.observed_aa_changes == without.observed_aa_changes
    assert with_ins.aa_sequence == without.aa_sequence
    assert with_ins.length_true_nt == REF[:69] + "GGG" + REF[69:]
    assert without.length_true_nt == REF


def test_an_anchor_outside_the_cds_window_is_dropped() -> None:
    """The rebuild is bounded to the window being compared, like the diff is.

    An insertion in flanking backbone is not part of this comparison, and
    admitting it would make the rebuilt length disagree with the window.
    """

    rec = BarcodeRecord(
        native_barcode="nb01",
        custom_barcode="w1",
        consensus_seq=REF,
        read_count=10,
        file_size_kb=1.0,
        source_path=Path("w1.fasta"),
        ins_majority_bases=((5, "TTT"), (100, "A")),
        n_ins_majority_anchors=2,
    )
    built = build_length_true_nt(rec, REF[30:150], 30, 150)
    assert built == REF[30:100] + "A" + REF[100:150]
