"""Deletions and insertions that repeat across one plate, and what tells them apart.

The substitution tally next door counts substitutions and nothing else: its
eligibility mask is ``counts[:, :4]`` in ``ingest/consensus.py``, so a deletion
token is in neither its numerator nor its denominator, and an insertion is not
in that encoding at all. A deletion majority repeating at one coordinate over a
plate was therefore invisible on every screen the app draws.

The reason these tests spend most of their length on the EXPECTATION axis is a
measured counterexample. On the ispS run the deletion at position 669 recurs in
the ``1_5`` well of ``sort_barcode06``, ``13`` and ``20``, and all three of
those wells expect V218L. Three wells sharing one expectation share a sample;
three wells expecting three different variants do not, and only the second
shape is what a basecaller artifact looks like. A tally that reported the well
count alone would have marked the first as systematic.

Nothing here grades, so nothing here asserts a severity. The only restriction
the tables carry is definitional: a coordinate one record named has not
recurred.
"""

from pathlib import Path

from kuma_core.mame.models import (
    BarcodeRecord,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.run_quality import (
    serialise_indel_recurrence,
    summarise_indel_recurrence,
)


def _verdict(
    *,
    expected: list[str],
    del_positions: tuple[int, ...] = (),
    n_del: int | None = None,
    ins_bases: tuple[tuple[int, str], ...] = (),
    n_ins: int | None = None,
) -> VerdictRecord:
    """One scored record, carrying only what the indel tally reads.

    ``n_del`` and ``n_ins`` default to the length of their list, which is the
    ordinary well. Passing them larger is how a record says it HAD evidence it
    did not report, which is the case the tally must not read as "none".
    """
    barcode = BarcodeRecord(
        native_barcode="sort_barcode06",
        custom_barcode="1_5",
        consensus_seq="ACGT",
        file_size_kb=100.0,
        source_path=Path("consensus.fasta"),
        del_majority_positions=del_positions,
        n_del_majority_positions=len(del_positions) if n_del is None else n_del,
        ins_majority_bases=ins_bases,
        n_ins_majority_anchors=len(ins_bases) if n_ins is None else n_ins,
    )
    return VerdictRecord(
        translated=TranslatedRecord(
            barcode=barcode,
            aa_sequence="MA",
            observed_nt_changes=[],
            observed_aa_changes=[],
        ),
        expected_mutations=list(expected),
        verdict=VerdictClass.PASS,
    )


def test_a_deletion_three_wells_share_becomes_a_row() -> None:
    """The signal: one coordinate, three records, one row naming all three."""
    verdicts = [
        _verdict(expected=["V218L"], del_positions=(669,)),
        _verdict(expected=["A31G"], del_positions=(669,)),
        _verdict(expected=["K77R"], del_positions=(669,)),
    ]

    summary = summarise_indel_recurrence(verdicts)

    assert [row.position for row in summary.deletions] == [669]
    assert summary.deletions[0].wells == 3
    assert summary.deletion_wells_contributing == 3
    assert summary.wells_scored == 3
    # Definitional and not a cut: seen once is not recurred.
    assert summary.deletion_positions_seen == 1
    assert summary.deletion_positions_single_well == 0
    # No grading anywhere on the serialised block, which is the whole point.
    payload = serialise_indel_recurrence(summary)
    assert "severity" not in payload
    assert "findings" not in payload


def test_a_deletion_only_one_well_reported_is_not_a_row() -> None:
    """Recurrence means more than once, and the remainder is counted not hidden."""
    verdicts = [
        _verdict(expected=["V218L"], del_positions=(669,)),
        _verdict(expected=["A31G"], del_positions=(412,)),
    ]

    summary = summarise_indel_recurrence(verdicts)

    assert summary.deletions == []
    assert summary.deletion_positions_seen == 2
    assert summary.deletion_positions_single_well == 2
    assert summary.deletion_wells_contributing == 2


def test_a_well_over_the_reporting_budget_is_omitted_not_absent() -> None:
    """``n_del > 0`` with an empty list is OMISSION, and has its own counter.

    ``ingest/consensus.py`` drops the coordinate list WHOLE past
    ``DEL_RUN_REPORT_BUDGET`` rather than cutting it short, so such a well is
    missing from every row rather than under-counted in one. That is a
    different event from the substitution block's truncation and the block
    keeps the two apart.
    """
    verdicts = [
        _verdict(expected=["V218L"], del_positions=(669,)),
        _verdict(expected=["A31G"], del_positions=(669,)),
        _verdict(expected=["K77R"], del_positions=(), n_del=91),
    ]

    summary = summarise_indel_recurrence(verdicts)

    assert summary.deletion_wells_omitted == 1
    # The omitted well contributed to no row, and said so rather than counting
    # as a well with no deletion.
    assert summary.deletion_wells_contributing == 2
    assert summary.deletions[0].wells == 2
    assert summary.wells_scored == 3

    payload = serialise_indel_recurrence(summary)
    assert payload["deletion_wells_omitted"] == 1
    # The flag and its cause travel together: omission here, truncation on the
    # substitution block, and a reader holding the json can tell which.
    assert payload["lower_bound"] is True
    assert payload["lower_bound_cause"] == "omission"


def test_a_tied_insertion_anchor_leaves_the_list_and_stays_in_the_count() -> None:
    """The insertion channel's third state, which the deletion channel lacks.

    A record reporting SOME anchors is inside the budget by construction, so
    every anchor it counted and did not list was dropped for a tie on which
    sequence the reads inserted. A record reporting NONE has two possible
    causes this layer cannot separate, and is named for the shape instead.
    """
    verdicts = [
        _verdict(expected=["V218L"], ins_bases=((900, "GGT"),), n_ins=3),
        _verdict(expected=["A31G"], ins_bases=((900, "GGT"),)),
        _verdict(expected=["K77R"], ins_bases=(), n_ins=70),
    ]

    summary = summarise_indel_recurrence(verdicts)

    # Two anchors counted and not listed by the first record, both ties.
    assert summary.insertion_anchors_tied == 2
    # The third record reported nothing at all, which is the ambiguous shape.
    assert summary.insertion_wells_unreported == 1
    assert summary.insertion_wells_contributing == 2
    assert [row.anchor for row in summary.insertions] == [900]
    assert summary.insertions[0].wells == 2
    assert summary.insertions[0].distinct_sequences == 1


def test_three_wells_one_expectation_reads_differently_from_three_expectations() -> None:
    """The axis the measured counterexample forced onto every row.

    Position 669 recurs in three ispS wells that ALL expect V218L, which is a
    shared sample rather than a systematic artifact. Same well count, different
    event, and the only field that says so is this one.
    """
    shared = summarise_indel_recurrence(
        [
            _verdict(expected=["V218L"], del_positions=(669,)),
            _verdict(expected=["V218L"], del_positions=(669,)),
            _verdict(expected=["V218L"], del_positions=(669,)),
        ]
    )
    spread = summarise_indel_recurrence(
        [
            _verdict(expected=["V218L"], del_positions=(669,)),
            _verdict(expected=["A31G"], del_positions=(669,)),
            _verdict(expected=["K77R"], del_positions=(669,)),
        ]
    )

    assert shared.deletions[0].wells == spread.deletions[0].wells == 3
    assert shared.deletions[0].expected_variants == 1
    assert spread.deletions[0].expected_variants == 3
    # Neither is graded, flagged or ordered ahead of the other. The number is
    # handed over and the operator reads it.
    assert serialise_indel_recurrence(shared)["deletions"][0]["expected_variants"] == 1
    assert serialise_indel_recurrence(spread)["deletions"][0]["expected_variants"] == 3


def test_expectation_is_a_set_and_an_empty_one_is_its_own_key() -> None:
    """Order does not make two wells different, and a control expects nothing.

    A wild-type control carries an empty expectation, which is an expectation
    and not a missing value, so it counts as a distinct key rather than being
    dropped from the axis.
    """
    same_order = summarise_indel_recurrence(
        [
            _verdict(expected=["A31G", "V218L"], del_positions=(669,)),
            _verdict(expected=["V218L", "A31G"], del_positions=(669,)),
        ]
    )
    assert same_order.deletions[0].expected_variants == 1

    with_control = summarise_indel_recurrence(
        [
            _verdict(expected=["V218L"], del_positions=(669,)),
            _verdict(expected=[], del_positions=(669,)),
        ]
    )
    assert with_control.deletions[0].expected_variants == 2


def test_a_plate_with_no_indel_reports_empty_tables_and_its_denominator() -> None:
    """Present on every run, including one with nothing to say.

    A block that appeared only when something recurred could not be told apart
    from a sidecar that never tallied one, which is the rule the run_quality
    block already follows.
    """
    summary = summarise_indel_recurrence(
        [_verdict(expected=["V218L"]), _verdict(expected=["A31G"])]
    )

    payload = serialise_indel_recurrence(summary)
    assert payload["deletions"] == []
    assert payload["insertions"] == []
    # The denominator is every scored record, never the contributing few: three
    # wells of three contributing would print as a whole plate.
    assert payload["wells_scored"] == 2
    assert payload["deletion_wells_contributing"] == 0
    assert payload["deletion_wells_omitted"] == 0
    assert payload["insertion_wells_unreported"] == 0
    assert payload["insertion_anchors_tied"] == 0


def test_a_contiguous_deletion_run_is_reported_per_position() -> None:
    """Three lost bases are three rows, because the record has no run grouping.

    ``del_majority_positions`` is per coordinate. Merging adjacent ones into a
    span here would invent a grouping the measurement does not carry, so the
    table stays at the resolution the evidence has.
    """
    summary = summarise_indel_recurrence(
        [
            _verdict(expected=["V218L"], del_positions=(669, 670, 671)),
            _verdict(expected=["A31G"], del_positions=(669, 670, 671)),
        ]
    )

    assert [row.position for row in summary.deletions] == [669, 670, 671]
    assert all(row.wells == 2 for row in summary.deletions)
