"""``export_excel`` and ``get_plate_data`` JSON-RPC handlers.

Both handlers require a prior successful ``analyze`` call. They read cached
state from ``sidecar.core``; absence raises ``RuntimeError`` which the
dispatcher maps to JSON-RPC error code ``-32002``.
"""

from __future__ import annotations

from sidecar_mame.core import (
    _ALLOWED_EXCEL_EXTENSIONS,
    _validate_output_path,
    get_state,
    set_last_analyze,
)


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
    )

    set_last_analyze(state.last_verdicts, state.last_replicates, str(output))

    return {"output_path": str(output)}


def handle_get_plate_data(_params: dict) -> dict:
    """Emit 96-well grid data derived from cached ``analyze`` verdicts."""
    from kuma_core.mame.export import seq_to_well

    state = get_state()
    if state.last_verdicts is None:
        raise RuntimeError(
            "No prior analyze result. Run 'analyze' before 'get_plate_data'."
        )

    # Map native_barcode -> selected custom_barcode (Final sheet accent wells).
    selected_by_plate: dict[str, str | None] = {}
    for rr in state.last_replicates or []:
        if rr.selected_plate and not rr.failed:
            vr = rr.plate_verdicts.get(rr.selected_plate)
            if vr is not None:
                selected_by_plate[rr.selected_plate] = (
                    vr.translated.barcode.custom_barcode
                )

    wells: list[dict] = []
    for vr in state.last_verdicts:
        b = vr.translated.barcode
        seq = _custom_barcode_to_seq(b.custom_barcode)
        well = seq_to_well(seq) if seq else ""
        # A verdict is the "selected" replicate iff its (native, custom) pair
        # matches the replicate_result mapping built above.
        is_selected = (
            selected_by_plate.get(b.native_barcode) == b.custom_barcode
        )
        mutant_id = next(iter(vr.expected_mutations), "") if vr.expected_mutations else ""
        wells.append(
            {
                "well": well,
                "barcode": b.custom_barcode,
                "native_barcode": b.native_barcode,
                "verdict": vr.verdict.value,
                "mutant_id": mutant_id,
                "selected": is_selected,
                "notes": vr.verdict_notes,
            }
        )

    return {"wells": wells}


__all__ = ["handle_export_excel", "handle_get_plate_data"]
