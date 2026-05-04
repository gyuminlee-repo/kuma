"""``activity.*`` JSON-RPC handlers for MAME activity integration.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §3.2

State model
-----------
Round objects are stored in the module-level ``_rounds`` dict, keyed by
``round_id``. Each entry is a plain dict matching the workspace schema
(§2.1). Callers (dispatcher, tests) interact with this state via the
four handler functions below.

Dispatcher registration is in ``sidecar_mame.dispatcher``.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from sidecar_mame.core import (
    _validate_filepath,
    _validate_output_path,
)

# ---------------------------------------------------------------------------
# Module-level round state (activity handlers only)
# ---------------------------------------------------------------------------
_rounds: dict[str, dict[str, Any]] = {}
_rounds_lock = threading.Lock()

_ALLOWED_ACTIVITY_EXTENSIONS = {".csv", ".xlsx", ".xls"}
_ALLOWED_EXPORT_EXTENSIONS = {".csv"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_round(round_id: str) -> dict:
    """Return the round dict or raise RuntimeError (-32002 in dispatcher)."""
    rd = _rounds.get(round_id)
    if rd is None:
        raise RuntimeError(f"Round not found: {round_id}")
    return rd


def _extract_kuro_design(design: dict) -> dict[tuple[str, str], str]:
    """Extract (plate_id, well_id) → mutation from a design snapshot dict.

    Expects ``design["plateMap"]`` to be a list of
    ``{plate_id, well_id, mutation}`` dicts. Unknown/missing keys return an
    empty mapping (graceful degradation for rounds where design is not yet
    populated).
    """
    plate_map = design.get("plateMap", [])
    result: dict[tuple[str, str], str] = {}
    for item in plate_map:
        pid = item.get("plate_id")
        wid = item.get("well_id")
        mut = item.get("mutation")
        if pid and wid and mut:
            result[(pid, wid)] = mut
    return result


def _extract_mame_genotype(genotype: dict) -> dict[tuple[str, str], str]:
    """Extract (plate_id, well_id) → called_mutation from a genotype snapshot dict.

    Expects ``genotype["verdict"]`` to be a list of
    ``{plate_id, well_id, called_mutation}`` dicts.
    """
    verdicts = genotype.get("verdict", [])
    result: dict[tuple[str, str], str] = {}
    for v in verdicts:
        pid = v.get("plate_id")
        wid = v.get("well_id")
        called = v.get("called_mutation")
        if pid and wid and called:
            result[(pid, wid)] = called
    return result


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_activity_upload(params: dict) -> dict:
    """``activity.upload`` — ingest a long-format CSV/Excel file.

    Params: ``{round_id, file_path, format}``

    Returns: ``{records: ActivityRecord[], warnings: string[]}``

    Raises:
        RuntimeError: round_id not found in state.
        FileNotFoundError: file_path missing or unresolvable.
        ValueError: unsupported file extension or missing required columns.
    """
    from kuma_core.mame.activity.ingest_long_csv import ingest_long_csv
    from kuma_core.mame.activity.models import PlateMeta

    round_id: str = params["round_id"]

    with _rounds_lock:
        rd = _get_round(round_id)

        resolved = _validate_filepath(
            params.get("file_path"),
            allowed_extensions=_ALLOWED_ACTIVITY_EXTENSIONS,
        )

        pmeta_raw: dict = rd["plate_meta"]
        wt_lookup: dict[str, list[str]] = {
            p["plate_id"]: p["wt_wells"]
            for p in pmeta_raw.get("plates", [])
        }

        table = ingest_long_csv(resolved, wt_lookup)

        # Persist raw records into round state for downstream merge
        rd["activity"] = {
            "raw_records": [r.model_dump() for r in table.records],
        }

    serialised = [r.model_dump() for r in table.records]
    return {"records": serialised, "warnings": []}


def handle_activity_set_plate_meta(params: dict) -> dict:
    """``activity.set_plate_meta`` — update plate metadata for a round.

    Params: ``{round_id, plate_meta}``

    Returns: ``{ok: true}``

    Raises:
        RuntimeError: round_id not found.
        KeyError: plate_meta key missing from params.
    """
    round_id: str = params["round_id"]
    new_meta: dict = params["plate_meta"]  # KeyError if missing — maps to -32602

    with _rounds_lock:
        rd = _get_round(round_id)
        rd["plate_meta"] = new_meta

    return {"ok": True}


def handle_activity_merge(params: dict) -> dict:
    """``activity.merge`` — merge design, genotype, and activity by (plate_id, well_id).

    Params: ``{round_id}``

    Returns: ``{merged: MergedRow[], stats: MergeStats}``

    Raises:
        RuntimeError: round_id not found.
    """
    from kuma_core.mame.activity.join import merge_activity_with_genotype
    from kuma_core.mame.activity.models import ActivityRecord, PlateMeta

    round_id: str = params["round_id"]

    with _rounds_lock:
        rd = _get_round(round_id)

        kuro_design = _extract_kuro_design(rd.get("design") or {})
        mame_genotype = _extract_mame_genotype(rd.get("genotype") or {})

        plate_meta = PlateMeta(**rd["plate_meta"])

        activity_data = rd.get("activity") or {}
        raw_dicts: list[dict] = activity_data.get("raw_records", [])
        activity_records: list[ActivityRecord] = [
            ActivityRecord(**r) for r in raw_dicts
        ]

        rows, stats = merge_activity_with_genotype(
            kuro_design, mame_genotype, activity_records, plate_meta
        )

        merged_dicts = [r.model_dump() for r in rows]
        rd["merged_table"] = merged_dicts
        rd["status"] = "activity_linked"

    return {
        "merged": merged_dicts,
        "stats": stats.model_dump(),
    }


def handle_activity_export_evolvepro_csv(params: dict) -> dict:
    """``activity.export_evolvepro_csv`` — write EVOLVEpro-compatible CSV.

    Params: ``{round_id, path}``

    Returns: ``{written_rows: int, columns: str[]}``

    Raises:
        RuntimeError: round_id not found.
        FileNotFoundError: parent directory of path does not exist.
        ValueError: unsupported output extension.
    """
    from kuma_core.mame.activity.export_evolvepro import (
        COLUMNS,
        export_evolvepro_csv,
    )
    from kuma_core.mame.activity.models import MergedRow

    round_id: str = params["round_id"]

    with _rounds_lock:
        rd = _get_round(round_id)
        merged_dicts: list[dict] = rd.get("merged_table") or []
        round_n: int = rd.get("n", 1)

    # Path validation happens outside the lock (I/O)
    out_path = _validate_output_path(
        params.get("path"),
        allowed_extensions=_ALLOWED_EXPORT_EXTENSIONS,
    )

    rows: list[MergedRow] = [MergedRow(**r) for r in merged_dicts]
    written = export_evolvepro_csv(rows, out_path, round_n=round_n)

    return {"written_rows": written, "columns": list(COLUMNS)}


__all__ = [
    "handle_activity_upload",
    "handle_activity_set_plate_meta",
    "handle_activity_merge",
    "handle_activity_export_evolvepro_csv",
    "_rounds",
]
