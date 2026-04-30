"""Barcode-mode consensus FASTA parser.

Expected layout::

    <input_dir>/
    +-- NB01/
    |   +-- 1_1.fasta   (header '>1_1')
    |   +-- 1_2.fasta
    ...

Header format is ``>{R}_{F}``; no metadata is carried
in the header. File size (LOWDEPTH signal) is measured via ``os.path.getsize``.

# TODO Phase 2: replace with native run-folder ingestion (now uses consumed directory)
# TODO Phase 2: F_R <-> R_F remapping (hmk xlsx uses F{n}_R{m}; FASTA uses {R}_{F})
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.models import BarcodeRecord


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
    with path.open("r", encoding="utf-8") as fh:
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

    # Fail-fast: reject raw-read FASTA bundles (multi-header files).
    # Each per-well file must contain exactly one consensus record after the
    # demux→alignment→consensus pipeline.  If multiple headers are present,
    # the caller passed a raw-read FASTA, which would cause incorrect
    # concatenated-sequence variant calling downstream.
    if header_count > 1:
        raise ValueError(
            f"FASTA file '{path}' contains {header_count} sequence records "
            "(expected exactly 1 consensus record). "
            "Raw-read FASTA bundles must be processed through the "
            "alignment+consensus pipeline before being passed to analyze()."
        )

    custom_barcode = header.split()[0] if header else path.stem
    consensus_seq = "".join(seq_parts).upper()
    size_bytes = path.stat().st_size
    file_size_kb = size_bytes / 1024.0
    read_count: int | None = header_count if header_count > 0 else None

    return BarcodeRecord(
        native_barcode=native_barcode,
        custom_barcode=custom_barcode,
        consensus_seq=consensus_seq,
        file_size_kb=file_size_kb,
        source_path=path,
        read_count=read_count,
    )


def load_barcode_directory(input_dir: Path) -> list[BarcodeRecord]:
    """Load all NBxx/{R}_{F}.fasta consensus files under ``input_dir``."""

    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Consensus FASTA input directory not found: {input_dir}")

    records: list[BarcodeRecord] = []
    for nb_dir in sorted(p for p in input_dir.iterdir() if p.is_dir()):
        native_barcode = nb_dir.name
        for fasta in sorted(nb_dir.glob("*.fasta")):
            records.append(parse_fasta_file(fasta, native_barcode=native_barcode))
    return records
