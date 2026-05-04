"""Genotype × activity merge logic for MAME integration.

Spec: notes/specs/2026-05-04-mame-activity-integration.md §2.4, §3.4
"""

from collections import defaultdict

from kuma_core.mame.activity.aggregate import aggregate_replicates
from kuma_core.mame.activity.models import (
    ActivityRecord,
    MergedRow,
    MergeStats,
    PlateMeta,
)
from kuma_core.mame.activity.normalize import compute_fold_change, compute_log2_fc


def merge_activity_with_genotype(
    kuro_design: dict[tuple[str, str], str],
    mame_genotype: dict[tuple[str, str], str],
    activity_records: list[ActivityRecord],
    plate_meta: PlateMeta,
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

    Returns:
        (rows, stats) where rows is a sorted list of MergedRow and stats
        is a MergeStats summary.
    """
    wt_lookup: dict[str, set[str]] = {
        p.plate_id: set(p.wt_wells) for p in plate_meta.plates
    }

    # Group activity records by (plate_id, well_id), deduplicating on replicate_idx
    by_well: dict[tuple[str, str], list[ActivityRecord]] = defaultdict(list)
    seen_keys: set[tuple[str, str, int]] = set()
    n_dup = 0
    for r in activity_records:
        key = (r.plate_id, r.well_id, r.replicate_idx)
        if key in seen_keys:
            n_dup += 1
            continue
        seen_keys.add(key)
        by_well[(r.plate_id, r.well_id)].append(r)

    # Compute WT mean per plate (used for fold-change normalization)
    wt_means: dict[str, float | None] = {}
    for plate_id, wt_wells in wt_lookup.items():
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
    )
    return rows, stats
