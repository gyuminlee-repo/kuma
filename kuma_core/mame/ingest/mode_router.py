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
from kuma_core.shared.fs_walk import rglob_entries

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

    One walk answers both patterns.  ``rglob`` per pattern was two complete
    recursive walks of the same tree, which on a Windows share (9p/drvfs) costs
    a stat per entry per walk.  The ``seen`` set is kept because the patterns
    could overlap in principle and the dedup decides which of two matches wins.
    Passing the walk's ``DirEntry`` down to ``parse_fasta_file`` also moves
    ``file_size_kb`` off ``Path.stat()``; amplicon mode was the last caller
    still taking that fallback.  On Linux this is not one fewer syscall, since
    ``scandir`` reports the file type but not ``st_size``, but it resolves
    against the directory fd rather than the whole path, which is the cheaper
    of the two on a share.  Measured effect is in ``scripts/verify_9p_sweep.py``:
    the walk, not the size lookup, is what this change buys.
    """

    records: list[BarcodeRecord] = []
    seen: set[Path] = set()
    matches = rglob_entries(input_dir, _AMPLICON_CONSENSUS_PATTERNS)
    for pattern in _AMPLICON_CONSENSUS_PATTERNS:
        for consensus_file, entry in sorted(matches[pattern]):
            if consensus_file in seen:
                continue
            seen.add(consensus_file)
            native = consensus_file.stem.replace("-consensus", "") or "AMPLICON"
            records.append(
                parse_fasta_file(consensus_file, native_barcode=native, entry=entry)
            )
    return records


def route_ingest(input_dir: Path, mode: IngestMode) -> list[BarcodeRecord]:
    if mode is IngestMode.BARCODE:
        return _load_barcode(input_dir)
    if mode is IngestMode.AMPLICON:
        return _load_amplicon(input_dir)
    raise ValueError(f"Unknown ingest mode: {mode!r}")
