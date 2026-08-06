"""``analyze`` and ``validate_inputs`` JSON-RPC handlers.

Wraps ``mame.pipeline.run_analyze`` and exposes a lightweight validation
probe so the frontend can surface missing files / broken KURO xlsx before a
multi-minute analyze is kicked off.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sidecar_mame.core import (
    _ALLOWED_EXCEL_EXTENSIONS,
    _ALLOWED_FASTA_EXTENSIONS,
    _ALLOWED_SEQUENCE_EXTENSIONS,
    _send,
    _validate_dirpath,
    _validate_filepath,
    _validate_output_path,
    set_last_analyze,
)

if TYPE_CHECKING:
    from kuma_core.mame.ingest.amplicon_reference import AmpliconReferenceResolution

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


def resolve_amplicon_cds(
    resolution: AmpliconReferenceResolution,
    original_cds_start: int,
    original_cds_end: int,
) -> tuple[int, int]:
    """CDS bounds to use once the reference has been cut down to the amplicon.

    The annotation is import-time free (``TYPE_CHECKING`` plus postponed
    evaluation), so the module keeps its lazy import of the ingest package.

    Four cases, in order:

    1. No span. ``resolve_amplicon_reference`` never reports ``extracted`` with
       a missing span (its one extracting return slices the sequence by that
       very span), so this is unreachable today. It is handled rather than
       asserted because the coordinates the resolution reports are its own
       answer either way, and reading ``span.end`` here instead would turn a
       contract change into an ``AttributeError`` in the middle of a finished
       demux. Handling it also narrows the optional for the branches below.
    2. The given CDS is stated in whole-reference coordinates and falls inside
       the amplicon: shift it by the span start.
    3. The given CDS already fits inside the amplicon length: it was stated in
       amplicon coordinates, so it is used unchanged.
    4. Neither: fall back to the ORF the resolution found in the amplicon.
    """
    span = resolution.span
    if span is None:
        return resolution.cds_start, resolution.cds_end
    if (
        original_cds_end > span.start
        and original_cds_start >= span.start
        and original_cds_end <= span.end
    ):
        return original_cds_start - span.start, original_cds_end - span.start
    if 0 < original_cds_end <= span.end - span.start:
        return original_cds_start, original_cds_end
    return resolution.cds_start, resolution.cds_end


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
        "n_no_call_aa": t.n_no_call_aa,
        "expected_mutations": list(vr.expected_mutations),
        "mutant_id": getattr(vr, "mutant_id", ""),
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
        n_no_call_aa=int(d.get("n_no_call_aa", 0)),
    )
    return VerdictRecord(
        translated=translated,
        expected_mutations=list(d.get("expected_mutations", [])),
        verdict=VerdictClass(d["verdict"]),
        verdict_notes=d.get("verdict_notes", ""),
        mutant_id=d.get("mutant_id", ""),
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


#: Token appended to the result workbook stem for the auto-saved pick list.
_PICKS_AUTOSAVE_SUFFIX = "_picks"

#: Token for the auto-saved instrument (9-column) mapping.
_MAPPING_AUTOSAVE_SUFFIX = "_janus"


def picks_autosave_path(output: Path) -> Path:
    """Where the pick list lands for a run whose workbook is *output*.

    The result workbook name is built on the frontend (``defaultMameExportFilename``
    in ``src/lib/mameFilename.ts``: date, source token, ``MAME``, verdict count) and
    arrives here fully formed. Deriving from that name rather than rebuilding the
    rule keeps the two artefacts of one run named alike and leaves a single place
    where the rule lives; a second implementation here would drift the first time
    the rule changed. Same directory, same stem, plus the picks token.

    The token says what the file is: the clones this run selected. The
    instrument sheet is the other file the run writes, and it keeps the
    ``_janus`` token (:func:`mapping_autosave_path`).
    """
    return output.with_name(f"{output.stem}{_PICKS_AUTOSAVE_SUFFIX}.csv")


def mapping_autosave_path(output: Path) -> Path:
    """Where the instrument (9-column) mapping lands, beside the pick list.

    Same derivation as :func:`picks_autosave_path` and a different token, so a
    run leaves two files nobody can confuse: ``..._picks.csv`` records what was
    selected, ``..._janus.csv`` is the sheet the robot reads.
    """
    return output.with_name(f"{output.stem}{_MAPPING_AUTOSAVE_SUFFIX}.csv")


def _autosave_janus(
    replicates: list,
    target: Path,
    run_meta: object,
    settings: object,
) -> dict:
    """Write one Janus file for a finished run and report what happened.

    The analysis is already done and cached when this runs, so nothing here may
    raise: a file that cannot be written is a fact to report, not a reason to
    lose a multi-minute run. Every outcome comes back in the same shape.

    Returns ``{"status", "output_path", "format", "row_count", "excluded",
    "excluded_count", "errors", "warnings"}``. ``status`` is ``"saved"``,
    ``"skipped"`` (nothing selected: no file is written, because an empty pick
    list reads like a finished plate), or ``"failed"``.

    ``warnings`` (a blank liquid class, deck numbers derived from the run) never
    stops the file. Only ``errors`` does.
    """
    result: dict = {
        "status": "failed",
        "output_path": None,
        "format": "csv",
        "row_count": 0,
        "excluded": [],
        "excluded_count": 0,
        "errors": [],
        "warnings": [],
    }
    try:
        from kuma_core.mame.export import export_mame_janus_csv
        from kuma_core.mame.export.janus_mapping import build_janus_preview_rows

        preview = build_janus_preview_rows(replicates, settings=settings)  # type: ignore[arg-type]
        result["row_count"] = preview["row_count"]
        result["excluded"] = preview["excluded"]
        result["excluded_count"] = preview["excluded_count"]
        result["warnings"] = preview["warnings"]

        if preview["errors"]:
            result["errors"] = preview["errors"]
            return result
        if preview["row_count"] == 0:
            result["status"] = "skipped"
            return result

        export_mame_janus_csv(
            replicates,
            target,
            ngs_run_meta=run_meta,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        )
        result["status"] = "saved"
        result["output_path"] = str(target)
        return result
    except Exception as exc:  # noqa: BLE001 - the run must survive any failure here
        result["errors"] = [
            {
                "code": "autosave_failed",
                "severity": "error",
                "message": str(exc),
                "mutant_ids": [],
            }
        ]
        return result


def _autosave_picks(
    replicates: list,
    output: Path,
    run_meta: object,
    janus_params: dict,
) -> dict:
    """Write the pick list for a finished run, next to its workbook.

    The schema is forced to ``legacy5`` and deliberately ignores the dialog's
    ``output_schema``. This file records the conclusion of the run (which variant
    sits on which plate and well, and where it should be collected), which is
    what an operator wants beside the workbook every time, and it stays readable
    without a deck in front of you. The instrument sheet is the other file
    (:func:`_autosave_mapping`); neither replaces the other, and the lab asked
    for the instrument sheet by name.

    Selection stays under the operator's control: ``dest_layout``,
    ``include_verdicts`` and ``include_fallback`` are honoured, because those
    describe which clones are picked and how they are gathered, not how the robot
    handles them.
    """
    from kuma_core.mame.export.janus_mapping import SCHEMA_LEGACY5

    from .export import _janus_settings_from_params

    try:
        # The schema is pinned before the params are resolved, not overridden
        # after, so the instrument fields of a device9 dialog (volume, racks)
        # cannot fail validation for a file that will not carry them.
        settings = _janus_settings_from_params(
            {**janus_params, "output_schema": SCHEMA_LEGACY5}
        )
    except Exception as exc:  # noqa: BLE001 - never lose the run over a setting
        return {
            "status": "failed",
            "output_path": None,
            "format": "csv",
            "row_count": 0,
            "excluded": [],
            "excluded_count": 0,
            "errors": [
                {
                    "code": "autosave_failed",
                    "severity": "error",
                    "message": str(exc),
                    "mutant_ids": [],
                }
            ],
            "warnings": [],
        }
    return _autosave_janus(
        replicates, picks_autosave_path(output), run_meta, settings
    )


def _autosave_mapping(
    replicates: list,
    output: Path,
    run_meta: object,
    janus_params: dict,
) -> dict:
    """Write the instrument (9-column) mapping for a finished run.

    The file the lab actually asked for: "the mapping file only has to come out
    the way KURO already makes it". KURO writes its JANUS sheet at the end of a
    design without asking anybody for a liquid class or a rack number
    (``kuma_core/kuro/plate_mapper.py:897`` onwards), so MAME writing one at the
    end of a run is the same habit, not a new promise.

    Nothing is invented to make it come out: rack numbers follow the plates of
    the run (``JanusSettings.resolve_deck``), a liquid class the operator has not
    set ships blank, and both facts come back in ``warnings``. ``volume`` is the
    one value that cannot be derived, which is why the dialog asks for it and
    the default is labelled an assumption.
    """
    from kuma_core.mame.export.janus_mapping import SCHEMA_DEVICE9

    from .export import _janus_settings_from_params

    try:
        settings = _janus_settings_from_params(
            {**janus_params, "output_schema": SCHEMA_DEVICE9}
        )
    except Exception as exc:  # noqa: BLE001 - never lose the run over a setting
        return {
            "status": "failed",
            "output_path": None,
            "format": "csv",
            "row_count": 0,
            "excluded": [],
            "excluded_count": 0,
            "errors": [
                {
                    "code": "autosave_failed",
                    "severity": "error",
                    "message": str(exc),
                    "mutant_ids": [],
                }
            ],
            "warnings": [],
        }
    return _autosave_janus(
        replicates, mapping_autosave_path(output), run_meta, settings
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


def _plate_order_finding(params: dict, expected_path: Path) -> dict | None:
    """Does the expected workbook agree with its own primer plate sheets?

    A workbook that writes one plate two ways is a workbook nobody can read back:
    which of the two sheets describes the tubes that were pipetted is not recorded
    anywhere in the file. So this is graded ``blocking`` whenever it is found, and
    :func:`handle_validate_inputs` turns it into a validation error.

    It used to be downgraded to ``info`` when ``well_layout`` or ``sample_map_xlsx``
    supplied the coordinates, on the grounds that the sheet order never reached a
    well in that case. That is true of the wells and false of the file: the run
    still scores every well against whichever of the two plates the operator's other
    input happens to agree with, and nothing checks that it agrees at all. The fix
    is to re-export the workbook, not to route around it (2026-08-05).

    ``params`` is unused now and kept so the call sites stay stable.

    Returns ``None`` when there is nothing to say: a workbook the check cannot compare
    (no plate sheet, a plain variant list), one whose sheets agree, or a check that
    failed outright. A failed check is not a reason to hold up validation.
    """
    del params  # graded the same way whatever this run's layout inputs are
    try:
        from kuma_core.mame.io.plate_order_check import check_plate_order

        from .barcode_package import plate_order_payload

        report = check_plate_order(expected_path)
    except Exception:  # noqa: BLE001, openpyxl surface is broad; silence beats noise
        return None
    if not report.comparable or report.ok:
        return None

    payload = plate_order_payload(report)
    payload["severity"] = "blocking"
    return payload


def _plate_order_error(payload: dict) -> str:
    """The validation error a plate-order disagreement produces.

    Says what disagrees and what ends it. The only way out is a workbook whose two
    plates match, so the sentence points at the file rather than at a setting: no
    MAME input can decide which sheet was pipetted.
    """
    sheet = payload.get("plate_sheet") or "the primer plate sheet"
    return (
        f"expected: {sheet} and expected_mutations describe different plates in the "
        "same workbook, so the wells this run would score cannot be trusted. "
        "Re-export the workbook from KURO v0.14.3 or later, or pick one whose "
        "sheets agree, and validate again."
    )


def handle_validate_inputs(params: dict) -> dict:
    """Check that all required paths exist and the expected-variant list is readable.

    "Readable" is whatever :func:`read_variant_source` accepts: a KURO export or a
    plain variant list. Optional ``variant_sheet`` / ``variant_column`` name the
    sheet and column for the plain shape and must match what will be sent to
    ``analyze``, or this check grades a different set of rows than the run reads.

    Always returns a 200 response with ``valid`` + ``errors``; callers surface
    the list directly to the user. Does *not* raise on individual validation
    failures, only on programmer errors (missing param key).

    A readable expected workbook is additionally checked against its own primer plate
    sheets (see :func:`_plate_order_finding`). A disagreement is a validation error
    like any other: it lands in ``errors`` and ``valid`` is false. The finding also
    rides along under ``plate_order`` so the frontend can name the wells that
    disagree, and the key is absent when there is nothing to report.

    Until 2026-08-05 the disagreement was reported under ``plate_order`` alone while
    ``valid`` stayed true, which left the run enabled over a workbook describing two
    different plates. Deciding which of the two was pipetted is not something this
    screen can do, so the answer is to refuse the file, not to annotate it.
    """
    errors: list[str] = []
    plate_order: dict | None = None

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
            # Read-level probe. A KURO export is not the only accepted shape, so
            # the old "does it carry an expected_mutations sheet" test would now
            # reject a plain variant list that analyze goes on to read fine.
            # Asking the reader itself keeps this check and the run in agreement,
            # and it reports the reader's own message (which names the sheet or
            # column at fault) instead of a single fixed sentence.
            from kuma_core.mame.io.variant_list import KURO_SHEET, read_variant_source

            from .barcode_package import _optional_str

            try:
                read_variant_source(
                    expected_path,
                    sheet=_optional_str(params.get("variant_sheet")),
                    variant_column=_optional_str(params.get("variant_column")),
                )
                expected_readable = True
            except (FileNotFoundError, ValueError) as exc:
                expected_readable = False
                errors.append(f"expected: {exc}")

            # The plate-order check compares the KURO sheet against the primer
            # plate sheets, so it only has something to say about a KURO export.
            import openpyxl  # local import keeps cold-start fast

            wb = openpyxl.load_workbook(expected_path, read_only=True, data_only=True)
            try:
                is_kuro_export = KURO_SHEET in wb.sheetnames
            finally:
                wb.close()
            if expected_readable and is_kuro_export:
                plate_order = _plate_order_finding(params, expected_path)
                # A validation error, not a note beside a passing validation: a
                # workbook that writes one plate two ways cannot say which plate
                # was pipetted, and no other input on this screen can say it for
                # the workbook. Reported here so `valid` is false and the run is
                # refused until the file is replaced (2026-08-05).
                if plate_order is not None:
                    errors.append(_plate_order_error(plate_order))
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"expected: {exc}")
        except Exception as exc:  # noqa: BLE001 — openpyxl surface is broad
            errors.append(f"expected: failed to open xlsx ({exc})")

    if reference_path is not None:
        try:
            _resolve_cds_end(cds_end, reference_path)
        except ValueError as exc:
            errors.append(str(exc))

    result: dict = {"valid": not errors, "errors": errors}
    if plate_order is not None:
        result["plate_order"] = plate_order
    return result


def handle_analyze(params: dict) -> dict:
    """Run the full pipeline and cache the resulting artefacts for downstream RPCs.

    Three files come out of one run: the result workbook at ``output``, the pick
    list beside it (:func:`picks_autosave_path`), and the instrument mapping
    (:func:`mapping_autosave_path`), all written here rather than waiting for the
    export dialog. Optional ``janus_settings`` carries the same fields the
    ``export_janus_mapping`` RPC accepts; the pick list pins ``legacy5`` and the
    mapping pins ``device9``, so which schema each file uses is not a setting.
    The two outcomes ride back on ``janus_autosave`` and
    ``janus_mapping_autosave`` and never raise.

    Optional ``variant_sheet`` / ``variant_column`` name the sheet and column of a
    plain expected-variant list. Omitting both is auto-detection, which leaves a
    KURO export on the path it always took.
    """
    # Lazy import: keeps the sidecar cold-start < 200 ms and lets the module
    # import during unit tests that stub mame.
    from kuma_core.mame.distribution import compute_distribution_stats
    from kuma_core.mame.ingest import (
        IngestMode,
        ingest_run_folder,
        is_minknow_run_dir,
        route_ingest,
    )
    from kuma_core.mame.perf import TIMER
    from kuma_core.mame.pipeline import run_analyze

    input_dir = _validate_dirpath(params["input_dir"])
    # Preserve the caller-supplied directory: in raw-run mode ``input_dir`` is
    # rebound to the demux output dir for the analyze body, but run-metadata
    # discovery must still see the original MinKNOW run folder.
    original_run_dir = input_dir
    reference = _validate_filepath(
        params["reference"], allowed_extensions=_ALLOWED_SEQUENCE_EXTENSIONS
    )
    reference_for_pipeline = reference
    amplicon_resolution = None
    resolved_raw_cds_start: int | None = None
    resolved_raw_cds_end: int | None = None
    expected = _validate_filepath(
        params["expected"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )
    # Optional sheet/column for an expected list that is not a KURO export. Both
    # absent (any frontend built before this) means auto-detection, which routes a
    # KURO export to the strict reader exactly as before.
    from .barcode_package import _optional_str

    variant_sheet = _optional_str(params.get("variant_sheet"))
    variant_column = _optional_str(params.get("variant_column"))
    output = _validate_output_path(
        params["output"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )

    # Raw-run gate: a MinKNOW run folder (has ``fastq_pass/``) needs demux first;
    # a pre-demuxed consensus dir takes the legacy path untouched.
    is_raw = is_minknow_run_dir(input_dir)
    # Demux gate counters, filled in by ``ingest_run_folder`` on the raw-run
    # path only. Stays empty in consensus-dir mode: that path never runs the
    # aligner, so no read ever passes (or fails) a MAPQ/coverage gate here and
    # there is nothing to report. Left empty rather than zero-filled so the
    # response omits the keys instead of claiming "0 reads passed".
    demux_gate_counts: dict[str, int] = {}
    # Latest demux progress, mirrored by _emit_demux so the demux-phase heartbeat
    # can re-emit a liveness pulse during long, low-event per-NB demux stretches.
    _demux_state = {"value": 0, "message": "Demuxing raw MinKNOW run", "current": 0, "total": 0}

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
            cur, tot = done, total
        elif stage_str == "demux":
            value = int(40 * done / max(1, total))
            message = f"Demuxing reads ({done}/{total})"
            cur, tot = done, total
        else:
            # Combinatorial demux reports aggregate progress as a per-mille
            # fraction (done out of 1000) purely to drive a smooth bar — it is
            # NOT a read count. Surface it as a percentage (current=pct,
            # total=None) so the UI shows "73%" instead of a meaningless
            # "730 / 1,000". The barcode tally stays in the message.
            value = int(50 * done / max(1, total))
            cur, tot = int(100 * done / max(1, total)), None
            message = f"Sorting reads — {stage_str}"
        emit_params: dict = {
            "value": min(50, value),
            "message": message,
            "current": cur,
            "total": tot,
            "stage": "demux",
        }
        _demux_state.update(
            value=emit_params["value"],
            message=message,
            current=cur,
            total=tot,
        )
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
        if not isinstance(raw_custom_barcodes_xlsx, str):
            raise ValueError("custom_barcodes_xlsx is required for raw-run analysis")

        demux_output_dir = (
            Path(params["demux_output_dir"])
            if params.get("demux_output_dir")
            else output.parent / "demux_filtered"
        )
        if reference.suffix.lower() not in _ALLOWED_FASTA_EXTENSIONS:
            demux_output_dir.mkdir(parents=True, exist_ok=True)
            reference_for_pipeline = _write_reference_fasta(reference, demux_output_dir)

        from kuma_core.mame.ingest.amplicon_reference import (
            check_coverage_reachable,
            resolve_amplicon_reference,
            unreachable_coverage_message,
        )

        demux_output_dir.mkdir(parents=True, exist_ok=True)
        amplicon_resolution = resolve_amplicon_reference(
            reference_for_pipeline,
            Path(raw_custom_barcodes_xlsx),
            demux_output_dir,
        )
        if not amplicon_resolution.extracted:
            # Extraction was skipped. That is FINE when the user already supplied
            # the amplicon itself, and fatal when it means a whole construct is
            # about to be used as the reference: the coverage gate would then
            # drop every read and the run would finish "successfully" with 0
            # wells (barcode 07/08/09, 2026-08-04). Decide between the two on
            # the data rather than on a length guess -- an alignment cannot span
            # more reference than the read is long, so if the longest read in
            # the run is shorter than coverage_fraction x reference length, no
            # read can pass and the run is refused before it starts.
            reachability = check_coverage_reachable(
                amplicon_resolution.reference_fasta,
                original_run_dir,
                raw_coverage_fraction,
            )
            if not reachability.reachable:
                raise ValueError(
                    unreachable_coverage_message(
                        reachability,
                        amplicon_resolution,
                        Path(raw_custom_barcodes_xlsx),
                        amplicon_resolution.reference_fasta,
                    )
                )
        reference_for_pipeline = amplicon_resolution.reference_fasta
        if amplicon_resolution.extracted:
            reference = reference_for_pipeline
            original_cds_start = int(params.get("cds_start", 0))
            original_cds_end = int(params.get("cds_end", 0) or 0)
            resolved_raw_cds_start, resolved_raw_cds_end = resolve_amplicon_cds(
                amplicon_resolution, original_cds_start, original_cds_end
            )

        AnalyzeRawRunParams.model_validate(
            {
                "minknow_run_dir": str(input_dir),
                "custom_barcodes_xlsx": raw_custom_barcodes_xlsx,
                "reference_fasta": str(reference_for_pipeline),
                "demux_output_dir": params.get("demux_output_dir"),
                "native_barcodes": raw_native_barcodes,
                "mapq_threshold": raw_mapq_threshold,
                "coverage_fraction": raw_coverage_fraction,
                "edit_dist_ratio": raw_edit_dist_ratio,
                "chimera_split": raw_chimera_split,
                "trim_flank_bp": raw_trim_flank_bp,
            }
        )

        _demux_started = time.monotonic()
        _demux_done_evt = threading.Event()

        def _demux_heartbeat() -> None:
            # Long per-NB demux reports progress only at each barcode completion;
            # re-emit the latest demux pulse with elapsed time so the bar stays
            # visibly alive and the frontend no-response watchdog never trips.
            while not _demux_done_evt.wait(_HEARTBEAT_INTERVAL_S):
                elapsed = int(time.monotonic() - _demux_started)
                mm, ss = divmod(elapsed, 60)
                with _emit_lock:
                    _send({
                        "jsonrpc": "2.0",
                        "method": "progress",
                        "params": {
                            "value": _demux_state["value"],
                            "message": f"{_demux_state['message']} — {mm}m{ss:02d}s",
                            "current": _demux_state["current"],
                            "total": _demux_state["total"],
                            "stage": "demux",
                        },
                    })

        _hb_thread = threading.Thread(target=_demux_heartbeat, daemon=True)
        _hb_thread.start()
        try:
            ingest_run_folder(
                run_dir=original_run_dir,
                custom_barcodes_xlsx=Path(raw_custom_barcodes_xlsx),
                reference_fasta=reference_for_pipeline,
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
                stats_out=demux_gate_counts,
            )
        finally:
            _demux_done_evt.set()
            _hb_thread.join(timeout=2.0)
        # The demux output is a barcode-mode consensus tree; the analyze body
        # ingests it exactly like a pre-demuxed consensus dir.
        input_dir = demux_output_dir

    # Perf window for the whole analyze body. ``run_analyze`` used to open its
    # own, which left everything this handler does around it (the ingest for the
    # distribution stats, run-meta discovery, the expected-mutations read, the
    # response serialisation) outside every reported scope: the handler measured
    # 2.33 s against a 1.26 s "analyze" scope on a share, and the missing second
    # was invisible. The window is opened here and ``run_analyze`` is told not to
    # report (``perf_scope=None``), so there is exactly ONE report and its wall is
    # the handler wall. The raw-run demux above is deliberately outside it: that
    # stage reports its own scopes.
    _perf_base = TIMER.begin()
    _emit(5, "Validating inputs...")

    mode = str(params.get("mode", "amplicon"))
    ingest_mode_raw = str(params.get("ingest_mode", "barcode"))
    cds_start = (
        resolved_raw_cds_start
        if resolved_raw_cds_start is not None
        else int(params.get("cds_start", 0))
    )
    cds_end = (
        resolved_raw_cds_end
        if resolved_raw_cds_end is not None and resolved_raw_cds_end > 0
        else _resolve_cds_end(params.get("cds_end"), reference)
    )
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
    #
    # ``layout_source`` records WHICH of the three branches actually produced
    # the mapping this run scored wells against, and rides into the response
    # as ``layout_provenance``. Without it a result cannot say whether a well
    # was placed by the operator, by a saved sample map, or guessed by
    # ``build_draft_layout`` from whatever ``expected`` happens to be current
    # -- the last of which is exactly the failure shape of the 2026-08
    # incident this file's mapping-integrity check was written for: a stale
    # ``expected`` produces a plausible-looking inferred layout with nothing
    # in the result to say it was inferred at all, let alone from what file.
    well_layout_raw = params.get("well_layout")
    well_layout: dict[str, str] | None = None
    layout_source: str
    if well_layout_raw is not None:
        if not isinstance(well_layout_raw, dict) or not all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in well_layout_raw.items()
        ):
            raise ValueError("well_layout must be a mapping of well_id (str) to sample_name (str)")
        well_layout = well_layout_raw
        layout_source = "explicit_well_layout"
    elif sample_map_path is not None:
        layout_source = "sample_map_xlsx"
    else:
        from kuma_core.mame.io.variant_list import read_variant_source
        from kuma_core.mame.layout import build_draft_layout

        # Same read and the same WT rule as ``mame.build_well_layout``: the two
        # produce the layout for the same file and must not disagree about it.
        _inferred = read_variant_source(
            expected, sheet=variant_sheet, variant_column=variant_column
        )
        well_layout = build_draft_layout(
            _inferred.expected, include_wt=not _inferred.has_explicit_wt
        ).layout
        layout_source = "inferred_draft_layout"

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

    # A11: discover MinKNOW run metadata once at analyze time and cache it.
    # It is pure read-only filesystem probing whose result is not needed until
    # ``set_last_analyze`` at the very end, and on a share it costs ~0.17 s of
    # directory globbing that used to sit on the critical path after the
    # pipeline. Running it alongside the pipeline removes it from the wall
    # without moving where its value is consumed. Imported lazily (cold start).
    from kuma_core.mame.ingest.run_meta import discover_run_meta

    _run_meta_holder: dict[str, Any] = {}

    def _discover_run_meta() -> None:
        # ``_sum`` suffix per kuma_core.mame.perf: this is accumulated on a
        # worker thread and overlaps the reporting thread's wall, so it is a
        # share-of-wall number, not a slice of a partition.
        try:
            with TIMER.phase("run_meta_sum"):
                _run_meta_holder["value"] = discover_run_meta(
                    original_run_dir if is_raw else input_dir
                )
        except BaseException as exc:  # noqa: BLE001 - re-raised on the main thread
            # Moving this call onto a thread must not turn a failure into a
            # silent ``run_meta=None``: the exception is carried back and raised
            # where the synchronous version would have raised it.
            _run_meta_holder["error"] = exc

    _meta_thread = threading.Thread(
        target=_discover_run_meta, daemon=True, name="analyze-run-meta"
    )
    _meta_thread.start()

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
        with TIMER.phase("ingest"):
            raw_records = route_ingest(input_dir, ingest_mode_enum)
        if is_raw and not raw_records:
            raise ValueError(
                "No wells were recovered from the MinKNOW reads. Check that the "
                "reference contains the sequenced amplicon and that the custom "
                "barcode definitions match this run."
            )
        dist_stats = compute_distribution_stats(
            [rec.file_size_kb for rec in raw_records]
        )

        # Read the expected-mutations xlsx ONCE. ``run_analyze`` needs the parsed
        # rows and this handler needs the designed-mutant denominator derived from
        # them; each used to open the same workbook separately.
        from kuma_core.mame.detected import designed_mutant_ids as _designed_ids
        from kuma_core.mame.io.variant_list import read_variant_source

        with TIMER.phase("expected_read"):
            expected_mutations = read_variant_source(
                expected, sheet=variant_sheet, variant_column=variant_column
            ).expected
        dids = _designed_ids(expected_mutations)

        _emit(30, "Translating sequences...")
        _holder["value"] = 30
        _holder["message"] = "Translating sequences..."
        _emit(60, "Classifying verdicts...")
        _holder["value"] = 60
        _holder["message"] = "Classifying verdicts..."

        if not is_raw and reference.suffix.lower() not in _ALLOWED_FASTA_EXTENSIONS:
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
                    records=raw_records,
                    expected_mutations=expected_mutations,
                    designed_mutant_ids=dids,
                    perf_scope=None,
                )
        else:
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
                records=raw_records,
                expected_mutations=expected_mutations,
                designed_mutant_ids=dids,
                perf_scope=None,
            )
    finally:
        # Stop and join the heartbeat BEFORE the terminal milestones so a stale
        # holder emit cannot race the 85/100 updates.
        _stop.set()
        _hb_thread.join(timeout=_HEARTBEAT_INTERVAL_S + 1.0)

    _emit(85, "Selecting best replicates...")
    _emit(100, "Writing Excel output...")

    # Collect the run metadata discovered alongside the pipeline. ``dids`` (the
    # recovery denominator: distinct designed mutant_ids) came from the single
    # expected-mutations read above, which ``run_analyze`` shared, so downstream
    # recovery still survives both analyze and workspace-reload.
    _meta_thread.join()
    _meta_error = _run_meta_holder.get("error")
    if _meta_error is not None:
        raise _meta_error
    run_meta = _run_meta_holder.get("value")

    set_last_analyze(
        verdicts,
        replicates,
        str(output),
        run_meta=run_meta,
        designed_mutant_ids=dids,
    )

    # The pick list is the second artefact of the same run, so it is written here
    # rather than waiting for the operator to open the dialog. Cached state is
    # already set above, so a failure here costs the file, never the analysis.
    # Post-hoc mapping sanity check (kuma_core.mame.qc): this is the ONLY place
    # left, after classification, that can see the failure signature a stale or
    # mis-drawn well_layout leaves behind -- every well individually classifies
    # fine against whatever expected set it was scoped to, and only comparing
    # observed changes across the whole plate exposes a systematic swap (see
    # kuma_core/mame/qc/mapping_integrity.py for the incident this guards).
    from kuma_core.mame.qc import check_mapping_integrity, observations_from_verdicts

    _mapping_integrity = check_mapping_integrity(observations_from_verdicts(verdicts))

    janus_params = params.get("janus_settings") or {}
    janus_autosave = _autosave_picks(replicates, output, run_meta, janus_params)
    # The mapping file the lab asked for by name: same run, same picks, the
    # instrument columns. Written unconditionally because KURO writes its JANUS
    # sheet the same way, and because the two files answer different questions
    # (what was selected vs. what the robot should do about it).
    janus_mapping_autosave = _autosave_mapping(
        replicates, output, run_meta, janus_params
    )

    response = {
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "output_path": str(output),
        "janus_autosave": janus_autosave,
        "janus_mapping_autosave": janus_mapping_autosave,
        "designed_mutant_ids": sorted(dids),
        "summary": _summarize(verdicts),
        # Which of the three well->sample sources this run actually scored
        # wells against, and the expected/sample-map files it came from. See
        # the ``layout_source`` assignment above for why this exists: an
        # inferred layout must not be able to pass itself off, downstream, as
        # one the operator supplied.
        "layout_provenance": {
            "source": layout_source,
            "expected_path": str(expected),
            "sample_map_path": (
                str(sample_map_path) if sample_map_path is not None else None
            ),
        },
        # Whole-run mapping sanity check (kuma_core.mame.qc.mapping_integrity).
        # ``suspect`` is a signal to surface prominently, not a hard failure:
        # the run already finished and the workbook the operator has may be
        # the only record of what was actually pipetted.
        "mapping_integrity": {
            "wells_considered": _mapping_integrity.wells_considered,
            "self_match": _mapping_integrity.self_match,
            "cross_match": _mapping_integrity.cross_match,
            "self_rate": _mapping_integrity.self_rate,
            "cross_rate": _mapping_integrity.cross_rate,
            "suspect": _mapping_integrity.suspect,
        },
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
        # Demux gate counters, keyed exactly as DemuxStats declares them. Only
        # the three that explain a zero-verdict run are surfaced: the ratio
        # ``passed_mapq / total_reads`` separates "nothing aligned" from "the
        # run had no reads", and ``passed_coverage`` splitting away from
        # ``passed_mapq`` is what a whole-construct reference against amplicon
        # reads looks like (v0.15.2 made the two counters count their own
        # gates, so the gap between them is now meaningful). Each key is
        # emitted only when the demux actually produced it; consensus-dir mode
        # contributes nothing and the keys stay absent.
        **{
            key: int(demux_gate_counts[key])
            for key in ("total_reads", "passed_mapq", "passed_coverage")
            if key in demux_gate_counts
        },
        **(
            {
                "reference_resolution": {
                    "path": str(amplicon_resolution.reference_fasta),
                    "extracted": amplicon_resolution.extracted,
                    "span_start": (
                        amplicon_resolution.span.start + 1
                        if amplicon_resolution.span is not None
                        else None
                    ),
                    "span_end": (
                        amplicon_resolution.span.end
                        if amplicon_resolution.span is not None
                        else None
                    ),
                    "original_length": amplicon_resolution.original_length,
                    "cds_start": cds_start,
                    "cds_end": cds_end,
                    "note": amplicon_resolution.note,
                }
            }
            if amplicon_resolution is not None
            else {}
        ),
    }
    TIMER.end("analyze", _perf_base, records=len(verdicts))
    return response


__all__ = [
    "handle_analyze",
    "handle_validate_inputs",
    "_serialize_verdict",
    "_serialize_replicate",
    "_deserialize_verdict",
    "_deserialize_replicate",
]
