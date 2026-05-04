from kuma_core.mame.activity.models import (
    ActivityRecord, ActivityTable, MergedRow, PlateConfig, PlateMeta, MergeStats
)
from datetime import datetime


def test_activity_record_required_fields():
    r = ActivityRecord(
        plate_id="P01", well_id="A01", value=1.23,
        replicate_idx=1, is_wt=True, source_file="round1.csv"
    )
    assert r.plate_id == "P01"
    assert r.replicate_idx == 1


def test_merged_row_mutation_source_enum():
    row = MergedRow(
        plate_id="P01", well_id="B03", mutation="F89W",
        mutation_source="kuro_design",
        expected_mutation="F89W", called_mutation="F89W",
        ngs_success=True,
        activity_raw_mean=2.45, activity_raw_sd=0.12,
        activity_replicates=[2.40, 2.50, 2.45], replicate_n=3,
        fold_change=1.99, log2_fc=0.99
    )
    assert row.mutation_source in {"kuro_design", "mame_genotype", "activity_only"}


def test_merge_stats_all_fields():
    s = MergeStats(
        n_total_wells=96, n_with_activity=96, n_with_genotype=90,
        n_ngs_success=88, n_wt=4,
        n_duplicate_warnings=0, n_excluded_from_export=10
    )
    assert s.n_total_wells == 96
