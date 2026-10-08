from pathlib import Path

import pytest
from sidecar_mame.handlers.demux import handle_demux_and_filter


@pytest.mark.parametrize(("quality", "expected"), [("!", 0), ("I", 1)])
def test_counts_match_reads_after_quality_filter(
    tmp_path: Path, quality: str, expected: int,
) -> None:
    source = tmp_path / "barcode01"
    source.mkdir()
    sequence = "AATCCCACT" + "ATGGTGTTCAAGAACTTCGATGCGCTGACCGGCAAAGACCTGAAAGAGTTCGCGAAATCG"
    (source / "reads.fastq").write_text(
        f"@read1\n{sequence}\n+\n{quality * len(sequence)}\n", encoding="utf-8",
    )
    output = tmp_path / "out"
    result = handle_demux_and_filter({
        "fastq_dir": str(source),
        "output_dir": str(output),
        "custom_barcodes": {"1_1": "AATCCCACT"},
        "use_cutadapt": False,
        "auto_detect_length": False,
        "target_length": len(sequence),
    })
    actual = sum(
        line.startswith(">")
        for path in output.rglob("*.fasta")
        if not path.name.startswith("_")
        for line in path.read_text().splitlines()
    )
    print("disk reads:", actual, "response:", result)
    assert actual == expected
    assert result["filter_stats"]["n_passed"] == expected
    assert result["n_assigned"] == expected
    assert result["n_unassigned"] == 1 - expected
    assert sum(result["per_well_counts"].values()) == expected
