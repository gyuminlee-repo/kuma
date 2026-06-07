"""Ingest mode router (Amplicon vs Barcode).

Phase 1 MVP consumes the Barcode-mode output tree. Amplicon mode is exposed
for completeness so the CLI can round-trip both layouts even though only the
barcode mode is wired into the end-to-end pipeline.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from kuma_core.mame.ingest.fasta_parser import load_barcode_directory, parse_fasta_file
from kuma_core.mame.models import BarcodeRecord

_AMPLICON_CONSENSUS_PATTERNS = (
    "*-consensus.fasta",
    "*-consensus.fa",
)


class IngestMode(StrEnum):
    AMPLICON = "amplicon"
    BARCODE = "barcode"


def _load_barcode(input_dir: Path) -> list[BarcodeRecord]:
    return load_barcode_directory(input_dir)


def _load_amplicon(input_dir: Path) -> list[BarcodeRecord]:
    """Amplicon mode: consumes a single ``{M_FILE}-consensus.fasta``.

    We treat the basename (minus ``-consensus``) as the native barcode label.
    """

    records: list[BarcodeRecord] = []
    seen: set[Path] = set()
    for pattern in _AMPLICON_CONSENSUS_PATTERNS:
        for consensus_file in sorted(input_dir.rglob(pattern)):
            if consensus_file in seen:
                continue
            seen.add(consensus_file)
            native = consensus_file.stem.replace("-consensus", "") or "AMPLICON"
            records.append(parse_fasta_file(consensus_file, native_barcode=native))
    return records


def route_ingest(input_dir: Path, mode: IngestMode) -> list[BarcodeRecord]:
    if mode is IngestMode.BARCODE:
        return _load_barcode(input_dir)
    if mode is IngestMode.AMPLICON:
        return _load_amplicon(input_dir)
    raise ValueError(f"Unknown ingest mode: {mode!r}")
