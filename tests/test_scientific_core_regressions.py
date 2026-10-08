from collections import defaultdict
from pathlib import Path

import pytest

from kuma_core.mame.ingest.align import Alignment
from kuma_core.mame.ingest.consensus import _accumulate, call_consensus_with_metrics
from kuma_core.mame.ingest.demux import demux_native_barcode


@pytest.mark.parametrize("strand", [1, -1])
@pytest.mark.parametrize("low_insertions", [1, 2])
def test_insertion_support_uses_only_accepted_anchor_votes(strand: int, low_insertions: int) -> None:
    reads: list[Alignment] = []
    for index in range(4):
        inserted = index < 2
        sequence = "ATCG" if inserted else "ACG"
        quality = ("!" if index < low_insertions else "I") + "I" * (len(sequence) - 1)
        if strand == -1:
            sequence = sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]
            quality = quality[::-1]
        reads.append(Alignment(
            read_id=str(index), read_seq=sequence, read_qual=quality, mapq=60,
            cigar=[[1, 0], [1, 1], [2, 0]] if inserted else [[3, 0]],
            r_st=0, r_en=3, q_st=0, q_en=len(sequence), strand=strand, reference_length=3,
        ))

    result = call_consensus_with_metrics(reads, "ACG", min_base_quality=10)
    positions: list[dict[str, int]] = [defaultdict(int) for _ in range(3)]
    events = [0, 0, 0]
    for read in reads:
        _accumulate(read, positions, events, 10)

    assert result.max_indel_event_fraction == pytest.approx((2 - low_insertions) / (4 - low_insertions))
    assert events == [2 - low_insertions, 0, 0]
    assert result.consensus_net_indel_bp == 0
    assert result.ins_majority_bases == ()


def test_split_insertion_ops_count_one_read_at_anchor() -> None:
    read = Alignment(
        read_id="read", read_seq="ATTCG", read_qual=None, mapq=60,
        cigar=[[1, 0], [1, 1], [1, 1], [2, 0]],
        r_st=0, r_en=3, q_st=0, q_en=5, strand=1, reference_length=3,
    )
    result = call_consensus_with_metrics([read] * 3, "ACG")
    assert result.max_indel_event_fraction == 1.0
    assert result.consensus_net_indel_bp == 2
    assert result.ins_majority_bases == ((1, "TT"),)
    positions: list[dict[str, int]] = [defaultdict(int) for _ in range(3)]
    events = [0, 0, 0]
    sequences: dict[int, dict[bytes, int]] = {}
    _accumulate(read, positions, events, 10, sequences)
    assert events == [1, 0, 0]
    assert sequences == {0: {b"TT": 1}}


def test_mixed_case_barcodes_do_not_mutate_caller_mapping(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    (source / "read.fastq").write_text("@read\nACGTATTT\n+\nIIIIIIII\n", encoding="ascii")
    barcodes = {"A1": "aCgTa"}

    result = demux_native_barcode(source, barcodes, tmp_path / "out", use_cutadapt=False, error_tolerance=0)

    assert result.per_well_counts == {"A1": 1}
    assert barcodes == {"A1": "aCgTa"}
