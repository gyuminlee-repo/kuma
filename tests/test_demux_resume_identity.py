import gzip
import json
import os
from pathlib import Path
from random import Random

import openpyxl
import pytest

from kuma_core.mame.ingest.combinatorial_demux import run_combinatorial_demux_per_nb
from kuma_core.mame.ingest.stage_marker import MARKER_FILENAME, is_unit_complete
from tests.mame.minimap2_support import requires_minimap2
from tests.mame.test_combinatorial_demux import (
    _F_BARCODES,
    _F_TAIL,
    _R_BARCODES,
    _R_TAIL,
    _build_read,
)

# Every test here drives the real combinatorial demux, which shells out to
# minimap2. ci.yml provisions that binary for Linux and macOS only, so the
# Windows leg has to skip rather than fail on a missing aligner.
pytestmark = requires_minimap2


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    sequence = "".join(Random(731).choices("ACGT", k=400))
    reference = tmp_path / "reference.fasta"
    reference.write_text(f">reference\n{sequence}\n", encoding="ascii")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    for axis, seeds, tail in (("f", _F_BARCODES, _F_TAIL), ("r", _R_BARCODES, _R_TAIL)):
        for index, seed in enumerate(seeds, 1):
            sheet.append([f"test_{axis}_{index}", seed + tail])
    barcodes = tmp_path / "barcodes.xlsx"
    workbook.save(barcodes)
    workbook.close()
    read = _build_read(1, 1, sequence)
    fastq = tmp_path / "reads.fastq"
    fastq.write_text(f"@read\n{read}\n+\n{'I' * len(read)}\n" * 3, encoding="ascii")
    return reference, barcodes, fastq, sequence


@pytest.mark.parametrize("change", ["same_stat", "gzip", "add", "remove", "rename", "legacy", "workbook"])
def test_changed_inputs_recompute_clean_inventory(
    inputs: tuple[Path, Path, Path, str], tmp_path: Path, change: str,
) -> None:
    reference, barcodes, fastq, sequence = inputs
    paths = [fastq]
    if change == "gzip":
        compressed = tmp_path / "reads.fastq.gz"
        compressed.write_bytes(gzip.compress(fastq.read_bytes(), mtime=0))
        paths = [compressed]
    if change == "remove":
        extra = tmp_path / "extra.fastq"
        extra.write_bytes(fastq.read_bytes())
        paths.append(extra)
    output = tmp_path / "output"
    first = run_combinatorial_demux_per_nb(
        {"barcode01": paths}, reference, barcodes, output, parallel=False,
    )
    unit = output / "sort_barcode01"
    old_consensus = (unit / "1_1.fasta").read_bytes()
    (unit / "reads").mkdir(exist_ok=True)
    (unit / "reads" / "stale.fasta").write_bytes(old_consensus)
    expected = {"1_1": 3}
    if change in {"same_stat", "gzip"}:
        read = _build_read(2, 1, sequence)
        record = f"@read\n{read}\n+\n{'I' * len(read)}\n" * 3
        before = paths[0].stat()
        content = record.encode("ascii")
        paths[0].write_bytes(gzip.compress(content, mtime=0) if change == "gzip" else content)
        os.utime(paths[0], ns=(before.st_atime_ns, before.st_mtime_ns))
        if change == "same_stat":
            assert paths[0].stat().st_size == before.st_size
        expected = {"2_1": 3}
    elif change == "add":
        extra = tmp_path / "extra.fastq"
        extra.write_bytes(fastq.read_bytes())
        paths.append(extra)
        expected = {"1_1": 6}
    elif change == "remove":
        paths.pop()
    elif change == "rename":
        renamed = tmp_path / "renamed.fastq"
        fastq.rename(renamed)
        paths = [renamed]
    elif change == "legacy":
        marker = unit / MARKER_FILENAME
        data = json.loads(marker.read_text())
        data["inputs"]["params"] = {
            key: value for key, value in data["inputs"]["params"].items()
            if key in {"mapq_threshold", "coverage_fraction", "trim_flank_bp", "edit_dist_ratio", "chimera_split"}
        }
        marker.write_text(json.dumps(data))
    elif change == "workbook":
        before = barcodes.stat()
        workbook = openpyxl.load_workbook(barcodes)
        sheet = workbook.active
        assert sheet is not None
        sheet["B1"], sheet["B2"] = sheet["B2"].value, sheet["B1"].value
        workbook.save(barcodes)
        workbook.close()
        os.utime(barcodes, ns=(before.st_atime_ns, before.st_mtime_ns))
        expected = {"1_2": 3}

    result = run_combinatorial_demux_per_nb(
        {"barcode01": paths}, reference, barcodes, output, parallel=False,
    )

    assert first["recomputed_units"] == 1
    assert result["reused_units"] == 0
    assert result["per_nb"][0]["per_well_read_counts"] == expected
    assert is_unit_complete(unit)
    assert {path.stem for path in unit.glob("*.fasta")} == set(expected)
    assert {path.stem for path in (unit / "reads").glob("*.fasta")} <= set(expected)
    archived = list(tmp_path.glob(".output-demux-stale-*/sort_barcode01/1_1.fasta"))
    assert len(archived) == 1
    assert archived[0].read_bytes() == old_consensus


@pytest.mark.parametrize("parallel", [False, True])
def test_unchanged_units_reuse_and_changed_unit_isolated(
    inputs: tuple[Path, Path, Path, str], tmp_path: Path, parallel: bool,
) -> None:
    reference, barcodes, fastq, _ = inputs
    other = tmp_path / "other.fastq"
    other.write_bytes(fastq.read_bytes())
    paths = {"barcode01": [fastq], "barcode02": [other]}
    output = tmp_path / "output"
    first = run_combinatorial_demux_per_nb(paths, reference, barcodes, output, parallel=parallel, max_workers=2)
    marker = output / "sort_barcode02" / MARKER_FILENAME
    before = marker.stat().st_mtime_ns
    os.utime(fastq, ns=(1, 1))
    os.utime(barcodes, ns=(1, 1))
    reused = run_combinatorial_demux_per_nb(paths, reference, barcodes, output, parallel=parallel, max_workers=2)
    assert reused["reused_units"] == 2
    assert reused["merged_stats"] == first["merged_stats"]
    fastq.write_bytes(fastq.read_bytes() * 2)

    changed = run_combinatorial_demux_per_nb(paths, reference, barcodes, output, parallel=parallel, max_workers=2)

    assert changed["reused_units"] == 1
    assert changed["recomputed_units"] == 1
    assert changed["per_nb"][0]["per_well_read_counts"] == {"1_1": 6}
    assert marker.stat().st_mtime_ns == before


def test_removed_native_barcode_is_not_left_in_active_output(
    inputs: tuple[Path, Path, Path, str], tmp_path: Path,
) -> None:
    reference, barcodes, fastq, _ = inputs
    output = tmp_path / "output"
    run_combinatorial_demux_per_nb(
        {"barcode01": [fastq], "barcode02": [fastq]}, reference, barcodes, output, parallel=False,
    )

    result = run_combinatorial_demux_per_nb(
        {"barcode01": [fastq]}, reference, barcodes, output, parallel=False,
    )

    assert result["reused_units"] == 1
    assert not (output / "sort_barcode02").exists()
    assert len(list(tmp_path.glob(".output-demux-stale-*/sort_barcode02/1_1.fasta"))) == 1
