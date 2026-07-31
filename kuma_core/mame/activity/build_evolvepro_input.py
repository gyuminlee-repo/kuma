"""Build an EVOLVEpro input xlsx from a MAME activity round.

This wires the four xlsx inputs of one MAME round into a single EVOLVEpro
input file (Variant, activity), merging two measurement sources in the short
EVOLVEpro variant space (no ref_seq, no internal notation round-trip):

  1. fallback (GC data + plate layout): one relative-activity replicate per
     mutant, taken from the pre-normalised GC sheet keyed by well position.
  2. authoritative (Agilent rep-batch report): three raw-area replicates per
     numeric base ID, normalised against the WT block areas, mapped onto a
     short variant via a rank-based ID->variant table derived from the
     previous EVOLVEpro file.

The authoritative source wins where both define a variant (replicate-priority
merge). The ID->variant rank assumption is isolated in build_id_variant_mapping
so it can be swapped without touching the rest of the pipeline, and the table
is emitted as a JSON audit artifact for human veto.

Spec inputs (see module-level constants for the file roles):
  (1) plate layout xlsx     -> parse_plate_layout_xlsx  (mutant <-> well)
  (2) GC data xlsx          -> parse_relative_only      (well -> relative)
  (3) Agilent rep-batch xlsx-> parse_agilent_block_rep_batch (id -> 3 raw reps)
  (4) previous EVOLVEpro xlsx-> read_evolvepro_rows      (rank order, descending)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .evolvepro_xlsx import (
    BlockRepBatchResult,
    parse_agilent_block_rep_batch,
    parse_agilent_standard,
    parse_relative_only,
    read_evolvepro_rows,
    write_evolvepro_xlsx,
    write_relative_activity_xlsx,
)
from .label_audit import LabelAudit, audit_labels
from .merge import merge_replicates_priority
from .numeric_id_decode import DecodeResult, decode_confirmation, decode_primary_screen
from .models import MergeReplicatesStats, Variant
from .plate_layout_xlsx import parse_plate_layout_xlsx, _normalise_well
from .sanity_check import detect_label_swap
from .variant_notation import to_evolvepro, is_canonical_internal, _SHORT_RE

logger = logging.getLogger(__name__)

# Fixed EVOLVEpro output header (single source of truth lives in
# write_evolvepro_xlsx; repeated here only for the audit metadata).
_OUTPUT_COLUMNS = ("Variant", "activity")

_WT_LITERAL = "WT"


# ---------------------------------------------------------------------------
# Mapping (isolated single function for veto / hot-swap)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MappingRow:
    """One ID->variant assignment plus its provenance for the audit artifact.

    id: 1-based numeric base ID from the Agilent rep-batch report.
    variant: short EVOLVEpro variant assigned to that ID by rank.
    well: optional well position when the variant also appears in the plate
        layout (lets a reviewer cross-check the layout against the rank).
    """

    id: int
    variant: str
    well: str | None = None


@dataclass
class IdVariantMapping:
    """Result of build_id_variant_mapping.

    rows: ordered MappingRow list (one per numeric base ID present in source 3).
    prev_descending: True when the previous EVOLVEpro file rows were in
        non-increasing activity order. The rank assumption holds only when
        this is True; a False value is a veto signal, not an auto-fix trigger.
    n_prev_variants: number of non-WT variants read from source 4 (the rank
        universe size).
    warnings: human-readable strings describing any rank/coverage issue.
    """

    rows: list[MappingRow]
    prev_descending: bool
    n_prev_variants: int
    warnings: list[str] = field(default_factory=list)

    def id_to_variant(self) -> dict[int, str]:
        return {r.id: r.variant for r in self.rows}


def build_id_variant_mapping(
    block_result: BlockRepBatchResult,
    prev_ep_rows: list[tuple[str, float]],
    well_by_variant: dict[str, str] | None = None,
) -> IdVariantMapping:
    """Assign each numeric base ID a short variant by previous-round rank.

    Assumption (audited, vetoable): the Agilent rep-batch base IDs are a
    contiguous 1..N rank into the previous EVOLVEpro file, which is ordered by
    descending activity. So base ID i maps to the i-th non-WT row of source 4
    (1-based: ID 1 -> top-ranked variant). The previous file order is used as
    given (physical row order); this function does not re-sort it. Whether the
    file is actually descending is reported via prev_descending for veto.

    Args:
        block_result: parse_agilent_block_rep_batch output (the source of IDs).
        prev_ep_rows: read_evolvepro_rows output for source 4 (ordered).
        well_by_variant: optional {short_variant: well_id} from the layout, used
            only to annotate the audit rows. Not used for the assignment.

    Returns:
        IdVariantMapping with one row per base ID, in ascending ID order.
    """
    warnings: list[str] = []

    non_wt = [(v, a) for v, a in prev_ep_rows if v.upper() != _WT_LITERAL]
    activities = [a for _, a in non_wt]
    prev_descending = all(
        activities[i] >= activities[i + 1] for i in range(len(activities) - 1)
    )
    if not prev_descending:
        warnings.append(
            "Previous EVOLVEpro file is not strictly descending by activity; "
            "rank-based ID mapping uses physical row order regardless. "
            "Review the mapping audit before trusting it."
        )

    seen: set[str] = set()
    duplicates = sorted({v for v, _ in non_wt if (v in seen) or seen.add(v)})
    if duplicates:
        warnings.append(
            "Previous EVOLVEpro file has duplicate variant labels "
            f"({', '.join(duplicates)}); ranks below the first duplicate may "
            "be misaligned."
        )

    well_lookup = well_by_variant or {}
    rows: list[MappingRow] = []
    for base_id in sorted(block_result.reps):
        rank_idx = base_id - 1  # 1-based ID -> 0-based row index
        if rank_idx < 0 or rank_idx >= len(non_wt):
            warnings.append(
                f"Base ID {base_id} has no rank-{base_id} variant in the "
                f"previous EVOLVEpro file ({len(non_wt)} non-WT variants); "
                "this ID is dropped from the mapping."
            )
            continue
        variant = non_wt[rank_idx][0]
        rows.append(
            MappingRow(id=base_id, variant=variant, well=well_lookup.get(variant))
        )

    return IdVariantMapping(
        rows=rows,
        prev_descending=prev_descending,
        n_prev_variants=len(non_wt),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

@dataclass
class BuildEvolveproResult:
    """Outcome of build_evolvepro_input."""

    output_path: Path
    mapping_audit_path: Path
    n_variants: int
    n_authoritative: int
    n_fallback_only: int
    mapping: IdVariantMapping
    replicate_stats: MergeReplicatesStats
    warnings: list[str]
    swap_warnings: list  # list[SwapWarning]
    # Confidence of the written activity table:
    #   "provisional" — fallback only (layout + 1-replicate GC; no rep-batch
    #                   confirmation and no previous-round rank mapping).
    #   "confirmed"   — rep-batch authoritative reps merged in.
    confidence: str = "confirmed"
    # QC: variants whose authoritative (3-replicate confirmation) mean diverged
    # from the fallback (1-replicate primary screen) mean beyond the merge
    # threshold. Each entry carries both means so a reviewer can eyeball the gap.
    mismatched: list[dict] = field(default_factory=list)


def _unconvertible_warnings(
    unconvertible: dict[str, list[str]],
    source_label: str,
) -> list[str]:
    """One warning per mutant that has no EVOLVEpro short-notation form.

    EVOLVEpro short notation carries a single position, so a multi-substitution
    label such as 'A40P_E61Y' has no representation. Such mutants are dropped
    from *source_label* rather than aborting the whole build. Wells are listed
    so a reviewer can find the missing rows in the layout.
    """
    return [
        f"Layout mutant {mutant!r} (wells {', '.join(wells)}) cannot be "
        "converted to EVOLVEpro short notation (multiple substitutions); "
        f"excluded from the {source_label}."
        for mutant, wells in unconvertible.items()
    ]


def _build_fallback(
    layout_xlsx: str | Path,
    gc_data_xlsx: str | Path,
) -> tuple[dict[str, list[float]], dict[str, str], list[str]]:
    """Build the fallback {short_variant: [relative]} from layout + GC data.

    For each (mutant, well) in the layout, take the GC relative value of that
    well as the single fallback replicate. Wells absent from the GC sheet (and
    WT wells) are excluded with a warning.

    Returns:
        (fallback, well_by_variant, warnings) where well_by_variant maps each
        included short variant to its layout well (for the audit).
    """
    warnings: list[str] = []

    layout_entries = parse_plate_layout_xlsx(layout_xlsx)
    gc_records = parse_relative_only(gc_data_xlsx)

    # GC sample names are raw well positions (e.g. 'A1'); the layout well_id is
    # zero-padded (e.g. 'A01'). Normalise the GC side so the join matches.
    gc_by_well: dict[str, float] = {}
    for rec in gc_records:
        try:
            key = _normalise_well(rec.sample_name)
        except (ValueError, IndexError):
            # Non-well sample name in the GC sheet (defensive); skip it.
            warnings.append(
                f"GC data sample name {rec.sample_name!r} is not a well "
                "position; skipped."
            )
            continue
        gc_by_well[key] = rec.area

    fallback: dict[str, list[float]] = {}
    well_by_variant: dict[str, str] = {}
    unconvertible: dict[str, list[str]] = {}
    for entry in layout_entries:
        if entry.is_wt:
            continue
        if entry.well_id not in gc_by_well:
            warnings.append(
                f"Layout mutant {entry.mutant!r} (well {entry.well_id}) has no "
                "GC data value; excluded from the fallback source."
            )
            continue
        try:
            short = to_evolvepro(entry.mutant)
        except ValueError:
            unconvertible.setdefault(entry.mutant, []).append(entry.well_id)
            continue
        fallback.setdefault(short, []).append(gc_by_well[entry.well_id])
        well_by_variant[short] = entry.well_id

    warnings.extend(_unconvertible_warnings(unconvertible, "fallback source"))
    return fallback, well_by_variant, warnings


def _build_authoritative(
    block_result: BlockRepBatchResult,
    mapping: IdVariantMapping,
) -> dict[str, list[float]]:
    """Build authoritative {short_variant: [relative_reps]} from rep-batch.

    The raw replicate areas of each base ID are normalised by the mean WT area
    (relative = area / mean(WT areas)), then keyed by the rank-assigned short
    variant.

    Raises:
        ValueError: WT block areas are empty (cannot normalise).
    """
    wt_areas = block_result.wt_areas
    if not wt_areas:
        raise ValueError(
            "Agilent rep-batch report has no WT block areas; cannot normalise "
            "raw areas to relative activity."
        )
    wt_mean = sum(wt_areas) / len(wt_areas)
    if wt_mean <= 0:
        raise ValueError(
            f"WT mean area must be > 0 (computed {wt_mean:.6g} from "
            f"{wt_areas})"
        )

    id_to_variant = mapping.id_to_variant()
    authoritative: dict[str, list[float]] = {}
    for base_id, reps in block_result.reps.items():
        variant = id_to_variant.get(base_id)
        if variant is None:
            # ID dropped by the mapping (out of rank range); already warned.
            continue
        authoritative[variant] = [area / wt_mean for area in reps]
    return authoritative


def _write_mapping_audit(
    mapping: IdVariantMapping,
    audit_path: Path,
) -> None:
    """Write the ID->variant mapping table as a JSON veto artifact."""
    payload = {
        "columns": ["id", "variant", "well"],
        "prev_descending": mapping.prev_descending,
        "n_prev_variants": mapping.n_prev_variants,
        "mapping": [
            {"id": r.id, "variant": r.variant, "well": r.well}
            for r in mapping.rows
        ],
        "warnings": mapping.warnings,
    }
    audit_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def build_evolvepro_input(
    layout_xlsx: str | Path,
    gc_data_xlsx: str | Path,
    output_xlsx: str | Path,
    *,
    rep_batch_xlsx: str | Path | None = None,
    prev_evolvepro_xlsx: str | Path | None = None,
    mismatch_threshold: float = 0.1,
    mapping_audit_path: str | Path | None = None,
) -> BuildEvolveproResult:
    """Assemble an EVOLVEpro input xlsx from the four MAME round files.

    Pipeline:
        1. fallback   = layout x GC data  (one relative replicate per mutant)
        2. mapping    = rank ID->variant from the previous EVOLVEpro file
        3. authoritative = rep-batch raw reps / mean(WT areas), keyed by mapping
        4. merged     = merge_replicates_priority(authoritative, fallback)
        5. sorted desc by merged activity -> write_evolvepro_xlsx
        6. label-swap guard against the previous EVOLVEpro file (advisory)

    The merge operates purely in the short EVOLVEpro variant space, so no
    ref_seq or internal-notation conversion is required.

    Args:
        layout_xlsx:        plate layout xlsx (mutant <-> well).
        gc_data_xlsx:       pre-normalised GC data xlsx (well -> relative).
        rep_batch_xlsx:     Agilent FID1B rep-batch xlsx (numeric id -> 3 reps).
        prev_evolvepro_xlsx:previous-round EVOLVEpro xlsx (rank order).
        output_xlsx:        destination xlsx. Parent directory must exist.
        mismatch_threshold: merge mismatch-flag threshold (passed through).
        mapping_audit_path: where to write the ID->variant JSON audit. Defaults
            to '<output>.mapping.json' next to output_xlsx.

    Returns:
        BuildEvolveproResult.

    Raises:
        ValueError: WT areas missing, empty replicate list, or no variants to
            write (every source empty).
        FileNotFoundError: output parent directory missing (from writer).
    """
    output_path = Path(output_xlsx)
    if mapping_audit_path is None:
        audit_path = output_path.with_suffix(".mapping.json")
    else:
        audit_path = Path(mapping_audit_path)

    # The numeric-index confirmation axis needs both the rep-batch report and
    # the rank source. Supplying only one degrades to a provisional build.
    partial_confirmation = (rep_batch_xlsx is None) != (prev_evolvepro_xlsx is None)
    if partial_confirmation:
        rep_batch_xlsx = None
        prev_evolvepro_xlsx = None

    axes = build_evolvepro_input_axes(
        output_path,
        gc_data_xlsx=gc_data_xlsx,
        layout_xlsx=layout_xlsx,
        rep_batch_xlsx=rep_batch_xlsx,
        rank_evolvepro_xlsx=prev_evolvepro_xlsx,
        mismatch_threshold=mismatch_threshold,
        mapping_audit_path=audit_path,
    )

    warnings = list(axes.warnings)
    if partial_confirmation:
        warnings.append(
            "Only one of rep_batch_xlsx / prev_evolvepro_xlsx was supplied; "
            "both are required for confirmation. Producing a provisional "
            "(fallback-only) result."
        )

    return BuildEvolveproResult(
        output_path=axes.output_path,
        mapping_audit_path=audit_path,
        n_variants=axes.n_variants,
        n_authoritative=axes.n_authoritative,
        n_fallback_only=axes.n_fallback_only,
        mapping=axes.mapping,
        replicate_stats=axes.replicate_stats,
        warnings=warnings,
        swap_warnings=axes.swap_warnings,
        confidence=axes.confidence,
        mismatched=axes.mismatched,
    )


# ---------------------------------------------------------------------------
# Reports mode (raw Agilent round-1 + variant-labeled re-measure; no rank file)
# ---------------------------------------------------------------------------

@dataclass
class BuildEvolveproReportsResult:
    """Outcome of build_evolvepro_input_from_reports (variant-labeled mode)."""

    output_path: Path
    n_variants: int
    n_authoritative: int
    n_fallback_only: int
    well_by_variant: dict[str, str]
    replicate_stats: MergeReplicatesStats
    warnings: list[str]
    mismatched: list[dict] = field(default_factory=list)
    # NGS verdict gating (optional): short variants dropped because their layout
    # well carried an explicit non-PASS verdict. Empty when no verdict file given.
    n_ngs_excluded: int = 0
    ngs_excluded: list[str] = field(default_factory=list)
    # Optional audit artifact: the intermediate well-level relative activity
    # derived from a raw round-1 report, written in the 'GC data' shape. None
    # when no export path was requested or the round-1 source was not raw.
    gc_export_path: Path | None = None


def _agilent_wt_mean(records: list) -> float:
    """Mean WT block area from parse_agilent_standard records. Raises if none."""
    wt = [r.area for r in records if r.is_wt]
    if not wt:
        raise ValueError(
            "report has no WT blocks; cannot normalise raw areas to relative activity"
        )
    m = sum(wt) / len(wt)
    if m <= 0:
        raise ValueError(f"WT mean area must be > 0 (computed {m:.6g})")
    return m


def _normalize_variant_label(label: str) -> str | None:
    """Re-measure sample label -> short EVOLVEpro notation.

    'V5F' (internal) -> '5F'; '5F' (already short) -> '5F'; non-variant -> None.
    """
    s = label.strip()
    if is_canonical_internal(s):
        return to_evolvepro(s)
    if _SHORT_RE.match(s):
        return s
    return None


def _build_fallback_from_raw_report(
    round1_report_xlsx,
    layout_xlsx,
) -> tuple[dict[str, list[float]], dict[str, str], list[str]]:
    """Fallback {short_variant: [relative]} from a raw Agilent round-1 report.

    Sample names are well coordinates; raw area / mean(WT block area) = relative.
    Mapped to short variant via plate layout. Non-well names and wells absent
    from the layout are skipped with a warning. WT and calibration rows are
    already excluded by parse_agilent_standard / the is_wt flag.
    """
    warnings: list[str] = []
    records = parse_agilent_standard(round1_report_xlsx)
    wt_mean = _agilent_wt_mean(records)

    layout_entries = parse_plate_layout_xlsx(layout_xlsx)
    well_to_variant: dict[str, str] = {
        e.well_id: e.mutant for e in layout_entries if not e.is_wt
    }

    fallback: dict[str, list[float]] = {}
    well_by_variant: dict[str, str] = {}
    unconvertible: dict[str, list[str]] = {}
    for r in records:
        if r.is_wt:
            continue
        try:
            well = _normalise_well(r.sample_name)
        except (ValueError, IndexError):
            warnings.append(
                f"round-1 report sample {r.sample_name!r} is not a well position; skipped."
            )
            continue
        variant_internal = well_to_variant.get(well)
        if variant_internal is None:
            warnings.append(f"round-1 well {well} has no layout mutant; skipped.")
            continue
        try:
            short = to_evolvepro(variant_internal)
        except ValueError:
            unconvertible.setdefault(variant_internal, []).append(well)
            continue
        fallback.setdefault(short, []).append(r.area / wt_mean)
        well_by_variant[short] = well
    warnings.extend(_unconvertible_warnings(unconvertible, "round-1 fallback source"))
    return fallback, well_by_variant, warnings


def _export_round1_relative_activity(
    round1_report_xlsx,
    gc_export_xlsx,
) -> Path:
    """Write the round-1 well-level relative activity as a 'GC data' shaped xlsx.

    A pure projection over the parsed round-1 records: every non-WT record
    contributes one row of (sample name verbatim, area / mean WT block area),
    in report order. No layout lookup and no well normalisation, so the row
    count equals the non-WT record count and the file round-trips through
    parse_relative_only. Calibration rows are already dropped by
    parse_agilent_standard.
    """
    records = parse_agilent_standard(round1_report_xlsx)
    wt_mean = _agilent_wt_mean(records)
    rows = [(r.sample_name, r.area / wt_mean) for r in records if not r.is_wt]
    export_path = Path(gc_export_xlsx)
    write_relative_activity_xlsx(rows, export_path)
    return export_path


def _build_authoritative_from_variant_report(
    remeasure_report_xlsx,
) -> tuple[dict[str, list[float]], list[str]]:
    """Authoritative {short_variant: [relative reps]} from a variant-labeled report.

    Sample names are variant labels (internal 'V5F' or short '5F'); repeated
    labels are replicates. Raw area / mean(WT block area) = relative. Non-variant
    labels skipped with a warning.
    """
    warnings: list[str] = []
    records = parse_agilent_standard(remeasure_report_xlsx)
    wt_mean = _agilent_wt_mean(records)

    authoritative: dict[str, list[float]] = {}
    for r in records:
        if r.is_wt:
            continue
        short = _normalize_variant_label(r.sample_name)
        if short is None:
            warnings.append(
                f"re-measure sample {r.sample_name!r} is not a variant label; skipped."
            )
            continue
        authoritative.setdefault(short, []).append(r.area / wt_mean)
    return authoritative, warnings


def _build_fallback_from_prev_evolvepro(
    prev_evolvepro_xlsx,
) -> tuple[dict[str, list[float]], list[str]]:
    """Fallback {short_variant: [activity]} from a previous-round EVOLVEpro file.

    The previous EVOLVEpro xlsx is already in short variant space (Variant,
    activity), so each row is one round-1 activity per variant. WT rows are
    skipped; non-variant labels are skipped with a warning. Used as the round-1
    baseline when the full round-1 already lives as an EVOLVEpro file rather than
    a raw Agilent report.
    """
    warnings: list[str] = []
    fallback: dict[str, list[float]] = {}
    for variant, activity in read_evolvepro_rows(prev_evolvepro_xlsx):
        if variant.upper() == _WT_LITERAL:
            continue
        short = _normalize_variant_label(variant)
        if short is None:
            warnings.append(
                f"previous EVOLVEpro variant {variant!r} is not a variant label; skipped."
            )
            continue
        fallback.setdefault(short, []).append(float(activity))
    return fallback, warnings


def _well_by_variant_from_layout(layout_xlsx) -> dict[str, str]:
    """short variant -> well from the plate layout (for optional NGS gating).

    Non-canonical mutant rows (controls, blanks, WT replicate labels not caught
    by is_wt, multi-substitution or lowercase labels) are skipped rather than
    raising, mirroring the raw-report path. For valid single-substitution layouts
    this is identical to mapping every entry (V5F -> 5F either way).
    """
    well_by_variant: dict[str, str] = {}
    for e in parse_plate_layout_xlsx(layout_xlsx):
        if e.is_wt:
            continue
        short = _normalize_variant_label(e.mutant)
        if short is not None:
            well_by_variant[short] = e.well_id
    return well_by_variant


def build_evolvepro_input_from_reports(
    layout_xlsx,
    round1_report_xlsx,
    remeasure_report_xlsx,
    output_xlsx,
    *,
    mismatch_threshold: float = 0.1,
    verdict_xlsx: str | Path | None = None,
    prev_evolvepro_xlsx: str | Path | None = None,
    gc_export_xlsx: str | Path | None = None,
) -> BuildEvolveproReportsResult:
    """Assemble an EVOLVEpro input xlsx from round-1 + a variant-labeled re-measure.

    Round-1 baseline (fallback) comes from one of two sources:
      - raw Agilent standard report (well-named) + plate layout, or
      - a previous-round EVOLVEpro file (``prev_evolvepro_xlsx``, Variant/activity)
        when the full round-1 already lives in EVOLVEpro form.
    Re-measure: variant-labeled report -> n relative replicates per variant
    (authoritative). Authoritative mean replaces fallback where both define a
    variant; other variants keep their round-1 value.

    ``gc_export_xlsx`` optionally writes the intermediate round-1 well-level
    relative activity ('Sample Name', 'Area') as a review artifact, the same
    role the mapping JSON plays in rank mode. It applies to the raw round-1
    path only; on the previous-EVOLVEpro path it records a warning instead.
    """
    if prev_evolvepro_xlsx is None and (
        layout_xlsx is None or round1_report_xlsx is None
    ):
        raise ValueError(
            "raw round-1 mode requires both layout_xlsx and round1_report_xlsx; "
            "pass prev_evolvepro_xlsx to use a previous EVOLVEpro file as round-1."
        )

    axes = build_evolvepro_input_axes(
        output_xlsx,
        round1_report_xlsx=(
            None if prev_evolvepro_xlsx is not None else round1_report_xlsx
        ),
        round1_evolvepro_xlsx=prev_evolvepro_xlsx,
        layout_xlsx=layout_xlsx,
        remeasure_report_xlsx=remeasure_report_xlsx,
        mismatch_threshold=mismatch_threshold,
        verdict_xlsx=verdict_xlsx,
        gc_export_xlsx=gc_export_xlsx,
        no_variants_message=(
            "No variants to write: both round-1 and re-measure sources are "
            "empty after parsing."
        ),
    )

    return BuildEvolveproReportsResult(
        output_path=axes.output_path,
        n_variants=axes.n_variants,
        n_authoritative=axes.n_authoritative,
        n_fallback_only=axes.n_fallback_only,
        well_by_variant=axes.well_by_variant,
        replicate_stats=axes.replicate_stats,
        warnings=axes.warnings,
        mismatched=axes.mismatched,
        n_ngs_excluded=axes.n_ngs_excluded,
        ngs_excluded=axes.ngs_excluded,
        gc_export_path=axes.gc_export_path,
    )


# ---------------------------------------------------------------------------
# Two-axis entry point (primary screen x confirmation)
# ---------------------------------------------------------------------------

# Axis A, what carries the 1-replicate primary screen (exactly one required).
PRIMARY_RAW_REPORT = "raw_report"           # raw Agilent report (well labels)
PRIMARY_GC_SHEET = "gc_sheet"               # pre-normalised GC sheet (well labels)
PRIMARY_PREV_EVOLVEPRO = "prev_evolvepro"   # previous EVOLVEpro file (variant labels)
PRIMARY_NUMERIC_REPORT = "numeric_report"   # numeric sample IDs, whole plate

# Axis B, how the n-replicate confirmation labels its samples (at most one).
CONFIRM_VARIANT_LABELS = "variant_labels"   # variant-labeled Agilent report
CONFIRM_NUMERIC_INDEX = "numeric_index"     # numeric base IDs + rank source
CONFIRM_NUMERIC_SUBSET = "numeric_subset"   # numeric IDs into the above-WT subset
CONFIRM_NONE = "none"                       # provisional, no confirmation

_DEFAULT_NO_VARIANTS_MESSAGE = (
    "No variants to write: both authoritative and fallback sources "
    "are empty after parsing."
)

_GC_EXPORT_IGNORED = (
    "gc_export_xlsx ignored: the well-level relative activity export "
    "needs a raw round-1 report (round1_report_xlsx); this build used "
    "{source} as the round-1 baseline."
)


@dataclass
class BuildEvolveproAxesResult:
    """Outcome of build_evolvepro_input_axes (two-axis assembly).

    primary_source / confirmation_source name the selected axis A and axis B
    builders (see the PRIMARY_* / CONFIRM_* constants), so a caller can report
    the combination without re-deriving it from the input paths.
    """

    output_path: Path
    n_variants: int
    n_authoritative: int
    n_fallback_only: int
    primary_source: str
    confirmation_source: str
    confidence: str
    well_by_variant: dict[str, str]
    mapping: IdVariantMapping
    mapping_audit_path: Path | None
    replicate_stats: MergeReplicatesStats
    warnings: list[str]
    swap_warnings: list  # list[SwapWarning]
    mismatched: list[dict] = field(default_factory=list)
    n_ngs_excluded: int = 0
    ngs_excluded: list[str] = field(default_factory=list)
    gc_export_path: Path | None = None
    label_audit: LabelAudit | None = None


def build_evolvepro_input_axes(
    output_xlsx: str | Path,
    *,
    # Axis A, primary screen (1 replicate). Exactly one of the four.
    round1_report_xlsx: str | Path | None = None,
    gc_data_xlsx: str | Path | None = None,
    round1_evolvepro_xlsx: str | Path | None = None,
    round1_rep_batch_xlsx: str | Path | None = None,
    layout_xlsx: str | Path | None = None,
    expected_mutations_xlsx: str | Path | None = None,
    # Axis B, confirmation (n replicates). At most one of the three.
    remeasure_report_xlsx: str | Path | None = None,
    remeasure_rep_batch_xlsx: str | Path | None = None,
    rep_batch_xlsx: str | Path | None = None,
    rank_evolvepro_xlsx: str | Path | None = None,
    # Shared options.
    mismatch_threshold: float = 0.1,
    verdict_xlsx: str | Path | None = None,
    mapping_audit_path: str | Path | None = None,
    gc_export_xlsx: str | Path | None = None,
    no_variants_message: str | None = None,
    allow_label_mismatch: bool = False,
) -> BuildEvolveproAxesResult:
    """Assemble an EVOLVEpro input xlsx from one primary screen + one confirmation.

    The two axes are independent, so all six combinations are expressible, plus
    the three provisional builds that omit axis B.

    Axis A, the primary screen baseline (exactly one):
        round1_report_xlsx    raw Agilent report, samples are well positions.
                              Requires layout_xlsx to name the variants.
        gc_data_xlsx          pre-normalised GC sheet, samples are well
                              positions. Requires layout_xlsx.
        round1_evolvepro_xlsx previous-round EVOLVEpro file, already in short
                              variant space. layout_xlsx is optional and only
                              feeds NGS verdict gating.

    Axis B, the confirmation that overrides the baseline (at most one):
        remeasure_report_xlsx Agilent report whose samples are variant labels.
        rep_batch_xlsx        Agilent rep-batch report whose samples are numeric
                              base IDs. Requires rank_evolvepro_xlsx, the
                              previous EVOLVEpro file those IDs rank into.
        (neither)             provisional build, baseline only.

    Args:
        output_xlsx: destination xlsx. Parent directory must exist.
        mismatch_threshold: merge mismatch-flag threshold.
        verdict_xlsx: optional NGS verdict xlsx. Variants whose layout well
            carries a non-PASS verdict are dropped. Needs a variant to well
            map, so it is skipped with a warning when no layout is available.
        mapping_audit_path: when set, the numeric-ID to variant mapping is
            written there as a JSON veto artifact (empty on the other axes).
        gc_export_xlsx: when set with a raw round-1 report, the intermediate
            well-level relative activity is written there. On the other axis A
            sources the build records a warning instead.
        no_variants_message: overrides the empty-result ValueError text.
        allow_label_mismatch: when False (default), a severity="error"
            label-swap warning from detect_label_swap (numeric-index
            confirmation axis only) aborts the build with a ValueError before
            anything is written. Set True to proceed anyway once the flagged
            wells/variants have been reviewed.

    Returns:
        BuildEvolveproAxesResult.

    Raises:
        ValueError: axis selection invalid, a required companion input missing,
            WT areas missing, no variants left to write, or (unless
            allow_label_mismatch=True) a severity="error" label-swap warning.
    """
    output_path = Path(output_xlsx)
    warnings: list[str] = []

    # --- axis A selection --------------------------------------------------
    primary_selected = [
        name
        for name, src in (
            (PRIMARY_RAW_REPORT, round1_report_xlsx),
            (PRIMARY_GC_SHEET, gc_data_xlsx),
            (PRIMARY_PREV_EVOLVEPRO, round1_evolvepro_xlsx),
            (PRIMARY_NUMERIC_REPORT, round1_rep_batch_xlsx),
        )
        if src is not None
    ]
    if len(primary_selected) != 1:
        raise ValueError(
            "exactly one primary screen source is required, got "
            f"{len(primary_selected)} ({', '.join(primary_selected) or 'none'}): "
            "pass round1_report_xlsx (raw report), gc_data_xlsx (pre-normalised "
            "GC sheet), round1_evolvepro_xlsx (previous EVOLVEpro file) or "
            "round1_rep_batch_xlsx (numeric sample IDs)"
        )
    primary_source = primary_selected[0]

    # --- axis B selection --------------------------------------------------
    confirm_selected = [
        name
        for name, src in (
            (CONFIRM_VARIANT_LABELS, remeasure_report_xlsx),
            (CONFIRM_NUMERIC_SUBSET, remeasure_rep_batch_xlsx),
            (CONFIRM_NUMERIC_INDEX, rep_batch_xlsx),
        )
        if src is not None
    ]
    if len(confirm_selected) > 1:
        raise ValueError(
            "at most one confirmation source is allowed, got "
            f"{', '.join(confirm_selected)}: pass remeasure_report_xlsx "
            "(variant labels), remeasure_rep_batch_xlsx (numeric IDs into the "
            "above-WT subset) or rep_batch_xlsx (numeric index), not several"
        )
    confirmation_source = (
        confirm_selected[0] if confirm_selected else CONFIRM_NONE
    )
    if confirmation_source == CONFIRM_NUMERIC_INDEX and rank_evolvepro_xlsx is None:
        raise ValueError(
            "numeric-index confirmation (rep_batch_xlsx) requires "
            "rank_evolvepro_xlsx: the numeric base IDs are ranks into a "
            "previous EVOLVEpro file, so variant names cannot be recovered "
            "without it"
        )
    # The above-WT subset is derived from the primary screen, so this
    # confirmation only means anything when the primary screen is the matching
    # numeric report. Pairing it with a variant-labelled or pre-normalised
    # primary would silently index into a set that was never measured.
    if (
        confirmation_source == CONFIRM_NUMERIC_SUBSET
        and primary_source != PRIMARY_NUMERIC_REPORT
    ):
        raise ValueError(
            "numeric-subset confirmation (remeasure_rep_batch_xlsx) requires "
            "round1_rep_batch_xlsx as the primary screen: its IDs index the "
            "above-WT subset of that screen, which no other primary source "
            f"can produce (got primary source {primary_source!r})"
        )

    # --- axis A build ------------------------------------------------------
    gc_export_path: Path | None = None
    # Set only by the numeric primary screen; the numeric-subset confirmation
    # indexes into it, which is why the two are locked together above.
    primary_decode: DecodeResult | None = None
    if primary_source == PRIMARY_RAW_REPORT:
        if layout_xlsx is None:
            raise ValueError(
                "raw round-1 report (round1_report_xlsx) requires layout_xlsx: "
                "its samples are well positions, so the plate layout is needed "
                "to name the variants"
            )
        assert round1_report_xlsx is not None
        fallback, well_by_variant, w_primary = _build_fallback_from_raw_report(
            round1_report_xlsx, layout_xlsx
        )
        if gc_export_xlsx is not None:
            gc_export_path = _export_round1_relative_activity(
                round1_report_xlsx, gc_export_xlsx
            )
        warnings.extend(w_primary)
    elif primary_source == PRIMARY_GC_SHEET:
        if layout_xlsx is None:
            raise ValueError(
                "rank-mode requires layout_xlsx: pre-normalised GC data "
                "(gc_data_xlsx) is keyed by well position, so the plate layout "
                "is needed to name the variants"
            )
        assert gc_data_xlsx is not None
        if gc_export_xlsx is not None:
            warnings.append(
                _GC_EXPORT_IGNORED.format(source="a pre-normalised GC sheet")
            )
        fallback, well_by_variant, w_primary = _build_fallback(
            layout_xlsx, gc_data_xlsx
        )
        warnings.extend(w_primary)
    elif primary_source == PRIMARY_NUMERIC_REPORT:
        if layout_xlsx is None and expected_mutations_xlsx is None:
            raise ValueError(
                "numeric primary screen (round1_rep_batch_xlsx) needs an order "
                "to index into: pass expected_mutations_xlsx (the KURO design, "
                "preferred) or layout_xlsx (hand-written plate file). The "
                "sample IDs carry no variant information on their own."
            )
        if gc_export_xlsx is not None:
            warnings.append(
                _GC_EXPORT_IGNORED.format(source="a numeric-ID report")
            )
        assert round1_rep_batch_xlsx is not None  # axis A selection guarantees it
        primary_decode = decode_primary_screen(
            round1_rep_batch_xlsx,
            None if expected_mutations_xlsx is not None else layout_xlsx,
            expected_xlsx=expected_mutations_xlsx,
        )
        fallback = primary_decode.by_variant()
        well_by_variant = {r.variant: r.well for r in primary_decode.rows}
        warnings.extend(primary_decode.warnings)
    else:
        assert round1_evolvepro_xlsx is not None
        if gc_export_xlsx is not None:
            warnings.append(
                _GC_EXPORT_IGNORED.format(source="a previous EVOLVEpro file")
            )
        fallback, w_primary = _build_fallback_from_prev_evolvepro(
            round1_evolvepro_xlsx
        )
        # Layout is optional here and only feeds NGS verdict gating.
        well_by_variant = (
            _well_by_variant_from_layout(layout_xlsx)
            if layout_xlsx is not None
            else {}
        )
        warnings.extend(w_primary)

    # --- axis B build ------------------------------------------------------
    mapping = IdVariantMapping(
        rows=[], prev_descending=True, n_prev_variants=0, warnings=[]
    )
    if primary_decode is not None:
        mapping = IdVariantMapping(
            rows=[
                MappingRow(id=r.id, variant=r.variant, well=r.well)
                for r in primary_decode.rows
            ],
            prev_descending=True,
            n_prev_variants=len(primary_decode.order),
            warnings=list(primary_decode.warnings),
        )
    prev_ep_rows: list[tuple[str, float]] = []
    authoritative: dict[str, list[float]] = {}
    if confirmation_source == CONFIRM_NUMERIC_INDEX:
        assert rep_batch_xlsx is not None
        assert rank_evolvepro_xlsx is not None
        block_result = parse_agilent_block_rep_batch(rep_batch_xlsx)
        prev_ep_rows = read_evolvepro_rows(rank_evolvepro_xlsx)
        mapping = build_id_variant_mapping(
            block_result, prev_ep_rows, well_by_variant
        )
        warnings.extend(mapping.warnings)
        authoritative = _build_authoritative(block_result, mapping)
    elif confirmation_source == CONFIRM_VARIANT_LABELS:
        assert remeasure_report_xlsx is not None
        authoritative, w_confirm = _build_authoritative_from_variant_report(
            remeasure_report_xlsx
        )
        warnings.extend(w_confirm)
    elif confirmation_source == CONFIRM_NUMERIC_SUBSET:
        # Axis selection already refused any primary other than the numeric one,
        # so the decode of that screen is what these IDs index into.
        assert primary_decode is not None
        assert remeasure_rep_batch_xlsx is not None
        confirm_decode = decode_confirmation(
            remeasure_rep_batch_xlsx, primary_decode
        )
        authoritative = confirm_decode.by_variant()
        warnings.extend(confirm_decode.warnings)

    # --- merge (short variant space) ---------------------------------------
    authoritative_v: dict[Variant, list[float]] = {
        Variant(k): v for k, v in authoritative.items()
    }
    fallback_v: dict[Variant, list[float]] = {
        Variant(k): v for k, v in fallback.items()
    }
    merged, replicate_stats = merge_replicates_priority(
        authoritative_v,
        fallback_v,
        mismatch_threshold=mismatch_threshold,
    )
    if not merged:
        raise ValueError(no_variants_message or _DEFAULT_NO_VARIANTS_MESSAGE)

    mismatched_detail: list[dict] = [
        {
            "variant": str(v),
            "authoritative": merged[v],
            "fallback": sum(fallback_v[v]) / len(fallback_v[v]),
        }
        for v in replicate_stats.mismatched
    ]

    # --- optional NGS verdict gating ---------------------------------------
    ngs_excluded: list[str] = []
    label_audit_result: LabelAudit | None = None
    if verdict_xlsx is not None:
        from kuma_core.mame.activity.verdict_ngs import parse_verdict_rows, _PASS

        verdict_rows_full = parse_verdict_rows(verdict_xlsx)
        verdict_by_well = {w: r.verdict for w, r in verdict_rows_full.items()}

        if not well_by_variant:
            warnings.append(
                "NGS verdict gating skipped: no layout to map variant->well "
                "(prev-EVOLVEpro round-1 mode without layout_xlsx)."
            )
        else:
            for variant in list(merged):
                well = well_by_variant.get(str(variant))
                if well is None:
                    continue
                vclass = verdict_by_well.get(well)
                if vclass is not None and vclass != _PASS:
                    del merged[variant]
                    ngs_excluded.append(str(variant))
            if ngs_excluded:
                warnings.append(
                    f"NGS verdict gating excluded {len(ngs_excluded)} non-PASS "
                    f"variant(s): {', '.join(sorted(ngs_excluded))}"
                )
            if not merged:
                raise ValueError(
                    "All variants excluded by NGS verdict gating (no PASS wells). "
                    "Check the verdict file or omit it to use layout-trust."
                )

        # Well<->mutant label audit (detection/classification only, Phase 1;
        # requires both an NGS verdict source and a plate layout).
        if layout_xlsx is not None:
            layout_map = {
                e.well_id: e.mutant for e in parse_plate_layout_xlsx(layout_xlsx)
            }
            label_audit_result = audit_labels(layout_map, verdict_rows_full)

    # --- label-swap guard (numeric-index axis only, advisory unless the
    # swap is severity="error", which blocks export by default) ------------
    swap_warnings: list = []
    if confirmation_source == CONFIRM_NUMERIC_INDEX:
        prev_ep_map = {
            v: a for v, a in prev_ep_rows if v.upper() != _WT_LITERAL
        }
        swap_layout: list[tuple[str, str]] = []
        swap_activity: dict[str, float] = {}
        for variant, activity in merged.items():
            well = well_by_variant.get(str(variant))
            if well is None:
                continue
            swap_layout.append((str(variant), well))
            swap_activity[well] = float(activity)
        swap_warnings = detect_label_swap(swap_layout, swap_activity, prev_ep_map)

        error_warnings = [w for w in swap_warnings if w.severity == "error"]
        if error_warnings and not allow_label_mismatch:
            details = "; ".join(w.message for w in error_warnings)
            raise ValueError(
                "Label swap detected (severity=error); export blocked. "
                f"{details} Review the flagged wells and variants, then "
                "re-run with allow_label_mismatch=True to proceed once "
                "confirmed."
            )

    # --- write -------------------------------------------------------------
    rows = sorted(merged.items(), key=lambda kv: -kv[1])
    n_variants = write_evolvepro_xlsx(
        [(str(v), float(a)) for v, a in rows], output_path
    )

    # --- mapping audit artifact --------------------------------------------
    audit_path: Path | None = None
    if mapping_audit_path is not None:
        audit_path = Path(mapping_audit_path)
        _write_mapping_audit(mapping, audit_path)

    n_authoritative = len(authoritative)
    n_fallback_only = sum(1 for k in fallback if k not in authoritative)

    return BuildEvolveproAxesResult(
        output_path=output_path,
        n_variants=n_variants,
        n_authoritative=n_authoritative,
        n_fallback_only=n_fallback_only,
        primary_source=primary_source,
        confirmation_source=confirmation_source,
        confidence=(
            "provisional" if confirmation_source == CONFIRM_NONE else "confirmed"
        ),
        well_by_variant=well_by_variant,
        mapping=mapping,
        mapping_audit_path=audit_path,
        replicate_stats=replicate_stats,
        warnings=warnings,
        swap_warnings=swap_warnings,
        mismatched=mismatched_detail,
        n_ngs_excluded=len(ngs_excluded),
        ngs_excluded=sorted(ngs_excluded),
        gc_export_path=gc_export_path,
        label_audit=label_audit_result,
    )
