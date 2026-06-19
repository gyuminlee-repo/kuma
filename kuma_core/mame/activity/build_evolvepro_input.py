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
)
from .merge import merge_replicates_priority
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
    # QC: variants whose authoritative (3-replicate confirmation) mean diverged
    # from the fallback (1-replicate primary screen) mean beyond the merge
    # threshold. Each entry carries both means so a reviewer can eyeball the gap.
    mismatched: list[dict] = field(default_factory=list)


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
    for entry in layout_entries:
        if entry.is_wt:
            continue
        if entry.well_id not in gc_by_well:
            warnings.append(
                f"Layout mutant {entry.mutant!r} (well {entry.well_id}) has no "
                "GC data value; excluded from the fallback source."
            )
            continue
        short = to_evolvepro(entry.mutant)
        fallback.setdefault(short, []).append(gc_by_well[entry.well_id])
        well_by_variant[short] = entry.well_id

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
    rep_batch_xlsx: str | Path,
    prev_evolvepro_xlsx: str | Path,
    output_xlsx: str | Path,
    *,
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

    warnings: list[str] = []

    # 1. fallback (short variant space).
    fallback, well_by_variant, fb_warnings = _build_fallback(
        layout_xlsx, gc_data_xlsx
    )
    warnings.extend(fb_warnings)

    # 2. mapping (rank ID->variant) from previous EVOLVEpro file (ordered read).
    block_result = parse_agilent_block_rep_batch(rep_batch_xlsx)
    prev_ep_rows = read_evolvepro_rows(prev_evolvepro_xlsx)
    mapping = build_id_variant_mapping(block_result, prev_ep_rows, well_by_variant)
    warnings.extend(mapping.warnings)

    # 3. authoritative (short variant space).
    authoritative = _build_authoritative(block_result, mapping)

    # 4. merge in short variant space (Variant NewType is str at runtime).
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
        raise ValueError(
            "No variants to write: both authoritative and fallback sources "
            "are empty after parsing."
        )

    # QC: surface variants where the authoritative confirmation mean diverged
    # from the fallback primary-screen mean (replicate_stats.mismatched holds
    # the names; the merge guarantees each is in both sources with non-empty
    # lists, so authoritative wins and merged[v] is the authoritative mean).
    mismatched_detail: list[dict] = [
        {
            "variant": str(v),
            "authoritative": merged[v],
            "fallback": sum(fallback_v[v]) / len(fallback_v[v]),
        }
        for v in replicate_stats.mismatched
    ]

    # 5. sort descending by merged activity, then write.
    rows = sorted(merged.items(), key=lambda kv: -kv[1])
    n_variants = write_evolvepro_xlsx(
        [(str(v), float(a)) for v, a in rows], output_path
    )

    # 6. label-swap guard (advisory): compare merged activity per well against
    #    the previous EVOLVEpro file. Layout is (variant, well) in short space.
    prev_ep_map = {v: a for v, a in prev_ep_rows if v.upper() != _WT_LITERAL}
    swap_layout: list[tuple[str, str]] = []
    swap_activity: dict[str, float] = {}
    for variant, activity in merged.items():
        well = well_by_variant.get(str(variant))
        if well is None:
            continue
        swap_layout.append((str(variant), well))
        swap_activity[well] = float(activity)
    swap_warnings = detect_label_swap(swap_layout, swap_activity, prev_ep_map)

    # 7. emit the mapping audit (veto artifact).
    _write_mapping_audit(mapping, audit_path)

    n_authoritative = len(authoritative)
    n_fallback_only = sum(1 for k in fallback if k not in authoritative)

    return BuildEvolveproResult(
        output_path=output_path,
        mapping_audit_path=audit_path,
        n_variants=n_variants,
        n_authoritative=n_authoritative,
        n_fallback_only=n_fallback_only,
        mapping=mapping,
        replicate_stats=replicate_stats,
        warnings=warnings,
        swap_warnings=swap_warnings,
        mismatched=mismatched_detail,
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
        short = to_evolvepro(variant_internal)
        fallback.setdefault(short, []).append(r.area / wt_mean)
        well_by_variant[short] = well
    return fallback, well_by_variant, warnings


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
    """short variant -> well from the plate layout (for optional NGS gating)."""
    entries = parse_plate_layout_xlsx(layout_xlsx)
    return {to_evolvepro(e.mutant): e.well_id for e in entries if not e.is_wt}


def build_evolvepro_input_from_reports(
    layout_xlsx,
    round1_report_xlsx,
    remeasure_report_xlsx,
    output_xlsx,
    *,
    mismatch_threshold: float = 0.1,
    verdict_xlsx: str | Path | None = None,
    prev_evolvepro_xlsx: str | Path | None = None,
) -> BuildEvolveproReportsResult:
    """Assemble an EVOLVEpro input xlsx from round-1 + a variant-labeled re-measure.

    Round-1 baseline (fallback) comes from one of two sources:
      - raw Agilent standard report (well-named) + plate layout, or
      - a previous-round EVOLVEpro file (``prev_evolvepro_xlsx``, Variant/activity)
        when the full round-1 already lives in EVOLVEpro form.
    Re-measure: variant-labeled report -> n relative replicates per variant
    (authoritative). Authoritative mean replaces fallback where both define a
    variant; other variants keep their round-1 value.
    """
    output_path = Path(output_xlsx)
    warnings: list[str] = []

    if prev_evolvepro_xlsx is not None:
        # Round-1 baseline from a previous-round EVOLVEpro file (Variant, activity).
        fallback, w1 = _build_fallback_from_prev_evolvepro(prev_evolvepro_xlsx)
        # Layout is optional here; only needed to map variant->well for NGS gating.
        well_by_variant = (
            _well_by_variant_from_layout(layout_xlsx) if layout_xlsx is not None else {}
        )
    else:
        if layout_xlsx is None or round1_report_xlsx is None:
            raise ValueError(
                "raw round-1 mode requires both layout_xlsx and round1_report_xlsx; "
                "pass prev_evolvepro_xlsx to use a previous EVOLVEpro file as round-1."
            )
        fallback, well_by_variant, w1 = _build_fallback_from_raw_report(
            round1_report_xlsx, layout_xlsx
        )
    warnings.extend(w1)
    authoritative, w2 = _build_authoritative_from_variant_report(remeasure_report_xlsx)
    warnings.extend(w2)

    authoritative_v: dict[Variant, list[float]] = {
        Variant(k): v for k, v in authoritative.items()
    }
    fallback_v: dict[Variant, list[float]] = {
        Variant(k): v for k, v in fallback.items()
    }
    merged, replicate_stats = merge_replicates_priority(
        authoritative_v, fallback_v, mismatch_threshold=mismatch_threshold
    )
    if not merged:
        raise ValueError(
            "No variants to write: both round-1 and re-measure sources are empty after parsing."
        )

    mismatched_detail: list[dict] = [
        {
            "variant": str(v),
            "authoritative": merged[v],
            "fallback": sum(fallback_v[v]) / len(fallback_v[v]),
        }
        for v in replicate_stats.mismatched
    ]

    # Optional NGS verdict gating: drop variants whose layout well carries an
    # explicit non-PASS verdict (ngs_success == verdict == PASS). A variant with
    # no layout well, or a well absent from the verdict file, is kept (graceful,
    # layout-trust). When no verdict file is given, behaviour is unchanged.
    ngs_excluded: list[str] = []
    if verdict_xlsx is not None:
        from kuma_core.mame.activity.verdict_ngs import parse_verdict_wells, _PASS

        if not well_by_variant:
            # prev-EVOLVEpro round-1 mode without a layout: no variant->well map,
            # so gating cannot run. Keep all variants (graceful, layout-trust).
            warnings.append(
                "NGS verdict gating skipped: no layout to map variant->well "
                "(prev-EVOLVEpro round-1 mode without layout_xlsx)."
            )
        else:
            verdict_by_well = parse_verdict_wells(verdict_xlsx)
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

    rows = sorted(merged.items(), key=lambda kv: -kv[1])
    n_variants = write_evolvepro_xlsx([(str(v), float(a)) for v, a in rows], output_path)

    n_authoritative = len(authoritative)
    n_fallback_only = sum(1 for k in fallback if k not in authoritative)

    return BuildEvolveproReportsResult(
        output_path=output_path,
        n_variants=n_variants,
        n_authoritative=n_authoritative,
        n_fallback_only=n_fallback_only,
        well_by_variant=well_by_variant,
        replicate_stats=replicate_stats,
        warnings=warnings,
        mismatched=mismatched_detail,
        n_ngs_excluded=len(ngs_excluded),
        ngs_excluded=sorted(ngs_excluded),
    )
