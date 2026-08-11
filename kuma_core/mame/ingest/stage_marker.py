"""Per-stage completion marker for the MAME demux+consensus stage.

After a unit (one native-barcode directory, ``nb_out``) finishes demux plus
optional consensus, a small JSON marker is written into that directory.  The
marker records the expected per-well inventory and read counts so that:

1. a rerun after interruption can SKIP a unit whose marker is present and whose
   recorded inventory still matches the files on disk (resume), and
2. a downstream consumer can fail-fast when a marker is present but the
   inventory no longer matches (the unit was interrupted mid-write), instead of
   silently consuming a partial directory.

Existence of the directory alone NEVER means "done"; only a valid marker whose
inventory matches the files on disk counts as complete.

Marker filename: ``.demux_consensus_complete.json`` (leading dot plus ``.json``
suffix so it is never picked up by ``*.fasta`` / ``*.fa`` / ``*.fas`` globs or
by the quality-filter ``rglob("*.fasta")`` pass).

Schema (version 2)::

    {
      "schema_version": 2,
      "stage": "demux_consensus",
      "unit": "<nb dir name>",
      "consensus": <bool>,            # True if A4/A5 consensus ran
      "per_well_counts": {"<well>": <int>, ...},
      "wells": ["<well>", ...],       # sorted expected inventory (well stems)
      "n_input_reads": <int|null>,    # optional: this unit's demux input reads
      "n_unassigned": <int|null>,     # optional: this unit's unassigned reads
      "stats": {"<key>": <int>, ...}, # optional: extra per-unit summary counters
      "inputs": {                     # v2: identity of what produced the unit
        "reference": {"length": <int>, "sha256": "<hex>"},
        "params": {"<name>": <scalar>, ...}
      }
    }

Version 2 adds ``inputs``: the identity of the reference the consensus was
called against, plus the parameters that decide which reads reach a well.  A
marker records only what its producer knows, so a unit written without a
reference (``consensus: false``) carries no ``inputs.reference``.

Why it exists: the earlier schema recorded nothing about the reference, so a
rerun that changed the reference resumed the completed units and translated the
OLD consensus against the NEW reference.  On 2026-08-04 that produced 96 wells
of roughly 530 amino-acid changes each from one real substitution, in a run that
finished in one second because every unit was resumed.  Resume must therefore
compare inputs, not just inventory (see :func:`marker_inputs_match`).

The ``n_input_reads`` / ``n_unassigned`` keys are optional.  They let a
fully-resumed run reconstruct the aggregate input/unassigned totals from the
markers of already-complete units; older markers that predate these keys simply
omit them (treated as "not seedable" by the consumer, never a crash).

The ``stats`` key is optional and holds an extra dict of integer summary
counters that a producer cannot express through ``per_well_counts`` /
``n_input_reads`` / ``n_unassigned`` alone (e.g. the combinatorial-demux
per-native-barcode DemuxStats: total_reads, passed_mapq, passed_coverage,
assigned_reads, ambiguous_dropped, chimera_splits, wells_with_reads,
wells_with_min_reads).  Recorded so a fully-resumed run can reseed the merged
aggregate of those counters from already-complete units.  Producers that do not
need it (``demux_and_filter``) simply omit it; older markers that predate the
key omit it too (treated as "not seedable", never a crash).

Since the drop-reason breakdown was added, ``stats`` also carries the seven
``drop_*`` counters that partition ``ambiguous_dropped``
(drop_short_window_read_5p, drop_short_window_read_3p, drop_no_barcode_f,
drop_no_barcode_r, drop_ambiguous_tie_f, drop_ambiguous_tie_r,
drop_both_axes).  Markers written before that omit them, and the consumer
treats the whole breakdown as unavailable for a run that reuses any such
marker rather than seeding zeros that would read as "measured, and no read hit
this cause" (see ``_summary_from_marker`` in combinatorial_demux).
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
from pathlib import Path, PurePath
from typing import Any

from kuma_core.shared.atomic_write import atomic_write_text

MARKER_FILENAME = ".demux_consensus_complete.json"
MARKER_SCHEMA_VERSION = 2
STAGE_NAME = "demux_consensus"

# Single source of truth for the per-well consensus FASTA extension set.  The
# downstream consumer (``fasta_parser._iter_consensus_entries``) shares this so
# the orphan/extra-file guard matches the SAME extensions the consumer reads;
# a stray ``.fa`` / ``.fas`` orphan is therefore caught, not silently consumed.
# Defined here (the leaf module) to avoid a circular import with fasta_parser.
CONSENSUS_FILE_PATTERNS: tuple[str, ...] = ("*.fasta", "*.fa", "*.fas")

# Compiled equivalents of ``Path.glob(pattern)`` name matching, so a single
# ``os.scandir`` pass can replace one ``glob`` pass per pattern.  ``pathlib``
# compiles glob patterns with ``fnmatch.translate`` and applies
# ``re.IGNORECASE`` on Windows flavours only; mirroring both keeps the matched
# name set byte-identical to the previous ``glob`` behaviour on every platform.
# Directories, symlinks (including broken ones) and dot-files match here exactly
# as they matched ``Path.glob`` before (verified empirically), so the guard's
# orphan/extra-file semantics are unchanged.
_GLOB_FLAGS = re.IGNORECASE if os.name == "nt" else 0
_CONSENSUS_FILE_MATCHERS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(fnmatch.translate(pattern), _GLOB_FLAGS)
    for pattern in CONSENSUS_FILE_PATTERNS
)

# ``name -> DirEntry`` for one directory, produced by a single readdir.
DirEntryMap = dict[str, "os.DirEntry[str]"]


def scan_unit_dir(unit_dir: Path) -> DirEntryMap:
    """Return ``{name: DirEntry}`` for *unit_dir* from a single readdir pass.

    The returned ``DirEntry`` objects are the unit of reuse: ``DirEntry.stat()``
    caches its result, so one map shared between the marker guard and the
    consensus reader costs at most one ``stat`` per file instead of one per
    consumer.  A missing or unreadable directory yields an empty map, matching
    ``Path.glob`` on a non-existent directory (silently empty, never raising).
    """
    try:
        with os.scandir(unit_dir) as it:
            return {entry.name: entry for entry in it}
    except OSError:
        return {}


def iter_consensus_names(entries: DirEntryMap) -> list[str]:
    """Return the consensus-FASTA names in *entries*, in ``glob`` pattern order.

    Reproduces ``for pattern in CONSENSUS_FILE_PATTERNS: sorted(dir.glob(...))``
    de-duplicated: names are grouped by the first pattern they match and sorted
    within the group.  The three patterns are mutually exclusive on POSIX, but
    the grouping is kept so the emitted order does not depend on that.
    """
    out: list[str] = []
    claimed: set[str] = set()
    for matcher in _CONSENSUS_FILE_MATCHERS:
        group = sorted(
            name for name in entries if name not in claimed and matcher.match(name)
        )
        claimed.update(group)
        out.extend(group)
    return out


def marker_path(unit_dir: Path) -> Path:
    """Return the marker path for *unit_dir* (does not check existence)."""
    return Path(unit_dir) / MARKER_FILENAME


def reference_fingerprint(reference_fasta: Path) -> dict[str, Any]:
    """Return ``{"length": int, "sha256": str}`` for a reference FASTA.

    The digest covers the bare upper-cased sequence, headers and line breaks
    excluded, because those are the bases the consensus is called against.  Two
    files that differ only in their header or line wrapping therefore resume
    against each other, while any change to the sequence (a different construct,
    a re-extracted amplicon span, a corrected base) does not.
    """
    sequence = "".join(
        line.strip()
        for line in Path(reference_fasta).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith(">")
    ).upper()
    return {
        "length": len(sequence),
        "sha256": hashlib.sha256(sequence.encode("ascii", "replace")).hexdigest(),
    }


def marker_inputs_match(
    marker: dict[str, Any],
    reference: dict[str, Any] | None,
    params: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Whether a completed unit may be REUSED for the inputs of the current run.

    Returns ``(ok, reason)``; *reason* is empty on success.

    A unit written without consensus carries no reference, so there is nothing
    to compare and it is reusable. Otherwise the recorded fingerprint and
    parameters must match the ones supplied.

    A marker that records no ``inputs`` at all (schema version 1) is NOT
    reusable when a reference is in play: nothing in it says which reference
    produced the consensus, so reusing it is exactly the bug this guards. Every
    caller answers a negative by recomputing the unit, which costs time and
    cannot be wrong; trusting the marker can be.
    """
    if not marker.get("consensus"):
        return (True, "")
    if reference is None:
        return (True, "")
    inputs = marker.get("inputs")
    if not isinstance(inputs, dict):
        return (
            False,
            "marker records no input identity (written before reference "
            "fingerprinting), so the reference it used is unknown",
        )
    recorded_reference = inputs.get("reference")
    if not isinstance(recorded_reference, dict):
        return (False, "marker records no reference fingerprint")
    if recorded_reference.get("sha256") != reference.get("sha256"):
        return (
            False,
            "reference changed since the unit was written "
            f"(marker {recorded_reference.get('length')} bp, "
            f"current {reference.get('length')} bp)",
        )
    if params:
        recorded_params = inputs.get("params")
        if not isinstance(recorded_params, dict):
            return (False, "marker records no parameters")
        differing = sorted(
            name
            for name, value in params.items()
            if name not in recorded_params or recorded_params[name] != value
        )
        if differing:
            return (False, f"parameters changed since the unit was written: {differing}")
    return (True, "")


def write_stage_marker(
    unit_dir: Path,
    *,
    per_well_counts: dict[str, int],
    consensus: bool,
    n_input_reads: int | None = None,
    n_unassigned: int | None = None,
    stats: dict[str, int] | None = None,
    reference: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Path:
    """Atomically write the completion marker into *unit_dir*.

    This is the commit point of the unit: callers must write it LAST, after all
    per-well FASTA / consensus files for the unit are on disk.

    Args:
        unit_dir: The per-NB output directory (``nb_out``).
        per_well_counts: ``{well_name: read_count}`` for the wells produced.
        consensus: Whether the A4/A5 consensus pipeline ran for this unit.
        n_input_reads: Optional demux input-read count for this unit.  Recorded
            so a fully-resumed run can reseed the aggregate input total instead
            of reporting 0.  Omitted from the payload when ``None``.
        n_unassigned: Optional unassigned-read count for this unit.  Recorded
            for the same reseed reason; omitted when ``None``.
        stats: Optional ``{key: int}`` dict of extra per-unit summary counters
            (e.g. the combinatorial per-NB DemuxStats) that the other recorded
            fields cannot express.  Recorded so a fully-resumed run can reseed
            the aggregate of those counters.  Omitted from the payload when
            ``None`` or empty; older markers that omit it are treated as "not
            seedable" by the consumer (never a crash).
        reference: Optional :func:`reference_fingerprint` of the reference the
            consensus was called against.  Recorded under ``inputs.reference``
            so a later run can refuse to reuse this unit once the reference
            changes.  A producer that used no reference passes ``None``.
        params: Optional ``{name: scalar}`` of the settings that decide which
            reads reach a well (alignment gates, trimming, consensus depth).
            Recorded under ``inputs.params`` and compared on resume.

    Returns:
        The resolved path of the written marker.
    """
    unit_dir = Path(unit_dir)
    payload: dict[str, Any] = {
        "schema_version": MARKER_SCHEMA_VERSION,
        "stage": STAGE_NAME,
        "unit": unit_dir.name,
        "consensus": bool(consensus),
        "per_well_counts": {str(k): int(v) for k, v in per_well_counts.items()},
        "wells": sorted(str(k) for k in per_well_counts),
    }
    if n_input_reads is not None:
        payload["n_input_reads"] = int(n_input_reads)
    if n_unassigned is not None:
        payload["n_unassigned"] = int(n_unassigned)
    if stats:
        payload["stats"] = {str(k): int(v) for k, v in stats.items()}
    inputs: dict[str, Any] = {}
    if reference is not None:
        inputs["reference"] = dict(reference)
    if params:
        inputs["params"] = dict(params)
    if inputs:
        payload["inputs"] = inputs
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return atomic_write_text(marker_path(unit_dir), content)


def read_stage_marker(
    unit_dir: Path, entries: DirEntryMap | None = None
) -> dict[str, Any] | None:
    """Return the parsed marker for *unit_dir*, or ``None`` when absent.

    A marker file that cannot be parsed as the expected JSON object is treated
    as absent (``None``) so a corrupt marker never crashes resume/consume; the
    unit is then re-processed (resume) or proceeds unguarded (consume, like a
    legacy dir).

    When *entries* (a :func:`scan_unit_dir` map) is supplied, the presence test
    reads that map instead of issuing a separate ``exists()`` stat.  A read that
    fails afterwards still returns ``None``, so a marker deleted between the
    scan and the read behaves exactly like an absent one.
    """
    mpath = marker_path(unit_dir)
    if entries is None:
        if not mpath.exists():
            return None
    elif MARKER_FILENAME not in entries:
        return None
    try:
        data = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _list_well_fasta(unit_dir: Path, entries: DirEntryMap | None = None) -> set[str]:
    """Return the set of per-well FASTA stems present in *unit_dir*.

    Mirrors the consumer (``fasta_parser._iter_consensus_entries``): every file
    matching ``CONSENSUS_FILE_PATTERNS`` (``*.fasta`` / ``*.fa`` / ``*.fas``)
    whose name does not start with ``_`` (so ``_unassigned.fasta`` is
    excluded).  Matching the SAME extension set the consumer reads is what lets
    a stray ``.fa`` / ``.fas`` orphan be flagged as an extra file instead of
    silently bypassing the guard.

    *entries* is an optional :func:`scan_unit_dir` map; supplying it replaces
    the three per-pattern directory scans with zero additional syscalls.
    """
    if entries is None:
        entries = scan_unit_dir(unit_dir)
    return {
        PurePath(name).stem
        for name in iter_consensus_names(entries)
        if not name.startswith("_")
    }


def validate_marker(
    marker: dict[str, Any], unit_dir: Path, entries: DirEntryMap | None = None
) -> tuple[bool, str]:
    """Validate *marker* against the files actually present in *unit_dir*.

    Validation is **inventory match**: the set of well names recorded in the
    marker must equal the set of non-underscore ``*.fasta`` stems on disk, and
    every recorded well file must exist and be non-empty.  Read counts are not
    recomputed from consensus files (those are single-record regardless of the
    recorded input-read count); atomic writes already prevent truncated files,
    so the marker's job is to catch a *missing* well from an interrupted run.

    Returns:
        ``(ok, reason)`` where *reason* is empty on success and a human-readable
        explanation on failure.
    """
    if entries is None:
        entries = scan_unit_dir(unit_dir)
    recorded = {str(w) for w in marker.get("wells", [])}
    on_disk = _list_well_fasta(unit_dir, entries)

    missing = recorded - on_disk
    if missing:
        return (
            False,
            f"marker lists {len(recorded)} wells but {len(missing)} are missing "
            f"on disk: {sorted(missing)[:5]}",
        )

    extra = on_disk - recorded
    if extra:
        return (
            False,
            f"{len(extra)} well FASTA files on disk are not in the marker "
            f"inventory: {sorted(extra)[:5]}",
        )

    # Existence AND non-zero size are both still required per recorded well.
    # A name absent from the scan, or one whose stat fails (a broken symlink is
    # the realistic case, and ``Path.exists()`` reported False for it before),
    # is reported as missing exactly as before; the size test is unchanged.
    for well in sorted(recorded):
        entry = entries.get(f"{well}.fasta")
        if entry is None:
            return (False, f"recorded well '{well}' FASTA missing on disk")
        try:
            size = entry.stat().st_size
        except OSError:
            return (False, f"recorded well '{well}' FASTA missing on disk")
        if size == 0:
            return (False, f"recorded well '{well}' FASTA is empty (truncated)")

    return (True, "")


def is_unit_complete(unit_dir: Path) -> bool:
    """True iff *unit_dir* has a valid marker whose inventory matches disk."""
    entries = scan_unit_dir(unit_dir)
    marker = read_stage_marker(unit_dir, entries)
    if marker is None:
        return False
    ok, _reason = validate_marker(marker, unit_dir, entries)
    return ok


__all__ = [
    "MARKER_FILENAME",
    "MARKER_SCHEMA_VERSION",
    "STAGE_NAME",
    "DirEntryMap",
    "scan_unit_dir",
    "iter_consensus_names",
    "marker_path",
    "marker_inputs_match",
    "reference_fingerprint",
    "write_stage_marker",
    "read_stage_marker",
    "validate_marker",
    "is_unit_complete",
]
