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

Schema (version 1)::

    {
      "schema_version": 1,
      "stage": "demux_consensus",
      "unit": "<nb dir name>",
      "consensus": <bool>,            # True if A4/A5 consensus ran
      "per_well_counts": {"<well>": <int>, ...},
      "wells": ["<well>", ...]        # sorted expected inventory (well stems)
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kuma_core.shared.atomic_write import atomic_write_text

MARKER_FILENAME = ".demux_consensus_complete.json"
MARKER_SCHEMA_VERSION = 1
STAGE_NAME = "demux_consensus"


def marker_path(unit_dir: Path) -> Path:
    """Return the marker path for *unit_dir* (does not check existence)."""
    return Path(unit_dir) / MARKER_FILENAME


def write_stage_marker(
    unit_dir: Path,
    *,
    per_well_counts: dict[str, int],
    consensus: bool,
) -> Path:
    """Atomically write the completion marker into *unit_dir*.

    This is the commit point of the unit: callers must write it LAST, after all
    per-well FASTA / consensus files for the unit are on disk.

    Args:
        unit_dir: The per-NB output directory (``nb_out``).
        per_well_counts: ``{well_name: read_count}`` for the wells produced.
        consensus: Whether the A4/A5 consensus pipeline ran for this unit.

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
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return atomic_write_text(marker_path(unit_dir), content)


def read_stage_marker(unit_dir: Path) -> dict[str, Any] | None:
    """Return the parsed marker for *unit_dir*, or ``None`` when absent.

    A marker file that cannot be parsed as the expected JSON object is treated
    as absent (``None``) so a corrupt marker never crashes resume/consume; the
    unit is then re-processed (resume) or proceeds unguarded (consume, like a
    legacy dir).
    """
    mpath = marker_path(unit_dir)
    if not mpath.exists():
        return None
    try:
        data = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _list_well_fasta(unit_dir: Path) -> set[str]:
    """Return the set of per-well FASTA stems present in *unit_dir*.

    Mirrors the consumer/quality-filter convention: ``*.fasta`` files whose
    name does not start with ``_`` (so ``_unassigned.fasta`` is excluded).
    """
    return {
        p.stem
        for p in Path(unit_dir).glob("*.fasta")
        if not p.name.startswith("_")
    }


def validate_marker(marker: dict[str, Any], unit_dir: Path) -> tuple[bool, str]:
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
    recorded = {str(w) for w in marker.get("wells", [])}
    on_disk = _list_well_fasta(unit_dir)

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

    for well in sorted(recorded):
        fpath = Path(unit_dir) / f"{well}.fasta"
        if not fpath.exists():
            return (False, f"recorded well '{well}' FASTA missing on disk")
        if fpath.stat().st_size == 0:
            return (False, f"recorded well '{well}' FASTA is empty (truncated)")

    return (True, "")


def is_unit_complete(unit_dir: Path) -> bool:
    """True iff *unit_dir* has a valid marker whose inventory matches disk."""
    marker = read_stage_marker(unit_dir)
    if marker is None:
        return False
    ok, _reason = validate_marker(marker, unit_dir)
    return ok


__all__ = [
    "MARKER_FILENAME",
    "MARKER_SCHEMA_VERSION",
    "STAGE_NAME",
    "marker_path",
    "write_stage_marker",
    "read_stage_marker",
    "validate_marker",
    "is_unit_complete",
]
