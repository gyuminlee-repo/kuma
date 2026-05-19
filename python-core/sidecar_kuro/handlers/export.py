"""Handlers: Excel/CSV export, plate map, workspace save/load."""

import csv
import json
from dataclasses import fields as dc_fields
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import openpyxl

from kuma_core.kuro.plate_mapper import (
    PlateMapping,
    export_idt_csv,
    export_echo_mapping_csv,
    export_echo_mapping_xlsx,
    export_janus_mapping_csv,
    export_janus_mapping_xlsx,
    export_plate_excel,
    export_twist_csv,
    generate_plate_map,
)
from kuma_core.shared.version import KUMA_VERSION, KURO_MODULE_VERSION
from kuma_core.shared.run_manifest import (
    build_run_manifest,
    write_run_manifest,
)
from kuma_core.shared.output_hash import write_output_checksum

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
    ExportMappingParams,
    ExportOrderParams,
    ExportOrderResultModel,
    ExportBenchmarkCsvParams,
    FileExportResultModel,
    SaveWorkspaceParams,
    SaveJsonParams,
    LoadWorkspaceParams,
    validate_workspace_data,
)

_ALLOWED_MAPPING_EXTENSIONS = {".xlsx", ".csv"}

_PLATE_MAPPING_KEYS = {f.name for f in dc_fields(PlateMapping)}


def _write_report_sheet(wb: openpyxl.Workbook, report_data: dict) -> None:
    if "Report" in wb.sheetnames:
        del wb["Report"]
    ws = wb.create_sheet("Report")
    ws.append(["Section", "Label", "Value", "Warn"])

    for section in report_data.get("sections", []):
        title = section.get("title", "")
        for item in section.get("items", []):
            ws.append([
                title,
                item.get("label", ""),
                str(item.get("value", "")),
                "Y" if item.get("warn") else "",
            ])


def _write_benchmark_raw_sheet(wb: openpyxl.Workbook, benchmark_raw: dict) -> None:
    if "Benchmark Raw" in wb.sheetnames:
        del wb["Benchmark Raw"]
    ws = wb.create_sheet("Benchmark Raw")

    ws.append(["Benchmark Raw Export"])
    ws.append(["exported_at", benchmark_raw.get("exported_at", "")])
    ws.append([])

    ws.append(["Settings"])
    ws.append(["key", "value"])
    for key, value in (benchmark_raw.get("settings") or {}).items():
        ws.append([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
    ws.append([])

    ws.append(["Domains"])
    ws.append(["bucket", "name", "id", "start", "end", "db"])
    domains = benchmark_raw.get("domains") or {}
    for bucket in ("active", "excluded"):
        for domain in domains.get(bucket, []):
            ws.append([
                bucket,
                domain.get("name", ""),
                domain.get("id", ""),
                domain.get("start", ""),
                domain.get("end", ""),
                domain.get("db", ""),
            ])
    ws.append([])

    ws.append(["Results"])
    ws.append([
        "strategy", "n_selected", "hit_rate", "mean_fitness", "unique_positions",
        "position_coverage", "domain_coverage", "structural_spread", "hits",
        "threshold", "n_trials",
    ])
    for strategy, metrics in (benchmark_raw.get("results") or {}).items():
        ws.append([
            strategy,
            metrics.get("n_selected", ""),
            metrics.get("hit_rate", ""),
            metrics.get("mean_fitness", ""),
            metrics.get("unique_positions", ""),
            metrics.get("position_coverage", ""),
            metrics.get("domain_coverage", ""),
            metrics.get("structural_spread", ""),
            metrics.get("hits", ""),
            metrics.get("threshold", ""),
            metrics.get("n_trials", ""),
        ])
    ws.append([])

    ws.append(["Landscape"])
    ws.append(["variant", "fitness"])
    for row in benchmark_raw.get("landscape", []):
        ws.append([row.get("variant", ""), row.get("fitness", "")])


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


def _manifest_path_for(output_path: Path) -> Path:
    """Return the sibling ``.run.json`` path for *output_path*.

    Examples:
        /out/primers.xlsx -> /out/primers.run.json
        /out/order.csv   -> /out/order.run.json
    """
    return output_path.parent / (output_path.stem + ".run.json")


def handle_get_plate_map(_params: dict) -> dict:  # noqa: ARG001
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
    started_at = datetime.now(timezone.utc)

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

    # Derive overlap_mode from the first result (all results in a run share the same mode).
    run_overlap_mode = results_for_export[0].overlap_mode if results_for_export else "partial"

    rescued_info = (
        [item.model_dump(exclude_none=True) for item in p.rescued_info]
        if p.rescued_info
        else None
    )

    export_plate_excel(
        mappings, resolved,
        rev_groups=rev_groups,
        results=results_for_export,
        overlap_mode=run_overlap_mode,
        rescued_info=rescued_info,
    )
    if p.project_id or p.report_data or p.benchmark_raw:
        wb = openpyxl.load_workbook(resolved)
        if p.report_data and isinstance(p.report_data, dict):
            _write_report_sheet(wb, p.report_data)
        if p.benchmark_raw and isinstance(p.benchmark_raw, dict):
            _write_benchmark_raw_sheet(wb, p.benchmark_raw)
        if "__kuma_meta__" in wb.sheetnames:
            del wb["__kuma_meta__"]
        meta = wb.create_sheet("__kuma_meta__")
        meta.sheet_state = "hidden"
        meta.append(["project_id", p.project_id or ""])
        meta.append(["kuma_version", p.kuma_version or KUMA_VERSION])
        meta.append(["kuro_module_version", KURO_MODULE_VERSION])
        meta.append(["exported_at", datetime.now(timezone.utc).isoformat()])
        meta.append(["overlap_mode", run_overlap_mode])
        wb.save(resolved)

    finished_at = datetime.now(timezone.utc)

    # Sanitise params for manifest: exclude large non-serialisable items.
    manifest_params = {
        k: v for k, v in params.items()
        if k not in ("mappings", "rescued_info", "report_data", "benchmark_raw")
    }
    manifest = build_run_manifest(
        method="export_excel",
        inputs={},
        params=manifest_params,
        started_at=started_at,
        finished_at=finished_at,
    )
    mpath = _manifest_path_for(resolved)
    write_run_manifest(mpath, manifest)
    cpath = write_output_checksum(resolved)

    result = FileExportResultModel(filepath=str(resolved)).to_rpc_dict()
    result["manifest_path"] = str(mpath)
    result["checksum_path"] = str(cpath)
    return result


def _order_payload_to_results(items):
    """Build the minimal result shape needed by order CSV exporters."""
    return [
        SimpleNamespace(
            mutation=SimpleNamespace(raw=item.mutation),
            forward_seq=item.forward_seq,
            reverse_seq=item.reverse_seq,
        )
        for item in items
    ]


def handle_export_order(params: dict) -> dict:
    """Export primer order CSV for IDT or Twist."""
    started_at = datetime.now(timezone.utc)

    p = ExportOrderParams(**params)
    resolved = _validate_output_path(p.filepath, allowed_extensions=_ALLOWED_CSV_EXTENSIONS)

    if p.results is not None:
        results = _order_payload_to_results(p.results)
    else:
        with _core._state_lock:
            if not _core._state.results:
                raise ValueError("No design available. Run design_sdm_primers first.")
            results = list(_core._state.results)

    encoding = "utf-8-sig" if p.bom else "utf-8"
    if p.format == "idt":
        export_idt_csv(results, resolved, encoding=encoding)  # pyright: ignore[reportArgumentType]
    else:
        export_twist_csv(results, resolved, encoding=encoding)  # pyright: ignore[reportArgumentType]

    finished_at = datetime.now(timezone.utc)

    manifest_params = {"filepath": params.get("filepath"), "format": p.format}
    manifest = build_run_manifest(
        method="export_order",
        inputs={},
        params=manifest_params,
        started_at=started_at,
        finished_at=finished_at,
    )
    mpath = _manifest_path_for(resolved)
    write_run_manifest(mpath, manifest)
    cpath = write_output_checksum(resolved)

    result = ExportOrderResultModel(
        filepath=str(resolved),
        format=p.format,
        primer_count=len(results) * 2,
    ).to_rpc_dict()
    result["manifest_path"] = str(mpath)
    result["checksum_path"] = str(cpath)
    return result


def handle_export_mapping(params: dict) -> dict:
    """Export liquid handler mapping file (Echo 525 or JANUS, CSV or XLSX)."""
    started_at = datetime.now(timezone.utc)

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

    encoding = "utf-8-sig" if p.bom else "utf-8"
    if p.format == "echo":
        vol = int(_resolve_mapping_transfer_volume(p.format, p.transfer_vol))
        if use_xlsx:
            export_echo_mapping_xlsx(fwd_mappings, rev_mappings, resolved,
                                     transfer_vol=vol, rev_groups=rev_groups)
        else:
            export_echo_mapping_csv(fwd_mappings, rev_mappings, resolved,
                                    transfer_vol=vol, rev_groups=rev_groups,
                                    encoding=encoding)
    else:
        vol = _resolve_mapping_transfer_volume(p.format, p.transfer_vol)
        if use_xlsx:
            export_janus_mapping_xlsx(fwd_mappings, rev_mappings, resolved,
                                      transfer_vol=vol, rev_groups=rev_groups)
        else:
            export_janus_mapping_csv(fwd_mappings, rev_mappings, resolved,
                                     transfer_vol=vol, rev_groups=rev_groups,
                                     encoding=encoding)

    finished_at = datetime.now(timezone.utc)

    primer_count = len(fwd_mappings) + len(rev_mappings)

    manifest_params = {
        "filepath": params.get("filepath"),
        "format": p.format,
        "transfer_vol": p.transfer_vol,
    }
    manifest = build_run_manifest(
        method="export_mapping",
        inputs={},
        params=manifest_params,
        started_at=started_at,
        finished_at=finished_at,
    )
    mpath = _manifest_path_for(resolved)
    write_run_manifest(mpath, manifest)
    cpath = write_output_checksum(resolved)

    result = ExportMappingResultModel(
        filepath=str(resolved),
        format=p.format,
        primer_count=primer_count,
    ).to_rpc_dict()
    result["manifest_path"] = str(mpath)
    result["checksum_path"] = str(cpath)
    return result


def handle_save_workspace(params: dict) -> dict:
    """Save workspace JSON to file."""
    p = SaveWorkspaceParams(**params)
    if not p.filepath or p.data is None:
        raise ValueError("filepath and data are required")
    resolved = _validate_output_path(p.filepath, allowed_extensions={".json"})
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(p.data, f, ensure_ascii=False, indent=2)
    return FileExportResultModel(filepath=str(resolved)).to_rpc_dict()


def handle_save_json(params: dict) -> dict:
    """Save generic JSON payload to file."""
    p = SaveJsonParams(**params)
    if not p.filepath or p.data is None:
        raise ValueError("filepath and data are required")
    resolved = _validate_output_path(p.filepath, allowed_extensions={".json"})
    with open(resolved, "w", encoding="utf-8") as f:
        json.dump(p.data, f, ensure_ascii=False, indent=2)
    return FileExportResultModel(filepath=str(resolved)).to_rpc_dict()


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
    return validated.to_rpc_dict(exclude_unset=True, round_trip=True)


def handle_export_benchmark_csv(params: dict) -> dict:
    """Export benchmark result table to CSV."""
    p = ExportBenchmarkCsvParams(**params)
    if not p.results:
        raise ValueError("Benchmark results are required")

    resolved = _validate_output_path(p.filepath, allowed_extensions=_ALLOWED_CSV_EXTENSIONS)
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
    encoding = "utf-8-sig" if p.bom else "utf-8"
    with open(resolved, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for strategy, metrics in p.results.items():
            writer.writerow({"strategy": strategy, **metrics})
    return FileExportResultModel(filepath=str(resolved)).to_rpc_dict()


# ---------------------------------------------------------------------------
# Export All + Macrogen (spec 2026-05-13)
# ---------------------------------------------------------------------------

from datetime import datetime as _dt

from kuma_core.kuro.plate_mapper import export_macrogen_xls
from sidecar_kuro.models import ExportAllParams, ExportMacrogenParams


def _split_fwd_rev(mappings: list[PlateMapping]) -> tuple[list[PlateMapping], list[PlateMapping]]:
    fwd = [m for m in mappings if m.primer_type == "forward"]
    rev = [m for m in mappings if m.primer_type == "reverse"]
    return fwd, rev


def handle_export_macrogen(params: dict) -> dict:
    """Export forward/reverse plate primers to Macrogen Plate Oligo .xls."""
    p = ExportMacrogenParams(**params)
    with _core._state_lock:
        mappings = list(_core._state.plate_mappings)

    fwd, rev = _split_fwd_rev(mappings)

    if fwd and not p.fwd_plate_name:
        raise ValueError("fwd_plate_name is required when forward primers exist")
    if rev and not p.rev_plate_name:
        raise ValueError("rev_plate_name is required when reverse primers exist")

    resolved = _validate_output_path(p.output_path, allowed_extensions={".xls"})
    export_macrogen_xls(
        fwd_primers=fwd,
        rev_primers=rev,
        fwd_plate_name=p.fwd_plate_name,
        rev_plate_name=p.rev_plate_name,
        amount=p.amount,
        purification=p.purification,
        output_path=str(resolved),
    )
    return {"ok": True, "path": str(resolved)}


def _export_primers_fasta(mappings: list[PlateMapping], output_path: Path) -> None:
    lines = []
    for m in mappings:
        lines.append(f">{m.primer_name}\n{m.sequence}\n")
    output_path.write_text("".join(lines), encoding="utf-8")


def _export_echo_for_all(
    fwd: list[PlateMapping],
    rev: list[PlateMapping],
    output_path: Path,
    transfer_vol: int,
    rev_groups: dict,
    bom: bool,
) -> None:
    export_echo_mapping_csv(
        fwd, rev, output_path,
        transfer_vol=transfer_vol,
        rev_groups=rev_groups,
        encoding="utf-8-sig" if bom else "utf-8",
    )


def _export_janus_for_all(
    fwd: list[PlateMapping],
    rev: list[PlateMapping],
    output_path: Path,
    transfer_vol: float,
    rev_groups: dict,
    bom: bool,
) -> None:
    export_janus_mapping_csv(
        fwd, rev, output_path,
        transfer_vol=transfer_vol,
        rev_groups=rev_groups,
        encoding="utf-8-sig" if bom else "utf-8",
    )


def _export_platemap_for_all(
    mappings: list[PlateMapping],
    results,
    rev_groups: dict,
    output_path: Path,
) -> None:
    export_plate_excel(
        mappings, output_path,
        rev_groups=rev_groups,
        results=results,
    )


def _export_run_json(
    mappings: list[PlateMapping],
    results,
    rev_groups: dict,
    output_path: Path,
) -> None:
    payload = {
        "exported_at": _dt.now().isoformat(),
        "mappings": [
            {
                "well": m.well,
                "primer_name": m.primer_name,
                "sequence": m.sequence,
                "primer_type": m.primer_type,
                "mutation": m.mutation,
            }
            for m in mappings
        ],
        "dedup_info": rev_groups,
        "result_count": len(results) if results else 0,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_echo_preview_rows(
    fwd: list[PlateMapping],
    rev: list[PlateMapping],
    transfer_vol: int,
    rev_groups: dict,
) -> list[dict]:
    """Build Echo mapping preview rows in-memory (no file I/O).

    Mirrors the row schema of ``export_echo_mapping_csv``.
    """
    from kuma_core.kuro.plate_mapper import (
        _build_rev_lookups,
        _parse_well_plate,
        _to_384_well_fwd,
        _to_384_well_rev,
        _split_echo_volume,
    )

    fwd_by_mut, rev_by_seq, mut_to_rev_seq = _build_rev_lookups(fwd, rev, rev_groups)

    rows: list[dict] = []
    for m in fwd:
        plate_idx, base_well = _parse_well_plate(m.well)
        src_plate = f"Source [{plate_idx + 1}]"
        dest_plate = f"Destination [{plate_idx + 1}]"
        src_well = _to_384_well_fwd(base_well)
        for vol in _split_echo_volume(transfer_vol):
            rows.append({
                "source_plate": src_plate,
                "source_well_name": m.primer_name,
                "source_well": src_well,
                "dest_plate": dest_plate,
                "dest_well_name": m.mutation,
                "dest_well": base_well,
                "transfer_vol": vol,
            })

    for fwd_m in fwd:
        rev_seq = mut_to_rev_seq.get(fwd_m.mutation)
        if rev_seq is None:
            continue
        rev_m = rev_by_seq.get(rev_seq)
        if rev_m is None:
            continue

        fwd_plate_idx, _ = _parse_well_plate(fwd_m.well)
        src_plate = f"Source [{fwd_plate_idx + 1}]"
        dest_plate = f"Destination [{fwd_plate_idx + 1}]"
        _, rev_base_well = _parse_well_plate(rev_m.well)
        src_well = _to_384_well_rev(rev_base_well)
        _, dest_well = _parse_well_plate(fwd_by_mut.get(fwd_m.mutation, fwd_m.well))

        for vol in _split_echo_volume(transfer_vol):
            rows.append({
                "source_plate": src_plate,
                "source_well_name": rev_m.primer_name,
                "source_well": src_well,
                "dest_plate": dest_plate,
                "dest_well_name": fwd_m.mutation,
                "dest_well": dest_well,
                "transfer_vol": vol,
            })
    return rows


def _build_janus_preview_rows(
    fwd: list[PlateMapping],
    rev: list[PlateMapping],
    transfer_vol: float,
    rev_groups: dict,
) -> list[dict]:
    """Build JANUS mapping preview rows in-memory (no file I/O)."""
    from kuma_core.kuro.plate_mapper import _build_rev_lookups

    fwd_by_mut, rev_by_seq, mut_to_rev_seq = _build_rev_lookups(fwd, rev, rev_groups)

    rows: list[dict] = []
    seq_no = 1

    for m in fwd:
        rows.append({
            "name": f"{m.mutation}-fw",
            "type": "primer",
            "dsp_rack_label": "Oligo 5pmol/ul",
            "no": seq_no,
            "asp_rack": 1,
            "asp_posi": m.well,
            "dsp_rack": 2,
            "dsp_posi": m.well,
            "volume": transfer_vol,
        })
        seq_no += 1

    for fwd_m in fwd:
        rev_seq = mut_to_rev_seq.get(fwd_m.mutation)
        if rev_seq is None:
            continue
        rev_m = rev_by_seq.get(rev_seq)
        if rev_m is None:
            continue
        dest_well = fwd_by_mut.get(fwd_m.mutation, fwd_m.well)
        rows.append({
            "name": f"{fwd_m.mutation}-rv",
            "type": "primer",
            "dsp_rack_label": "Oligo 5pmol/ul",
            "no": seq_no,
            "asp_rack": 2,
            "asp_posi": rev_m.well,
            "dsp_rack": 2,
            "dsp_posi": dest_well,
            "volume": transfer_vol,
        })
        seq_no += 1

    return rows


def handle_export_echo_mapping_dry_run(params: dict) -> dict:
    """Return Echo 525 mapping rows for preview without writing a file.

    Params:
        transfer_vol: optional override (nL, integer). Default 100.

    Returns:
        ``{"rows": [...], "total": N, "transfer_vol": int}``.
    """
    transfer_vol = params.get("transfer_vol")
    vol = _resolve_mapping_transfer_volume("echo", transfer_vol)
    with _core._state_lock:
        if not _core._state.results:
            return {"rows": [], "total": 0, "transfer_vol": int(vol)}
        mappings = list(_core._state.plate_mappings)
        rev_groups = dict(_core._state.dedup_info or {})
    fwd, rev = _split_fwd_rev(mappings)
    rows = _build_echo_preview_rows(fwd, rev, int(vol), rev_groups)
    return {"rows": rows, "total": len(rows), "transfer_vol": int(vol)}


def handle_export_janus_mapping_dry_run(params: dict) -> dict:
    """Return JANUS mapping rows for preview without writing a file.

    Params:
        transfer_vol: optional override (µL, float). Default 2.0.

    Returns:
        ``{"rows": [...], "total": N, "transfer_vol": float}``.
    """
    transfer_vol = params.get("transfer_vol")
    vol = _resolve_mapping_transfer_volume("janus", transfer_vol)
    with _core._state_lock:
        if not _core._state.results:
            return {"rows": [], "total": 0, "transfer_vol": float(vol)}
        mappings = list(_core._state.plate_mappings)
        rev_groups = dict(_core._state.dedup_info or {})
    fwd, rev = _split_fwd_rev(mappings)
    rows = _build_janus_preview_rows(fwd, rev, float(vol), rev_groups)
    return {"rows": rows, "total": len(rows), "transfer_vol": float(vol)}


def handle_export_all(params: dict) -> dict:
    """Run the 6-file batch export pipeline.

    Returns ``{"success": [filename, ...], "failed": [{path, reason}, ...], "output_dir": str}``.
    Individual exporter failures are recorded but do not raise.
    """
    p = ExportAllParams(**params)
    out_dir = Path(p.output_dir).expanduser().resolve()
    if not out_dir.is_absolute():
        raise ValueError(f"output_dir must be absolute: {p.output_dir}")
    if out_dir.exists() and not out_dir.is_dir():
        raise ValueError(f"output_dir exists but is not a directory: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    if p.mappings:
        mappings = _pydantic_to_plate_mappings(p.mappings)
        rev_groups = dict(p.dedup_info or {})
        # Filter backend results to only those present in frontend mappings
        # so capped designs (e.g. maxPrimers=95) export the capped set.
        mut_keys = {m.mutation for m in mappings}
        with _core._state_lock:
            results = [r for r in _core._state.results if r.mutation.raw in mut_keys]
    else:
        with _core._state_lock:
            mappings = list(_core._state.plate_mappings)
            results = list(_core._state.results)
            rev_groups = dict(_core._state.dedup_info or {})

    fwd, rev = _split_fwd_rev(mappings)

    now = _dt.now()
    if p.project_name:
        base_folder_name = f"{p.project_name}_{now.strftime('%Y%m%d')}"
    else:
        base_folder_name = f"kuro_{now.strftime('%y%m%d_%H%M')}"
    target_dir = out_dir / base_folder_name
    suffix = 1
    while target_dir.exists():
        suffix += 1
        target_dir = out_dir / f"{base_folder_name}_{suffix}"
    target_dir.mkdir(parents=True)

    ECHO_CSV = "echo.csv"
    ECHO_XLSX = "echo.xlsx"
    JANUS_CSV = "janus.csv"
    JANUS_XLSX = "janus.xlsx"
    MACROGEN = "macrogen.xls"
    PRIMERS_FASTA = "primers.fasta"
    PLATEMAP_XLSX = "platemap.xlsx"
    RUN_JSON = "run.json"

    success: list[str] = []
    failed: list[dict] = []

    def _try(name: str, fn) -> None:
        try:
            fn()
            success.append(name)
        except Exception as exc:  # noqa: BLE001 -- intentionally aggregating per-file
            failed.append({"path": name, "reason": str(exc)})

    _try(MACROGEN, lambda: export_macrogen_xls(
        fwd_primers=fwd,
        rev_primers=rev,
        fwd_plate_name=p.fwd_plate_name,
        rev_plate_name=p.rev_plate_name,
        amount=p.amount,
        purification=p.purification,
        output_path=str(target_dir / MACROGEN),
    ))

    _try(PRIMERS_FASTA, lambda: _export_primers_fasta(mappings, target_dir / PRIMERS_FASTA))

    _try(ECHO_CSV, lambda: _export_echo_for_all(
        fwd, rev, target_dir / ECHO_CSV,
        transfer_vol=int(p.echo_transfer_vol),
        rev_groups=rev_groups,
        bom=p.bom,
    ))

    _try(ECHO_XLSX, lambda: export_echo_mapping_xlsx(
        fwd, rev, target_dir / ECHO_XLSX,
        transfer_vol=int(p.echo_transfer_vol),
        rev_groups=rev_groups,
    ))

    _try(JANUS_CSV, lambda: _export_janus_for_all(
        fwd, rev, target_dir / JANUS_CSV,
        transfer_vol=float(p.janus_transfer_vol),
        rev_groups=rev_groups,
        bom=p.bom,
    ))

    _try(JANUS_XLSX, lambda: export_janus_mapping_xlsx(
        fwd, rev, target_dir / JANUS_XLSX,
        transfer_vol=float(p.janus_transfer_vol),
        rev_groups=rev_groups,
    ))

    _try(PLATEMAP_XLSX, lambda: _export_platemap_for_all(
        mappings, results, rev_groups, target_dir / PLATEMAP_XLSX,
    ))

    _try(RUN_JSON, lambda: _export_run_json(
        mappings, results, rev_groups, target_dir / RUN_JSON,
    ))

    return {
        "success": success,
        "failed": failed,
        "output_dir": str(target_dir),
    }
