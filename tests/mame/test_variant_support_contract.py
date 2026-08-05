"""FASTA-header round trip for the called-substitution support metric.

The writer and the reader live in different modules, so the contract is only
real if a record written by one is read back identically by the other. The
absent-key case matters as much as the present one: a consensus file written
before this metric existed must read back as unknown, never as zero support.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kuma_core.mame.ingest.consensus_metadata import (
    MIN_VARIANT_SUPPORT,
    VARIANT_POSITIONS,
    ConsensusMetadata,
    format_consensus_fasta_record,
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


def test_support_survives_a_write_read_round_trip(tmp_path: Path) -> None:
    metadata = _metadata(min_variant_support=0.809, variant_positions=2)
    record = parse_fasta_file(_write(tmp_path, metadata), "NB07")

    assert record.min_variant_support == pytest.approx(0.809)
    assert record.n_variant_positions == 2


def test_absent_keys_read_back_as_unknown_not_zero(tmp_path: Path) -> None:
    """A file predating the metric must not look like a zero-support well."""
    header = _metadata().header_suffix()
    assert MIN_VARIANT_SUPPORT not in header
    assert VARIANT_POSITIONS not in header

    record = parse_fasta_file(_write(tmp_path, _metadata()), "NB07")

    assert record.min_variant_support is None
    assert record.n_variant_positions == 0
