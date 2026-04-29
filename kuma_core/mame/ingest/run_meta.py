"""Discover MinKNOW NGS run metadata from the filesystem.

MinKNOW writes artefacts alongside the raw run directory. This module
searches *input_dir*, its parent, and its grandparent for a run folder that
contains ``final_summary_*.txt`` and optionally ``sample_sheet_*.csv``.

Search stops at the first match or after 2 levels up (grandparent).  Symbolic
links and paths outside the search subtree are silently skipped.  Any
``OSError`` / ``PermissionError`` is absorbed and returns ``None``.

Typical MinKNOW layout::

    run_xyz/
      final_summary_PAX12345_a1b2c3d4.txt
      sample_sheet_PAX12345.csv
      sort_barcode06/        <-- input_dir passed by the caller
        NB01/
          ...
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class NgsRunMeta:
    """Parsed MinKNOW run metadata.

    All fields are ``None`` when the corresponding key was absent.
    ``raw_run_dir`` is the discovered run directory (absolute path string).
    """

    instrument: str | None
    position: str | None
    flow_cell_id: str | None
    sample_id: str | None
    kit: str | None
    started: str | None         # ISO timestamp from final_summary
    basecalling_enabled: bool | None
    raw_run_dir: str | None     # absolute path of the discovered run folder


# ---------------------------------------------------------------------------
# Internal parsers
# ---------------------------------------------------------------------------

_FINAL_SUMMARY_KEYS = {
    "instrument": "instrument",
    "position": "position",
    "flow_cell_id": "flow_cell_id",
    "sample_id": "sample_id",
    "kit": "kit",
    "started": "started",
    "basecalling_enabled": "basecalling_enabled",
}

def _parse_final_summary(path: Path) -> dict[str, str]:
    """Parse ``key = value`` pairs from a MinKNOW final_summary file."""
    kv: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return kv
    for line in text.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if key in _FINAL_SUMMARY_KEYS:
            kv[key] = value
    return kv


def _parse_sample_sheet_kit(path: Path) -> str | None:
    """Extract kit value from a MinKNOW sample_sheet CSV.

    MinKNOW sample sheets may encode the kit as a CSV column header or as a
    key=value line in the header section.  We do a best-effort extraction.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # Key=value style (common in EXP-NBD196 sheets): "kit,SQK-LSK109"
    for line in text.splitlines():
        line = line.strip()
        lower = line.lower()
        if lower.startswith("kit,") or lower.startswith("kit="):
            sep = "," if "," in line else "="
            parts = line.split(sep, 1)
            if len(parts) == 2 and parts[1].strip():
                return parts[1].strip()
    return None


# ---------------------------------------------------------------------------
# Discovery logic
# ---------------------------------------------------------------------------

_MAX_LEVELS_UP = 2  # search input_dir, parent, grandparent only


def _is_run_dir(candidate: Path) -> bool:
    """Return True if *candidate* looks like a MinKNOW run directory."""
    try:
        if not candidate.is_dir():
            return False
        summaries = list(candidate.glob("final_summary_*.txt"))
        return len(summaries) > 0
    except OSError:
        return False


def _collect_siblings(directory: Path) -> list[Path]:
    """Return immediate subdirectory siblings of *directory*."""
    parent = directory.parent
    try:
        return [p for p in parent.iterdir() if p.is_dir() and p != directory]
    except OSError:
        return []


def _search_run_dir(start: Path) -> Path | None:
    """Walk up at most ``_MAX_LEVELS_UP`` levels looking for a run dir.

    Checks:
    1. ``start`` itself
    2. ``start.parent``  (and its siblings)
    3. ``start.parent.parent``  (and its siblings)

    Returns the first match or ``None``.
    """
    candidates: list[Path] = [start]

    current = start
    for _ in range(_MAX_LEVELS_UP):
        parent = current.parent
        if parent == current:
            # Reached filesystem root — stop.
            break
        candidates.append(parent)
        # Also check siblings of *current* at this level (e.g. run folder is
        # a sibling of the barcode-sorted output folder).
        candidates.extend(_collect_siblings(current))
        current = parent

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if resolved.is_symlink():
                continue
        except OSError:
            continue
        if _is_run_dir(resolved):
            return resolved

    return None


def discover_run_meta(input_dir: Path) -> Optional[NgsRunMeta]:
    """Search input_dir, its parents, and siblings for MinKNOW run artefacts.

    Returns ``None`` if no MinKNOW run folder can be located.  Never raises —
    all I/O errors are absorbed silently.

    Extraction sources:
    - ``final_summary_*.txt``: instrument, position, flow_cell_id,
      sample_id, started, kit, basecalling_enabled
    - ``sample_sheet_*.csv``: kit (fallback when absent from final_summary)
    """
    try:
        resolved_input = input_dir.resolve()
    except OSError:
        return None

    run_dir = _search_run_dir(resolved_input)
    if run_dir is None:
        return None

    # Parse first found final_summary.
    kv: dict[str, str] = {}
    try:
        summaries = sorted(run_dir.glob("final_summary_*.txt"))
        if summaries:
            kv = _parse_final_summary(summaries[0])
    except OSError:
        pass

    # Supplement kit from sample_sheet if absent.
    kit_val: str | None = kv.get("kit") or None
    if kit_val is None:
        try:
            sample_sheets = sorted(run_dir.glob("sample_sheet_*.csv"))
            if sample_sheets:
                kit_val = _parse_sample_sheet_kit(sample_sheets[0])
        except OSError:
            pass

    # Parse basecalling_enabled (string "true"/"false" → bool).
    basecalling_raw = kv.get("basecalling_enabled")
    basecalling: bool | None = None
    if basecalling_raw is not None:
        basecalling = basecalling_raw.strip().lower() == "true"

    return NgsRunMeta(
        instrument=kv.get("instrument") or None,
        position=kv.get("position") or None,
        flow_cell_id=kv.get("flow_cell_id") or None,
        sample_id=kv.get("sample_id") or None,
        kit=kit_val,
        started=kv.get("started") or None,
        basecalling_enabled=basecalling,
        raw_run_dir=str(run_dir),
    )


__all__ = ["NgsRunMeta", "discover_run_meta"]
