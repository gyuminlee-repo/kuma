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
    from kuma_core.mame.layout import DraftLayout, WtPlacement

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
    """Return the single sequence in a FASTA file, refusing several records.

    A reference is ONE molecule. Joining a plasmid backbone to a target gene
    produces a sequence with a junction no molecule has, and the length this
    reader hands to the CDS default, the run-quality scale and the read-length
    ratios would all be measured against that chimera without a word said.

    A file with no header at all stays acceptable, as it always was here. The
    count-and-name judgement is shared with the two ``kuma_core`` readers so the
    operator reads one sentence whichever path opened the file; the import stays
    inside the function because pulling it in at module level would drag the
    whole ingest package into a handler that loads it lazily on purpose.
    """
    from kuma_core.mame.reference_fasta import multi_record_reason

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    reason = multi_record_reason(lines)
    if reason is not None:
        # ValueError is what every other refusal in this reader raises, and the
        # error type the ingest layer uses for the same refusal subclasses it,
        # so a caller catching ValueError sees both paths alike.
        raise ValueError(f"{reason}: {path}")
    seq_parts: list[str] = []
    for line in lines:
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
    4. Neither: fall back to the ORF the resolution found in the amplicon. When
       the resolution found none, there is nothing left to fall back to and the
       run is refused rather than framed at zero. The old fallback returned
       ``(0, 0)``, which is not "CDS unknown" anywhere downstream: ``cds_end``
       of 0 is replaced by the full reference length below, so the plate was
       translated in frame 0 from the first base of the amplicon, which is the
       primer tail. Amino-acid numbering then belonged to a frame the design
       never used, and the two ways that showed up were both wrong quietly:
       wells carrying an expected mutation failed as WRONG_AA, and wells with
       an empty expected list (WT controls) passed clean. Refusing follows the
       same reasoning ``ExpectedCoordinateMismatchError`` is raised on, a whole
       plate scored against the wrong coordinates while still producing
       verdicts that read as ordinary.
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
    if not resolution.coding_bounds_found:
        raise ValueError(
            "Coding sequence bounds could not be determined for the extracted "
            "amplicon: it contains no forward reading frame (no ATG followed "
            "by an in-frame stop codon), and the CDS bounds given do not fit "
            f"it either (cds_start={original_cds_start}, "
            f"cds_end={original_cds_end}; amplicon is "
            f"{span.end - span.start} bp, cut from reference positions "
            f"{span.start + 1}-{span.end}).\n"
            f"  reference: {resolution.reference_fasta}\n"
            f"  resolution: {resolution.note}\n"
            "Without a frame the whole amplicon would be translated from its "
            "first base, which is the primer tail, so every amino-acid "
            "position would be numbered against a frame the design never "
            "used. Supply cds_start / cds_end for this reference, in either "
            "whole-reference or amplicon coordinates, or use a reference "
            "whose amplicon carries a complete coding sequence."
        )
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
    out = {
        "native_barcode": b.native_barcode,
        "custom_barcode": b.custom_barcode,
        "file_size_kb": b.file_size_kb,
        "read_count": b.read_count,
        "n_mixed_positions": b.n_mixed_positions,
        "max_minor_allele_fraction": b.max_minor_allele_fraction,
        # The noise floor this well ran at. ``max_minor_allele_fraction`` alone
        # cannot be read: 0.04 is a clean well when ordinary positions sit at
        # 0.03 and a contaminated one when they sit at 0.002. Written to the
        # workbook since v0.15.14 (export/excel_writer.py) and carried here so
        # the same comparison is available on screen.
        "median_minor_allele_fraction": b.median_minor_allele_fraction,
        "n_low_depth_positions": b.n_low_depth_positions,
        "consensus_n_fraction": b.consensus_n_fraction,
        # False when the consensus predates the covered-scoped N-fraction
        # definition, in which case ``consensus_n_fraction`` means nothing and
        # the NO_CALL gate was skipped for this well (compare/verdict.py).
        # Without the flag a reader cannot tell a measured 0.0 from a
        # substituted one, which is a 0.0 that was never measured being read as
        # a clean well.
        "consensus_n_fraction_evaluable": b.consensus_n_fraction_evaluable,
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
        # How many mix-eligible positions this well had, which is the pool
        # ``noisy_positions`` samples. Unconditional because 0 is a real answer
        # (nothing eligible) and because without it a truncated top-K sample
        # reads as a census: on a real ONT amplicon every well fills the budget.
        "n_eligible_positions": b.n_eligible_positions,
        "noisy_positions": [
            {
                "position": p.position,
                "minor_fraction": p.minor_fraction,
                "depth": p.depth,
                "plus_count": p.plus_count,
                "minus_count": p.minus_count,
            }
            for p in b.noisy_positions
        ],
    }
    # OMITTED, never zero-filled, when the well has no mix-eligible position:
    # 0.0 is the artifact reading (minor allele on one strand only), so a
    # zero-filled key would report one-strand evidence that was never measured.
    # The two counts travel with the share because they are its denominators and
    # mean nothing without it. Same contract as the yield fields.
    if b.max_minor_allele_strand_share is not None:
        out["max_minor_allele_strand_share"] = b.max_minor_allele_strand_share
        out["max_minor_allele_plus_count"] = b.max_minor_allele_plus_count
        out["max_minor_allele_minus_count"] = b.max_minor_allele_minus_count
    # Coverage uniformity and consensus identity, report only. ``mean_depth``
    # cannot separate a well covered evenly from one with the same mean and a
    # hole, and these say which it was. Each key is emitted INDEPENDENTLY and
    # only when measured: a well that produced no consensus still has a real
    # breadth of 0.0 while the other four are unmeasurable, so guarding them as
    # one block would drop that measurement. Absence means unknown, never 0.0.
    for key, value in (
        ("depth_cv", b.depth_cv),
        ("depth_p10", b.depth_p10),
        ("depth_min_covered", b.depth_min_covered),
        ("breadth_at_mix_min_depth", b.breadth_at_mix_min_depth),
        ("consensus_identity", b.consensus_identity),
    ):
        if value is not None:
            out[key] = value
    return out


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
        NoisyPosition,
        TranslatedRecord,
        VerdictClass,
        VerdictRecord,
    )

    # Absent for a payload persisted before the strand evidence was serialized.
    # ``None`` is passed through as the record's own default, so a legacy payload
    # restores as unknown rather than as a one-strand measurement.
    strand_share = d.get("max_minor_allele_strand_share")

    def _opt_float(key: str) -> float | None:
        """``None`` when the key is absent, so unknown never becomes 0.0."""
        value = d.get(key)
        return None if value is None else float(value)

    depth_min_covered = d.get("depth_min_covered")
    barcode = BarcodeRecord(
        native_barcode=d["native_barcode"],
        custom_barcode=d["custom_barcode"],
        consensus_seq="",  # not serialized; not read by downstream consumers
        file_size_kb=float(d.get("file_size_kb", 0.0)),
        source_path=Path(d.get("source_path", "")),
        read_count=d.get("read_count"),
        n_mixed_positions=int(d.get("n_mixed_positions", 0)),
        max_minor_allele_fraction=float(d.get("max_minor_allele_fraction", 0.0)),
        # Absent in payloads persisted before these two were serialized. The
        # defaults are BarcodeRecord's own (0.0 = noise floor unknown,
        # True = the N fraction means what it says), so a legacy payload
        # restores exactly as it does today and no gate changes.
        median_minor_allele_fraction=float(
            d.get("median_minor_allele_fraction", 0.0)
        ),
        n_low_depth_positions=int(d.get("n_low_depth_positions", 0)),
        consensus_n_fraction=float(d.get("consensus_n_fraction", 0.0)),
        consensus_n_fraction_evaluable=bool(
            d.get("consensus_n_fraction_evaluable", True)
        ),
        n_low_quality_bases=int(d.get("n_low_quality_bases", 0)),
        n_input_reads=d.get("n_input_reads"),
        n_aligned_reads=d.get("n_aligned_reads"),
        n_mapq_failed=int(d.get("n_mapq_failed", 0)),
        n_span_failed=int(d.get("n_span_failed", 0)),
        max_minor_allele_strand_share=(
            None if strand_share is None else float(strand_share)
        ),
        max_minor_allele_plus_count=int(d.get("max_minor_allele_plus_count", 0)),
        max_minor_allele_minus_count=int(d.get("max_minor_allele_minus_count", 0)),
        n_eligible_positions=int(d.get("n_eligible_positions", 0)),
        noisy_positions=tuple(
            NoisyPosition(
                position=int(p["position"]),
                minor_fraction=float(p["minor_fraction"]),
                depth=int(p["depth"]),
                plus_count=int(p["plus_count"]),
                minus_count=int(p["minus_count"]),
            )
            for p in d.get("noisy_positions", ())
        ),
        # Absent in a payload persisted before these existed, and absent for any
        # well that could not measure one of them. ``None`` is passed through as
        # unknown; coercing to 0.0 would report a perfectly flat, zero-identity
        # well that nobody measured.
        depth_cv=_opt_float("depth_cv"),
        depth_p10=_opt_float("depth_p10"),
        depth_min_covered=(
            None if depth_min_covered is None else int(depth_min_covered)
        ),
        breadth_at_mix_min_depth=_opt_float("breadth_at_mix_min_depth"),
        consensus_identity=_opt_float("consensus_identity"),
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


def picks_autosave_path(output: Path) -> Path:
    """Where the pick list lands for a run whose workbook is *output*.

    The result workbook name is built on the frontend (``defaultMameExportFilename``
    in ``src/lib/mameFilename.ts``: date, source token, ``MAME``, verdict count) and
    arrives here fully formed. Deriving from that name rather than rebuilding the
    rule keeps the two artefacts of one run named alike and leaves a single place
    where the rule lives; a second implementation here would drift the first time
    the rule changed. Same directory, same stem, plus the picks token.

    The token says what the file is: the clones this run selected. The
    instrument sheet (``_janus`` token) is a separate file, written only on a
    manual ``export_janus_mapping`` call, not derived from this path.
    """
    return output.with_name(f"{output.stem}{_PICKS_AUTOSAVE_SUFFIX}.csv")


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

    The schema is forced to ``legacy5`` and deliberately ignores the export
    settings' ``output_schema``. This file records the conclusion of the run
    (which variant sits on which plate and well, and where it should be
    collected), which is what an operator wants beside the workbook every
    time, and it stays readable without a deck in front of you. The
    instrument sheet is a separate file, written only by a manual
    ``export_janus_mapping`` call (``device``); a robot worklist states a deck
    that describes the room at export time, and this automatic write has no
    reason to assert it on every re-run.

    Selection stays under the operator's control: ``dest_layout``,
    ``include_verdicts`` and ``include_fallback`` are honoured, because those
    describe which clones are picked and how they are gathered, not how the robot
    handles them.
    """
    from kuma_core.mame.export.janus_mapping import SCHEMA_LEGACY5

    from .export import _janus_settings_from_params

    try:
        # The schema is pinned before the params are resolved, not overridden
        # after, so the instrument fields of a device dialog (volume, racks)
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


def _barcode_layout_error(barcodes_path: Path) -> str | None:
    """Does this barcode file describe wells on the plate MAME can name?

    The combinatorial custom barcode is ``{R}_{F}`` with R the plate row and F
    the plate column, so a set has to number its reverse seeds 1..8 and its
    forward seeds 1..12, with no gaps. Neither condition was checked anywhere,
    and both fail quietly:

    * An index past the plate makes ``_custom_barcode_to_seq`` return ``None``,
      and the well id goes into the workbook as an empty string. On a sheet where
      other rows have coordinates, that reads as a well that failed to sequence.
    * A gap renumbers everything after it. ``load_barcode_prefixes`` sorts by
      index and then keeps position, so a set numbered 1, 2, 5 hands the matcher
      three barcodes and it reports the third as F3. Reads carrying ``_f_5`` are
      filed under plate column 3 with nothing to show for it.

    Returns the message to put in front of the operator, or ``None`` when the
    file fits. A file that cannot be opened is not this check's business; the
    caller has already validated the path, and a read failure here would only
    duplicate whatever the run reports.
    """
    try:
        from kuma_core.mame.ingest.combinatorial_demux import read_barcode_indices
        from kuma_core.mame.plate_geometry import (
            PLATE_COLS,
            PLATE_ROWS,
            check_barcode_layout,
        )

        r_idx, f_idx = read_barcode_indices(barcodes_path)
    except Exception:  # noqa: BLE001 - openpyxl surface is broad
        return None

    if not r_idx and not f_idx:
        return (
            f"custom_barcodes_xlsx: {barcodes_path.name} carries no barcode rows. "
            "Rows are named <prefix>_f_<n> and <prefix>_r_<n>, for example "
            "isps_f_1 and isps_r_1."
        )

    report = check_barcode_layout(r_idx, f_idx)
    problems: list[str] = []
    if report.out_of_range:
        listed = ", ".join(f"{axis}{n}" for axis, n in report.out_of_range)
        problems.append(
            f"numbered past the plate ({listed}); a well is named {{R}}_{{F}} with "
            f"R the row 1..{PLATE_ROWS} and F the column 1..{PLATE_COLS}, so those "
            "wells would come out of the run with no coordinate"
        )
    if report.gaps:
        listed = ", ".join(f"{axis}{n}" for axis, n in report.gaps)
        problems.append(
            f"missing {listed}; a gap shifts every later barcode down one place, "
            "so reads land in the wrong plate column or row without saying so"
        )
    if not problems:
        return None
    return (
        f"custom_barcodes_xlsx: {barcodes_path.name} is "
        + "; and it is ".join(problems)
        + f". Read {len(report.r_indices)} R and {len(report.f_indices)} F barcodes."
    )


def _barcode_axis_counts(barcodes_path: Path) -> dict | None:
    """How many seeds each axis carries, and how many wells they can name.

    Read-only and cheap (the same two columns :func:`_barcode_layout_error`
    opens). Reported so the operator can see what the file actually contains
    before starting a run, rather than inferring it from the absence of an
    error. ``None`` when the file cannot be read, which the caller has already
    reported some other way.

    Also ``None`` for a set that does not fit the plate, and that is the point
    rather than a shortcut. The counts are every index the file carries while
    ``describable_wells`` counts only the in-range combinations, so a 13F x 9R
    workbook would render "13 forward x 9 reverse seeds, 96 wells" -- three
    numbers that do not multiply, printed beside the layout error that already
    names F13 and R9. One statement about such a file is enough, and it is the
    one that says what is wrong with it.
    """
    try:
        from kuma_core.mame.ingest.combinatorial_demux import read_barcode_indices
        from kuma_core.mame.plate_geometry import check_barcode_layout

        r_idx, f_idx = read_barcode_indices(barcodes_path)
    except Exception:  # noqa: BLE001 - openpyxl surface is broad
        return None
    report = check_barcode_layout(r_idx, f_idx)
    if not report.fits:
        return None
    return {
        "forward_count": len(report.f_indices),
        "reverse_count": len(report.r_indices),
        "wells": report.describable_wells,
    }


def _layout_is_inferred(params: dict) -> bool:
    """Will this run place wells by reading ``expected``, or was it told where?

    The same two-way decision ``handle_analyze`` makes when it sets
    ``layout_source``, asked early and off the raw params so the checks that
    have to run before the demux can ask it too. Kept as one function because
    two copies of it would be two chances for a check to guard a branch the run
    does not take.

    ``selected_wells`` does not make a layout explicit. It says which wells the
    campaign occupies, not what sits in them, and the contents still come from
    reading ``expected``: the capacity and plate-order checks below have exactly
    as much to say about such a run as about one with no selection at all.
    """
    return params.get("well_layout") is None


def _selected_wells_param(params: dict) -> list[str] | None:
    """The wells this run declares as occupied, or ``None`` for "all of them".

    A campaign smaller than the plate leaves wells empty, and no input file says
    which. Absent means the layout fills the leading wells, which is what every
    run did before this parameter existed, so an unset selection produces the
    same bytes it always did.

    A malformed payload raises rather than being ignored: this parameter decides
    where every variant lands, and silently falling back to the default would
    place the plate somewhere the operator did not ask for.
    """
    raw = params.get("selected_wells")
    if raw is None:
        return None
    if not isinstance(raw, list) or not all(isinstance(w, str) for w in raw):
        raise ValueError("selected_wells must be a list of well ids (str)")
    if not raw:
        raise ValueError(
            "selected_wells is empty. A run with no wells has nothing to score; "
            "omit the parameter to use the whole plate."
        )
    return raw


def _off_layout_records(
    verdicts: list,
    well_layout: dict[str, str] | None,
    skipped_records: dict[str, int] | None = None,
) -> dict:
    """How many records came from wells the layout does not name.

    Reported, never refused. An operator who declares which wells the campaign
    occupies is stating that the rest are empty, and reads from an empty well
    are worth seeing. But the same counts appear when barcode crosstalk leaks
    reads across wells, and nothing in the count separates the two, so this
    hands the operator the wells and lets them decide.

    ``None`` layout means no well was declared and every record is in scope, so
    the count is zero rather than "all of them".

    ``skipped_records`` carries the wells the pipeline refused to score because
    a declared selection left them out. They have no verdict by construction,
    so counting verdicts alone would report zero for exactly the runs this
    signal exists for: the declaration is what makes an off-layout read
    meaningful in the first place.
    """
    from kuma_core.mame.export.excel_writer import _custom_barcode_to_seq
    from kuma_core.mame.export.well_mapper import seq_to_well
    from kuma_core.mame.plate_geometry import norm_well

    if not well_layout:
        return {"count": 0, "wells": []}
    declared = {norm_well(well) for well in well_layout}
    off: dict[str, int] = {}
    for vr in verdicts:
        seq = _custom_barcode_to_seq(vr.translated.barcode.custom_barcode)
        if seq is None:
            continue
        well = seq_to_well(seq)
        if norm_well(well) in declared:
            continue
        off[well] = off.get(well, 0) + 1
    for well, count in (skipped_records or {}).items():
        off[well] = off.get(well, 0) + count
    return {
        "count": sum(off.values()),
        "wells": [
            {"well": well, "records": count}
            for well, count in sorted(off.items(), key=lambda pair: pair[0])
        ],
    }


def _plate_capacity_finding(
    expected_path: Path,
    variant_sheet: str | None,
    variant_column: str | None,
    wt_placement: "WtPlacement | None" = None,
) -> tuple[str | None, "DraftLayout | None"]:
    """Does the designed list fit the one plate a *drafted* layout would place?

    Returns ``(error, draft)``. The draft is handed back rather than a summary
    of it so the caller can place wells with the very object this graded; a
    second ``build_draft_layout`` over the same file is a second chance to
    disagree with the check that let the run start.

    Only ask this when the run has no layout of its own. A designed list is the
    campaign, and ``well_layout`` is what names the plate cut out of it: the
    pipeline scopes each well through ``well_to_sample``
    (``kuma_core/mame/pipeline.py``), so a longer list is a lookup table with
    spare rows, not an overflowing plate. :func:`_layout_is_inferred` is the
    gate, and without it this refuses a configuration that ran correctly before
    the check existed.

    The plate holds ``N + 1`` occupants, not ``N``: the WT control is a
    sequencing target and takes a well of its own. Judging on ``N`` alone let a
    96-mutant list through and then asked ``seq_to_well`` for well 97 in the
    middle of a run.

    A workbook this cannot be OPENED produces ``(None, None)``: a file that will
    not open says nothing about the plate, and the path validation the caller
    already ran reports it in better words than "could not open it" would.

    Every refusal the reader itself raises travels up instead. Those are
    judgements about the contents (a row read and not placed, a second WT row, a
    duplicate variant, a column that cannot be identified), and each of them is
    a mis-scored plate if let through. Swallowing them here is what put them
    after the demux: with ``draft`` back as ``None`` the caller re-read the same
    workbook further down and raised there, by which point the multi-minute
    ingest this check exists to precede had already run. The catch is deliberately
    narrow now, and widening it again re-creates that bug.

    ``wt_placement`` is the caller's own resolved value (``None`` takes
    :data:`~kuma_core.mame.layout.DEFAULT_WT_PLACEMENT` via
    :func:`~kuma_core.mame.layout.resolve_wt_placement`, the same function
    every ``wt_placement``-accepting RPC resolves the param with).
    ``handle_analyze`` passes what it read off ``params`` with that same
    function, so the draft this grades is the draft the run will place.
    ``handle_validate_inputs`` passes nothing: that RPC does not read
    ``wt_placement`` today, so its capacity check stays on the pre-2026-08-18
    default regardless of what a later run asks for.
    """
    from kuma_core.mame.io.variant_list import read_variant_source
    from kuma_core.mame.layout import (
        MUTANT_CAPACITY,
        build_draft_layout,
        resolve_wt_placement,
    )
    from kuma_core.mame.plate_geometry import PLATE_CAPACITY

    try:
        read = read_variant_source(
            expected_path, sheet=variant_sheet, variant_column=variant_column
        )
    except ValueError:
        # The reader's own verdict on the contents. ``read_variant_source``
        # documents ValueError as the type every one of its refusals takes, so
        # this is the whole of "the file is readable and says something that
        # cannot be placed". Raised, never swallowed.
        raise
    except Exception:  # noqa: BLE001 - "will not open" has no single type
        # Everything else: a missing path (FileNotFoundError), a file that is
        # not a workbook (zipfile.BadZipFile, which derives straight from
        # Exception rather than OSError), whatever openpyxl reaches for on a
        # truncated one. None of them is a statement about the plate, and the
        # caller's path validation already reported the file.
        return None, None
    # The whole read, not a subset of it. ``wells``/``wt_well`` are the
    # placement for a file that states one, and dropping them here would grade
    # and then place that file by row order instead.
    draft = build_draft_layout(
        read.expected,
        wt_ordinal=read.wt_ordinal,
        wells=read.wells,
        wt_well=read.wt_well,
        wt_placement=resolve_wt_placement(wt_placement),
    )

    if not draft.dropped_mutant_ids:
        return None, draft

    listed = ", ".join(draft.dropped_mutant_ids[:5])
    if len(draft.dropped_mutant_ids) > 5:
        listed += f", and {len(draft.dropped_mutant_ids) - 5} more"
    return (
        f"expected: {expected_path.name} lists {len(read.expected)} designed "
        f"mutants. One plate has {PLATE_CAPACITY} wells and the WT control "
        f"takes one of them, so it can carry {MUTANT_CAPACITY} mutants, and "
        "this run was given no well layout to say which of them are on the "
        "plate. One analyze run scores one plate; native barcodes are "
        "replicates of that plate, so a mutant past the last well carries no "
        "barcode of its own and would be scored as a repeat of an earlier "
        "well. Supply a well layout for this plate, or split the campaign and "
        f"run one plate at a time. Past the plate: {listed}."
    ), draft


def _barcode_seed_rule_error(barcodes_path: Path) -> str | None:
    """Does this barcode file say where its seeds end?

    The run derives the annealing tail from the file and refuses the workbook
    when neither axis states one; there is no fallback seed length any more
    (``combinatorial_demux._resolve_axis_prefixes``). Asking the same reader
    here is what keeps the button and the run from disagreeing: without it a
    workbook passes validation, the operator starts a multi-minute demux, and
    the refusal arrives at the point where it costs the most. The reader is the
    check rather than a copy of its rules, so the two cannot drift apart, and
    it reports the reader's own sentence, which names the axis, the arithmetic
    and (when a majority of rows agree) the rows at fault.

    Returns the message to put in front of the operator, or ``None`` when the
    file states its rule. Anything other than a refusal is not this check's
    business: a file that cannot be opened at all is reported by the path
    validation the caller already ran, and duplicating it here would put two
    sentences about one problem on the screen.
    """
    try:
        from kuma_core.mame.ingest.combinatorial_demux import (
            load_barcode_prefixes_with_provenance,
        )

        load_barcode_prefixes_with_provenance(barcodes_path)
    except ValueError as exc:
        return str(exc)
    except Exception:  # noqa: BLE001 - openpyxl surface is broad
        return None
    return None


def _plate_order_finding(params: dict, expected_path: Path) -> dict | None:
    """Does the expected workbook agree with its own primer plate sheets?

    A workbook that writes one plate two ways is a workbook nobody can read back:
    which of the two sheets describes the tubes that were pipetted is not recorded
    anywhere in the file. So this is graded ``blocking`` whenever it is found, and
    :func:`handle_validate_inputs` turns it into a validation error.

    It used to be downgraded to ``info`` when ``well_layout``
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


def _place_on_selected_wells(
    draft: "DraftLayout",
    selected_wells: list[str] | None,
) -> "DraftLayout":
    """Narrow the draft to the declared wells, or leave it alone.

    One function so every caller applies the selection at the same point and in
    the same way. ``None`` means nothing was declared, which is the draft's own
    wells, so the draft comes back untouched and byte-identical to what a run
    produced before this parameter existed. (Those used to be the leading
    ``N + 1`` wells; since 2026-08-18 the control well is H12 by default, so
    naming them by count would be wrong where naming them by draft is not.)

    The draft's placement is kept: an undeclared well drops what sits in it
    (``excluded_occupants``) rather than pulling the next occupant into it. See
    ``apply_well_selection``.
    """
    if selected_wells is None:
        return draft
    from kuma_core.mame.layout import apply_well_selection

    return apply_well_selection(draft, selected_wells)


def declared_designed_ids(
    designed_ids: frozenset[str],
    well_layout: dict[str, str] | None,
) -> frozenset[str]:
    """Narrow the designed-mutant denominator to the wells actually declared.

    Only for a run that declared a selection. What this removes is designed
    mutants the operator said are NOT ON THIS PLATE, which is a different thing
    from designed mutants that failed: ``kuma_core.mame.detected`` deliberately
    keeps a designed mutant with zero reads in the denominator so a run cannot
    lift its own rate by losing wells, and that rule is untouched here. A
    variant sitting in a declared well still counts against the run whether or
    not it produced anything; a variant sitting in no declared well was never
    part of the run to begin with.

    The narrowing reads ``well_layout``, which is the same mapping the scored
    wells are built from, so the numerator and the denominator come from one
    statement about the plate rather than two that can drift apart. That drift
    was the defect: a ten-well declaration in which every variant passed was
    reported as 9 % because the numerator had been narrowed to the declaration
    and the denominator was still the whole expected-mutations sheet.

    ``WT`` and any ``UNKNOWN_*`` occupant of a declared well are absent from
    ``designed_ids`` already and so cannot be added back by this intersection.
    """
    occupants = set((well_layout or {}).values())
    return frozenset(mid for mid in designed_ids if mid in occupants)


def _legacy_sample_map_finding(
    legacy_path: str | None,
    placed: "DraftLayout",
) -> dict | None:
    """Does an old project's sample map say the same plate the draft does?

    The sample map is gone as an input. A project that already has one still has
    a file on disk stating where every variant sits, written and checked by
    hand, and quietly ignoring it is the one option that cannot be defended: if
    the two disagree, one of them describes the tubes that were pipetted and
    the run would score the plate the operator did not build.

    So the file is read and compared, well by well, against the layout this run
    would use. Agreement is reported and the run proceeds; disagreement is named
    down to the well and refused. Either way the file is left alone: deleting an
    operator's record of the bench is not this handler's call.

    ``placed`` is the layout AFTER the well selection has been applied, because
    that is the plate the run will score. The selection used to be applied in
    here, which meant this function also had to decide what to do about a
    selection too short for the draft, and it decided to say nothing at all.

    Returns ``None`` when there is no legacy file, when it cannot be read, or
    when it holds no rows. ``{"path", "status", "differences", "wells_compared"}``
    otherwise, with ``status`` either ``"matches"`` or ``"differs"``.
    """
    if not legacy_path:
        return None
    try:
        from kuma_core.mame.ingest.sort_barcode import parse_sample_map
        from kuma_core.mame.plate_geometry import norm_well

        from_file = parse_sample_map(Path(legacy_path))
    except Exception:  # noqa: BLE001 - a legacy file that cannot be read is silent
        return None
    if not from_file:
        return None

    from_draft = {norm_well(well): sample for well, sample in placed.layout.items()}

    differences = [
        {
            "well": well,
            "file": from_file[well],
            "draft": from_draft.get(well, ""),
        }
        for well in sorted(set(from_file) | set(from_draft))
        if from_file.get(well, "") != from_draft.get(well, "")
    ]
    return {
        "path": str(legacy_path),
        "status": "differs" if differences else "matches",
        "differences": differences[:10],
        "wells_compared": len(set(from_file) | set(from_draft)),
    }


def _legacy_sample_map_error(payload: dict) -> str:
    """The validation error a disagreeing legacy sample map produces."""
    listed = "; ".join(
        f"{d['well']}: file says {d['file'] or '(empty)'}, "
        f"layout says {d['draft'] or '(empty)'}"
        for d in payload["differences"][:5]
    )
    return (
        f"sample map: {Path(payload['path']).name} disagrees with the layout "
        "this run would use. That file is no longer an input, so the run cannot "
        "follow it, and it is the only record of what was pipetted, so the run "
        "cannot ignore it either. Check which of the two describes the plate "
        "and fix the variant list or the well selection to match, then delete "
        f"the file. Disagreements: {listed}."
    )


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


def _acceptance_findings(params: dict) -> list[str]:
    """Refusals the Validate button and the run itself have to agree on.

    Returned as a list rather than raised, because the two entry points need
    different shapes: :func:`handle_validate_inputs` collects the lot so the
    operator sees every problem at once, and :func:`handle_analyze` raises the
    first. Sharing the *collector* and not the raise is what stops the button
    and the run from grading the same inputs differently, which they did until
    2026-08-07: the run refused an ``output`` the button never looked at, and
    the button refused a ``fastq_pass/`` selection the run walked straight past.

    That second one loses data rather than time. ``is_minknow_run_dir`` asks
    whether ``path/fastq_pass`` exists, so a run pointed at ``fastq_pass/``
    itself answers False, takes the pre-sorted consensus branch and scores
    whatever it finds there in silence.

    Asked on the run and not only behind the button for the same reason every
    other pre-run refusal here is mirrored: a CLI call, a harness, a script, an
    operator who never validated all go past the button, and the frontend's
    ``selectCanRun`` is not a defence the run can rely on.

    ``input_dir`` / ``output`` shape errors (missing, traversal, wrong
    extension) are left to the callers, which already report them under their
    own names; this collector only speaks where the two disagreed.
    """
    findings: list[str] = []

    input_dir = params.get("input_dir")
    if input_dir:
        try:
            input_path = _validate_dirpath(input_dir)
        except (FileNotFoundError, ValueError):
            input_path = None
        if input_path is not None:
            # Raw-run guardrails: catch the two most common misselections
            # before a multi-minute demux is kicked off.
            from kuma_core.mame.ingest import is_minknow_run_dir

            if input_path.name == "fastq_pass":
                findings.append(
                    "Select the MinKNOW run folder (the parent of fastq_pass/), "
                    "not fastq_pass/ itself."
                )
            elif is_minknow_run_dir(input_path) and not params.get(
                "custom_barcodes_xlsx"
            ):
                findings.append(
                    "custom_barcodes_xlsx is required when input_dir is a raw "
                    "MinKNOW run folder"
                )

    # Only when the caller states one. The MAME input screen picks an output
    # directory and names the workbook at run time, so a validation asked
    # before that is not missing an answer, it has not been asked the question.
    output = params.get("output")
    if output:
        try:
            _validate_output_path(
                output, allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
            )
        except (FileNotFoundError, ValueError) as exc:
            findings.append(f"output: {exc}")

    return findings


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
    barcode_axes: dict | None = None
    legacy_sample_map: dict | None = None

    # The refusals this screen shares with the run itself. Collected from the
    # one function both entry points call, so a green check here cannot mean
    # something the run will reject (see :func:`_acceptance_findings`).
    errors.extend(_acceptance_findings(params))

    # Parsed here, at the top, and reported under its own name. It used to be
    # parsed inside the ``expected`` block, where the enclosing
    # ``except ValueError`` relabelled "selected_wells is empty" as an
    # ``expected:`` problem and sent the operator to the wrong file. The
    # messages this raises already name the parameter, so they are appended
    # verbatim.
    try:
        selected_wells = _selected_wells_param(params)
    except ValueError as exc:
        selected_wells = None
        errors.append(str(exc))

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
            # The raw-run misselection guards live in ``_acceptance_findings``,
            # already collected above, because the run has to make the same two
            # refusals. What is left here is the barcode workbook itself, whose
            # contents this screen reports and the run reads for seeds.
            from kuma_core.mame.ingest import is_minknow_run_dir

            custom_barcodes_xlsx = params.get("custom_barcodes_xlsx")
            is_raw_run = is_minknow_run_dir(input_path)
            if custom_barcodes_xlsx:
                try:
                    barcodes_path = _validate_filepath(
                        custom_barcodes_xlsx,
                        allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS,
                    )
                except (FileNotFoundError, ValueError) as exc:
                    errors.append(f"custom_barcodes_xlsx: {exc}")
                else:
                    # What the file contains, whether or not it passes. Stated
                    # rather than inferred from a silent validation: two axes and
                    # a well count is the whole shape of the plate this run can
                    # name, and reading it back is how an operator confirms the
                    # workbook they picked is the one they meant.
                    barcode_axes = _barcode_axis_counts(barcodes_path)
                    layout_error = _barcode_layout_error(barcodes_path)
                    if layout_error is not None:
                        errors.append(layout_error)
                    elif is_raw_run:
                        # Only for a raw run, because that is the only mode
                        # that cuts seeds out of this file; a sorted-directory
                        # analysis never opens it, and refusing a workbook the
                        # run would not have read would block a correct job.
                        # After the layout check rather than beside it, for the
                        # reason the run orders them the same way: a workbook
                        # with no primer rows fails both, and the layout
                        # sentence names the row-naming rule.
                        seed_rule_error = _barcode_seed_rule_error(barcodes_path)
                        if seed_rule_error is not None:
                            errors.append(seed_rule_error)

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

            # The same plate-capacity gate the run applies, asked here for the
            # reason every other pre-run refusal in this handler is mirrored:
            # without it the workbook passes validation, the operator starts a
            # multi-minute demux, and the refusal arrives where it costs the
            # most. Same condition too, read off the params the frontend already
            # sends under the analyze names, so the button and the run agree
            # about which runs draft their own layout.
            if expected_readable and _layout_is_inferred(params):
                capacity_error, _draft = _plate_capacity_finding(
                    expected_path,
                    _optional_str(params.get("variant_sheet")),
                    _optional_str(params.get("variant_column")),
                )
                if capacity_error is not None:
                    errors.append(capacity_error)
                elif _draft is not None:
                    # The wells the run would score, decided here as well as in
                    # the run. Narrowing never refuses: an undeclared well is a
                    # well the campaign did not fill, and what the draft put
                    # there is simply not on this plate.
                    placed = _place_on_selected_wells(_draft, selected_wells)
                    # An old project's sample map, compared against the
                    # layout that replaced it rather than deleted or
                    # ignored. See :func:`_legacy_sample_map_finding`.
                    legacy_sample_map = _legacy_sample_map_finding(
                        _optional_str(params.get("legacy_sample_map_xlsx")),
                        placed,
                    )
                    if legacy_sample_map is not None and legacy_sample_map[
                        "status"
                    ] == "differs":
                        errors.append(_legacy_sample_map_error(legacy_sample_map))
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
    # Absent when no barcode workbook was given or it could not be read. The
    # frontend shows it as a line of text, never as something to change: which
    # axis is the plate row and which way the plate fills are properties of how
    # the barcodes were prepared, not of a run.
    if barcode_axes is not None:
        result["barcode_axes"] = barcode_axes
    # Absent when this project carries no legacy sample map, which is every
    # project created from here on.
    if legacy_sample_map is not None:
        result["legacy_sample_map"] = legacy_sample_map
    return result


def handle_analyze(params: dict) -> dict:
    """Run the full pipeline and cache the resulting artefacts for downstream RPCs.

    Two files come out of one run: the result workbook at ``output`` and the
    pick list beside it (:func:`picks_autosave_path`), written here rather
    than waiting for a manual export. Optional ``janus_settings`` carries the
    same fields the ``export_janus_mapping`` RPC accepts; the pick list pins
    ``output_schema`` to ``legacy5`` regardless of what the settings say, so
    the file only ever states the selection, never instrument columns. The
    outcome rides back on ``janus_autosave`` and never raises.

    The instrument mapping (``device``, the 8-column sheet the robot reads) is
    not written here. It states a deck that describes the room at the moment it
    is written, so unlike the pick list it must not be reasserted by every
    re-run; only a manual ``export_janus_mapping`` call writes it (see
    ``handlers/export.py``).

    Optional ``variant_sheet`` / ``variant_column`` name the sheet and column of a
    plain expected-variant list. Omitting both is auto-detection, which leaves a
    KURO export on the path it always took.

    Optional ``selected_wells`` says which wells the campaign occupies, and
    optional ``legacy_sample_map_xlsx`` points at an old project's sample map.
    Neither is read as a layout: the first re-seats the drafted one, the second
    is only compared against it. Both are handled before the demux, so a run
    they refuse is refused in seconds.

    Optional ``wt_placement`` names the control-well policy for a row-order
    list that names no well of its own; see ``BuildWellLayoutParams`` for the
    values and the default. Ignored for a file with a ``Well`` column, which
    states the control well itself. Only consulted when the layout is drafted
    (``well_layout`` absent): an explicit ``well_layout`` already says which
    well is the control, if any.
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

    # The refusals this run shares with the Validate button, from the one
    # function both call. Raised at the first finding because a run has nowhere
    # to put a list, and asked before anything is read because the cheapest
    # refusal is the one that happens before the demux.
    for finding in _acceptance_findings(params):
        raise ValueError(finding)

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
    # Raw-run only: which annealing tail the barcode workbook stated, and the
    # seed lengths cutting it left. Stays None in consensus-dir mode, which
    # reads no barcode file, so the response key is absent there.
    barcode_prefix_resolution = None
    resolved_raw_cds_start: int | None = None
    resolved_raw_cds_end: int | None = None
    # Whether the amplicon between the primer sites was cut out, or the supplied
    # reference is being aligned against unmodified. Only the second case can put
    # an expected mutation against a reference end, so the run-quality warning
    # needs this here. None in consensus-dir mode, which resolves no reference.
    amplicon_extracted: bool | None = None
    expected = _validate_filepath(
        params["expected"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )
    # Optional sheet/column for an expected list that is not a KURO export. Both
    # absent (any frontend built before this) means auto-detection, which routes a
    # KURO export to the strict reader exactly as before.
    from .barcode_package import _optional_str

    variant_sheet = _optional_str(params.get("variant_sheet"))
    variant_column = _optional_str(params.get("variant_column"))
    selected_wells = _selected_wells_param(params)
    # The control-well policy this run asked for. Resolved once here (same
    # function every wt_placement-accepting RPC resolves it with; see
    # kuma_core.mame.layout.resolve_wt_placement) and reused at both places
    # below that draft a layout out of ``expected``, so the plate this run
    # scores is the plate ``mame.build_well_layout`` drew for the same request
    # rather than the pre-2026-08-18 default regardless of what the operator
    # picked.
    from kuma_core.mame.layout import resolve_wt_placement

    wt_placement = resolve_wt_placement(params.get("wt_placement"))
    output = _validate_output_path(
        params["output"], allowed_extensions=_ALLOWED_EXCEL_EXTENSIONS
    )

    # Plate capacity, decided before the demux rather than after it. When this
    # run has to draft its own layout out of ``expected``, a designed list longer
    # than one plate has no answer it can give: the layout is keyed by well alone
    # and the native barcode is a replicate axis over that same plate, so a
    # mutant past the last well carries nothing to tell it apart and is scored as
    # a repeat of an earlier one. One read-only workbook read here costs a
    # fraction of the multi-minute demux it stops, which is why it sits ahead of
    # the raw-run block rather than inside it.
    #
    # ONLY asked when the layout is drafted. A run given ``well_layout`` was
    # told which wells it scores, and the designed list is then a lookup table
    # those wells index into, so a longer one is not an overflowing plate and
    # refusing it would block a configuration that ran correctly before this
    # check existed.
    #
    # The graded draft is kept and reused as the layout further down, so the
    # object that passed the check is the object that places the wells.
    drafted_layout: DraftLayout | None = None
    if _layout_is_inferred(params):
        plate_capacity_error, drafted_layout = _plate_capacity_finding(
            expected, variant_sheet, variant_column, wt_placement
        )
        if plate_capacity_error is not None:
            raise ValueError(plate_capacity_error)
        if drafted_layout is not None:
            # Which wells the campaign occupies, seated here rather than after
            # the demux. Too few wells for the occupants is a refusal, and a
            # refusal that waits for the ingest costs the operator the very run
            # it exists to stop. Absent selection returns the draft untouched,
            # so a run that declares nothing is byte-identical to one from
            # before this parameter existed.
            drafted_layout = _place_on_selected_wells(drafted_layout, selected_wells)
            # An old project's sample map, compared against the layout this run
            # would use, on the run and not only behind the validate button.
            # Same reason ``check_plate_order`` moved down here: nothing that
            # skips the button (a CLI call, a harness, a script, an operator who
            # never validated) went past this at all, and the file on disk names
            # a plate the run would otherwise contradict in silence.
            _legacy = _legacy_sample_map_finding(
                _optional_str(params.get("legacy_sample_map_xlsx")), drafted_layout
            )
            if _legacy is not None and _legacy["status"] == "differs":
                raise ValueError(_legacy_sample_map_error(_legacy))

    # A workbook that writes one plate two ways, refused here as well as on the
    # validate button. ``handle_validate_inputs`` was the only caller of
    # ``check_plate_order``, which left the run itself defended by nothing but
    # the frontend's ``selectCanRun``: a CLI call, a harness, or a script went
    # straight past it and scored every well against whichever of the two sheets
    # the reader happened to pick. Read-only and cheap, and ahead of the demux.
    _plate_order = _plate_order_finding(params, expected)
    if _plate_order is not None:
        raise ValueError(_plate_order_error(_plate_order))

    # Raw-run gate: a MinKNOW run folder (has ``fastq_pass/``) needs demux first;
    # a pre-demuxed consensus dir takes the legacy path untouched.
    is_raw = is_minknow_run_dir(input_dir)
    # Demux gate counters, filled in by ``ingest_run_folder`` on the raw-run
    # path only. Stays empty in consensus-dir mode: that path never runs the
    # aligner, so no read ever passes (or fails) a MAPQ/coverage gate here and
    # there is nothing to report. Left empty rather than zero-filled so the
    # response omits the keys instead of claiming "0 reads passed".
    demux_gate_counts: dict[str, int] = {}
    # The per-plate demux matrix, same raw-run-only reasoning as the counters
    # above. Each entry is one plate copy with its own DemuxStats and its
    # {R}_{F} -> reads mapping. This is the only measurement MAME makes of reads
    # that landed on a barcode combination the campaign never pipetted, and it
    # used to be computed inside ``ingest_run_folder`` and dropped there.
    demux_per_nb: list[dict] = []
    # Resume split for the same demux, kept in its own sink because
    # ``demux_gate_counts`` mirrors the DemuxStats field set exactly (one shape
    # in both demux modes). Same empty-not-zero-filled rule: only per-NB mode
    # has per-unit markers to resume from, so any other path leaves this empty
    # and the response omits the key.
    demux_resume_counts: dict[str, int] = {}
    # Unit directories sitting in the ingested directory that the run recorded
    # there did NOT produce, i.e. output left behind by an earlier run into the
    # same folder. Filled in by the ingest read below, and only where that
    # directory carries a run manifest to compare against: a directory somebody
    # else sorted makes no membership claim, so it leaves this empty and the
    # response omits the key rather than reporting "0 leftovers found" about a
    # question that was never asked. Same empty-not-zero-filled rule as the
    # three sinks above.
    ingest_strays: dict[str, Any] = {}
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
        # Plate-fit check, run on the run rather than only on the validate
        # button: ``inputSlice._demuxAndAnalyze`` calls this RPC directly, so a
        # file numbered past the 8x12 plate otherwise reaches a multi-minute
        # demux and comes back with wells that have no coordinate. One small
        # read-only workbook read, and still before the demux.
        #
        # Deliberately AFTER the amplicon and coverage refusal above. A workbook
        # with no primer rows at all fails both checks, and the coverage message
        # is the better of the two: it names the row-naming rule and shows the
        # arithmetic that will drop every read. Running this first would replace
        # it with the narrower "carries no barcode rows".
        layout_error = _barcode_layout_error(Path(raw_custom_barcodes_xlsx))
        if layout_error is not None:
            raise ValueError(layout_error)

        # How the barcode seeds are about to be cut, read before the demux so
        # the answer is on the response and in the result workbook. This also
        # refuses, by raising out of the reader, a workbook whose axes state no
        # shared annealing tail: there is no fallback seed length any more, and
        # a multi-minute demux over guessed seeds was the failure this whole
        # path exists to stop.
        #
        # Deliberately AFTER the amplicon, coverage and layout refusals above,
        # for the same reason the layout check is: a workbook with no primer
        # rows at all fails several of these, and the earlier messages name the
        # row-naming rule and show the arithmetic, which is the more useful of
        # the two answers.
        from kuma_core.mame.ingest.combinatorial_demux import (
            load_barcode_prefixes_with_provenance,
        )

        barcode_prefix_resolution = load_barcode_prefixes_with_provenance(
            Path(raw_custom_barcodes_xlsx)
        )

        reference_for_pipeline = amplicon_resolution.reference_fasta
        amplicon_extracted = amplicon_resolution.extracted
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
                per_nb_out=demux_per_nb,
                resume_out=demux_resume_counts,
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

    # Snapshot of the four thresholds just resolved, taken here rather than at
    # the response so it cannot be rebuilt from a different reading of
    # ``params`` than the one ``run_analyze`` was given. Rides out on
    # ``compare_params``; see the response for why these four and no others.
    #
    # ``_MIXED_CONFIDENT_DEPTH_FACTOR`` is imported from the classifier instead
    # of restated, so the reported floor is the floor that fired. The floor is
    # derived here too, by the classifier's own rule (None when the read-count
    # gate is off), so that reading it never means re-implementing the rule.
    from kuma_core.mame.compare.verdict import _MIXED_CONFIDENT_DEPTH_FACTOR

    compare_params = {
        "min_file_size_kb": min_file_size_kb,
        "min_read_count": min_read_count,
        "max_consensus_n_fraction": max_consensus_n_fraction,
        "many_mutation_cutoff": many_cutoff,
        "mixed_confident_depth_factor": _MIXED_CONFIDENT_DEPTH_FACTOR,
        "mixed_confident_read_count": (
            min_read_count * _MIXED_CONFIDENT_DEPTH_FACTOR
            if min_read_count is not None
            else None
        ),
    }

    # well_layout: optional well_id -> sample_name override. Fail-fast on a
    # malformed payload rather than silently ignoring it.
    #
    # ``layout_source`` records WHICH of the two branches actually produced the
    # mapping this run scored wells against, and rides into the response as
    # ``layout_provenance``. Without it a result cannot say whether a well was
    # placed by the operator or guessed by ``build_draft_layout`` from whatever
    # ``expected`` happens to be current -- the latter is exactly the failure
    # shape of the 2026-08 incident this file's mapping-integrity check was
    # written for: a stale ``expected`` produces a plausible-looking inferred
    # layout with nothing in the result to say it was inferred at all, let alone
    # from what file.
    #
    # There used to be a third branch, a sample-map xlsx. It stated the plate a
    # second time and nothing kept the two statements in step, so it is gone.
    # An old project's file is not ignored: both this handler (above, before the
    # demux) and ``validate_inputs`` compare it against the layout the run would
    # use and name the wells where they disagree.
    well_layout_raw = params.get("well_layout")
    well_layout: dict[str, str] | None = None
    layout_source: str
    # What this run declared and what came of it, both filled by the drafted
    # branch below. An explicit ``well_layout`` places the wells itself and no
    # selection is applied to it, so a result from that branch reports neither
    # rather than reporting a choice that did not reach a well.
    declared_wells: list[str] | None = None
    unused_wells: list[str] = []
    excluded_occupants: dict[str, str] = {}
    if well_layout_raw is not None:
        if not isinstance(well_layout_raw, dict) or not all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in well_layout_raw.items()
        ):
            raise ValueError("well_layout must be a mapping of well_id (str) to sample_name (str)")
        well_layout = well_layout_raw
        layout_source = "explicit_well_layout"
    else:
        # The draft the plate-capacity gate above already graded, reused rather
        # than rebuilt: same read and the same WT rule as
        # ``mame.build_well_layout``, and building it twice would be two chances
        # to disagree about the same file. ``None`` only when that read failed,
        # which the refusals further down report in their own words; an empty
        # layout there behaves as it did before the gate existed.
        if drafted_layout is None:
            from kuma_core.mame.io.variant_list import read_variant_source
            from kuma_core.mame.layout import build_draft_layout

            _inferred = read_variant_source(
                expected, sheet=variant_sheet, variant_column=variant_column
            )
            drafted_layout = _place_on_selected_wells(
                build_draft_layout(
                    _inferred.expected,
                    wt_ordinal=_inferred.wt_ordinal,
                    wells=_inferred.wells,
                    wt_well=_inferred.wt_well,
                    wt_placement=wt_placement,
                ),
                selected_wells,
            )
        # The selection is already applied: the block above did it for a draft
        # the capacity gate handed over, and this fallback does it for the one
        # it could not.
        well_layout = drafted_layout.layout
        unused_wells = list(drafted_layout.unused_wells)
        excluded_occupants = dict(drafted_layout.excluded_occupants)
        if selected_wells is not None:
            from kuma_core.mame.layout import normalise_selected_wells

            # The declaration in the column-major form the placement rule uses,
            # whatever order the caller sent it in.
            declared_wells = normalise_selected_wells(selected_wells)
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

    # Which wells this run judges, and what it refused to judge.
    #
    # Only a declared selection narrows this. Without one the layout names every
    # occupant the campaign has, an unlisted well is a well nobody said anything
    # about, and the pipeline keeps its old fallback verdict for it; passing
    # None leaves that path byte-identical.
    #
    # With one, an unlisted well is a well the operator declared EMPTY, and
    # scoring it was the defect: the fallback compares such a well against the
    # whole expected list, which nothing can match, so declaring ten wells on a
    # 96-well run came back with ten passes and eighty-six failures instead of
    # ten results. The reads are still there (leakage puts a few on
    # combinations nobody pipetted) and are still counted, as off-layout
    # records, which is what they are.
    _scored_wells: set[str] | None = (
        set(well_layout or {}) if selected_wells is not None else None
    )
    _skipped_records: dict[str, int] = {}

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
            # On the raw-run path ``input_dir`` was rebound to the demux output
            # directory above, and this is the SECOND read of that tree: the
            # demux already returned records that ``ingest_run_folder`` had
            # scoped to the units it wrote, and they are re-read here so the
            # raw-run and consensus-dir paths share one body. Nothing is passed
            # to scope this read, which is how a run selecting three native
            # barcodes came back with six plates. The scoping now comes from the
            # run manifest in the directory itself, so this call does not have
            # to state it; the sink is what carries the leftovers back out.
            raw_records = route_ingest(
                input_dir, ingest_mode_enum, strays_out=ingest_strays
            )
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
        if selected_wells is not None:
            # The same narrowing ``_scored_wells`` applies to the numerator,
            # applied to the denominator it is divided by. Without it the rate
            # is one population over another: nine declared variants all passing
            # came back as 9 % because the denominator was still the whole
            # ninety-five-row sheet. See ``declared_designed_ids``.
            dids = declared_designed_ids(dids, well_layout)

        # The provenance sentence goes into the workbook as well as onto the
        # response. The response key is for a caller that reads it; the workbook
        # row is what an operator opening the result actually sees, and the cut
        # itself is invisible in every other cell of it.
        _barcode_prefix_note = (
            barcode_prefix_resolution.note
            if barcode_prefix_resolution is not None
            else None
        )

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
                    well_layout=well_layout,
                    scored_wells=_scored_wells,
                    skipped_records_out=_skipped_records,
                    progress_callback=_band_callback,
                    records=raw_records,
                    expected_mutations=expected_mutations,
                    designed_mutant_ids=dids,
                    perf_scope=None,
                    barcode_prefix_note=_barcode_prefix_note,
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
                well_layout=well_layout,
                scored_wells=_scored_wells,
                skipped_records_out=_skipped_records,
                progress_callback=_band_callback,
                records=raw_records,
                expected_mutations=expected_mutations,
                designed_mutant_ids=dids,
                perf_scope=None,
                barcode_prefix_note=_barcode_prefix_note,
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
        barcode_prefix_note=_barcode_prefix_note,
    )

    # The pick list is the second artefact of the same run, so it is written here
    # rather than waiting for a manual export. Cached state is already set
    # above, so a failure here costs the file, never the analysis.
    # Post-hoc mapping sanity check (kuma_core.mame.qc): this is the ONLY place
    # left, after classification, that can see the failure signature a stale or
    # mis-drawn well_layout leaves behind -- every well individually classifies
    # fine against whatever expected set it was scoped to, and only comparing
    # observed changes across the whole plate exposes a systematic swap (see
    # kuma_core/mame/qc/mapping_integrity.py for the incident this guards).
    from kuma_core.mame.qc import check_mapping_integrity, observations_from_verdicts

    _mapping_integrity = check_mapping_integrity(observations_from_verdicts(verdicts))

    # What the demux matrix says about reads that landed outside the campaign.
    # Raw-run only: a consensus-dir run never demuxed, so there is no matrix and
    # no counter, and the key stays absent rather than reporting six unavailable
    # signals that would all say the same thing about the mode rather than
    # about the run.
    #
    # The occupancy handed over is ``well_layout``'s own keys, which is the set
    # the pipeline scored these verdicts against. Deliberately NOT the declared
    # selection: ``layout_provenance.selected_wells`` can be wider than the
    # campaign (``unused_wells`` names the surplus), and taking it here would
    # let one response carry two different answers to "which wells were
    # occupied" -- ``off_layout_records`` already reads the layout, and a read
    # would be off-layout there and on-layout here.
    contamination = None
    if is_raw:
        from kuma_core.mame.qc.contamination import analyze_contamination

        contamination = analyze_contamination(
            demux_per_nb,
            list(well_layout or {}),
            occupancy_source=layout_source,
        )

    # ── Could this run have worked at all ────────────────────────────────
    # Three facts the app was reading none of: how deep the typical scored well
    # is, how many pores the cell started with, and whether this project has
    # already sequenced on that cell. See kuma_core.mame.run_quality for why
    # depth grades and the other two only report.
    #
    # Depth comes from the VERDICTS, not from the ingested records, so it
    # measures the wells this run actually judged. A declared selection has
    # already removed the wells the campaign left empty by the time verdicts
    # exist, and grading their leaked reads as shallow wells would report a
    # thin plate for a run that deliberately used ten of ninety-six.
    from kuma_core.mame.ingest.flow_cell import (
        find_previous_use,
        read_flow_cell_history,
        read_ledger,
        record_use,
    )
    from kuma_core.mame.run_quality import (
        assess_run_quality,
        serialise_position_recurrence,
        serialise_run_quality,
        summarise_position_recurrence,
        variants_near_reference_edge,
    )

    # Mutations sitting against an end of the reference that was actually
    # aligned against. Only asked when extraction was skipped: an extracted
    # amplicon carries the primer anneal regions, which is exactly what puts a
    # terminal codon far enough inside the reference for the aligner to reach it.
    # ``reference`` is rebound to the extracted file in that case, so the length
    # read here is always the length reads were aligned to.
    _edge_variants: list[str] = []
    # Length of the reference reads were aligned to, i.e. the extracted amplicon
    # when extraction happened. Read once and shared: the edge check below needs
    # it, and the MIXED-factor scale check falls back to it when no well carried
    # a measured position count. None when unreadable, which both callers treat
    # as "not known" rather than as a number.
    _run_quality_reference_length: int | None
    try:
        _run_quality_reference_length = _read_reference_length(reference)
    except (OSError, ValueError):
        _run_quality_reference_length = None
    if amplicon_extracted is False and _run_quality_reference_length is not None:
        try:
            _edge_variants = variants_near_reference_edge(
                {em.mutant_id: em.position for em in expected_mutations},
                cds_start,
                _run_quality_reference_length,
            )
        except (OSError, ValueError):
            # An advisory sentence is never worth failing a finished run for.
            _edge_variants = []

    _flow_cell = read_flow_cell_history(input_dir)
    _ledger_root = output.parent
    _previous_use = find_previous_use(
        read_ledger(_ledger_root), _flow_cell.flow_cell_id, str(input_dir)
    )
    # One entry per scored record, so a run with replicate plates contributes
    # each plate's reading of a well. A ``None`` depth is a well whose consensus
    # header never stated one, which is not zero reads and is left out rather
    # than graded as the worst case.
    _well_reads = [
        int(vr.translated.barcode.read_count)
        for vr in verdicts
        if vr.translated.barcode.read_count is not None
    ]
    run_quality = serialise_run_quality(
        assess_run_quality(
            well_read_counts=_well_reads,
            min_read_count=min_read_count,
            flow_cell_id=_flow_cell.flow_cell_id,
            pore_start=_flow_cell.pore_start,
            pore_end=_flow_cell.pore_end,
            reused_from=_previous_use,
            amplicon_extracted=amplicon_extracted,
            edge_variants=_edge_variants,
            # The scale the MIXED confidence floor was derived over. Taken from
            # the same verdicts the depth is, for the same reason: a declared
            # selection has already removed the wells the campaign left empty.
            # The reference length is the fallback when no well measured a
            # position count (legacy consensus files), and it is read from the
            # reference reads were actually aligned to, which is the extracted
            # amplicon whenever extraction happened.
            well_eligible_positions=[
                int(vr.translated.barcode.n_eligible_positions) for vr in verdicts
            ],
            reference_length=_run_quality_reference_length,
        )
    )
    # Which reference positions came back well after well, nested on the same
    # block because it is another run-level fact read before the verdicts.
    # Aggregated over the VERDICTS for the same reason the depth above is: a
    # declared selection has already removed the wells the campaign left empty,
    # and counting their leaked reads' noisy positions would inflate a
    # recurrence tally with wells nobody pipetted into.
    #
    # No grading, by design: see summarise_position_recurrence for why neither
    # the well count nor the strand share carries a cut this repo will defend.
    run_quality["position_recurrence"] = serialise_position_recurrence(
        summarise_position_recurrence(vr.translated.barcode for vr in verdicts)
    )
    # What MinKNOW already measured about read lengths, nested on the same block
    # for the same reason: a run-level fact read before the verdicts, and one
    # more thing that decides whether the plate could have been scored. The N50
    # is quoted from the instrument rather than computed here.
    #
    # The reference length handed over is the one reads were ALIGNED to, which
    # is why it is read from `reference` at this point: that name has already
    # been rebound to the extracted amplicon when extraction happened. Reading
    # the original plasmid instead would divide a 3 kb N50 by a 7 kb backbone
    # and report a fragmented run as a clean one. Advisory in the same way as
    # `_edge_variants` above: a reference that cannot be read leaves the ratios
    # null and never fails a finished run.
    from kuma_core.mame.ingest.read_length import (
        read_read_length_qc,
        serialise_read_length_qc,
    )

    try:
        _reference_bp: int | None = _read_reference_length(reference)
    except (OSError, ValueError):
        _reference_bp = None
    # ``original_run_dir`` rather than ``input_dir``: on the raw-run path the
    # latter was rebound to the demux output directory, which is wherever the
    # caller asked the outputs to go and is not required to sit inside the
    # MinKNOW folder. The report json lives with the run.
    run_quality["read_length"] = serialise_read_length_qc(
        read_read_length_qc(original_run_dir if is_raw else input_dir),
        _reference_bp,
    )
    # Recorded after the grading, so this run cannot report itself as its own
    # earlier use, and only when the report json named a cell.
    record_use(
        _ledger_root,
        _flow_cell,
        str(input_dir),
        getattr(run_meta, "started", None) if run_meta is not None else None,
    )

    janus_params = params.get("janus_settings") or {}
    janus_autosave = _autosave_picks(replicates, output, run_meta, janus_params)

    response = {
        "verdicts": [_serialize_verdict(v) for v in verdicts],
        "replicates": [_serialize_replicate(r) for r in replicates],
        "output_path": str(output),
        "janus_autosave": janus_autosave,
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
            # The wells this run declared as occupied, in plate order. Stamped
            # onto the result rather than left in the frontend store because a
            # selection is what makes an empty well mean "nothing was pipetted
            # here" instead of "the draft ran out", and a result that cannot say
            # which wells were declared cannot be reproduced. null when the run
            # declared none, which reads as the leading N+1 wells.
            #
            # The DECLARATION, not the subset that found an occupant. Reporting
            # the placed wells made a declaration wider than the campaign
            # unreadable off the result: 96 wells declared against 31 occupants
            # came back as 31 wells, which is also what declaring exactly those
            # 31 looks like.
            "selected_wells": declared_wells,
            # Declared wells no occupant took, in plate order. Empty for every
            # run that declared none or declared exactly enough. Not a refusal:
            # selecting a column that turned out to hold fewer variants than
            # planned says nothing false about the bench, but dropping the
            # surplus in silence would leave the result unable to say the
            # declaration and the campaign were different sizes.
            "unused_wells": unused_wells,
            # Draft occupants whose well the declaration left out, ``{well:
            # sample}`` in plate order. The placement is anchored to the plate,
            # so leaving a well out means the campaign did not fill it and what
            # the draft put there was never sequenced. Empty for a run that
            # declared none or declared every occupied well.
            #
            # Reported rather than refused, and reported rather than dropped:
            # the variants named here have no verdict anywhere else on the
            # result, so without this the only trace of them is an absence.
            "excluded_occupants": excluded_occupants,
        },
        # Reads that arrived from wells the layout does not name. NOT a refusal:
        # a declared-empty well producing reads is the same signal as barcode
        # crosstalk, and which of the two it is cannot be decided from the count.
        # Reported so an operator can see it rather than having it disappear
        # into an UNKNOWN_* group.
        # Whether the run could have produced a scorable plate, and the numbers
        # behind that with the provenance of every threshold. Read BEFORE the
        # verdicts: a blocking severity here means every verdict below it is an
        # artefact of a plate that never had the depth to be scored.
        "run_quality": run_quality,
        "off_layout_records": _off_layout_records(
            verdicts, well_layout, _skipped_records
        ),
        # Stray-read signals read straight off the demux matrix
        # (kuma_core.mame.qc.contamination). Raw-run only, so the key is absent
        # in consensus-dir mode. Every signal inside is either a measurement or
        # an explicit ``state: "unavailable"`` with a reason: none is
        # zero-filled, because a 0 from a question that could not be asked reads
        # as a clean plate.
        **({"contamination": contamination} if contamination is not None else {}),
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
        # The thresholds this run was actually judged against. Every per-well
        # number in the response is a measurement, and a measurement without
        # the number it was compared to cannot be read: the caller has no way
        # to know that read_count=22 failed and 31 passed, because the default
        # applies whenever the caller omits the field (which the frontend does
        # for min_read_count) and nothing on the wire said so.
        #
        # Only the four values resolved above and handed to ``run_analyze``
        # appear here, plus the depth factor the MIXED gate multiplies
        # min_read_count by. ``CompareParams`` also carries
        # ``indel_window_codon`` / ``frameshift_window_bp`` /
        # ``max_indel_event_fraction``, and those are deliberately absent
        # because the handler never resolves them from ``params``: they sit at
        # their dataclass defaults on every run, so reporting them here would
        # state a caller decision nobody made. ``max_indel_event_fraction``
        # additionally gates a measurement that is not serialized at all
        # (``max_indel_event_fraction`` on BarcodeRecord), so its threshold
        # would have no number to stand beside.
        #
        # Reporting only. Values are read off the same locals the pipeline
        # received, so this key cannot drift from what judged the run.
        "compare_params": compare_params,
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
        # Why the reads that cleared both gates still failed to reach a well.
        # These seven partition the demux ``ambiguous_dropped`` total, which is
        # itself NOT surfaced here: a single number that mixes four unrelated
        # causes is what the operator could not act on, and the split is the
        # part that names something to fix. The short-window pair is keyed on
        # the READ END rather than the F/R axis on purpose; see the DemuxStats
        # docstring for why an axis-keyed tally splits one 3'-end phenomenon
        # across both axes according to strand and hides it.
        #
        # Same emission rule as the three gate counters: present only when the
        # demux reported them. Consensus-dir mode contributes nothing, and a
        # per-NB resume that reused a marker predating the breakdown omits all
        # seven rather than reporting zeros it did not measure.
        **{
            key: int(demux_gate_counts[key])
            for key in (
                "total_reads", "passed_mapq", "passed_coverage",
                "drop_short_window_read_5p", "drop_short_window_read_3p",
                "drop_no_barcode_f", "drop_no_barcode_r",
                "drop_ambiguous_tie_f", "drop_ambiguous_tie_r",
                "drop_both_axes",
            )
            if key in demux_gate_counts
        },
        # Resume split for the demux this run drove: per-barcode units reseeded
        # from a prior run's completion marker vs recomputed here. Reuse is
        # already gated on a matching reference/parameter fingerprint
        # (``marker_inputs_match``), so this is not a correctness warning; it is
        # the only place the operator can see that part of the result predates
        # this run, which is what an earlier "why does this look wrong" had no
        # way to check. Emitted only when the demux reported it (per-NB raw-run
        # mode); consensus-dir and single-pool modes leave the key absent rather
        # than sending a zero that would read as "nothing was reused".
        **(
            {
                "demux_resume": {
                    "reused_units": int(demux_resume_counts["reused_units"]),
                    "recomputed_units": int(
                        demux_resume_counts["recomputed_units"]
                    ),
                }
            }
            if "reused_units" in demux_resume_counts
            else {}
        ),
        # Unit directories in the ingested folder that the run recorded there
        # did not produce. Reported, never acted on: the files are left exactly
        # where they are, because deleting a previous run output is the
        # operator's decision and not this handler's. The names ride along
        # because "three leftover plates" is not actionable and
        # "sort_barcode15, 16, 17 belong to the run of 2026-08-10" is.
        #
        # Emitted only where the read had a manifest to compare against, which
        # is what makes an empty ``names`` meaningful: it says this folder was
        # checked and holds nothing stale, as against the key being absent,
        # which says no membership record existed to check. A directory someone
        # else sorted is the second case and must stay silent.
        **(
            {
                "stale_units": {
                    "names": [str(n) for n in ingest_strays.get("names", [])],
                    "run_dir": str(ingest_strays.get("manifest_run_dir", "")),
                    "written_at": str(ingest_strays.get("manifest_written_at", "")),
                }
            }
            if "names" in ingest_strays
            else {}
        ),
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
        # Raw-run only. Says what was cut off the barcode seeds this run matched
        # against: the tail derived from the workbook, per axis, and the seed
        # lengths it left behind. There is one rule and no alternatives to name,
        # because a workbook that states no tail is refused before the demux
        # starts, so this payload is the cut itself rather than a label for
        # which of several rules was picked. It is worth carrying because the
        # cut is otherwise invisible: the operator can check the tail and the
        # seed lengths against the seed workbook the primers were ordered from.
        # The same sentence goes into the result workbook as the
        # ``barcode_prefix_rule`` row of ``__kuma_meta__``, which is the copy an
        # operator actually sees; this key is for a caller that reads it.
        **(
            {"barcode_prefix_resolution": barcode_prefix_resolution.as_dict()}
            if barcode_prefix_resolution is not None
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
