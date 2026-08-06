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

from dataclasses import asdict
from pathlib import Path
from typing import Callable

from kuma_core.mame.ingest.combinatorial_demux import (
    CONSENSUS_SUBDIR,
    run_combinatorial_demux,
    run_combinatorial_demux_per_nb,
)
from kuma_core.mame.ingest.demux import FASTQ_PATTERNS
from kuma_core.mame.ingest.fasta_parser import load_barcode_directory
from kuma_core.mame.models import BarcodeRecord

# The name a pooled run files its single pseudo-plate under. Imported from the
# consumer rather than restated here: "pool" is the token that tells the
# contamination report a run has no replicate axis, and two spellings of it
# would let the producer and the consumer disagree in silence.
from kuma_core.mame.qc.contamination import POOLED_PLATE_NAME as _POOLED_PLATE_NAME
from kuma_core.shared.fs_walk import rglob_entries

ProgressCallback = Callable[[int, int, str], None]


def _collect_fastq_sorted(directory: Path) -> list[Path]:
    """FASTQ(.gz) under *directory*, ordered as the two-``rglob`` version was.

    The previous expression was ``sorted(rglob("*.fastq")) + sorted(rglob(
    "*.fastq.gz"))``: two walks, and a concatenation of two independently sorted
    groups rather than one merged sort.  Both properties are preserved here, the
    group order included, because this list is the demux input order.
    """
    matches = rglob_entries(directory, FASTQ_PATTERNS)
    out: list[Path] = []
    for pattern in FASTQ_PATTERNS:
        out.extend(sorted(path for path, _entry in matches[pattern]))
    return out


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
    paths = _collect_fastq_sorted(fastq_pass)
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
        fq = _collect_fastq_sorted(nb_input)
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
    stats_out: dict[str, int] | None = None,
    per_nb_out: list[dict] | None = None,
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
    stats_out:
        Optional sink for the demux gate counters.  When given, it is updated
        in place with the :class:`DemuxStats` fields the run produced
        (``total_reads``, ``passed_mapq``, ``passed_coverage``,
        ``assigned_reads``, ``ambiguous_dropped``, ``chimera_splits``,
        ``wells_with_reads``, ``wells_with_min_reads``), summed across native
        barcodes in per-NB mode.  Passed as a sink rather than folded into the
        return value so existing callers that only want the records keep the
        same signature.  These counters exist only because this function runs
        the demux; a caller that consumes an already-demuxed consensus
        directory has no equivalent source for them.
    per_nb_out:
        Optional sink for the per-native-barcode demux summaries, same shape of
        contract as ``stats_out``: a container the caller owns, extended in
        place, so the return value keeps its type. Each entry is one plate copy
        and carries ``nb_name``, ``sort_barcode_name``, ``stats`` (the same 8
        ``DemuxStats`` counters, for that copy alone) and
        ``per_well_read_counts`` (``{R}_{F}`` token -> reads assigned to it).

        That last mapping is the reason this sink exists. The demux already
        counts reads for every barcode combination it saw, including the ones
        no well of the campaign occupies, and until now the whole matrix was
        computed and dropped on the floor here: only the summed counters
        reached the caller. Reads landing on a combination nobody pipetted are
        the one direct measurement of stray reads this pipeline makes, and a
        sum cannot say where they landed.

        Single-pool mode contributes exactly one entry, a pseudo-plate named
        ``"pool"`` on both name fields. Pooling is one plate as far as the
        matrix is concerned; giving it zero entries would make "pooled" and
        "no demux ran" the same observation.

    Returns
    -------
    list[BarcodeRecord]
        Parsed per-well consensus records.  ``custom_barcode`` carries the
        ``{R}_{F}`` token straight from the consensus header (no transform).
    """

    demux_output_dir.mkdir(parents=True, exist_ok=True)

    if native_barcodes:
        nb_to_fastq = _collect_per_nb_fastq(run_dir, native_barcodes)
        per_nb = run_combinatorial_demux_per_nb(
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
        if stats_out is not None:
            # ``merged_stats`` already sums the DemuxStats counters across every
            # native barcode, including units restored from a resume marker.
            stats_out.update(
                {k: int(v) for k, v in per_nb["merged_stats"].items()}
            )
        if per_nb_out is not None:
            # Copied out rather than handed over: the summaries are the demux
            # orchestrator's own working state (a resume reseeds entries from
            # markers into the same list), and a caller that held a reference to
            # it would be reading a structure that is not its to keep.
            per_nb_out.extend(
                {
                    "nb_name": str(summary["nb_name"]),
                    "sort_barcode_name": str(summary["sort_barcode_name"]),
                    "stats": {k: int(v) for k, v in summary["stats"].items()},
                    "per_well_read_counts": {
                        str(well): int(count)
                        for well, count in summary["per_well_read_counts"].items()
                    },
                }
                for summary in per_nb["per_nb"]
            )
        units = [str(summary["sort_barcode_name"]) for summary in per_nb["per_nb"]]
    else:
        fastq_paths = _collect_pool_fastq(run_dir)
        pooled = run_combinatorial_demux(
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
        if stats_out is not None:
            stats_out.update(
                {k: int(v) for k, v in asdict(pooled.stats).items()}
            )
        if per_nb_out is not None:
            # One pseudo-plate. Pooling puts every read of the folder onto one
            # plate, so the matrix has one column; what it cannot have is a
            # replicate axis, and the consumer decides what that costs each
            # signal rather than being handed an empty list it would have to
            # tell apart from "no demux ran".
            per_nb_out.append(
                {
                    "nb_name": _POOLED_PLATE_NAME,
                    "sort_barcode_name": _POOLED_PLATE_NAME,
                    "stats": {k: int(v) for k, v in asdict(pooled.stats).items()},
                    "per_well_read_counts": {
                        str(well): int(count)
                        for well, count in pooled.per_well_read_counts.items()
                    },
                }
            )
        units = [CONSENSUS_SUBDIR]

    # Read back the units THIS run wrote, not whatever the directory holds.
    # ``demux_output_dir`` is stable so a re-run can resume, and nothing removes
    # what an earlier run left: analysing the same folder per native barcode and
    # then pooled leaves ``sort_barcode06/`` and ``sort_barcode20/`` beside
    # ``consensus/``, and reading all three would put three plates in the
    # verdicts while ``per_nb_out`` states one. One response, one plate count.
    return load_barcode_directory(demux_output_dir, units=units)
