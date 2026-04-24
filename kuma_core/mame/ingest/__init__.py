"""Consensus FASTA ingest + mode routing."""

from kuma_core.mame.ingest.fasta_parser import load_barcode_directory, parse_fasta_file
from kuma_core.mame.ingest.mode_router import IngestMode, route_ingest

__all__ = ["load_barcode_directory", "parse_fasta_file", "IngestMode", "route_ingest"]
