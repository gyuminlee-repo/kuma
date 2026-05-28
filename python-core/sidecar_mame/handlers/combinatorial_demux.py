"""``mame.run_combinatorial_demux`` JSON-RPC handler.

Collects FASTQ reads from a MinKNOW run directory, runs MAPQ-filtered
alignment-anchored fuzzy barcode demux against a 96-well combinatorial
barcode plate, and returns per-well read counts and consensus sequences.

RPC method name: ``mame.run_combinatorial_demux``
Registered in ``sidecar_mame.dispatcher._METHODS``.

Parameter schema
----------------
See :class:`sidecar_mame.models.CombinatorialDemuxParams` for full field
documentation and validation rules.

Response schema
---------------
``output_dir``        (str)               Resolved output directory path.
``stats``             (dict)              Summary counters from DemuxStats:
                                          total_reads, passed_mapq,
                                          passed_coverage, assigned_reads,
                                          ambiguous_dropped, chimera_splits,
                                          wells_with_reads, wells_with_min_reads.
``wells_with_reads``  (int)               Shortcut for stats.wells_with_reads.
``assigned_reads``    (int)               Shortcut for stats.assigned_reads.
``chimera_splits``    (int)               Shortcut for stats.chimera_splits.
``per_well_consensus`` (dict[str, str])   Well name -> consensus sequence.
``per_well_read_counts`` (dict[str, int]) Well name -> read count.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sidecar_mame.core import _send
from sidecar_mame.models import CombinatorialDemuxParams

_logger = logging.getLogger(__name__)


def _collect_fastq(minknow_run_dir: Path) -> list[Path]:
    """Collect FASTQ(.gz) files from a MinKNOW run directory.

    Searches ``fastq_pass/`` recursively for ``.fastq`` and ``.fastq.gz``
    files.  Raises ``FileNotFoundError`` when the ``fastq_pass/`` directory is
    absent or contains no FASTQ files.
    """
    fastq_pass = minknow_run_dir / "fastq_pass"
    if not fastq_pass.exists():
        raise FileNotFoundError(
            f"fastq_pass/ directory not found under {minknow_run_dir}"
        )
    paths = sorted(fastq_pass.rglob("*.fastq")) + sorted(
        fastq_pass.rglob("*.fastq.gz")
    )
    if not paths:
        raise FileNotFoundError(
            f"No FASTQ files found under {fastq_pass}"
        )
    return paths


def _send_progress(req_id: object, stage: str, pct: int, message: str) -> None:
    """Emit a JSON-RPC progress notification to stdout."""
    _send(
        {
            "jsonrpc": "2.0",
            "method": "progress",
            "params": {
                "id": req_id,
                "stage": stage,
                "pct": pct,
                "message": message,
            },
        }
    )


def handle_run_combinatorial_demux(params: dict) -> dict:
    """Run combinatorial barcode demux pipeline.

    Heavy I/O (alignment + consensus) - registered as an async method in
    dispatcher.py so that stdin keeps draining during execution.

    Parameters
    ----------
    params:
        Raw JSON-RPC params dict validated via
        :class:`~sidecar_mame.models.CombinatorialDemuxParams`.

    Returns
    -------
    dict
        Result dict matching the response schema documented in the module
        docstring.
    """
    from kuma_core.mame.ingest.combinatorial_demux import run_combinatorial_demux

    # Validate and parse params via Pydantic model
    p = CombinatorialDemuxParams.model_validate(params)

    req_id = params.get("_req_id")  # passed by dispatcher for progress tracking

    run_dir = Path(p.minknow_run_dir)
    barcodes_xlsx = Path(p.custom_barcodes_xlsx)
    reference_fasta = Path(p.reference_fasta)
    output_dir = Path(p.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Stage 1: collect FASTQ files
    _send_progress(req_id, "alignment", 0, "Collecting FASTQ files...")
    fastq_paths = _collect_fastq(run_dir)
    _logger.info(
        "combinatorial_demux: %d FASTQ files from %s",
        len(fastq_paths),
        run_dir,
    )

    # Stage 2: alignment (happens inside run_combinatorial_demux)
    _send_progress(req_id, "alignment", 10, f"Aligning {len(fastq_paths)} FASTQ file(s)...")

    # Stage 3: coverage filter notification (emitted before call; actual
    # filtering is internal to the core function)
    _send_progress(req_id, "coverage_filter", 30, "Applying MAPQ and coverage filter...")

    # Stage 4: demux (emitted optimistically; core runs alignment+demux atomically)
    _send_progress(req_id, "demux", 50, "Running combinatorial barcode demux...")

    result = run_combinatorial_demux(
        raw_fastq_paths=fastq_paths,
        reference_fasta=reference_fasta,
        barcodes_xlsx=barcodes_xlsx,
        output_dir=output_dir,
        mapq_threshold=p.mapq_threshold,
        coverage_fraction=p.coverage_fraction,
        trim_flank_bp=p.trim_flank_bp,
        edit_dist_ratio=p.edit_dist_ratio,
        chimera_split=p.chimera_split,
    )

    # Stage 5: consensus
    _send_progress(req_id, "consensus", 80, "Calling per-well consensus sequences...")

    _send_progress(req_id, "consensus", 100, "Done.")

    stats = result.stats
    per_well_read_counts = {
        well: len(reads) for well, reads in result.per_well_reads.items()
    }

    _logger.info(
        "combinatorial_demux complete: %d assigned reads, %d wells with reads",
        stats.assigned_reads,
        stats.wells_with_reads,
    )

    return {
        "output_dir": str(output_dir.resolve()),
        "stats": {
            "total_reads": stats.total_reads,
            "passed_mapq": stats.passed_mapq,
            "passed_coverage": stats.passed_coverage,
            "assigned_reads": stats.assigned_reads,
            "ambiguous_dropped": stats.ambiguous_dropped,
            "chimera_splits": stats.chimera_splits,
            "wells_with_reads": stats.wells_with_reads,
            "wells_with_min_reads": stats.wells_with_min_reads,
        },
        "wells_with_reads": stats.wells_with_reads,
        "assigned_reads": stats.assigned_reads,
        "chimera_splits": stats.chimera_splits,
        "per_well_consensus": result.per_well_consensus,
        "per_well_read_counts": per_well_read_counts,
    }


__all__ = ["handle_run_combinatorial_demux"]
