"""FASTA-header round trip for the called-substitution support metric.

The writer and the reader live in different modules, so the contract is only
real if a record written by one is read back identically by the other. The
absent-key case matters as much as the present one: a consensus file written
before this metric existed must read back as unknown, never as zero support.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kuma_core.mame.ingest.consensus_metadata import (
    MIN_VARIANT_SUPPORT,
    MIN_VARIANT_SUPPORT_DEPTH,
    VARIANT_POSITIONS,
    ConsensusMetadata,
    format_consensus_fasta_record,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file


def _metadata(**overrides) -> ConsensusMetadata:
    base: dict[str, Any] = dict(
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
    metadata = _metadata(
        min_variant_support=0.809, variant_positions=2, min_variant_support_depth=67
    )
    record = parse_fasta_file(_write(tmp_path, metadata), "NB07")

    assert record.min_variant_support == pytest.approx(0.809)
    assert record.n_variant_positions == 2
    assert record.min_variant_support_depth == 67


def test_absent_keys_read_back_as_unknown_not_zero(tmp_path: Path) -> None:
    """A file predating the metric must not look like a zero-support well."""
    header = _metadata().header_suffix()
    assert MIN_VARIANT_SUPPORT not in header
    assert VARIANT_POSITIONS not in header
    assert MIN_VARIANT_SUPPORT_DEPTH not in header

    record = parse_fasta_file(_write(tmp_path, _metadata()), "NB07")

    assert record.min_variant_support is None
    assert record.n_variant_positions == 0
    assert record.min_variant_support_depth == 0


def test_noise_floor_survives_the_round_trip(tmp_path: Path) -> None:
    """The threshold the mixed gate uses is only auditable if the floor travels.

    ``max_minor_allele_fraction`` says how bad the worst position is;
    ``median_minor_allele_fraction`` says what an ordinary position looks like,
    which is what a fixed gate has to clear to mean anything.
    """
    metadata = _metadata(median_minor_allele_fraction=0.0031)
    record = parse_fasta_file(_write(tmp_path, metadata), "NB07")

    assert record.median_minor_allele_fraction == pytest.approx(0.0031)


def test_noise_floor_absent_reads_back_as_zero(tmp_path: Path) -> None:
    """A file predating the metric carries no floor, and 0.0 is the honest value.

    Unlike the support metric this one has no "unknown" state to protect: a
    missing floor cannot be mistaken for a purity claim, it just means the gate
    cannot be audited for that file.
    """
    record = parse_fasta_file(_write(tmp_path, _metadata()), "NB07")

    assert record.median_minor_allele_fraction == 0.0
