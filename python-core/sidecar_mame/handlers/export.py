"""``export_excel``, ``get_plate_data``, and ``export_janus_mapping`` JSON-RPC handlers.

All handlers require a prior successful ``analyze`` call. They read cached
state from ``sidecar.core``; absence raises ``RuntimeError`` which the
dispatcher maps to JSON-RPC error code ``-32002``.
"""

from __future__ import annotations

from kuma_core.shared.version import KUMA_VERSION
from sidecar_mame.core import (
    _ALLOWED_EXCEL_EXTENSIONS,
    _validate_output_path,
    get_state,
    set_last_analyze,
)

_ALLOWED_JANUS_EXTENSIONS = {".csv", ".xlsx"}


def _custom_barcode_to_seq(custom: str) -> int | None:
    """``{R}_{F}`` -> 1-based column-major sequence index (mirrors excel_writer)."""
    parts = custom.split("_")
    if len(parts) != 2:
        return None
    try:
        r = int(parts[0])
        f = int(parts[1])
    except ValueError:
        return None
    if not (1 <= r <= 8 and 1 <= f <= 12):
        return None
    return (f - 1) * 8 + r


def handle_export_excel(params: dict) -> dict:
    """Rewrite the Excel workbook from cached analyze artefacts.

    A11: MinKNOW run metadata discovered at analyze time is forwarded to
    ``write_excel`` so the ``__kuma_meta__`` sheet is populated automatically.

    Raises ``RuntimeError`` if no analyze has been run in this session.
    """
    from kuma_core.mame.export import WellMapper, write_excel

    state = get_state()
    if state.last_verdicts is None or state.last_replicates is None:
        raise RuntimeError(
            "No prior analyze result. Run 'analyze' before 'export_excel'."
        )

    output = _validate_output_path(
        params["output"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )
    mode = str(params.get("mode", "amplicon"))
    mode_norm = "amplicon" if mode == "amplicon" else "plasmid"

    write_excel(
        verdict_records=state.last_verdicts,
        replicate_results=state.last_replicates,
        output_path=output,
        mapper=WellMapper(),
        mode=mode_norm,
        ngs_run_meta=state.last_run_meta,  # type: ignore[arg-type]  — NgsRunMeta | None
        kuma_version=KUMA_VERSION,
        designed_mutant_ids=state.last_designed_mutant_ids,
    )

    set_last_analyze(
        state.last_verdicts,
        state.last_replicates,
        str(output),
        run_meta=state.last_run_meta,
    )

    return {"output_path": str(output)}


def handle_get_plate_data(_params: dict) -> dict:
    """Emit 96-well grid data derived from cached ``analyze`` verdicts."""
    from kuma_core.mame.export import seq_to_well

    state = get_state()
    if state.last_verdicts is None:
        raise RuntimeError(
            "No prior analyze result. Run 'analyze' before 'get_plate_data'."
        )

    # Set of (native_barcode, custom_barcode) pairs that are the chosen
    # replicate for some mutant. Keyed by the full pair, NOT by native_barcode
    # alone: in combinatorial-sort runs one native_barcode (sort bin) carries
    # many wells, each the selected replicate of a different mutant, so a
    # native->custom dict collapsed every plate to a single "picked" well (and
    # a later mutant's pick overwrote an earlier PASS pick on the same plate).
    selected_pairs: set[tuple[str, str]] = set()
    # (native_barcode, custom_barcode) -> (is_fallback, fallback_reason) for the
    # selected replicate of each mutant.
    fallback_by_pair: dict[tuple[str, str], tuple[bool, str | None]] = {}
    for rr in state.last_replicates or []:
        if rr.selected_plate and not rr.failed:
            vr = rr.plate_verdicts.get(rr.selected_plate)
            if vr is not None:
                key = (rr.selected_plate, vr.translated.barcode.custom_barcode)
                selected_pairs.add(key)
                fallback_by_pair[key] = (
                    bool(getattr(rr, "is_fallback", False)),
                    getattr(rr, "fallback_reason", None),
                )

    wells: list[dict] = []
    for vr in state.last_verdicts:
        b = vr.translated.barcode
        seq = _custom_barcode_to_seq(b.custom_barcode)
        well = seq_to_well(seq) if seq else ""
        # A verdict is the "selected" replicate iff its (native, custom) pair
        # matches a chosen-replicate pair built above. Pair-keyed so EVERY
        # mutant's pick is marked, not just one per native barcode.
        key = (b.native_barcode, b.custom_barcode)
        is_selected = key in selected_pairs
        fb_info = fallback_by_pair.get(key, (False, None))
        is_fallback = fb_info[0] if is_selected else False
        fallback_reason = fb_info[1] if is_selected else None
        # Per-well variant identity: authoritative pipeline-assigned mutant_id
        # (sample_map ground truth in combinatorial-sort runs), falling back to
        # the scoped expected label for legacy payloads that predate the field.
        mutant_id = getattr(vr, "mutant_id", "") or (
            next(iter(vr.expected_mutations), "") if vr.expected_mutations else ""
        )
        wells.append(
            {
                "well": well,
                "barcode": b.custom_barcode,
                "native_barcode": b.native_barcode,
                "verdict": vr.verdict.value,
                "mutant_id": mutant_id,
                "selected": is_selected,
                "notes": vr.verdict_notes,
                "is_fallback": is_fallback,
                "fallback_reason": fallback_reason,
            }
        )

    return {"wells": wells}


def handle_export_janus_mapping(params: dict) -> dict:
    """Export final cell-stock Janus mapping as CSV or XLSX.

    Params:
        output (str): destination file path (.csv or .xlsx).
        format (str, optional): "csv" (default) or "xlsx".

    Raises ``RuntimeError`` if no analyze has been run in this session.

    Phase 1 note: priority_score column carries file_size_kb as a volume proxy.
    G6/A6 round will replace with actual read_count once fasta_parser exposes
    per-record counts.
    """
    from kuma_core.mame.export import export_mame_janus_csv, export_mame_janus_xlsx

    state = get_state()
    if state.last_replicates is None:
        raise RuntimeError(
            "No prior analyze result. Run 'analyze' before 'export_janus_mapping'."
        )

    output = _validate_output_path(
        params["output"], allowed_extensions=_ALLOWED_JANUS_EXTENSIONS
    )

    fmt = str(params.get("format", "csv")).lower()
    if fmt not in ("csv", "xlsx"):
        raise ValueError(f"Invalid format '{fmt}'. Expected 'csv' or 'xlsx'.")

    # G3: pass cached run meta to embed in the Janus output.
    run_meta = state.last_run_meta  # NgsRunMeta | None

    if fmt == "xlsx":
        export_mame_janus_xlsx(
            state.last_replicates,
            output,
            ngs_run_meta=run_meta,  # type: ignore[arg-type]
            kuma_version=KUMA_VERSION,
        )
    else:
        export_mame_janus_csv(
            state.last_replicates,
            output,
            ngs_run_meta=run_meta,  # type: ignore[arg-type]
        )

    return {"output_path": str(output), "format": fmt}


__all__ = ["handle_export_excel", "handle_get_plate_data", "handle_export_janus_mapping"]
