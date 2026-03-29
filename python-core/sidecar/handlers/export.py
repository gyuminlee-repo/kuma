"""Handlers: Excel/CSV export, plate map, workspace save/load."""

import json
from dataclasses import fields as dc_fields

from kuro.plate_mapper import PlateMapping, export_plate_excel, export_idt_csv, export_twist_csv

import sidecar.core as _core
from sidecar.core import (
    _validate_filepath,
    _validate_output_path,
    _ALLOWED_EXCEL_EXTENSIONS,
    _ALLOWED_CSV_EXTENSIONS,
)
from sidecar.models import (
    ExportExcelParams,
    ExportOrderParams,
    SaveWorkspaceParams,
    LoadWorkspaceParams,
)

_ALLOWED_ORDER_CSV_EXTENSIONS = {".csv"}


def handle_get_plate_map(_params: dict) -> dict:
    """Return the plate map from last design."""
    if not _core._state.results:
        raise ValueError("No design available. Run design_sdm_primers first.")

    return {
        "mappings": [
            {
                "well": m.well,
                "primer_name": m.primer_name,
                "sequence": m.sequence,
                "primer_type": m.primer_type,
                "mutation": m.mutation,
            }
            for m in _core._state.plate_mappings
        ],
        "dedup_info": _core._state.dedup_info,
    }


def handle_export_excel(params: dict) -> dict:
    """Export plate map to Excel.

    Accepts optional 'mappings' and 'dedup_info' from the frontend to reflect
    the current UI state (sorted order, custom additions from failed mutations).
    Falls back to backend state when not provided (CLI usage).
    """
    p = ExportExcelParams(**params)
    resolved = _validate_output_path(
        p.filepath, allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )

    mappings_data = p.mappings
    dedup_data = p.dedup_info

    if mappings_data:
        if not isinstance(mappings_data, list):
            raise ValueError("mappings must be a list")
        required_fields = {"well", "primer_name", "sequence", "primer_type", "mutation"}
        mappings = []
        for i, m in enumerate(mappings_data):
            if not isinstance(m, dict):
                raise ValueError(f"mappings[{i}] must be an object")
            missing = required_fields - m.keys()
            if missing:
                raise ValueError(f"mappings[{i}] missing fields: {sorted(missing)}")
            # Only pass fields that PlateMapping accepts
            valid_keys = {f.name for f in dc_fields(PlateMapping)}
            filtered = {k: v for k, v in m.items() if k in valid_keys}
            mappings.append(PlateMapping(**filtered))
        rev_groups = dedup_data or {}
    else:
        if not _core._state.results:
            raise ValueError("No design available")
        mappings = _core._state.plate_mappings
        rev_groups = _core._state.dedup_info

    export_plate_excel(mappings, resolved, rev_groups=rev_groups)
    return {"success": True, "filepath": str(resolved)}


def handle_export_order(params: dict) -> dict:
    """Export primer order CSV in IDT or Twist format.

    Params:
        filepath: Output CSV path.
        format: "idt" or "twist".
        scale: IDT synthesis scale (default "25nm").
        purification: IDT purification (default "STD").
    """
    p = ExportOrderParams(**params)
    fmt = p.format.lower()
    if fmt not in ("idt", "twist"):
        raise ValueError(f"Invalid export format: '{fmt}'. Must be 'idt' or 'twist'.")

    resolved = _validate_output_path(
        p.filepath, allowed_extensions=_ALLOWED_ORDER_CSV_EXTENSIONS
    )

    if not _core._state.results:
        raise ValueError("No design available. Run design_sdm_primers first.")

    if fmt == "idt":
        export_idt_csv(_core._state.results, resolved, scale=p.scale, purification=p.purification)
    else:
        export_twist_csv(_core._state.results, resolved)

    return {"success": True, "filepath": str(resolved), "format": fmt, "primer_count": len(_core._state.results) * 2}


def handle_save_workspace(params: dict) -> dict:
    """Save workspace JSON to file."""
    p = SaveWorkspaceParams(**params)
    if not p.filepath or p.data is None:
        raise ValueError("filepath and data are required")
    resolved = _validate_output_path(p.filepath, allowed_extensions={".json"})
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(p.data, f, ensure_ascii=False, indent=2)
    return {"success": True, "filepath": str(resolved)}


def handle_load_workspace(params: dict) -> dict:
    """Load workspace JSON from file."""
    p = LoadWorkspaceParams(**params)
    resolved = _validate_filepath(p.filepath, allowed_extensions={".json"})
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {p.filepath}")
    file_size = resolved.stat().st_size
    if file_size > 50 * 1024 * 1024:
        raise ValueError(f"Workspace file too large: {file_size / 1024 / 1024:.1f} MB (max 50 MB)")
    with open(resolved, encoding="utf-8") as f:
        data = json.load(f)

    # Validate loaded workspace structure
    if not isinstance(data, dict):
        raise ValueError("Workspace file must contain a JSON object")
    if "results" in data:
        if not isinstance(data["results"], list):
            raise ValueError("Workspace 'results' must be an array")
        if len(data["results"]) > 10_000:
            raise ValueError(f"Workspace contains {len(data['results'])} results, exceeding 10,000 limit")

    return data
