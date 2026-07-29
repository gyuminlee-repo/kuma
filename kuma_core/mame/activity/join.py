"""Genotype × activity merge logic for MAME integration.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.4, §3.4
"""

from collections import defaultdict
import re

from kuma_core.mame.activity.aggregate import aggregate_replicates
from kuma_core.mame.activity.models import (
    ActivityRecord,
    MergedRow,
    MergeStats,
    PlateMeta,
    WtReplicateRecord,
)
from kuma_core.mame.activity.normalize import compute_fold_change, compute_log2_fc


_WELL_RE = re.compile(r"^([A-Pa-p])(\d{1,2})$")


def _canonical_well(well: str) -> str:
    """Canonicalize a well coordinate to zero-padded 2-digit column ('A1' → 'A01').

    Non-well strings pass through unchanged. Idempotent ('A01' → 'A01'). Keeps the
    merge join key format consistent across the design / genotype / activity /
    WT-well sources — previously only the activity CSV path normalized to 'A01',
    so an unpadded design or genotype well silently failed to match a padded
    activity well (and vice versa).
    """
    m = _WELL_RE.match(well.strip())
    if not m:
        return well
    return f"{m.group(1).upper()}{int(m.group(2)):02d}"


def merge_activity_with_genotype(
    kuro_design: dict[tuple[str, str], str],
    mame_genotype: dict[tuple[str, str], str],
    activity_records: list[ActivityRecord],
    plate_meta: PlateMeta,
    wt_records: list[WtReplicateRecord] | None = None,
) -> tuple[list[MergedRow], MergeStats]:
    """Merge KURO design, MAME genotype, and activity data by (plate_id, well_id).

    mutation_source rules (spec §2.4):
    - kuro_design: KURO designed a mutation and MAME agrees (or no NGS data).
    - mame_genotype: MAME called a different mutation, or NGS overrides design.
    - activity_only: Neither KURO nor MAME has data for this well.

    ngs_success = True only when expected_mutation == called_mutation (both non-None).

    n_wt counts wells designated as WT controls in plate_meta (is_wt_well),
    not NGS-called WT results.

    Args:
        kuro_design: (plate_id, well_id) → expected mutation string.
        mame_genotype: (plate_id, well_id) → called mutation string.
        activity_records: Raw ActivityRecord list (may contain replicates).
        plate_meta: PlateMeta specifying WT well coordinates per plate.
        wt_records: Dedicated WT replicate rows from the activity file. When a
            plate has them they define that plate WT denominator; plates without
            them fall back to the plate-designated WT wells. stats reports which
            source ran via n_wt_replicate_rows / n_plates_wt_from_replicates.

    Returns:
        (rows, stats) where rows is a sorted list of MergedRow and stats
        is a MergeStats summary.
    """
    # Canonicalize well_id on every key source so unpadded ('A1') and padded
    # ('A01') coordinates join correctly. Previously only the activity CSV path
    # normalized to 'A01', so an unpadded design/genotype/WT well silently failed
    # to match a padded activity well (and vice versa) — dropping NGS calls.
    kuro_design = {(p, _canonical_well(w)): m for (p, w), m in kuro_design.items()}
    mame_genotype = {(p, _canonical_well(w)): m for (p, w), m in mame_genotype.items()}
    wt_lookup: dict[str, set[str]] = {
        p.plate_id: {_canonical_well(w) for w in p.wt_wells}
        for p in plate_meta.plates
    }

    # Group activity records by (plate_id, well_id), deduplicating on replicate_idx
    by_well: dict[tuple[str, str], list[ActivityRecord]] = defaultdict(list)
    seen_keys: set[tuple[str, str, int]] = set()
    n_dup = 0
    for r in activity_records:
        wid = _canonical_well(r.well_id)
        key = (r.plate_id, wid, r.replicate_idx)
        if key in seen_keys:
            n_dup += 1
            continue
        seen_keys.add(key)
        by_well[(r.plate_id, wid)].append(r)

    # Compute WT mean per plate (used for fold-change normalization).
    # Priority per plate:
    #   (a) dedicated WT replicate rows shipped in the activity file ('WT_1'...),
    #       which is the same denominator definition reports-mode uses
    #       (build_evolvepro_input._agilent_wt_mean).
    #   (b) fallback: back-compute from the WT wells the user marked on the plate.
    # Known definition choice for (b) (unchanged on purpose): all replicates of all
    # WT wells on the plate are flat-pooled into one mean. With multiple WT wells
    # holding unequal replicate counts this differs from a mean-of-well-means.
    dedicated_wt: dict[str, list[float]] = defaultdict(list)
    for wr in wt_records or []:
        dedicated_wt[wr.plate_id].append(wr.value)

    wt_means: dict[str, float | None] = {}
    n_wt_replicate_rows = 0
    n_plates_wt_from_replicates = 0
    for plate_id in set(wt_lookup) | set(dedicated_wt):
        dedicated = dedicated_wt.get(plate_id, [])
        if dedicated:
            m = sum(dedicated) / len(dedicated)
            # Non-positive denominator is physically invalid; keep the existing
            # "no usable WT" contract (None) rather than emit a bogus ratio.
            wt_means[plate_id] = m if m > 0 else None
            n_wt_replicate_rows += len(dedicated)
            n_plates_wt_from_replicates += 1
            continue
        wt_wells = wt_lookup.get(plate_id, set())
        wt_values = [
            r.value
            for (p, w), recs in by_well.items()
            for r in recs
            if p == plate_id and w in wt_wells
        ]
        wt_means[plate_id] = sum(wt_values) / len(wt_values) if wt_values else None

    # Union of all (plate_id, well_id) keys across all three tables
    all_keys = (
        set(kuro_design.keys())
        | set(mame_genotype.keys())
        | set(by_well.keys())
    )

    rows: list[MergedRow] = []
    n_with_activity = 0
    n_with_genotype = 0
    n_ngs_success = 0
    n_wt = 0
    n_excluded = 0

    for plate_id, well_id in sorted(all_keys):
        expected = kuro_design.get((plate_id, well_id))
        called = mame_genotype.get((plate_id, well_id))
        is_wt_well = well_id in wt_lookup.get(plate_id, set())

        # Determine mutation, mutation_source, ngs_success per §2.4
        if is_wt_well:
            mutation = "WT"
            mutation_source = "kuro_design" if expected else "activity_only"
            ngs_success = (called == "WT") if called is not None else (expected == "WT")
        elif expected and (not called or called == expected):
            mutation = expected
            mutation_source = "kuro_design"
            ngs_success = called == expected
        elif called:
            mutation = called
            mutation_source = "mame_genotype"
            ngs_success = expected is not None and called == expected
        else:
            mutation = None
            mutation_source = "activity_only"
            ngs_success = False

        recs = by_well.get((plate_id, well_id), [])
        replicates = [r.value for r in recs]
        mean, sd, n_rep = aggregate_replicates(replicates)

        wt_m = wt_means.get(plate_id)
        fold_change = compute_fold_change(mean, wt_m)
        log2 = compute_log2_fc(fold_change, is_wt=(mutation == "WT"))

        if recs:
            n_with_activity += 1
        if called:
            n_with_genotype += 1
        if ngs_success:
            n_ngs_success += 1
        # n_wt counts plate_meta-designated WT control wells only
        if is_wt_well:
            n_wt += 1
        if not (ngs_success and mutation != "WT" and log2 is not None):
            n_excluded += 1

        rows.append(
            MergedRow(
                plate_id=plate_id,
                well_id=well_id,
                mutation=mutation,
                mutation_source=mutation_source,
                expected_mutation=expected,
                called_mutation=called,
                ngs_success=ngs_success,
                activity_raw_mean=mean,
                activity_raw_sd=sd,
                activity_replicates=replicates,
                replicate_n=n_rep,
                fold_change=fold_change,
                log2_fc=log2,
            )
        )

    stats = MergeStats(
        n_total_wells=len(rows),
        n_with_activity=n_with_activity,
        n_with_genotype=n_with_genotype,
        n_ngs_success=n_ngs_success,
        n_wt=n_wt,
        n_duplicate_warnings=n_dup,
        n_excluded_from_export=n_excluded,
        n_wt_replicate_rows=n_wt_replicate_rows,
        n_plates_wt_from_replicates=n_plates_wt_from_replicates,
    )
    return rows, stats
