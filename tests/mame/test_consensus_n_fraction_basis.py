"""Consensus N-fraction basis marker: legacy headers must not change meaning.

``consensus_n_fraction`` was redefined to range over positions that reached
``min_depth`` instead of the whole reference. Files written before the change
carry the old number under the same key, so the parser must tell the two apart
by the ``consensus_n_fraction_basis`` marker, recover the covered-scoped value
where the header allows it, and mark the well as not evaluable otherwise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.compare import classify_verdict
from kuma_core.mame.ingest.consensus_metadata import (
    BASIS_COVERED,
    CONSENSUS_N_FRACTION_BASIS,
    ConsensusMetadata,
    format_consensus_fasta_record,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file
from kuma_core.mame.models import CompareParams, TranslatedRecord, VerdictClass

# 60 bp reference. Reads interrogate the first 20 bp; the trailing 40 bp are
# reference the amplicon never covers, so they are N and counted as low depth.
_COVERED_CLEAN = "ATGGTTTTTAAACCCGGGAA"
_COVERED_DIRTY = "ATGGTTNTTAAACCCGNGAA"
_UNCOVERED = "N" * 40

_LEGACY_HEADER = (
    "depth=20 input_reads=20 aligned_reads=20 mapq_failed=0 span_failed=0 "
    "mixed_positions=0 max_minor_allele_fraction=0.000 "
    "low_depth_positions=40 consensus_n_fraction={frac} low_quality_bases=0"
)


def _write(tmp_path: Path, name: str, header: str, seq: str) -> Path:
    path = tmp_path / f"{name}.fasta"
    path.write_text(f">{name} {header}\n{seq}\n", encoding="utf-8")
    return path


def _verdict(record) -> tuple[VerdictClass, str]:
    translated = TranslatedRecord(
        barcode=record,
        aa_sequence="MVFKPG",
        observed_nt_changes=[],
        observed_aa_changes=[],
        n_no_call_aa=0,
    )
    result = classify_verdict(
        translated, [], CompareParams(min_read_count=None, min_file_size_kb=0.0)
    )
    return result.verdict, result.verdict_notes


def test_legacy_header_recovers_covered_scoped_fraction(tmp_path: Path) -> None:
    """A legacy value of 0.667 over the full reference is really 0.0 covered."""

    path = _write(
        tmp_path,
        "1_1",
        _LEGACY_HEADER.format(frac="0.667"),
        _COVERED_CLEAN + _UNCOVERED,
    )
    record = parse_fasta_file(path, native_barcode="NB01")

    assert record.consensus_n_fraction_evaluable is True
    assert record.consensus_n_fraction == pytest.approx(0.0)
    # Without recovery the stored 0.667 would trip the zero-tolerance gate.
    verdict, _notes = _verdict(record)
    assert verdict is VerdictClass.PASS


def test_legacy_header_recovery_still_fails_a_dirty_covered_region(
    tmp_path: Path,
) -> None:
    """Recovery is not a blanket pass: real covered no-calls still gate."""

    path = _write(
        tmp_path,
        "1_2",
        _LEGACY_HEADER.format(frac="0.700"),
        _COVERED_DIRTY + _UNCOVERED,
    )
    record = parse_fasta_file(path, native_barcode="NB01")

    assert record.consensus_n_fraction_evaluable is True
    assert record.consensus_n_fraction == pytest.approx(2 / 20)
    verdict, notes = _verdict(record)
    assert verdict is VerdictClass.NO_CALL
    assert "consensus_n_fraction=0.100" in notes


def test_header_without_low_depth_key_is_not_evaluable(tmp_path: Path) -> None:
    """No marker and no low_depth_positions: no value can be justified."""

    path = _write(
        tmp_path,
        "1_3",
        "depth=20 consensus_n_fraction=0.667",
        _COVERED_CLEAN + _UNCOVERED,
    )
    record = parse_fasta_file(path, native_barcode="NB01")

    assert record.consensus_n_fraction_evaluable is False


def test_not_evaluable_skips_the_gate_and_says_why(tmp_path: Path) -> None:
    """The skipped gate must reach the user through verdict_notes."""

    path = _write(
        tmp_path,
        "1_4",
        "depth=20 consensus_n_fraction=0.667",
        _COVERED_CLEAN + _UNCOVERED,
    )
    record = parse_fasta_file(path, native_barcode="NB01")

    verdict, notes = _verdict(record)
    assert verdict is VerdictClass.PASS
    assert "not evaluable" in notes
    assert "legacy consensus file" in notes
    assert "re-run consensus" in notes


def test_new_writes_carry_the_basis_marker_and_round_trip(tmp_path: Path) -> None:
    """A record written now is self-describing and parses back unchanged."""

    path = tmp_path / "1_5.fasta"
    path.write_text(
        format_consensus_fasta_record(
            "1_5",
            _COVERED_DIRTY + _UNCOVERED,
            ConsensusMetadata(
                depth=20,
                input_reads=20,
                aligned_reads=20,
                mapq_failed=0,
                span_failed=0,
                mixed_positions=0,
                max_minor_allele_fraction=0.0,
                low_depth_positions=40,
                consensus_n_fraction=0.1,
                low_quality_bases=0,
                consensus_n_fraction_basis=BASIS_COVERED,
            ),
        ),
        encoding="utf-8",
    )

    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert f"{CONSENSUS_N_FRACTION_BASIS}={BASIS_COVERED}" in header

    record = parse_fasta_file(path, native_barcode="NB01")
    assert record.consensus_n_fraction_evaluable is True
    assert record.consensus_n_fraction == pytest.approx(0.1)


def test_marked_value_is_trusted_verbatim_not_recomputed(tmp_path: Path) -> None:
    """A marked header is authoritative even when recomputation would differ."""

    header = (
        f"depth=20 low_depth_positions=40 consensus_n_fraction=0.250 "
        f"{CONSENSUS_N_FRACTION_BASIS}={BASIS_COVERED}"
    )
    path = _write(tmp_path, "1_6", header, _COVERED_DIRTY + _UNCOVERED)
    record = parse_fasta_file(path, native_barcode="NB01")

    assert record.consensus_n_fraction_evaluable is True
    assert record.consensus_n_fraction == pytest.approx(0.25)
