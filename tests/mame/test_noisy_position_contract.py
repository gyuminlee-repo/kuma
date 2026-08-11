"""FASTA-header round trip for the minor-allele strand evidence.

The writer (``consensus_metadata``) and the reader (``fasta_parser``) live in
different modules, so the contract is only real if a record written by one is
read back identically by the other.

Two absence rules carry the weight here and they are NOT the same rule:

``max_minor_allele_strand_share``
    Emitted only when a mix-eligible position exists. Absent means UNKNOWN.
    0.0 is a real measurement saying the minor allele came off one strand only,
    which is the sequence-context artifact signature, so a file predating the
    metric must never read back as 0.0.
``eligible_positions`` / ``noisy_positions``
    A plain count and its top-K sample. 0 and ``()`` are honest for a well with
    no eligible position, and a legacy file lands on the same pair without
    claiming anything false.

Nothing here is a verdict input; these tests guard reporting fidelity only.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from kuma_core.mame.ingest.consensus_metadata import (
    ELIGIBLE_POSITIONS,
    MAX_MINOR_ALLELE_MINUS,
    MAX_MINOR_ALLELE_PLUS,
    MAX_MINOR_ALLELE_STRAND_SHARE,
    NOISY_POSITIONS,
    ConsensusMetadata,
    NoisyPosition,
    format_consensus_fasta_record,
    format_noisy_positions,
    parse_noisy_positions,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file


def _metadata(**overrides) -> ConsensusMetadata:
    base = dict(
        depth=500,
        input_reads=500,
        aligned_reads=500,
        mapq_failed=0,
        span_failed=0,
        mixed_positions=0,
        max_minor_allele_fraction=0.05,
        low_depth_positions=0,
        consensus_n_fraction=0.0,
        low_quality_bases=0,
    )
    base.update(overrides)
    return ConsensusMetadata(**base)


def _write(tmp_path: Path, metadata: ConsensusMetadata) -> Path:
    path = tmp_path / "4_11.fasta"
    path.write_text(format_consensus_fasta_record("4_11", "ACGT" * 10, metadata))
    return path


# Self-consistent by construction: minor_fraction == (plus + minus) / depth, the
# invariant the engine produces. 13/312 and 11/298. The first record is the
# artifact shape (minor allele on one strand only), the second is balanced.
_POSITIONS = (
    NoisyPosition(
        position=1248, minor_fraction=13 / 312, depth=312, plus_count=13, minus_count=0
    ),
    NoisyPosition(
        position=1196, minor_fraction=11 / 298, depth=298, plus_count=5, minus_count=6
    ),
)


def test_strand_evidence_survives_a_write_read_round_trip(tmp_path: Path) -> None:
    metadata = _metadata(
        max_minor_allele_strand_share=0.375,
        max_minor_allele_plus=5,
        max_minor_allele_minus=3,
        n_eligible_positions=214,
        noisy_positions=_POSITIONS,
    )
    record = parse_fasta_file(_write(tmp_path, metadata), "NB07")

    assert record.max_minor_allele_strand_share == pytest.approx(0.375)
    assert record.max_minor_allele_plus_count == 5
    assert record.max_minor_allele_minus_count == 3
    assert record.n_eligible_positions == 214
    # Counts and positions survive exactly; only the fraction is rounded to the
    # header's .3f, which costs nothing because it equals (plus+minus)/depth.
    assert [
        (p.position, p.depth, p.plus_count, p.minus_count)
        for p in record.noisy_positions
    ] == [(1248, 312, 13, 0), (1196, 298, 5, 6)]
    for written, read_back in zip(_POSITIONS, record.noisy_positions):
        assert read_back.minor_fraction == pytest.approx(
            written.minor_fraction, abs=5e-4
        )
    # The sample states its own truncation.
    assert len(record.noisy_positions) < record.n_eligible_positions


def test_a_measured_zero_share_round_trips_and_is_not_dropped(
    tmp_path: Path,
) -> None:
    """0.0 is the artifact reading, so it must survive as a value, not vanish.

    A one-strand minor allele is the single most informative thing this metric
    reports. An emit-when-truthy writer would drop exactly that case and leave
    it indistinguishable from a well that measured nothing.
    """
    metadata = _metadata(
        max_minor_allele_strand_share=0.0,
        max_minor_allele_plus=7,
        max_minor_allele_minus=0,
        n_eligible_positions=88,
        noisy_positions=_POSITIONS[:1],
    )
    header = metadata.header_suffix()
    assert f"{MAX_MINOR_ALLELE_STRAND_SHARE}=0.000" in header

    record = parse_fasta_file(_write(tmp_path, metadata), "NB07")

    assert record.max_minor_allele_strand_share is not None
    assert record.max_minor_allele_strand_share == 0.0
    assert record.max_minor_allele_plus_count == 7
    assert record.max_minor_allele_minus_count == 0


def test_absent_keys_read_back_as_unknown_not_zero(tmp_path: Path) -> None:
    """A consensus file predating the metric must keep working, and read unknown.

    This is the important one: old consensus directories are re-analysed all the
    time, and the share is the field where a substituted 0.0 would be actively
    wrong rather than merely uninformative.
    """
    header = _metadata().header_suffix()
    assert MAX_MINOR_ALLELE_STRAND_SHARE not in header
    assert MAX_MINOR_ALLELE_PLUS not in header
    assert MAX_MINOR_ALLELE_MINUS not in header
    assert NOISY_POSITIONS not in header
    # The pool size is unconditional, so it IS written, as a truthful 0.
    assert f"{ELIGIBLE_POSITIONS}=0" in header

    record = parse_fasta_file(_write(tmp_path, _metadata()), "NB07")

    assert record.max_minor_allele_strand_share is None
    assert record.max_minor_allele_plus_count == 0
    assert record.max_minor_allele_minus_count == 0
    assert record.n_eligible_positions == 0
    assert record.noisy_positions == ()


def test_a_header_with_no_new_keys_at_all_parses_without_raising(
    tmp_path: Path,
) -> None:
    """The minimal legacy header, not merely one this writer produced."""
    path = tmp_path / "1_2.fasta"
    path.write_text(">1_2 depth=10\nATGCATGC\n", encoding="utf-8")

    record = parse_fasta_file(path, native_barcode="NB01")

    assert record.max_minor_allele_strand_share is None
    assert record.n_eligible_positions == 0
    assert record.noisy_positions == ()


def test_encoding_is_stable() -> None:
    encoded = format_noisy_positions(_POSITIONS)
    assert encoded == "1248:0.042:312:13:0,1196:0.037:298:5:6"
    # Round trip through the parser reproduces the counts exactly; only the
    # fraction is rounded, and it is the one value recoverable without it.
    parsed = parse_noisy_positions(encoded)
    assert [(p.position, p.depth, p.plus_count, p.minus_count) for p in parsed] == [
        (1248, 312, 13, 0),
        (1196, 298, 5, 6),
    ]
    for written, read_back in zip(_POSITIONS, parsed):
        assert read_back.minor_fraction == pytest.approx(
            written.minor_fraction, abs=5e-4
        )


def test_a_malformed_record_is_skipped_and_the_rest_survive(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Documented behaviour: skip the bad record, keep the good ones, warn once.

    Dropping the whole list would lose readable positions next to an unreadable
    one, and raising would fail the parse of an otherwise fine consensus file
    over evidence no gate reads.
    """
    raw = (
        "1248:0.041:312:6:0"      # good
        ",1196:0.038:298:5"        # four fields, not five
        ",1100:abc:200:4:4"        # unparseable fraction
        ",1050:0.021:190:3:2"      # good
    )
    with caplog.at_level(logging.WARNING):
        parsed = parse_noisy_positions(raw)

    assert [p.position for p in parsed] == [1248, 1050]
    # Written order is preserved; nothing is re-ranked on the way in.
    assert parsed[0].minor_fraction == pytest.approx(0.041)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2


def test_empty_and_missing_list_values_both_give_an_empty_tuple() -> None:
    assert parse_noisy_positions(None) == ()
    assert parse_noisy_positions("") == ()


def test_the_encoding_carries_no_whitespace() -> None:
    """A space in the value would truncate it at the first record.

    ``_METADATA_RE`` in fasta_parser reads a header value as a run of non-space
    characters, so the separators must stay whitespace-free or every position
    after the first is silently lost.
    """
    encoded = format_noisy_positions(_POSITIONS)
    assert " " not in encoded
    assert "\t" not in encoded
