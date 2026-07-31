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


def _parse_positive_int(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid {label} {value!r}. Expected a positive integer.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
    else:
        raise ValueError(f"Invalid {label} {value!r}. Expected a positive integer.")
    if parsed < 1:
        raise ValueError(f"Invalid {label} {value!r}. Expected a positive integer.")
    return parsed


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


def _janus_settings_from_params(params: dict):
    """Build the one ``JanusSettings`` both Janus handlers resolve behaviour from.

    Shared by ``export_janus_mapping`` and ``export_janus_mapping_dry_run`` so
    the plate the operator approves in the preview is the plate the exported
    file describes.

    Accepted params (all optional; ``None`` falls back to the default):
        dest_layout (str): "compact" (default) or "source".
        include_verdicts (list[str]): verdict classes to keep. Default ["PASS"].
        include_fallback (bool): keep fallback picks. Default false.
        output_schema (str): "device9" (default, instrument-native 9 columns) or
            "legacy5" (kuma-internal 5 columns).
        volume (number): dispense volume in µL (device9 only).
        sample_type (str): ``type`` column value (device9 only).
        liquid_class (str): liquid/labware class string (device9 only, required).
        source_racks (dict[str, int]): plate label -> Asp. Rack number.
        dest_rack (int): Dsp. Rack number.

    Raises ``ValueError`` on any invalid value.
    """
    from kuma_core.mame.export.janus_mapping import (
        DEFAULT_DEST_RACK,
        DEFAULT_LIQUID_CLASS,
        DEFAULT_SAMPLE_TYPE,
        DEFAULT_SOURCE_RACKS,
        DEFAULT_VOLUME_UL,
        DEST_LAYOUT_COMPACT,
        SCHEMA_DEVICE9,
        JanusSettings,
        normalize_include_verdicts,
    )

    # `or` (not a get default) so an explicit JSON null also falls back.
    dest_layout = str(params.get("dest_layout") or DEST_LAYOUT_COMPACT).lower()
    output_schema = str(params.get("output_schema") or SCHEMA_DEVICE9).lower()
    include_verdicts = normalize_include_verdicts(params.get("include_verdicts"))
    include_fallback = bool(params.get("include_fallback") or False)

    raw_volume = params.get("volume")
    if raw_volume is None:
        volume = DEFAULT_VOLUME_UL
    else:
        try:
            volume = float(raw_volume)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid volume {raw_volume!r}. Expected a positive number of µL."
            ) from exc

    sample_type = str(params.get("sample_type") or DEFAULT_SAMPLE_TYPE)
    liquid_class = str(
        params.get("liquid_class")
        if params.get("liquid_class") is not None
        else DEFAULT_LIQUID_CLASS
    )

    raw_racks = params.get("source_racks")
    if raw_racks is None:
        source_racks = tuple(DEFAULT_SOURCE_RACKS.items())
    else:
        if not isinstance(raw_racks, dict):
            raise ValueError(
                "source_racks must be an object mapping plate label to rack number."
            )
        pairs: list[tuple[str, int]] = []
        for label, rack in raw_racks.items():
            try:
                pairs.append(
                    (str(label), _parse_positive_int(rack, f"rack number for source plate {label!r}"))
                )
            except ValueError as exc:
                raise ValueError(
                    f"Invalid rack number {rack!r} for source plate {label!r}. "
                    "Expected a positive integer."
                ) from exc
        source_racks = tuple(pairs)

    raw_dest_rack = params.get("dest_rack")
    if raw_dest_rack is None:
        dest_rack = DEFAULT_DEST_RACK
    else:
        try:
            dest_rack = _parse_positive_int(raw_dest_rack, "dest_rack")
        except ValueError as exc:
            raise ValueError(
                f"Invalid dest_rack {raw_dest_rack!r}. Expected a positive integer."
            ) from exc

    # JanusSettings.__post_init__ validates dest_layout, output_schema, volume.
    return JanusSettings(
        dest_layout=dest_layout,
        include_verdicts=include_verdicts,
        include_fallback=include_fallback,
        output_schema=output_schema,
        volume=volume,
        sample_type=sample_type,
        liquid_class=liquid_class,
        source_racks=source_racks,
        dest_rack=dest_rack,
    )


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
        plus every selection and instrument param of ``_janus_settings_from_params``.

    Returns the written path alongside ``excluded`` (clones left out, with the
    reason) so a retry plan can be built from the same call. The excluded list
    comes from a preview run with the *same* settings object, which is why the
    core export functions still return only a path.

    Raises ``RuntimeError`` if no analyze has been run in this session.
    Raises ``ValueError`` on an invalid argument, or when the core rejects the
    row set (unresolved well, >96 picks, duplicate dest_well, missing liquid
    class, unmapped source rack).

    Phase 1 note: priority_score column carries file_size_kb as a volume proxy.
    G6/A6 round will replace with actual read_count once fasta_parser exposes
    per-record counts.
    """
    from kuma_core.mame.export import export_mame_janus_csv, export_mame_janus_xlsx
    from kuma_core.mame.export.janus_mapping import build_janus_preview_rows

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

    settings = _janus_settings_from_params(params)

    # G3: pass cached run meta to embed in the Janus output.
    run_meta = state.last_run_meta  # NgsRunMeta | None

    if fmt == "xlsx":
        export_mame_janus_xlsx(
            state.last_replicates,
            output,
            ngs_run_meta=run_meta,  # type: ignore[arg-type]
            kuma_version=KUMA_VERSION,
            settings=settings,
        )
    else:
        export_mame_janus_csv(
            state.last_replicates,
            output,
            ngs_run_meta=run_meta,  # type: ignore[arg-type]
            settings=settings,
        )

    # Same settings object as the export above, so the exclusion list describes
    # exactly the file that was just written.
    preview = build_janus_preview_rows(state.last_replicates, settings=settings)

    return {
        "output_path": str(output),
        "format": fmt,
        "row_count": preview["row_count"],
        "excluded": preview["excluded"],
        "excluded_count": preview["excluded_count"],
        "settings": preview["settings"],
    }


def handle_export_janus_mapping_dry_run(params: dict) -> dict:
    """Return Janus mapping rows for preview without writing a file.

    Same prerequisite as ``export_janus_mapping`` (a prior ``analyze``), but no
    output path: nothing is written. Validation problems come back inside the
    payload instead of raising, so the dialog can show every problem before the
    user commits to a file. The export path keeps its fail-fast behaviour.

    Params: every selection and instrument param of
    ``_janus_settings_from_params`` (no ``output``: nothing is written).

    Returns ``{"rows", "errors", "row_count", "excluded", "excluded_count",
    "settings"}``. Each error is ``{"code", "message", "mutant_ids"}`` with code
    one of ``unresolved_well``, ``plate_capacity``, ``duplicate_dest_well``,
    ``missing_liquid_class``, ``unknown_source_rack``. Each excluded entry is
    ``{"mutant_id", "reason", "verdict", "selected_plate", "is_fallback"}``.

    Raises ``RuntimeError`` if no analyze has been run in this session, and
    ``ValueError`` on an invalid setting.
    """
    from kuma_core.mame.export.janus_mapping import build_janus_preview_rows

    state = get_state()
    if state.last_replicates is None:
        raise RuntimeError(
            "No prior analyze result. Run 'analyze' before "
            "'export_janus_mapping_dry_run'."
        )

    settings = _janus_settings_from_params(params)
    return build_janus_preview_rows(state.last_replicates, settings=settings)


__all__ = [
    "handle_export_excel",
    "handle_get_plate_data",
    "handle_export_janus_mapping",
    "handle_export_janus_mapping_dry_run",
]
