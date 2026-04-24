"""Handlers: Excel/CSV export, plate map, workspace save/load."""

import csv
import json
from dataclasses import fields as dc_fields

from kuma_core.kuro.plate_mapper import (
    PlateMapping,
    export_echo_mapping_csv,
    export_echo_mapping_xlsx,
    export_janus_mapping_csv,
    export_janus_mapping_xlsx,
    export_plate_excel,
    export_idt_csv,
    export_twist_csv,
    generate_plate_map,
)

import sidecar_kuro.core as _core
from sidecar_kuro.core import (
    _validate_filepath,
    _validate_output_path,
    _ALLOWED_EXCEL_EXTENSIONS,
    _ALLOWED_CSV_EXTENSIONS,
)
from sidecar_kuro.models import (
    ExportExcelParams,
    ExportMappingResultModel,
    ExportOrderResultModel,
    ExportMappingParams,
    ExportOrderParams,
    ExportBenchmarkCsvParams,
    FileExportResultModel,
    SaveWorkspaceParams,
    SaveJsonParams,
    LoadWorkspaceParams,
    validate_workspace_data,
)

_ALLOWED_ORDER_CSV_EXTENSIONS = {".csv"}
_ALLOWED_MAPPING_EXTENSIONS = {".xlsx", ".csv"}

_PLATE_MAPPING_KEYS = {f.name for f in dc_fields(PlateMapping)}


def _pydantic_to_plate_mappings(items) -> list[PlateMapping]:
    """Convert a list of Pydantic PlateMappingItem objects to PlateMapping dataclasses."""
    return [
        PlateMapping(**{k: v for k, v in m.model_dump().items() if k in _PLATE_MAPPING_KEYS})
        for m in items
    ]


def _resolve_mapping_transfer_volume(fmt: str, transfer_vol: float | None) -> int | float:
    """Validate and normalize mapping transfer volume by instrument."""
    if fmt == "echo":
        if transfer_vol is None:
            return 100
        if transfer_vol <= 0:
            raise ValueError("Echo transfer volume must be greater than 0 nL.")
        if not float(transfer_vol).is_integer():
            raise ValueError("Echo transfer volume must be a whole number of nL.")
        return int(transfer_vol)

    if transfer_vol is None:
        return 2.0
    if transfer_vol <= 0:
        raise ValueError("JANUS transfer volume must be greater than 0 uL.")
    return float(transfer_vol)


def handle_get_plate_map(_params: dict) -> dict:
    """Return the plate map from last design."""
    with _core._state_lock:
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

    dedup_data = p.dedup_info

    if p.mappings:
        mappings = _pydantic_to_plate_mappings(p.mappings)
        rev_groups = dedup_data or {}
        with _core._state_lock:
            results_for_export = list(_core._state.results)
    else:
        with _core._state_lock:
            if not _core._state.results:
                raise ValueError("No design available")
            mappings = _core._state.plate_mappings
            rev_groups = _core._state.dedup_info
            results_for_export = list(_core._state.results)

    export_plate_excel(
        mappings, resolved,
        rev_groups=rev_groups,
        results=results_for_export,
    )
    return FileExportResultModel(filepath=str(resolved)).model_dump(mode="json")


def handle_export_order(params: dict) -> dict:
    """Export primer order CSV in IDT or Twist format."""
    p = ExportOrderParams(**params)
    fmt = p.format.lower()
    if fmt not in ("idt", "twist"):
        raise ValueError(f"Invalid export format: '{fmt}'. Must be 'idt' or 'twist'.")

    resolved = _validate_output_path(
        p.filepath, allowed_extensions=_ALLOWED_ORDER_CSV_EXTENSIONS
    )

    if p.results:
        rows = p.results
        with open(resolved, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if fmt == "idt":
                writer.writerow(["Name", "Sequence", "Scale", "Purification"])
                for r in rows:
                    writer.writerow([f"{r.mutation}_F", r.forward_seq, p.scale, p.purification])
                    writer.writerow([f"{r.mutation}_R", r.reverse_seq, p.scale, p.purification])
            else:
                writer.writerow(["Name", "Sequence", "Notes"])
                for r in rows:
                    writer.writerow([f"{r.mutation}_F", r.forward_seq, r.mutation])
                    writer.writerow([f"{r.mutation}_R", r.reverse_seq, r.mutation])
        primer_count = len(rows) * 2
    else:
        with _core._state_lock:
            if not _core._state.results:
                raise ValueError("No design available. Run design_sdm_primers first.")
            results = _core._state.results

        if fmt == "idt":
            export_idt_csv(results, resolved, scale=p.scale, purification=p.purification)
        else:
            export_twist_csv(results, resolved)
        primer_count = len(results) * 2

    return ExportOrderResultModel(
        filepath=str(resolved),
        format=fmt,
        primer_count=primer_count,
    ).model_dump(mode="json")


def handle_export_mapping(params: dict) -> dict:
    """Export liquid handler mapping file (Echo 525 or JANUS, CSV or XLSX)."""
    p = ExportMappingParams(**params)
    resolved = _validate_output_path(p.filepath, allowed_extensions=_ALLOWED_MAPPING_EXTENSIONS)

    if p.mappings:
        mappings = _pydantic_to_plate_mappings(p.mappings)
        fwd_mappings = [m for m in mappings if m.primer_type == "forward"]
        rev_mappings = [m for m in mappings if m.primer_type == "reverse"]
        rev_groups = p.dedup_info or {}
    else:
        with _core._state_lock:
            if not _core._state.results:
                raise ValueError("No design available. Run design_sdm_primers first.")
            results = _core._state.results
            rev_groups = _core._state.dedup_info or {}

        fwd_mappings, rev_mappings = generate_plate_map(
            results,
            deduplicate_rev=True,
        )

    use_xlsx = resolved.suffix.lower() == ".xlsx"

    if p.format == "echo":
        vol = _resolve_mapping_transfer_volume(p.format, p.transfer_vol)
        if use_xlsx:
            export_echo_mapping_xlsx(fwd_mappings, rev_mappings, resolved,
                                     transfer_vol=vol, rev_groups=rev_groups)
        else:
            export_echo_mapping_csv(fwd_mappings, rev_mappings, resolved,
                                    transfer_vol=vol, rev_groups=rev_groups)
    else:
        vol = _resolve_mapping_transfer_volume(p.format, p.transfer_vol)
        if use_xlsx:
            export_janus_mapping_xlsx(fwd_mappings, rev_mappings, resolved,
                                      transfer_vol=vol, rev_groups=rev_groups)
        else:
            export_janus_mapping_csv(fwd_mappings, rev_mappings, resolved,
                                     transfer_vol=vol, rev_groups=rev_groups)

    primer_count = len(fwd_mappings) + len(rev_mappings)
    return ExportMappingResultModel(
        filepath=str(resolved),
        format=p.format,
        primer_count=primer_count,
    ).model_dump(mode="json")


def handle_save_workspace(params: dict) -> dict:
    """Save workspace JSON to file."""
    p = SaveWorkspaceParams(**params)
    if not p.filepath or p.data is None:
        raise ValueError("filepath and data are required")
    resolved = _validate_output_path(p.filepath, allowed_extensions={".json"})
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(p.data, f, ensure_ascii=False, indent=2)
    return FileExportResultModel(filepath=str(resolved)).model_dump(mode="json")


def handle_save_json(params: dict) -> dict:
    """Save generic JSON payload to file."""
    p = SaveJsonParams(**params)
    if not p.filepath or p.data is None:
        raise ValueError("filepath and data are required")
    resolved = _validate_output_path(p.filepath, allowed_extensions={".json"})
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(p.data, f, ensure_ascii=False, indent=2)
    return FileExportResultModel(filepath=str(resolved)).model_dump(mode="json")


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

    if not isinstance(data, dict):
        raise ValueError("Workspace file must contain a JSON object")
    result_list = None
    if isinstance(data.get("results"), list):
        result_list = data["results"]
    elif isinstance(data.get("results"), dict) and isinstance(data["results"].get("designResults"), list):
        result_list = data["results"]["designResults"]

    if result_list is not None and len(result_list) > 10_000:
        raise ValueError(f"Workspace contains {len(result_list)} results, exceeding 10,000 limit")

    validated = validate_workspace_data(data)
    return validated.model_dump(mode="json", exclude_unset=True, round_trip=True)


def handle_export_benchmark_csv(params: dict) -> dict:
    """Export benchmark result table to CSV."""
    p = ExportBenchmarkCsvParams(**params)
    if not p.results:
        raise ValueError("Benchmark results are required")

    resolved = _validate_output_path(p.filepath, allowed_extensions=_ALLOWED_ORDER_CSV_EXTENSIONS)
    fieldnames = [
        "strategy",
        "n_selected",
        "hit_rate",
        "mean_fitness",
        "unique_positions",
        "position_coverage",
        "domain_coverage",
        "structural_spread",
        "hits",
        "threshold",
        "n_trials",
    ]
    with open(resolved, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for strategy, metrics in p.results.items():
            writer.writerow({"strategy": strategy, **metrics})
    return FileExportResultModel(filepath=str(resolved)).model_dump(mode="json")
