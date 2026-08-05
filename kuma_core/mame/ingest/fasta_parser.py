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
import os
import re
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from kuma_core.mame.ingest.consensus_metadata import (
    ALIGNED_READS,
    BASIS_COVERED,
    CONSENSUS_N_FRACTION,
    CONSENSUS_N_FRACTION_BASIS,
    CONSENSUS_NET_INDEL,
    DEPTH,
    INDEL_EVENT_POSITIONS,
    INPUT_READS,
    LOW_DEPTH_POSITIONS,
    LOW_QUALITY_BASES,
    MAPQ_FAILED,
    MAX_DEL_RUN_LENGTH,
    MAX_INDEL_EVENT_FRACTION,
    MAX_MINOR_ALLELE_FRACTION,
    MIN_VARIANT_SUPPORT,
    MIXED_POSITIONS,
    NET_INDEL,
    READ_NET_INDEL,
    SPAN_FAILED,
    VARIANT_POSITIONS,
)
from kuma_core.mame.ingest.stage_marker import (
    DirEntryMap,
    iter_consensus_names,
    read_stage_marker,
    scan_unit_dir,
    validate_marker,
)
from kuma_core.mame.models import BarcodeRecord

_logger = logging.getLogger(__name__)

_METADATA_RE = re.compile(r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")

# Batched per-well metadata + content access (see ``_batch_map``).
#
# Ingesting one consensus directory costs two per-file round trips: the marker
# guard's ``DirEntry.stat()`` (size check) and the parser's ``open``+``read``.  On
# a local filesystem each is microseconds; on a Windows share (9p) each is a
# network round trip of milliseconds, and the 283-file reference workload spent
# ~0.87 s of ingest almost entirely waiting on them.  Both syscalls release the
# GIL, so overlapping them with a small thread pool hides the latency: reading
# the same 283 files measured 555 ms sequential vs 59 ms at 8 threads.
#
# The same fan-out is a *pessimisation* on ext4, where one read costs less than
# the thread hand-off (1.6 ms -> 23 ms for those 283 files).  The mode is
# therefore decided by measuring, not by guessing from the path: the first few
# items are done inline and, if they average slower than ``_PROBE_LATENCY_S``,
# the storage is round-trip bound and the remainder is fanned out.
_ENV_INGEST_WORKERS = "KUMA_MAME_INGEST_WORKERS"
#: Items handled inline before the auto decision. Large enough to average out one
#: slow outlier, small enough that the probe itself costs ~16 ms on 9p.
_PROBE_ITEMS = 8
#: Per-item wall above which thread fan-out pays for itself. ext4 measures ~5 us
#: per file and 9p ~2 ms, so the two populations are three orders of magnitude
#: apart and the exact cut-off inside that gap does not matter.
_PROBE_LATENCY_S = 3e-4
#: Fan-out used when the probe says "round-trip bound". The 9p sweep is flat from
#: 8 to 32 workers (59 / 60 / 76 / 63 ms), so 8 is the smallest value on the
#: plateau: same wall, fewest threads.
_DEFAULT_INGEST_WORKERS = 8


def _open_text(path: Path):
    return path.open("r", encoding="utf-8")


def _configured_workers() -> int | None:
    """Worker count from ``KUMA_MAME_INGEST_WORKERS``; ``None`` means auto-probe.

    ``0`` or ``1`` forces the sequential path, which is also the escape hatch if
    a filesystem ever misbehaves under concurrent reads.
    """
    raw = os.environ.get(_ENV_INGEST_WORKERS, "").strip()
    if not raw:
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        _logger.warning(
            "%s=%r is not an integer; falling back to auto worker sizing.",
            _ENV_INGEST_WORKERS,
            raw,
        )
        return None


def _map_parallel(fn, items: list, workers: int) -> list:
    """Apply *fn* to *items* over *workers* threads, results in input order.

    Work is handed out as ``workers`` round-robin slices rather than one task per
    item: ``ThreadPoolExecutor`` ignores ``chunksize``, and one future per item
    adds measurable dispatch overhead at this granularity.  Round-robin (rather
    than contiguous) slicing keeps every worker spread across all directories, so
    one slower directory does not serialise onto a single thread.

    An empty *items* returns before the pool is built: ``min(workers, 0)`` is 0
    and ``ThreadPoolExecutor`` rejects that, so a directory holding no consensus
    files used to raise ``ValueError: max_workers must be greater than 0`` in
    place of the empty result the callers already handle.
    """
    if not items:
        return []
    n = min(workers, len(items))
    slices = [items[i::n] for i in range(n)]
    with ThreadPoolExecutor(max_workers=n) as pool:
        parts = list(pool.map(lambda group: [fn(x) for x in group], slices))
    out: list = [None] * len(items)
    for i, part in enumerate(parts):
        out[i::n] = part
    return out


def _batch_map(fn, items: list, parallel: bool | None = None) -> tuple[list, bool]:
    """Apply *fn* to every item in order; return ``(results, used_parallel)``.

    *parallel* pre-decides the mode so two passes over the same directory (stat
    then read) pay for the latency probe only once.  ``None`` resolves the mode
    from ``KUMA_MAME_INGEST_WORKERS`` or, absent that, from the probe.  The
    returned flag is that decision, for the caller to feed forward.
    """
    if not items:
        return [], bool(parallel)

    if parallel is None:
        workers = _configured_workers()
        if workers is not None:
            if workers <= 1:
                return [fn(item) for item in items], False
            return _map_parallel(fn, items, workers), True
    elif parallel:
        return _map_parallel(fn, items, _DEFAULT_INGEST_WORKERS), True
    else:
        return [fn(item) for item in items], False

    probe_n = min(_PROBE_ITEMS, len(items))
    started = time.perf_counter()
    head = [fn(item) for item in items[:probe_n]]
    per_item = (time.perf_counter() - started) / probe_n
    rest = items[probe_n:]
    if per_item < _PROBE_LATENCY_S:
        head.extend(fn(item) for item in rest)
        return head, False
    head.extend(_map_parallel(fn, rest, _DEFAULT_INGEST_WORKERS))
    return head, True


def _warm_size(entry: "os.DirEntry[str]") -> None:
    """Populate *entry*'s cached ``stat`` result; a failed lookup is left to the guard.

    ``DirEntry.stat()`` memoises on the entry object, so pre-warming a whole
    directory in one batched pass makes the marker guard's later per-well size
    check free.  A failure is only logged here: the guard re-issues the same call
    and already reports an ``OSError`` as "well missing on disk", so raising now
    would turn that diagnosis into a crash.
    """
    try:
        entry.stat()
    except OSError as exc:
        _logger.debug("stat pre-warm failed for %s: %s", entry.path, exc)


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


def _iter_consensus_entries(
    directory: Path, entries: DirEntryMap | None = None
) -> Iterator[tuple[Path, "os.DirEntry[str] | None"]]:
    """Yield ``(path, entry)`` for each consensus FASTA under *directory*.

    Emission order matches the previous per-pattern ``sorted(dir.glob(...))``
    walk.  The ``DirEntry`` is carried alongside the path so the caller can take
    the file size from the already-performed scan instead of a fresh ``stat``.
    """
    if entries is None:
        entries = scan_unit_dir(directory)
    for name in iter_consensus_names(entries):
        yield directory / name, entries.get(name)


def _split_lines(data: bytes) -> list[str]:
    """Decode *data* into the exact line list ``open(path, "r").readlines()`` gave.

    Text mode applies universal newlines (``\\r\\n`` and a lone ``\\r`` both become
    ``\\n``) and the caller then stripped the terminator, so translating first and
    splitting on ``\\n`` reproduces it.  ``str.splitlines`` is deliberately NOT used:
    it also breaks on ``\\x0b``, ``\\x0c``, ``\\x1c``-``\\x1e`` and ``\\u2028``, which text
    mode does not, so a header carrying one of those would split differently.
    """
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    # ``readlines`` yields no trailing empty element for a file ending in a
    # newline; ``split`` does. Drop it so the line list matches.
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _parse_single_fasta(
    path: Path, data: bytes | None = None
) -> tuple[str, str, int, dict[str, str]]:
    if data is None:
        with _open_text(path) as fh:
            lines = [ln.rstrip("\r\n") for ln in fh.readlines()]
    else:
        lines = _split_lines(data)

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


def parse_fasta_file(
    path: Path,
    native_barcode: str,
    entry: "os.DirEntry[str] | None" = None,
    data: bytes | None = None,
) -> BarcodeRecord:
    """Parse a single consensus FASTA file into a BarcodeRecord.

    *entry* is the optional ``os.DirEntry`` for *path* from the caller's
    directory scan.  ``DirEntry.stat()`` caches its result, so passing an entry
    the marker guard already stat-ed makes ``file_size_kb`` free instead of a
    second ``stat`` per well.  The value is identical either way: both follow
    symlinks and read ``st_size``.

    *data* is the file content when the caller already read it (see
    ``_read_all``).  Supplying it also supplies the size: ``len(data)`` is the
    ``st_size`` of the regular file that was just read in full, so the record no
    longer needs a ``stat`` at all.  That matters on a share, where the stat is a
    round trip of its own even for an entry the scan already produced.

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
    header, consensus_seq, record_count, metadata = _parse_single_fasta(path, data)

    custom_barcode = header.split()[0] if header else path.stem
    if data is not None:
        size_bytes = len(data)
    elif entry is not None:
        size_bytes = entry.stat().st_size
    else:
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
    consensus_net_indel_bp = _read_int_metadata(metadata, CONSENSUS_NET_INDEL)
    # The legacy ``net_indel`` key stored the per-read median under a name that
    # read like a consensus measurement. It is folded into the read metric, never
    # into the verdict-bearing one, so a file written before the rename cannot
    # revive the misread frameshift call.
    median_read_net_indel_bp = _read_int_metadata(metadata, READ_NET_INDEL)
    if median_read_net_indel_bp is None:
        median_read_net_indel_bp = _read_int_metadata(metadata, NET_INDEL)

    # Absent key means unknown, so the float helper's None is kept rather than
    # coerced to 0.0: a legacy file must not look like a zero-support well.
    min_variant_support = _read_float_metadata(metadata, MIN_VARIANT_SUPPORT)
    n_variant_positions = _read_int_metadata(metadata, VARIANT_POSITIONS) or 0

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
        min_variant_support=min_variant_support,
        n_variant_positions=n_variant_positions,
        consensus_net_indel_bp=consensus_net_indel_bp,
        median_read_net_indel_bp=median_read_net_indel_bp,
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

    # Three ordered passes over the tree, each batched, instead of one
    # file-at-a-time loop: readdir every NB dir, pre-warm every entry's size,
    # then guard + read.  The order of the emitted records is unchanged, because
    # the pending list is built in exactly the old walk order (NB dirs sorted by
    # name, files in ``iter_consensus_names`` order) and consumed in that order.
    pending: list[tuple[Path, str, "os.DirEntry[str] | None"]] = []
    # One readdir per NB directory, reused by the marker presence test, the
    # inventory guard and the per-well file size. ``entry.is_dir()`` here reads
    # the readdir type field where the platform supplies it, so the top-level
    # walk no longer stats every child either.
    with os.scandir(input_dir) as top:
        nb_dirs = sorted(
            (input_dir / e.name for e in top if e.is_dir()), key=lambda p: p.name
        )
    scanned = [(nb_dir, scan_unit_dir(nb_dir)) for nb_dir in nb_dirs]

    # The marker guard checks every recorded well's size, one ``stat`` each, and
    # that loop alone measured ~1.2 s of the reference workload's ingest on 9p.
    # Warming those cached stats in one batched pass leaves the guard itself
    # unchanged but removes its per-well round trip.  The decision is carried
    # into the content read below so the latency probe runs only once.
    parallel: bool | None = None
    if scanned:
        _warmed, parallel = _batch_map(
            _warm_size,
            [entry for _nb_dir, entries in scanned for entry in entries.values()],
        )

    for nb_dir, entries in scanned:
        native_barcode = nb_dir.name
        marker = read_stage_marker(nb_dir, entries)
        if marker is None:
            _logger.warning(
                "No demux/consensus completion marker in %s; proceeding "
                "(legacy or externally-sorted directory).",
                nb_dir,
            )
        else:
            ok, reason = validate_marker(marker, nb_dir, entries)
            if not ok:
                raise ValueError(
                    f"Demux/consensus output for '{native_barcode}' is "
                    f"incomplete or corrupt (completion marker present but "
                    f"inventory does not match): {reason}. "
                    "Re-run the demux+consensus stage for this unit."
                )

        for consensus_file, entry in _iter_consensus_entries(nb_dir, entries):
            pending.append((consensus_file, native_barcode, entry))

    contents, _used_parallel = _batch_map(
        Path.read_bytes, [path for path, _nb, _entry in pending], parallel
    )
    return [
        parse_fasta_file(path, native_barcode=nb, entry=entry, data=data)
        for (path, nb, entry), data in zip(pending, contents)
    ]
