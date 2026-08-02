"""Round-trip tests for the net-indel consensus-header metadata fields.

The consensus FASTA header is the only channel that carries the CIGAR-derived
net-indel evidence from the demux/consensus stage to the verdict stage, so the
values written by :func:`format_consensus_fasta_record` must survive parsing by
:func:`parse_fasta_file` unchanged.

Two distinct measurements travel here and only one of them is a verdict input:

``consensus_net_indel``
    Net indel of the called consensus. The FRAMESHIFT gate reads this.
``read_net_indel``
    Median per-read net indel. Read-quality evidence only.

The legacy ``net_indel`` key wrote the per-read median under a name that reads
like the consensus measurement, so a file carrying it must land on the
read-quality field, never on the gate.
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.ingest.consensus_metadata import (
    CONSENSUS_NET_INDEL,
    READ_NET_INDEL,
    ConsensusMetadata,
    format_consensus_fasta_record,
)
from kuma_core.mame.ingest.fasta_parser import parse_fasta_file


def _metadata(consensus_net_indel: int, read_net_indel: int = 0) -> ConsensusMetadata:
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
        consensus_net_indel=consensus_net_indel,
        read_net_indel=read_net_indel,
    )


def test_header_suffix_carries_both_net_indel_fields() -> None:
    suffix = _metadata(-1, read_net_indel=-2).header_suffix()
    assert f"{CONSENSUS_NET_INDEL}=-1" in suffix
    assert f"{READ_NET_INDEL}=-2" in suffix


def test_consensus_net_indel_round_trips_through_fasta(tmp_path: Path) -> None:
    for value in (-3, -1, 0, 1, 2):
        record = format_consensus_fasta_record(
            "1_1", "ATGCATGC", _metadata(value, read_net_indel=-1)
        )
        path = tmp_path / f"1_1_{value}.fasta"
        path.write_text(record, encoding="utf-8")
        parsed = parse_fasta_file(path, native_barcode="NB01")
        assert parsed.consensus_net_indel_bp == value
        # The read metric rides along and stays distinct from the gate value.
        assert parsed.median_read_net_indel_bp == -1


def test_legacy_header_without_net_indel_parses_none(tmp_path: Path) -> None:
    # A pre-aligned / legacy consensus FASTA carries no net-indel token at all.
    path = tmp_path / "1_2.fasta"
    path.write_text(">1_2 depth=10\nATGCATGC\n", encoding="utf-8")
    parsed = parse_fasta_file(path, native_barcode="NB01")
    assert parsed.consensus_net_indel_bp is None
    assert parsed.median_read_net_indel_bp is None


def test_legacy_net_indel_key_is_read_metric_not_the_gate(tmp_path: Path) -> None:
    # Files written between #201 and this fix store the per-read median under
    # ``net_indel``. Reading that value as a consensus measurement would re-fail
    # every ONT well whose reads carry homopolymer indel error, so it must land
    # on the read metric and leave the FRAMESHIFT gate disarmed.
    path = tmp_path / "1_3.fasta"
    path.write_text(">1_3 depth=10 net_indel=-1\nATGCATGC\n", encoding="utf-8")
    parsed = parse_fasta_file(path, native_barcode="NB01")
    assert parsed.consensus_net_indel_bp is None
    assert parsed.median_read_net_indel_bp == -1
