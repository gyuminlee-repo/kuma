"""Round-trip tests for the ``net_indel`` consensus-header metadata field.

The consensus FASTA header is the only channel that carries the CIGAR-derived
net-indel signal from the demux/consensus stage to the verdict stage, so the
``netindel`` value written by :func:`format_consensus_fasta_record` must survive
parsing by :func:`parse_fasta_file` unchanged.
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.ingest.consensus_metadata import (
    NET_INDEL,
    ConsensusMetadata,
    format_consensus_fasta_record,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file


def _metadata(net_indel: int) -> ConsensusMetadata:
    return ConsensusMetadata(
        depth=12,
        input_reads=15,
        aligned_reads=14,
        mapq_failed=1,
        span_failed=0,
        mixed_positions=0,
        max_minor_allele_fraction=0.0,
        low_depth_positions=0,
        consensus_n_fraction=0.0,
        low_quality_bases=2,
        net_indel=net_indel,
    )


def test_header_suffix_includes_net_indel() -> None:
    suffix = _metadata(-1).header_suffix()
    assert f"{NET_INDEL}=-1" in suffix


def test_net_indel_round_trips_through_fasta(tmp_path: Path) -> None:
    for value in (-3, -1, 0, 1, 2):
        record = format_consensus_fasta_record(
            "1_1", "ATGCATGC", _metadata(value)
        )
        path = tmp_path / f"1_1_{value}.fasta"
        path.write_text(record, encoding="utf-8")
        parsed = parse_fasta_file(path, native_barcode="NB01")
        assert parsed.net_indel_bp == value


def test_legacy_header_without_net_indel_parses_none(tmp_path: Path) -> None:
    # A pre-aligned / legacy consensus FASTA carries no netindel token.
    path = tmp_path / "1_2.fasta"
    path.write_text(">1_2 depth=10\nATGCATGC\n", encoding="utf-8")
    parsed = parse_fasta_file(path, native_barcode="NB01")
    assert parsed.net_indel_bp is None
