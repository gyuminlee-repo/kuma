"""``analyze`` and ``validate_inputs`` JSON-RPC handlers.

Wraps ``mame.pipeline.run_analyze`` and exposes a lightweight validation
probe so the frontend can surface missing files / broken KURO xlsx before a
multi-minute analyze is kicked off.
"""

from __future__ import annotations

from typing import Any

from sidecar_mame.core import (
    _ALLOWED_EXCEL_EXTENSIONS,
    _ALLOWED_FASTA_EXTENSIONS,
    _progress,
    _validate_dirpath,
    _validate_filepath,
    _validate_output_path,
    set_last_analyze,
)


def _serialize_verdict(vr: Any) -> dict:
    t = vr.translated
    b = t.barcode
    return {
        "native_barcode": b.native_barcode,
        "custom_barcode": b.custom_barcode,
        "file_size_kb": b.file_size_kb,
        "read_count": b.read_count,  # None in Phase 1 / file-size proxy builds
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
        "is_fallback": bool(getattr(rr, "is_fallback", False)),
        "fallback_reason": getattr(rr, "fallback_reason", None),
    }


def _summarize(verdicts: list) -> dict:
    total = len(verdicts)
    pass_count = sum(1 for v in verdicts if v.verdict.value == "PASS")
    amb = sum(1 for v in verdicts if v.verdict.value == "AMBIGUOUS")
    fail = total - pass_count - amb
    return {
        "total": total,
        "pass_count": pass_count,
        "ambiguous_count": amb,
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

    if not input_dir:
        errors.append("input_dir is required")
    else:
        try:
            _validate_dirpath(input_dir)
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"input_dir: {exc}")

    if not reference:
        errors.append("reference is required")
    else:
        try:
            _validate_filepath(
                reference, allowed_extensions=_ALLOWED_FASTA_EXTENSIONS
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

    if cds_end is None:
        errors.append("cds_end is required")
    else:
        try:
            if int(cds_end) <= 0:
                errors.append("cds_end must be > 0")
        except (TypeError, ValueError):
            errors.append("cds_end must be an integer")

    return {"valid": not errors, "errors": errors}


def handle_analyze(params: dict) -> dict:
    """Run the full pipeline and cache the resulting artefacts for downstream RPCs."""
    # Lazy import: keeps the sidecar cold-start < 200 ms and lets the module
    # import during unit tests that stub mame.
    from kuma_core.mame.distribution import compute_distribution_stats
    from kuma_core.mame.ingest import IngestMode, route_ingest
    from kuma_core.mame.pipeline import run_analyze

    _progress(5, "Validating inputs...")

    input_dir = _validate_dirpath(params["input_dir"])
    reference = _validate_filepath(
        params["reference"], allowed_extensions=_ALLOWED_FASTA_EXTENSIONS
    )
    expected = _validate_filepath(
        params["expected"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )
    output = _validate_output_path(
        params["output"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )

    mode = str(params.get("mode", "amplicon"))
    ingest_mode_raw = str(params.get("ingest_mode", "barcode"))
    cds_start = int(params.get("cds_start", 0))
    cds_end = int(params["cds_end"])
    min_file_size_kb = float(params.get("min_file_size_kb", 50.0))
    many_cutoff = int(params.get("many_cutoff", 5))

    _progress(10, "Ingesting FASTA files...")

    # ── Distribution analysis (A4) ───────────────────────────────────────
    # Compute before the main pipeline so the frontend gets stats even if
    # the pipeline raises later.
    ingest_mode_enum = IngestMode(ingest_mode_raw)
    raw_records = route_ingest(input_dir, ingest_mode_enum)
    dist_stats = compute_distribution_stats(
        [rec.file_size_kb for rec in raw_records]
    )

    _progress(30, "Translating sequences...")
    _progress(60, "Classifying verdicts...")

    verdicts, replicates = run_analyze(
        input_dir=input_dir,
        reference_path=reference,
        expected_path=expected,
        output_path=output,
        cds_start=cds_start,
        cds_end=cds_end,
        mode=mode,
        min_file_size_kb=min_file_size_kb,
        many_cutoff=many_cutoff,
        ingest_mode=ingest_mode_enum,
    )

    _progress(85, "Selecting best replicates...")
    _progress(100, "Writing Excel output...")

    # A11: discover MinKNOW run metadata once at analyze time and cache it.
    # Imported lazily to avoid cold-start overhead.
    from kuma_core.mame.ingest.run_meta import discover_run_meta

    run_meta = discover_run_meta(input_dir)

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
    }


__all__ = [
    "handle_analyze",
    "handle_validate_inputs",
    "_serialize_verdict",
    "_serialize_replicate",
]
