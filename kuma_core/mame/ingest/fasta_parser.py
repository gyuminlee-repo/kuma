"""Barcode-mode consensus FASTA parser.

Expected layout::

    <input_dir>/
    +-- NB01/
    |   +-- 1_1.fasta       (header '>1_1 depth=12')
    |   +-- 1_2.fasta
    ...

Header format is ``>{R}_{F}``, optionally followed by MAME demux→consensus
metadata such as ``depth=N``, ``low_depth_positions=N``, and
``consensus_n_fraction=0.000``. Alignment drop counters
(``input_reads``, ``aligned_reads``, ``mapq_failed``, ``span_failed``) and
``low_quality_bases`` are preserved when present. File size is kept as a legacy
LOWDEPTH fallback for consensus files that do not carry real read depth.

# TODO Phase 2: replace with native run-folder ingestion (now uses consumed directory)
# TODO Phase 2: F_R <-> R_F remapping (barcode xlsx uses F{n}_R{m}; FASTA uses {R}_{F})
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path

from kuma_core.mame.ingest.consensus_metadata import (
    ALIGNED_READS,
    CONSENSUS_N_FRACTION,
    DEPTH,
    INPUT_READS,
    LOW_DEPTH_POSITIONS,
    LOW_QUALITY_BASES,
    MAPQ_FAILED,
    MAX_MINOR_ALLELE_FRACTION,
    MIXED_POSITIONS,
    SPAN_FAILED,
)
from kuma_core.mame.ingest.stage_marker import (
    CONSENSUS_FILE_PATTERNS,
    read_stage_marker,
    validate_marker,
)
from kuma_core.mame.models import BarcodeRecord

_logger = logging.getLogger(__name__)

_METADATA_RE = re.compile(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")


def _open_text(path: Path):
    return path.open("r", encoding="utf-8")


def _read_metadata(header: str) -> dict[str, str]:
    return {key.lower(): value for key, value in _METADATA_RE.findall(header)}


def _read_int_metadata(metadata: dict[str, str], key: str) -> int | None:
    value = metadata.get(key.lower())
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _read_float_metadata(metadata: dict[str, str], key: str) -> float | None:
    value = metadata.get(key.lower())
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _consensus_n_fraction(consensus_seq: str) -> float:
    if not consensus_seq:
        return 0.0
    return consensus_seq.count("N") / len(consensus_seq)


def _iter_consensus_files(directory: Path) -> Iterator[Path]:
    seen: set[Path] = set()
    for pattern in CONSENSUS_FILE_PATTERNS:
        for path in sorted(directory.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            yield path


def _parse_single_fasta(path: Path) -> tuple[str, str, int, dict[str, str]]:
    with _open_text(path) as fh:
        lines = [ln.rstrip("\r\n") for ln in fh.readlines()]

    header: str | None = None
    seq_parts: list[str] = []
    header_count: int = 0
    for ln in lines:
        if ln.startswith(">"):
            if header_count == 0:
                header = ln[1:].strip()
            header_count += 1
        elif ln:
            seq_parts.append(ln.strip())

    if header is None:
        raise ValueError(f"FASTA file '{path}' has no header line")

    if header_count > 1:
        raise ValueError(
            f"FASTA file '{path}' contains {header_count} sequence records "
            "(expected exactly 1 consensus record). "
            "Raw-read FASTA bundles must be processed through the "
            "alignment+consensus pipeline before being passed to analyze()."
        )

    consensus_seq = "".join(seq_parts).upper()
    return header, consensus_seq, header_count, _read_metadata(header)


def parse_fasta_file(path: Path, native_barcode: str) -> BarcodeRecord:
    """Parse a single consensus FASTA file into a BarcodeRecord.

    Raises
    ------
    ValueError
        If the file has no header line.
    ValueError
        If the file contains more than one header record (``>`` line).
        After the demux→consensus pipeline, each per-well file must contain
        exactly one consensus sequence.  Multiple headers indicate that raw
        read FASTA was passed instead of a consensus file.
    """

    # Read-only access: raw data is never modified.
    header, consensus_seq, record_count, metadata = _parse_single_fasta(path)

    custom_barcode = header.split()[0] if header else path.stem
    size_bytes = path.stat().st_size
    file_size_kb = size_bytes / 1024.0
    depth = _read_int_metadata(metadata, DEPTH)
    read_count: int | None = depth if depth is not None else record_count
    n_mixed_positions = _read_int_metadata(metadata, MIXED_POSITIONS) or 0
    max_minor_allele_fraction = (
        _read_float_metadata(metadata, MAX_MINOR_ALLELE_FRACTION) or 0.0
    )
    n_low_depth_positions = _read_int_metadata(metadata, LOW_DEPTH_POSITIONS) or 0
    consensus_n_fraction = _read_float_metadata(metadata, CONSENSUS_N_FRACTION)
    if consensus_n_fraction is None:
        consensus_n_fraction = _consensus_n_fraction(consensus_seq)
    n_low_quality_bases = _read_int_metadata(metadata, LOW_QUALITY_BASES) or 0
    n_input_reads = _read_int_metadata(metadata, INPUT_READS)
    n_aligned_reads = _read_int_metadata(metadata, ALIGNED_READS)
    n_mapq_failed = _read_int_metadata(metadata, MAPQ_FAILED) or 0
    n_span_failed = _read_int_metadata(metadata, SPAN_FAILED) or 0

    return BarcodeRecord(
        native_barcode=native_barcode,
        custom_barcode=custom_barcode,
        consensus_seq=consensus_seq,
        file_size_kb=file_size_kb,
        source_path=path,
        read_count=read_count,
        n_mixed_positions=n_mixed_positions,
        max_minor_allele_fraction=max_minor_allele_fraction,
        n_low_depth_positions=n_low_depth_positions,
        consensus_n_fraction=consensus_n_fraction,
        n_low_quality_bases=n_low_quality_bases,
        n_input_reads=n_input_reads,
        n_aligned_reads=n_aligned_reads,
        n_mapq_failed=n_mapq_failed,
        n_span_failed=n_span_failed,
    )


def load_barcode_directory(input_dir: Path) -> list[BarcodeRecord]:
    """Load all NBxx consensus FASTA files under ``input_dir``.

    Asymmetric completion-marker guard (per NB subdir):

    - marker PRESENT and valid (recorded inventory matches files on disk):
      proceed.
    - marker PRESENT but invalid (count mismatch / interrupted write): raise
      ``ValueError`` (fail-fast), converting a silent partial-directory read
      into an explicit error.
    - marker ABSENT: proceed (warn once for the dir).  Legacy output dirs and
      externally-sorted barcode directories carry no marker and must still
      work; a marker is never required.
    """

    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Consensus FASTA input directory not found: {input_dir}")

    records: list[BarcodeRecord] = []
    for nb_dir in sorted(p for p in input_dir.iterdir() if p.is_dir()):
        native_barcode = nb_dir.name

        marker = read_stage_marker(nb_dir)
        if marker is None:
            _logger.warning(
                "No demux/consensus completion marker in %s; proceeding "
                "(legacy or externally-sorted directory).",
                nb_dir,
            )
        else:
            ok, reason = validate_marker(marker, nb_dir)
            if not ok:
                raise ValueError(
                    f"Demux/consensus output for '{native_barcode}' is "
                    f"incomplete or corrupt (completion marker present but "
                    f"inventory does not match): {reason}. "
                    "Re-run the demux+consensus stage for this unit."
                )

        for consensus_file in _iter_consensus_files(nb_dir):
            records.append(parse_fasta_file(consensus_file, native_barcode=native_barcode))
    return records
