# ruff: noqa: S101
"""Tests for the shared demux parameter contract in sidecar_mame.models.

Covers DemuxParamsBase and its two subclasses (CombinatorialDemuxParams,
AnalyzeRawRunParams), verifying the shared validators apply identically to
both subclasses and that subclass-specific required fields are enforced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sidecar_mame.models import (
    AnalyzeRawRunParams,
    CombinatorialDemuxParams,
    DemuxParamsBase,
)


# ---------------------------------------------------------------------------
# Fixtures: real files/dirs under tmp_path (validators only check existence)
# ---------------------------------------------------------------------------


@pytest.fixture()
def barcodes_xlsx(tmp_path: Path) -> Path:
    path = tmp_path / "barcodes.xlsx"
    path.write_bytes(b"stub")
    return path


@pytest.fixture()
def reference_fasta(tmp_path: Path) -> Path:
    path = tmp_path / "reference.fasta"
    path.write_text(">ref\nACGT\n")
    return path


@pytest.fixture()
def run_dir(tmp_path: Path) -> Path:
    path = tmp_path / "run"
    path.mkdir()
    return path


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    # Parent (tmp_path) exists; dir itself need not exist.
    return tmp_path / "output"


# ---------------------------------------------------------------------------
# Inheritance sanity
# ---------------------------------------------------------------------------


def test_subclasses_inherit_base() -> None:
    assert issubclass(CombinatorialDemuxParams, DemuxParamsBase)
    assert issubclass(AnalyzeRawRunParams, DemuxParamsBase)


# ---------------------------------------------------------------------------
# Valid parse
# ---------------------------------------------------------------------------


def test_valid_combinatorial_demux_params(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
) -> None:
    p = CombinatorialDemuxParams(
        minknow_run_dir=str(run_dir),
        custom_barcodes_xlsx=str(barcodes_xlsx),
        reference_fasta=str(reference_fasta),
        output_dir=str(output_dir),
    )
    assert p.minknow_run_dir == str(run_dir)
    assert p.custom_barcodes_xlsx == str(barcodes_xlsx)
    assert p.reference_fasta == str(reference_fasta)
    assert p.output_dir == str(output_dir)
    # Inherited defaults.
    assert p.mapq_threshold == 25
    assert p.coverage_fraction == 0.98
    assert p.edit_dist_ratio == 0.25
    assert p.chimera_split is True
    assert p.trim_flank_bp == 30
    assert p.native_barcodes is None


def test_valid_analyze_raw_run_params(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
) -> None:
    p = AnalyzeRawRunParams(
        minknow_run_dir=str(run_dir),
        custom_barcodes_xlsx=str(barcodes_xlsx),
        reference_fasta=str(reference_fasta),
    )
    assert p.minknow_run_dir == str(run_dir)
    assert p.custom_barcodes_xlsx == str(barcodes_xlsx)
    assert p.reference_fasta == str(reference_fasta)
    assert p.demux_output_dir is None
    # Inherited defaults present on the analyze subset too.
    assert p.mapq_threshold == 25
    assert p.chimera_split is True


def test_analyze_raw_run_optional_demux_output_dir(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "demux_out"  # parent exists
    p = AnalyzeRawRunParams(
        minknow_run_dir=str(run_dir),
        custom_barcodes_xlsx=str(barcodes_xlsx),
        reference_fasta=str(reference_fasta),
        demux_output_dir=str(out),
    )
    assert p.demux_output_dir == str(out)


def test_analyze_raw_run_demux_output_dir_parent_missing(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    tmp_path: Path,
) -> None:
    out = tmp_path / "missing_parent" / "demux_out"
    with pytest.raises(ValidationError):
        AnalyzeRawRunParams(
            minknow_run_dir=str(run_dir),
            custom_barcodes_xlsx=str(barcodes_xlsx),
            reference_fasta=str(reference_fasta),
            demux_output_dir=str(out),
        )


# ---------------------------------------------------------------------------
# Shared validators reject for BOTH subclasses
# ---------------------------------------------------------------------------


def _combinatorial_kwargs(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
) -> dict[str, object]:
    return {
        "minknow_run_dir": str(run_dir),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
        "reference_fasta": str(reference_fasta),
        "output_dir": str(output_dir),
    }


def _analyze_kwargs(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
) -> dict[str, object]:
    return {
        "minknow_run_dir": str(run_dir),
        "custom_barcodes_xlsx": str(barcodes_xlsx),
        "reference_fasta": str(reference_fasta),
    }


def test_traversal_in_barcodes_rejected_both(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
) -> None:
    bad = "../evil/barcodes.xlsx"

    combo = _combinatorial_kwargs(barcodes_xlsx, reference_fasta, run_dir, output_dir)
    combo["custom_barcodes_xlsx"] = bad
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(**combo)

    analyze = _analyze_kwargs(barcodes_xlsx, reference_fasta, run_dir)
    analyze["custom_barcodes_xlsx"] = bad
    with pytest.raises(ValidationError):
        AnalyzeRawRunParams(**analyze)


def test_missing_barcodes_rejected_both(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
    tmp_path: Path,
) -> None:
    missing = str(tmp_path / "does_not_exist.xlsx")

    combo = _combinatorial_kwargs(barcodes_xlsx, reference_fasta, run_dir, output_dir)
    combo["custom_barcodes_xlsx"] = missing
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(**combo)

    analyze = _analyze_kwargs(barcodes_xlsx, reference_fasta, run_dir)
    analyze["custom_barcodes_xlsx"] = missing
    with pytest.raises(ValidationError):
        AnalyzeRawRunParams(**analyze)


def test_missing_reference_rejected_both(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
    tmp_path: Path,
) -> None:
    missing = str(tmp_path / "no_reference.fasta")

    combo = _combinatorial_kwargs(barcodes_xlsx, reference_fasta, run_dir, output_dir)
    combo["reference_fasta"] = missing
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(**combo)

    analyze = _analyze_kwargs(barcodes_xlsx, reference_fasta, run_dir)
    analyze["reference_fasta"] = missing
    with pytest.raises(ValidationError):
        AnalyzeRawRunParams(**analyze)


def test_empty_native_barcodes_rejected_both(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
) -> None:
    combo = _combinatorial_kwargs(barcodes_xlsx, reference_fasta, run_dir, output_dir)
    combo["native_barcodes"] = []
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(**combo)

    analyze = _analyze_kwargs(barcodes_xlsx, reference_fasta, run_dir)
    analyze["native_barcodes"] = []
    with pytest.raises(ValidationError):
        AnalyzeRawRunParams(**analyze)


def test_native_barcode_path_separator_rejected_both(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
) -> None:
    combo = _combinatorial_kwargs(barcodes_xlsx, reference_fasta, run_dir, output_dir)
    combo["native_barcodes"] = ["barcode06", "evil/barcode07"]
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(**combo)

    analyze = _analyze_kwargs(barcodes_xlsx, reference_fasta, run_dir)
    analyze["native_barcodes"] = ["barcode06", "evil/barcode07"]
    with pytest.raises(ValidationError):
        AnalyzeRawRunParams(**analyze)


# ---------------------------------------------------------------------------
# Range validation still works (inherited Field constraints)
# ---------------------------------------------------------------------------


def test_mapq_threshold_out_of_range_rejected_both(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
) -> None:
    combo = _combinatorial_kwargs(barcodes_xlsx, reference_fasta, run_dir, output_dir)
    combo["mapq_threshold"] = 100
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(**combo)

    analyze = _analyze_kwargs(barcodes_xlsx, reference_fasta, run_dir)
    analyze["mapq_threshold"] = 100
    with pytest.raises(ValidationError):
        AnalyzeRawRunParams(**analyze)


def test_coverage_fraction_zero_rejected(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
    output_dir: Path,
) -> None:
    combo = _combinatorial_kwargs(barcodes_xlsx, reference_fasta, run_dir, output_dir)
    combo["coverage_fraction"] = 0.0
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(**combo)


# ---------------------------------------------------------------------------
# Regression: CombinatorialDemuxParams still requires its own fields
# ---------------------------------------------------------------------------


def test_combinatorial_requires_minknow_run_dir(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    output_dir: Path,
) -> None:
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(
            custom_barcodes_xlsx=str(barcodes_xlsx),
            reference_fasta=str(reference_fasta),
            output_dir=str(output_dir),
        )


def test_combinatorial_requires_output_dir(
    barcodes_xlsx: Path,
    reference_fasta: Path,
    run_dir: Path,
) -> None:
    with pytest.raises(ValidationError):
        CombinatorialDemuxParams(
            minknow_run_dir=str(run_dir),
            custom_barcodes_xlsx=str(barcodes_xlsx),
            reference_fasta=str(reference_fasta),
        )


def test_analyze_requires_minknow_run_dir(
    barcodes_xlsx: Path,
    reference_fasta: Path,
) -> None:
    with pytest.raises(ValidationError):
        AnalyzeRawRunParams(
            custom_barcodes_xlsx=str(barcodes_xlsx),
            reference_fasta=str(reference_fasta),
        )
