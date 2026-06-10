"""``analyze`` and ``validate_inputs`` JSON-RPC handlers.

Wraps ``mame.pipeline.run_analyze`` and exposes a lightweight validation
probe so the frontend can surface missing files / broken KURO xlsx before a
multi-minute analyze is kicked off.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path
from typing import Any

from sidecar_mame.core import (
    _ALLOWED_EXCEL_EXTENSIONS,
    _ALLOWED_FASTA_EXTENSIONS,
    _ALLOWED_SEQUENCE_EXTENSIONS,
    _progress,
    _send,
    _validate_dirpath,
    _validate_filepath,
    _validate_output_path,
    set_last_analyze,
)

# Keep-alive heartbeat interval for the analyze stage. Re-emits the latest
# progress state during otherwise-silent stretches (FASTA ingest, the
# per-record loop between updates, and the Excel write) so the frontend idle
# watchdog does not fire. Must stay well under the frontend
# DEADLOCK_THRESHOLD_MS (300 s). Mirrors combinatorial_demux.py.
_HEARTBEAT_INTERVAL_S: float = 30.0

# Serialises concurrent stdout writes from the heartbeat thread + main thread
# when building the multi-field progress params dict.
_emit_lock = threading.Lock()


def _read_fasta_sequence(path: Path) -> str:
    """Return concatenated sequence content from a FASTA file."""
    seq_parts: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith(">"):
                continue
            seq_parts.append(line)
    return "".join(seq_parts).upper()


def _read_reference_sequence(path: Path) -> str:
    """Return sequence content from FASTA, GenBank, or SnapGene input."""
    if path.suffix.lower() in _ALLOWED_FASTA_EXTENSIONS:
        sequence = _read_fasta_sequence(path)
    else:
        from kuma_core.kuro.sdm_engine import load_sequence

        _header, sequence, _genes = load_sequence(path)
        sequence = sequence.upper()
    if not sequence:
        raise ValueError(f"Reference sequence contains no sequence data: {path}")
    return sequence


def _read_reference_length(path: Path) -> int:
    """Return total sequence length from a supported reference sequence file."""
    return len(_read_reference_sequence(path))


def _resolve_cds_end(raw_cds_end: Any, reference_path: Path) -> int:
    """Use explicit CDS end when positive; otherwise default to full reference."""
    if raw_cds_end is None:
        return _read_reference_length(reference_path)
    try:
        cds_end = int(raw_cds_end)
    except (TypeError, ValueError):
        raise ValueError("cds_end must be an integer") from None
    if cds_end <= 0:
        return _read_reference_length(reference_path)
    return cds_end


def _write_reference_fasta(reference_path: Path, output_dir: Path) -> Path:
    """Materialize non-FASTA sequence input as FASTA for the pipeline."""
    if reference_path.suffix.lower() in _ALLOWED_FASTA_EXTENSIONS:
        return reference_path

    sequence = _read_reference_sequence(reference_path)
    fasta_path = output_dir / f"{reference_path.stem or 'reference'}.reference.fa"
    with fasta_path.open("w", encoding="utf-8") as fh:
        fh.write(f">{reference_path.stem or 'reference'}\n")
        for i in range(0, len(sequence), 80):
            fh.write(sequence[i:i + 80] + "\n")
    return fasta_path


def _serialize_verdict(vr: Any) -> dict:
    t = vr.translated
    b = t.barcode
    return {
        "native_barcode": b.native_barcode,
        "custom_barcode": b.custom_barcode,
        "file_size_kb": b.file_size_kb,
        "read_count": b.read_count,
        "n_mixed_positions": b.n_mixed_positions,
        "max_minor_allele_fraction": b.max_minor_allele_fraction,
        "n_low_depth_positions": b.n_low_depth_positions,
        "consensus_n_fraction": b.consensus_n_fraction,
        "n_low_quality_bases": b.n_low_quality_bases,
        "n_input_reads": b.n_input_reads,
        "n_aligned_reads": b.n_aligned_reads,
        "n_mapq_failed": b.n_mapq_failed,
        "n_span_failed": b.n_span_failed,
        "source_path": str(b.source_path),
        "aa_sequence": t.aa_sequence,
        "observed_nt_changes": list(t.observed_nt_changes),
        "observed_aa_changes": list(t.observed_aa_changes),
        "expected_mutations": list(vr.expected_mutations),
        "verdict": vr.verdict.value,
        "verdict_notes": vr.verdict_notes,
    }


def _serialize_replicate(rr: Any) -> dict:
    return {
        "mutant_id": rr.mutant_id,
        "selected_plate": rr.selected_plate,
        "selection_reason": rr.selection_reason,
        "failed": bool(rr.failed),
        "plate_keys": list(rr.plate_verdicts.keys()),
        # Full nested verdict per plate so that load_analyze_result can rebuild
        # a lossless ReplicateResult (get_plate_data / export_excel read
        # plate_verdicts[selected_plate].translated.barcode.custom_barcode).
        "plate_verdicts": {
            plate: _serialize_verdict(vr)
            for plate, vr in rr.plate_verdicts.items()
        },
        "is_fallback": bool(getattr(rr, "is_fallback", False)),
        "fallback_reason": getattr(rr, "fallback_reason", None),
    }


def _deserialize_verdict(d: dict) -> Any:
    """Inverse of ``_serialize_verdict``: rebuild a ``VerdictRecord`` dataclass.

    Kept adjacent to ``_serialize_verdict`` so the two stay in lockstep.
    """
    from kuma_core.mame.models import (
        BarcodeRecord,
        TranslatedRecord,
        VerdictClass,
        VerdictRecord,
    )

    barcode = BarcodeRecord(
        native_barcode=d["native_barcode"],
        custom_barcode=d["custom_barcode"],
        consensus_seq="",  # not serialized; not read by downstream consumers
        file_size_kb=float(d.get("file_size_kb", 0.0)),
        source_path=Path(d.get("source_path", "")),
        read_count=d.get("read_count"),
        n_mixed_positions=int(d.get("n_mixed_positions", 0)),
        max_minor_allele_fraction=float(d.get("max_minor_allele_fraction", 0.0)),
        n_low_depth_positions=int(d.get("n_low_depth_positions", 0)),
        consensus_n_fraction=float(d.get("consensus_n_fraction", 0.0)),
        n_low_quality_bases=int(d.get("n_low_quality_bases", 0)),
        n_input_reads=d.get("n_input_reads"),
        n_aligned_reads=d.get("n_aligned_reads"),
        n_mapq_failed=int(d.get("n_mapq_failed", 0)),
        n_span_failed=int(d.get("n_span_failed", 0)),
    )
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence=d.get("aa_sequence", ""),
        observed_nt_changes=list(d.get("observed_nt_changes", [])),
        observed_aa_changes=list(d.get("observed_aa_changes", [])),
    )
    return VerdictRecord(
        translated=translated,
        expected_mutations=list(d.get("expected_mutations", [])),
        verdict=VerdictClass(d["verdict"]),
        verdict_notes=d.get("verdict_notes", ""),
    )


def _deserialize_replicate(d: dict) -> Any:
    """Inverse of ``_serialize_replicate``: rebuild a ``ReplicateResult``."""
    from kuma_core.mame.models import ReplicateResult

    plate_verdicts = {
        plate: _deserialize_verdict(vr)
        for plate, vr in (d.get("plate_verdicts") or {}).items()
    }
    return ReplicateResult(
        mutant_id=d["mutant_id"],
        plate_verdicts=plate_verdicts,
        selected_plate=d.get("selected_plate"),
        selection_reason=d.get("selection_reason", ""),
        failed=bool(d.get("failed", False)),
        is_fallback=bool(d.get("is_fallback", False)),
        fallback_reason=d.get("fallback_reason"),
    )


def _summarize(verdicts: list) -> dict:
    total = len(verdicts)
    pass_count = sum(1 for v in verdicts if v.verdict.value == "PASS")
    amb = sum(1 for v in verdicts if v.verdict.value == "AMBIGUOUS")
    mixed = sum(1 for v in verdicts if v.verdict.value == "MIXED")
    fail = total - pass_count - amb
    return {
        "total": total,
        "pass_count": pass_count,
        "ambiguous_count": amb,
        "mixed_count": mixed,
        "fail_count": fail,
    }


def handle_validate_inputs(params: dict) -> dict:
    """Check that all required paths exist and the KURO xlsx has the required sheet.

    Always returns a 200 response with ``valid`` + ``errors``; callers surface
    the list directly to the user. Does *not* raise on individual validation
    failures — only on programmer errors (missing param key).
    """
    errors: list[str] = []

    input_dir = params.get("input_dir")
    reference = params.get("reference")
    expected = params.get("expected")
    cds_end = params.get("cds_end")
    reference_path = None

    if not input_dir:
        errors.append("input_dir is required")
    else:
        try:
            input_path = _validate_dirpath(input_dir)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"input_dir: {exc}")
        else:
            # Raw-run guardrails: catch the two most common misselections before
            # a multi-minute demux is kicked off.
            from kuma_core.mame.ingest import is_minknow_run_dir

            custom_barcodes_xlsx = params.get("custom_barcodes_xlsx")
            if input_path.name == "fastq_pass":
                errors.append(
                    "Select the MinKNOW run folder (the parent of fastq_pass/), "
                    "not fastq_pass/ itself."
                )
            elif is_minknow_run_dir(input_path) and not custom_barcodes_xlsx:
                errors.append(
                    "custom_barcodes_xlsx is required when input_dir is a raw "
                    "MinKNOW run folder"
                )
            if custom_barcodes_xlsx:
                try:
                    _validate_filepath(
                        custom_barcodes_xlsx,
                        allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS,
                    )
                except (FileNotFoundError, ValueError) as exc:
                    errors.append(f"custom_barcodes_xlsx: {exc}")

    if not reference:
        errors.append("reference is required")
    else:
        try:
            reference_path = _validate_filepath(
                reference, allowed_extensions=_ALLOWED_SEQUENCE_EXTENSIONS
            )
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"reference: {exc}")

    if not expected:
        errors.append("expected is required")
    else:
        try:
            expected_path = _validate_filepath(
                expected, allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
            )
            # Sheet-level probe: load workbook read-only and assert the sheet exists.
            import openpyxl  # local import keeps cold-start fast

            wb = openpyxl.load_workbook(expected_path, read_only=True, data_only=True)
            try:
                if "expected_mutations" not in wb.sheetnames:
                    errors.append(
                        "expected: missing required 'expected_mutations' sheet"
                    )
            finally:
                wb.close()
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"expected: {exc}")
        except Exception as exc:  # noqa: BLE001 — openpyxl surface is broad
            errors.append(f"expected: failed to open xlsx ({exc})")

    if reference_path is not None:
        try:
            _resolve_cds_end(cds_end, reference_path)
        except ValueError as exc:
            errors.append(str(exc))

    return {"valid": not errors, "errors": errors}


def handle_analyze(params: dict) -> dict:
    """Run the full pipeline and cache the resulting artefacts for downstream RPCs."""
    # Lazy import: keeps the sidecar cold-start < 200 ms and lets the module
    # import during unit tests that stub mame.
    from kuma_core.mame.distribution import compute_distribution_stats
    from kuma_core.mame.ingest import (
        IngestMode,
        ingest_run_folder,
        is_minknow_run_dir,
        route_ingest,
    )
    from kuma_core.mame.pipeline import run_analyze

    input_dir = _validate_dirpath(params["input_dir"])
    # Preserve the caller-supplied directory: in raw-run mode ``input_dir`` is
    # rebound to the demux output dir for the analyze body, but run-metadata
    # discovery must still see the original MinKNOW run folder.
    original_run_dir = input_dir
    reference = _validate_filepath(
        params["reference"], allowed_extensions=_ALLOWED_SEQUENCE_EXTENSIONS
    )
    expected = _validate_filepath(
        params["expected"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )
    output = _validate_output_path(
        params["output"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )

    # Raw-run gate: a MinKNOW run folder (has ``fastq_pass/``) needs demux first;
    # a pre-demuxed consensus dir takes the legacy path untouched.
    is_raw = is_minknow_run_dir(input_dir)

    def _emit(
        value: int,
        message: str,
        current: int | None = None,
        total: int | None = None,
        stage: str | None = None,
    ) -> None:
        """Single progress emitter for the whole analyze flow.

        Consensus-dir (non-raw) mode emits the legacy ``{value, message,
        current?, total?}`` shape with NO ``stage`` key — byte-identical to the
        pre-raw-run handler. Raw-run mode reserves 0..50 for demux and rescales
        these analyze-phase values into 50..100 and stamps a ``stage`` key.
        """
        if is_raw:
            value = min(100, 50 + value // 2)
        emit_params: dict = {"value": value, "message": message}
        if current is not None:
            emit_params["current"] = current
        if total is not None:
            emit_params["total"] = total
        if is_raw:
            emit_params["stage"] = stage or "analyze"
        with _emit_lock:
            _send(
                {"jsonrpc": "2.0", "method": "progress", "params": emit_params}
            )

    def _emit_demux(done: int, total: int, stage_str: str) -> None:
        """Pre-analyze (demux + consensus) emitter, mapped into the 0..50 band.

        The core demux runs two restarting sub-phases — read demux (``done`` of
        the demux total) then per-well consensus (``done`` of the well total) —
        each starting back at 0. Mapping both flat into 0..50 would step the bar
        backward at the handoff, so the demux sub-phase fills 0..40 and the
        consensus sub-phase fills 40..50, keeping the whole pre-analyze phase
        monotonic. Per-native-barcode mode reports a single completion count and
        spans the full 0..50. Always stamped ``stage='demux'`` (the frontend
        treats the entire pre-analyze stretch as one phase). Bypasses ``_emit``'s
        analyze rescale. Only invoked in raw-run mode.
        """
        if stage_str == "consensus":
            value = 40 + int(10 * done / max(1, total))
            message = f"Building consensus ({done}/{total})"
        elif stage_str == "demux":
            value = int(40 * done / max(1, total))
            message = f"Demuxing reads ({done}/{total})"
        else:
            value = int(50 * done / max(1, total))
            message = f"Demuxing {stage_str} ({done}/{total})"
        emit_params = {
            "value": min(50, value),
            "message": message,
            "current": done,
            "total": total,
            "stage": "demux",
        }
        with _emit_lock:
            _send(
                {"jsonrpc": "2.0", "method": "progress", "params": emit_params}
            )

    if is_raw:
        # Validate the raw-run demux subset (raises a clear ValidationError when
        # custom_barcodes_xlsx is missing) and run demux into a STABLE dir so a
        # re-run can resume rather than re-demuxing into a throwaway tmp dir.
        from sidecar_mame.models import AnalyzeRawRunParams

        raw_mapq_threshold = int(params.get("mapq_threshold", 25))
        raw_coverage_fraction = float(params.get("coverage_fraction", 0.98))
        raw_edit_dist_ratio = float(params.get("edit_dist_ratio", 0.25))
        raw_chimera_split = bool(params.get("chimera_split", True))
        raw_trim_flank_bp = int(params.get("trim_flank_bp", 30))
        raw_custom_barcodes_xlsx = params.get("custom_barcodes_xlsx")
        raw_native_barcodes = params.get("native_barcodes")

        AnalyzeRawRunParams.model_validate(
            {
                "minknow_run_dir": str(input_dir),
                "custom_barcodes_xlsx": raw_custom_barcodes_xlsx,
                "reference_fasta": str(reference),
                "demux_output_dir": params.get("demux_output_dir"),
                "native_barcodes": raw_native_barcodes,
                "mapq_threshold": raw_mapq_threshold,
                "coverage_fraction": raw_coverage_fraction,
                "edit_dist_ratio": raw_edit_dist_ratio,
                "chimera_split": raw_chimera_split,
                "trim_flank_bp": raw_trim_flank_bp,
            }
        )

        demux_output_dir = (
            Path(params["demux_output_dir"])
            if params.get("demux_output_dir")
            else output.parent / "demux_filtered"
        )
        ingest_run_folder(
            run_dir=original_run_dir,
            custom_barcodes_xlsx=Path(raw_custom_barcodes_xlsx),
            reference_fasta=reference,
            demux_output_dir=demux_output_dir,
            native_barcodes=raw_native_barcodes,
            mapq_threshold=raw_mapq_threshold,
            coverage_fraction=raw_coverage_fraction,
            trim_flank_bp=raw_trim_flank_bp,
            edit_dist_ratio=raw_edit_dist_ratio,
            chimera_split=raw_chimera_split,
            progress_callback=lambda done, total, stage_str: _emit_demux(
                done, total, stage_str
            ),
        )
        # The demux output is a barcode-mode consensus tree; the analyze body
        # ingests it exactly like a pre-demuxed consensus dir.
        input_dir = demux_output_dir

    _emit(5, "Validating inputs...")

    mode = str(params.get("mode", "amplicon"))
    ingest_mode_raw = str(params.get("ingest_mode", "barcode"))
    cds_start = int(params.get("cds_start", 0))
    cds_end = _resolve_cds_end(params.get("cds_end"), reference)
    min_file_size_kb = float(params.get("min_file_size_kb", 50.0))
    # Default to 30 when the caller omits the field entirely; an explicit None
    # or "" disables the read-depth gate (legacy file-size fallback).
    if "min_read_count" not in params:
        min_read_count: int | None = 30
    else:
        min_read_count_raw = params.get("min_read_count")
        min_read_count = (
            None if min_read_count_raw in (None, "") else int(min_read_count_raw)
        )
    max_consensus_n_fraction_raw = params.get("max_consensus_n_fraction", 0.0)
    max_consensus_n_fraction = (
        None
        if max_consensus_n_fraction_raw in (None, "")
        else float(max_consensus_n_fraction_raw)
    )
    many_cutoff = int(params.get("many_cutoff", 5))

    sample_map_raw = params.get("sample_map_xlsx")
    sample_map_path = None
    if sample_map_raw:
        sample_map_path = _validate_filepath(sample_map_raw, allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS)

    # well_layout: optional well_id -> sample_name override (highest-priority
    # well->sample source; takes precedence over sample_map_path in run_analyze).
    # Fail-fast on a malformed payload rather than silently ignoring it.
    well_layout_raw = params.get("well_layout")
    well_layout: dict[str, str] | None = None
    if well_layout_raw is not None:
        if not isinstance(well_layout_raw, dict) or not all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in well_layout_raw.items()
        ):
            raise ValueError("well_layout must be a mapping of well_id (str) to sample_name (str)")
        well_layout = well_layout_raw

    _emit(10, "Ingesting FASTA files...")

    # Latest progress state, re-emitted by the heartbeat thread during silent
    # stretches. Initialised at the current phase (ingest, value 10) and synced
    # to each milestone below so the heartbeat always re-emits the phase that is
    # actually in flight, never a value ahead of reality (which would make the
    # bar step backward when the next milestone fires).
    _holder: dict[str, Any] = {
        "value": 10,
        "message": "Ingesting FASTA files...",
        "current": None,
        "total": None,
    }
    _stop = threading.Event()

    def _heartbeat() -> None:
        # References the module-global interval so tests can shrink it.
        while not _stop.wait(_HEARTBEAT_INTERVAL_S):
            _emit(
                _holder["value"],
                _holder["message"],
                current=_holder["current"],
                total=_holder["total"],
            )

    def _band_callback(i: int, total: int) -> None:
        # Map per-record progress into the 60..85 band so the frontend ETA
        # advances instead of freezing at 60 %. Throttle to ~1 % steps (or
        # every record when there are few) to avoid a stdout flood.
        value = 60 + int(25 * i / total) if total else 60
        step = max(1, total // 25) if total else 1
        _holder["value"] = value
        _holder["message"] = f"Classifying verdicts... ({i}/{total})"
        _holder["current"] = i
        _holder["total"] = total
        if i == total or i % step == 0:
            _emit(
                value,
                f"Classifying verdicts... ({i}/{total})",
                current=i,
                total=total,
            )

    _hb_thread = threading.Thread(
        target=_heartbeat, daemon=True, name="analyze-heartbeat"
    )
    _hb_thread.start()
    try:
        # ── Distribution analysis (A4) ───────────────────────────────────
        # Compute before the main pipeline so the frontend gets stats even if
        # the pipeline raises later. This ingest is silent I/O; the heartbeat
        # (already running) covers it.
        ingest_mode_enum = IngestMode(ingest_mode_raw)
        raw_records = route_ingest(input_dir, ingest_mode_enum)
        dist_stats = compute_distribution_stats(
            [rec.file_size_kb for rec in raw_records]
        )

        _emit(30, "Translating sequences...")
        _holder["value"] = 30
        _holder["message"] = "Translating sequences..."
        _emit(60, "Classifying verdicts...")
        _holder["value"] = 60
        _holder["message"] = "Classifying verdicts..."

        with tempfile.TemporaryDirectory(prefix="mame-reference-") as tmpdir:
            reference_for_pipeline = _write_reference_fasta(reference, Path(tmpdir))
            verdicts, replicates = run_analyze(
                input_dir=input_dir,
                reference_path=reference_for_pipeline,
                expected_path=expected,
                output_path=output,
                cds_start=cds_start,
                cds_end=cds_end,
                mode=mode,
                min_file_size_kb=min_file_size_kb,
                min_read_count=min_read_count,
                max_consensus_n_fraction=max_consensus_n_fraction,
                many_cutoff=many_cutoff,
                ingest_mode=ingest_mode_enum,
                sample_map_path=sample_map_path,
                well_layout=well_layout,
                progress_callback=_band_callback,
            )
    finally:
        # Stop and join the heartbeat BEFORE the terminal milestones so a stale
        # holder emit cannot race the 85/100 updates.
        _stop.set()
        _hb_thread.join(timeout=_HEARTBEAT_INTERVAL_S + 1.0)

    _emit(85, "Selecting best replicates...")
    _emit(100, "Writing Excel output...")

    # A11: discover MinKNOW run metadata once at analyze time and cache it.
    # Imported lazily to avoid cold-start overhead.
    from kuma_core.mame.ingest.run_meta import discover_run_meta

    run_meta = discover_run_meta(original_run_dir if is_raw else input_dir)

    set_last_analyze(verdicts, replicates, str(output), run_meta=run_meta)

    return {
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "output_path": str(output),
        "summary": _summarize(verdicts),
        "distribution_stats": {
            "n_files": dist_stats.n_files,
            "file_size_kb": dist_stats.file_size_kb,
            "suggested_cutoff_kb": dist_stats.suggested_cutoff_kb,
            "suggested_method": dist_stats.suggested_method,
            "bimodal": dist_stats.bimodal,
        },
        # Raw-run only: surface demux yield derived from the consensus records
        # ingested out of the demux output dir (``raw_records`` above). Absent
        # in consensus-dir mode so that response shape stays byte-identical.
        **(
            {
                "assigned_reads": int(
                    sum(int(getattr(r, "read_count", 0) or 0) for r in raw_records)
                ),
                "wells_with_reads": len(raw_records),
            }
            if is_raw
            else {}
        ),
    }


__all__ = [
    "handle_analyze",
    "handle_validate_inputs",
    "_serialize_verdict",
    "_serialize_replicate",
    "_deserialize_verdict",
    "_deserialize_replicate",
]
