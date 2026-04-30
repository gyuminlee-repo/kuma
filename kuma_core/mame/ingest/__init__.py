"""Consensus FASTA ingest + mode routing + raw-run demux/filter + alignment/consensus."""

from kuma_core.mame.ingest.fasta_parser import load_barcode_directory, parse_fasta_file
from kuma_core.mame.ingest.mode_router import IngestMode, route_ingest
from kuma_core.mame.ingest.demux import DemuxResult, demux_native_barcode, parse_custom_barcodes
from kuma_core.mame.ingest.quality_filter import (
    QualityFilterParams,
    QualityFilterResult,
    filter_reads_by_summary,
)
from kuma_core.mame.ingest.align import Alignment, align_reads
from kuma_core.mame.ingest.consensus import call_consensus, per_position_depth
from kuma_core.mame.ingest.well_consensus import ConsensusResult, compute_well_consensuses

__all__ = [
    "load_barcode_directory",
    "parse_fasta_file",
    "IngestMode",
    "route_ingest",
    "DemuxResult",
    "demux_native_barcode",
    "parse_custom_barcodes",
    "QualityFilterParams",
    "QualityFilterResult",
    "filter_reads_by_summary",
    "Alignment",
    "align_reads",
    "call_consensus",
    "per_position_depth",
    "ConsensusResult",
    "compute_well_consensuses",
]
