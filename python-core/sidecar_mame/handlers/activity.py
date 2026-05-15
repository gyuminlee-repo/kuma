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
from datetime import datetime, timezone
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
_ALLOWED_EXPORT_XLSX_EXTENSIONS = {".xlsx"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_round(round_id: str) -> dict:
    """Return the round dict or raise RuntimeError (-32002 in dispatcher).

    Raises ValueError for empty/missing round_id (-32602 in dispatcher).
    """
    if not round_id:
        raise ValueError("round_id is required")
    rd = _rounds.get(round_id)
    if rd is None:
        raise RuntimeError(f"Round not found: {round_id}")
    return rd


def _ensure_round(round_id: str, *, n: int = 1) -> dict:
    """Return the round dict, lazily creating it with defaults if missing.

    Frontend ``addRound`` only mutates the React Zustand store; the sidecar
    has no corresponding state until an activity.* RPC is called. Without
    lazy-init, the first ``activity.upload`` call after entering the Activity
    phase fails with ``Round not found`` because no prior RPC seeded
    ``_rounds[round_id]``. Lazy-init keeps the dispatcher API ergonomic
    (frontend does not need a separate ``round.create`` RPC) without breaking
    tests that pre-populate ``_rounds`` directly.

    Caller must hold ``_rounds_lock``.
    """
    if not round_id:
        raise ValueError("round_id is required")
    rd = _rounds.get(round_id)
    if rd is None:
        rd = {
            "round_id": round_id,
            "n": n,
            "status": "design",
            "plate_meta": {"plates": []},
        }
        _rounds[round_id] = rd
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


def _is_wt_key(key: str) -> bool:
    """Return True if *key* represents a WT entry.

    Covers both plain 'WT' (EVOLVEpro convention) and 'WT_1'/'WT1' patterns
    (well-level replicate names from normalize.WT_PATTERN).
    Plain 'WT' is not matched by WT_PATTERN (which requires a numeric suffix),
    so this function unions both checks.
    """
    from kuma_core.mame.activity.normalize import WT_PATTERN
    return key == "WT" or bool(WT_PATTERN.match(key))


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

    round_id: str = params["round_id"]

    with _rounds_lock:
        # Lazy-init: frontend addRound only mutates Zustand; sidecar would
        # otherwise raise "Round not found" on the first upload call.
        rd = _ensure_round(round_id)

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
    return {"records": serialised, "plate_meta": pmeta_raw, "warnings": []}


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
        # Lazy-init so the very first frontend call after addRound succeeds.
        rd = _ensure_round(round_id)
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

    Returns: ``{written_rows: int, columns: str[], manifest_path: str}``

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
    from kuma_core.shared.run_manifest import build_run_manifest, write_run_manifest
    from kuma_core.shared.output_hash import write_output_checksum

    started_at = datetime.now(timezone.utc)

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

    bom: bool = bool(params.get("bom", False))
    encoding = "utf-8-sig" if bom else "utf-8"
    rows: list[MergedRow] = [MergedRow(**r) for r in merged_dicts]
    written = export_evolvepro_csv(rows, out_path, round_n=round_n, encoding=encoding)

    finished_at = datetime.now(timezone.utc)

    manifest = build_run_manifest(
        method="activity.export_evolvepro_csv",
        inputs={},
        params={"round_id": round_id, "path": params.get("path")},
        started_at=started_at,
        finished_at=finished_at,
    )
    mpath = out_path.parent / (out_path.stem + ".run.json")
    write_run_manifest(mpath, manifest)
    cpath = write_output_checksum(out_path)

    return {
        "written_rows": written,
        "columns": list(COLUMNS),
        "manifest_path": str(mpath),
        "checksum_path": str(cpath),
    }


def handle_activity_export_evolvepro_xlsx(params: dict) -> dict:
    """``activity.export_evolvepro_xlsx`` — write EVOLVEpro-compatible xlsx.

    Spec: notes/specs/2026-05-06-mame-activity-v0.3-xlsx-pipeline.md §1, §2.4

    Params: ``{round_id, path}``

    Returns: ``{written_rows: int, columns: str[], manifest_path: str}``

    Raises:
        RuntimeError: round_id not found.
        FileNotFoundError: parent directory of path does not exist.
        ValueError: unsupported output extension.
    """
    from kuma_core.mame.activity.export_evolvepro import export_evolvepro_xlsx
    from kuma_core.mame.activity.models import MergedRow
    from kuma_core.shared.run_manifest import build_run_manifest, write_run_manifest
    from kuma_core.shared.output_hash import write_output_checksum

    started_at = datetime.now(timezone.utc)

    round_id: str = params["round_id"]

    with _rounds_lock:
        rd = _get_round(round_id)
        merged_dicts: list[dict] = rd.get("merged_table") or []

    out_path = _validate_output_path(
        params.get("path"),
        allowed_extensions=_ALLOWED_EXPORT_XLSX_EXTENSIONS,
    )

    rows: list[MergedRow] = [MergedRow(**r) for r in merged_dicts]
    written, excluded = export_evolvepro_xlsx(rows, out_path)

    finished_at = datetime.now(timezone.utc)

    manifest = build_run_manifest(
        method="activity.export_evolvepro_xlsx",
        inputs={},
        params={"round_id": round_id, "path": params.get("path")},
        started_at=started_at,
        finished_at=finished_at,
    )
    mpath = out_path.parent / (out_path.stem + ".run.json")
    write_run_manifest(mpath, manifest)
    cpath = write_output_checksum(out_path)

    return {
        "written_rows": written,
        "columns": ["Variant", "activity"],
        "excluded": [{"label": label, "reason": reason} for label, reason in excluded],
        "manifest_path": str(mpath),
        "checksum_path": str(cpath),
    }


# ---------------------------------------------------------------------------
# B-5: New handler — merge + label-swap guard + EVOLVEpro export preparation
# ---------------------------------------------------------------------------

class ExportBlockedError(RuntimeError):
    """Raised when label-swap guard blocks export (-32004)."""


def handle_merge_for_evolvepro(params: dict) -> dict:
    """``mame.activity.merge_for_evolvepro`` — merge replicates + label-swap guard.

    This handler integrates Phase A xlsx adapters with Phase B merge logic.
    It does NOT replace ``activity.merge`` (5/12 demo path — unchanged).

    Params:
        round_id (str): Round identifier. Must exist in _rounds state.
        prev_round_evolvepro (dict): {short_variant: activity} from round N-1.
            Pass {} for round 1.
        authoritative_measurements (dict, optional): Phase B. short_variant →
            list[float] re-measurement data. Empty dict skips replicate merge.
        fallback_measurements (dict, optional): Phase B. short_variant →
            list[float] primary measurement data.
        mismatch_threshold (float, optional): Mean difference threshold for
            mismatch flagging. Default 0.1.
        ref_seq (str, optional): WT reference sequence for from_evolvepro
            conversion. Required when authoritative or fallback measurements
            are non-empty.

    Returns:
        {
          "merged": MergedRow[],
          "stats": MergeStats (includes warnings),
          "replicate_stats": MergeReplicatesStats | null,
          "export_blocked": bool
        }

    Raises:
        RuntimeError(-32002): round_id not found.
        ExportBlockedError(-32004): SwapWarning with severity="error" detected.
        KeyError(-32602): required parameter missing.
        ValueError(-32602): ref_seq missing when replicate data provided;
            empty measurement list; from_evolvepro parse failure.
    """
    from kuma_core.mame.activity.join import merge_activity_with_genotype
    from kuma_core.mame.activity.merge import merge_replicates_priority
    from kuma_core.mame.activity.models import (
        ActivityRecord,
        MergeReplicatesStats,
        MergeStats,
        PlateMeta,
        Variant,
    )
    from kuma_core.mame.activity.sanity_check import detect_label_swap
    from kuma_core.mame.activity.variant_notation import from_evolvepro
    from kuma_core.mame.activity.ref_seq import get_isps_wt_aa_seq

    round_id: str = params["round_id"]  # KeyError → -32602 via dispatcher
    prev_round_evolvepro: dict[str, float] = params.get("prev_round_evolvepro", {})
    authoritative_measurements: dict[str, list[float]] = params.get(
        "authoritative_measurements", {}
    ) or {}
    fallback_measurements: dict[str, list[float]] = params.get(
        "fallback_measurements", {}
    ) or {}
    mismatch_threshold: float = float(params.get("mismatch_threshold", 0.1))
    ref_seq: str | None = params.get("ref_seq")

    # Fast-fail: replicate data provided but ref_seq missing.
    has_replicate_data = bool(authoritative_measurements or fallback_measurements)
    if has_replicate_data and not ref_seq:
        # OQ-④: auto-load IspS WT reference when ref_seq not explicitly provided.
        try:
            ref_seq = get_isps_wt_aa_seq()
        except (FileNotFoundError, ValueError) as _e:
            raise ValueError(
                "ref_seq required and IspS auto-load failed: "
                f"{_e}"
            ) from _e

    # WT key filtering (OQ-3 decision): remove WT entries before passing to
    # merge_replicates_priority. WT is reference baseline, not a variant.
    # Covers plain 'WT' (EVOLVEpro convention) and 'WT_N'/'WTN' patterns.
    if has_replicate_data:
        authoritative_measurements = {
            k: v for k, v in authoritative_measurements.items()
            if not _is_wt_key(k)
        }
        fallback_measurements = {
            k: v for k, v in fallback_measurements.items()
            if not _is_wt_key(k)
        }
        # Re-evaluate after WT filtering: both may be empty now.
        has_replicate_data = bool(authoritative_measurements or fallback_measurements)

    with _rounds_lock:
        rd = _get_round(round_id)  # RuntimeError → -32002 via dispatcher

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

        # Phase B replicate merge (skipped when no replicate data provided).
        replicate_stats: MergeReplicatesStats | None = None
        if has_replicate_data:
            # Convert short EVOLVEpro notation → internal notation.
            # ValueError from from_evolvepro (bad notation) → -32602 via dispatcher.
            # ref_seq is guaranteed non-None here (checked above).
            if ref_seq is None:  # pragma: no cover — defensive narrowing
                raise ValueError("ref_seq required for replicate merge")
            authoritative_internal: dict[Variant, list[float]] = {
                Variant(from_evolvepro(k, ref_seq)): v
                for k, v in authoritative_measurements.items()
            }
            fallback_internal: dict[Variant, list[float]] = {
                Variant(from_evolvepro(k, ref_seq)): v
                for k, v in fallback_measurements.items()
            }

            # ValueError (empty list) → -32602 via dispatcher.
            merged_dict, replicate_stats = merge_replicates_priority(
                authoritative_internal,
                fallback_internal,
                mismatch_threshold=mismatch_threshold,
            )

            # Map merged values onto MergedRow.activity_merged_mean.
            for row in rows:
                if row.mutation is not None:
                    v_key = Variant(row.mutation)
                    if v_key in merged_dict:
                        row.activity_merged_mean = merged_dict[v_key]

        # Build activity_map: well_id → mean activity (for swap detection).
        # activity_raw_mean is used per D-2 decision (OQ-2: no change).
        activity_map: dict[str, float] = {}
        for row in rows:
            if row.activity_raw_mean is not None:
                activity_map[row.well_id] = row.activity_raw_mean

        # Build layout from merged rows that have a mutation assigned.
        layout: list[tuple[str, str]] = []
        for row in rows:
            if row.mutation is not None:
                layout.append((row.mutation, row.well_id))

        # Label-swap detection (round 1 → prev_round_evolvepro={} → returns []).
        swap_warnings = detect_label_swap(
            layout,
            activity_map,
            prev_round_evolvepro,
        )

        # Attach warnings to stats.
        stats_with_warnings = MergeStats(
            **{
                **stats.model_dump(exclude={"warnings"}),
                "warnings": swap_warnings,
            }
        )

        merged_dicts = [r.model_dump() for r in rows]
        rd["merged_table"] = merged_dicts
        rd["status"] = "activity_linked"

    export_blocked = any(w.severity == "error" for w in swap_warnings)

    result: dict[str, Any] = {
        "merged": merged_dicts,
        "stats": stats_with_warnings.model_dump(),
        "replicate_stats": (
            replicate_stats.__dict__ if replicate_stats is not None else None
        ),
        "export_blocked": export_blocked,
    }

    if export_blocked:
        # Raise so the dispatcher maps this to error code -32004.
        raise ExportBlockedError(
            f"Export blocked: {sum(1 for w in swap_warnings if w.severity == 'error')} "
            "label-swap error(s) detected. Resolve warnings before exporting. "
            f"Affected variants: "
            f"{[v for w in swap_warnings if w.severity == 'error' for v in w.variants]}"
        )

    return result


__all__ = [
    "handle_activity_upload",
    "handle_activity_set_plate_meta",
    "handle_activity_merge",
    "handle_activity_export_evolvepro_csv",
    "handle_activity_export_evolvepro_xlsx",
    "handle_merge_for_evolvepro",
    "ExportBlockedError",
    "_rounds",
]
