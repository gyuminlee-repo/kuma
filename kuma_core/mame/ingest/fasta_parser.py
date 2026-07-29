"""Barcode-mode consensus FASTA parser.

Expected layout::

    <input_dir>/
    +-- NB01/
    |   +-- 1_1.fasta       (header '>1_1 depth=12')
    |   +-- 1_2.fasta
    ...

Header format is ``>{R}_{F}`` (R = reverse-barcode index / plate row 1–8,
F = forward-barcode index / plate column 1–12), optionally followed by MAME
demux→consensus metadata such as ``depth=N``, ``low_depth_positions=N``, and
``consensus_n_fraction=0.000``. Alignment drop counters
(``input_reads``, ``aligned_reads``, ``mapq_failed``, ``span_failed``) and
``low_quality_bases`` are preserved when present. File size is kept as a legacy
LOWDEPTH fallback for consensus files that do not carry real read depth.

This parser consumes the post-demux consensus directory produced by the
combinatorial-demux stage (``combinatorial_demux`` writes ``{R}_{F}.fasta``).
The ``{R}_{F}`` token is the single canonical well-naming convention shared
verbatim with every downstream consumer (``_custom_barcode_to_seq`` →
``seq_to_well``, F→column / R→row); the producer↔consumer orientation is locked
by ``tests/mame/test_well_naming_contract.py``. Direct native MinKNOW
run-folder ingestion (skipping the explicit demux output directory) is a
separate future pipeline entry point, not a concern of this consensus parser.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path

from kuma_core.mame.ingest.consensus_metadata import (
    ALIGNED_READS,
    BASIS_COVERED,
    CONSENSUS_N_FRACTION,
    CONSENSUS_N_FRACTION_BASIS,
    DEPTH,
    INDEL_EVENT_POSITIONS,
    INPUT_READS,
    LOW_DEPTH_POSITIONS,
    LOW_QUALITY_BASES,
    MAPQ_FAILED,
    MAX_DEL_RUN_LENGTH,
    MAX_INDEL_EVENT_FRACTION,
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


def _recover_covered_n_fraction(
    consensus_seq: str,
    n_low_depth_positions: int | None,
) -> float | None:
    """Recover the covered-scoped no-call rate from a legacy consensus header.

    Legacy headers store ``consensus_n_fraction`` against the whole reference
    length, which is not comparable to the covered-scoped threshold the verdict
    gate applies. The covered-scoped value is recoverable because the consensus
    caller emits 'N' at every position below ``min_depth`` and counts exactly
    those positions in ``low_depth_positions`` (kuma_core/mame/ingest/
    consensus.py). Both the numerator and denominator therefore follow by
    subtraction.

    Returns ``None`` when recovery is not possible: no ``low_depth_positions``
    key, an empty sequence, or counts that contradict the invariant. Callers must
    treat ``None`` as "not evaluable" rather than substituting a value.
    """

    if not consensus_seq or n_low_depth_positions is None:
        return None
    if n_low_depth_positions < 0:
        return None
    n_covered = len(consensus_seq) - n_low_depth_positions
    n_covered_no_call = consensus_seq.count("N") - n_low_depth_positions
    if n_covered < 0 or n_covered_no_call < 0:
        return None
    if n_covered == 0:
        # Nothing reached usable depth: fully no-call, matching the zero-coverage
        # branch of call_consensus_with_metrics.
        return 1.0
    return n_covered_no_call / n_covered


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
    low_depth_raw = _read_int_metadata(metadata, LOW_DEPTH_POSITIONS)
    n_low_depth_positions = low_depth_raw or 0
    # The stored consensus_n_fraction is only comparable to the verdict threshold
    # when the header declares the covered-scoped denominator. Without that
    # marker the file predates the definition change and its number means
    # something else, so it is recovered or declared not evaluable, never reused.
    basis = metadata.get(CONSENSUS_N_FRACTION_BASIS.lower())
    stored_n_fraction = _read_float_metadata(metadata, CONSENSUS_N_FRACTION)
    if basis == BASIS_COVERED and stored_n_fraction is not None:
        consensus_n_fraction = stored_n_fraction
        consensus_n_fraction_evaluable = True
    else:
        recovered = _recover_covered_n_fraction(consensus_seq, low_depth_raw)
        if recovered is None:
            _logger.warning(
                "Consensus file %s carries no %s marker and the covered-scoped "
                "N fraction cannot be recovered; the N-fraction gate is skipped "
                "for this well.",
                path,
                CONSENSUS_N_FRACTION_BASIS,
            )
            consensus_n_fraction = 0.0
            consensus_n_fraction_evaluable = False
        else:
            consensus_n_fraction = recovered
            consensus_n_fraction_evaluable = True
    n_low_quality_bases = _read_int_metadata(metadata, LOW_QUALITY_BASES) or 0
    n_input_reads = _read_int_metadata(metadata, INPUT_READS)
    n_aligned_reads = _read_int_metadata(metadata, ALIGNED_READS)
    n_mapq_failed = _read_int_metadata(metadata, MAPQ_FAILED) or 0
    n_span_failed = _read_int_metadata(metadata, SPAN_FAILED) or 0
    n_indel_event_positions = _read_int_metadata(metadata, INDEL_EVENT_POSITIONS) or 0
    max_indel_event_fraction = _read_float_metadata(metadata, MAX_INDEL_EVENT_FRACTION) or 0.0
    max_del_run_length = _read_int_metadata(metadata, MAX_DEL_RUN_LENGTH) or 0

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
        consensus_n_fraction_evaluable=consensus_n_fraction_evaluable,
        n_low_quality_bases=n_low_quality_bases,
        n_input_reads=n_input_reads,
        n_aligned_reads=n_aligned_reads,
        n_mapq_failed=n_mapq_failed,
        n_span_failed=n_span_failed,
        n_indel_event_positions=n_indel_event_positions,
        max_indel_event_fraction=max_indel_event_fraction,
        max_del_run_length=max_del_run_length,
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
