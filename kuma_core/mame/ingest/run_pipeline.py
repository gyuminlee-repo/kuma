"""Native MinKNOW run-folder ingestion.

Thin orchestration layer that turns a raw MinKNOW run directory
(``<run>/fastq_pass/...``) into per-well consensus :class:`BarcodeRecord`
objects, reusing the existing combinatorial-demux core functions.

Two modes:

- Single pool: all reads under ``fastq_pass/`` are pooled and demuxed with
  :func:`run_combinatorial_demux` (consensus written under
  ``demux_output_dir/consensus/{R}_{F}.fasta``).
- Per native barcode: each selected ``fastq_pass/<nb>/`` directory is demuxed
  independently with :func:`run_combinatorial_demux_per_nb`
  (consensus written under ``demux_output_dir/sort_barcode{NN}/{R}_{F}.fasta``).

No transform is inserted between the demux producer and the consensus consumer
so the ``{R}_{F}`` well-naming contract is preserved end to end.  This module
deliberately depends only on :mod:`kuma_core`; it never imports the sidecar
layer (the fastq-collection helpers are reimplemented here to keep that
boundary clean).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from kuma_core.mame.ingest.combinatorial_demux import (
    run_combinatorial_demux,
    run_combinatorial_demux_per_nb,
)
from kuma_core.mame.ingest.fasta_parser import load_barcode_directory
from kuma_core.mame.models import BarcodeRecord

ProgressCallback = Callable[[int, int, str], None]


def is_minknow_run_dir(path: Path) -> bool:
    """Return ``True`` iff *path* looks like a MinKNOW run directory.

    The only structural requirement is a ``fastq_pass/`` subdirectory.
    """

    return (path / "fastq_pass").is_dir()


def _collect_pool_fastq(run_dir: Path) -> list[Path]:
    """Collect all FASTQ(.gz) files under ``run_dir/fastq_pass`` (single pool).

    Mirrors the sidecar combinatorial-demux handler semantics: searches
    ``fastq_pass/`` recursively and raises :class:`FileNotFoundError` when the
    directory is absent or contains no FASTQ files.
    """

    fastq_pass = run_dir / "fastq_pass"
    if not fastq_pass.is_dir():
        raise FileNotFoundError(f"fastq_pass/ directory not found under {run_dir}")
    paths = sorted(fastq_pass.rglob("*.fastq")) + sorted(fastq_pass.rglob("*.fastq.gz"))
    if not paths:
        raise FileNotFoundError(f"No FASTQ files found under {fastq_pass}")
    return paths


def _collect_per_nb_fastq(
    run_dir: Path, native_barcodes: list[str]
) -> dict[str, list[Path]]:
    """Build ``{nb: [fastq, ...]}`` from ``run_dir/fastq_pass/<nb>`` directories.

    Mirrors the sidecar handler: raises :class:`FileNotFoundError` when a
    selected native-barcode directory is missing or has no FASTQ files.
    """

    fastq_pass = run_dir / "fastq_pass"
    if not fastq_pass.is_dir():
        raise FileNotFoundError(f"fastq_pass/ directory not found under {run_dir}")

    nb_to_fastq: dict[str, list[Path]] = {}
    for nb_name in native_barcodes:
        nb_input = fastq_pass / nb_name
        if not nb_input.is_dir():
            raise FileNotFoundError(f"native barcode dir not found: {nb_input}")
        fq = sorted(nb_input.rglob("*.fastq")) + sorted(nb_input.rglob("*.fastq.gz"))
        if not fq:
            raise FileNotFoundError(f"No FASTQ files under {nb_input}")
        nb_to_fastq[nb_name] = fq
    return nb_to_fastq


def ingest_run_folder(
    run_dir: Path,
    custom_barcodes_xlsx: Path,
    reference_fasta: Path,
    demux_output_dir: Path,
    native_barcodes: list[str] | None = None,
    *,
    mapq_threshold: int = 25,
    coverage_fraction: float = 0.98,
    trim_flank_bp: int = 30,
    edit_dist_ratio: float = 0.25,
    chimera_split: bool = True,
    min_depth: int = 3,
    progress_callback: ProgressCallback | None = None,
) -> list[BarcodeRecord]:
    """Ingest a raw MinKNOW run folder into per-well consensus records.

    Parameters
    ----------
    run_dir:
        MinKNOW run directory containing a ``fastq_pass/`` subdirectory.
    custom_barcodes_xlsx:
        xlsx with the combinatorial F/R barcode prefixes.
    reference_fasta:
        Single-record DNA FASTA used as the alignment reference.
    demux_output_dir:
        Destination directory for demux/consensus output (created if absent).
    native_barcodes:
        When truthy, run one demux per listed native barcode (per-NB mode);
        each name must correspond to a ``fastq_pass/<nb>/`` directory.  When
        ``None`` or empty, pool all reads (single-pool mode).

    Returns
    -------
    list[BarcodeRecord]
        Parsed per-well consensus records.  ``custom_barcode`` carries the
        ``{R}_{F}`` token straight from the consensus header (no transform).
    """

    demux_output_dir.mkdir(parents=True, exist_ok=True)

    if native_barcodes:
        nb_to_fastq = _collect_per_nb_fastq(run_dir, native_barcodes)
        run_combinatorial_demux_per_nb(
            nb_to_fastq,
            reference_fasta,
            custom_barcodes_xlsx,
            demux_output_dir,
            mapq_threshold=mapq_threshold,
            coverage_fraction=coverage_fraction,
            trim_flank_bp=trim_flank_bp,
            edit_dist_ratio=edit_dist_ratio,
            chimera_split=chimera_split,
            progress_callback=progress_callback,
        )
    else:
        fastq_paths = _collect_pool_fastq(run_dir)
        run_combinatorial_demux(
            fastq_paths,
            reference_fasta,
            custom_barcodes_xlsx,
            demux_output_dir,
            mapq_threshold=mapq_threshold,
            coverage_fraction=coverage_fraction,
            trim_flank_bp=trim_flank_bp,
            min_depth=min_depth,
            edit_dist_ratio=edit_dist_ratio,
            chimera_split=chimera_split,
            progress_callback=progress_callback,
        )

    return load_barcode_directory(demux_output_dir)
