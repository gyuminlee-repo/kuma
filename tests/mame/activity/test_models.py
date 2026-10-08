"""Tests for kuma_core.mame.activity.models.

Covers existing models plus v0.3 Phase B-4 additions:
  - Variant NewType
  - SwapWarning dataclass
  - MergeReplicatesStats dataclass
  - MergeStats.warnings field (default=[], round-trip safe)
"""

import json
from kuma_core.mame.activity.models import (
    ActivityRecord,
    MergedRow,
    MergeReplicatesStats,
    MergeStats,
    SwapWarning,
    Variant,
)


# ---------------------------------------------------------------------------
# Existing tests (must not regress)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# B-4: SwapWarning
# ---------------------------------------------------------------------------

def test_swap_warning_construction():
    w = SwapWarning(
        severity="error",
        code="label_swap_cycle",
        variants=["10A", "10B"],
        wells=["A01", "A02"],
        values=[0.5, 0.7],
        message="test swap",
    )
    assert w.severity == "error"
    assert w.code == "label_swap_cycle"
    assert len(w.variants) == 2


def test_swap_warning_warning_severity():
    w = SwapWarning(
        severity="warning",
        code="layout_orphan",
        variants=["99Z"],
        wells=["C01"],
        values=[],
        message="orphan",
    )
    assert w.severity == "warning"
    assert w.code == "layout_orphan"


# ---------------------------------------------------------------------------
# B-4: MergeReplicatesStats
# ---------------------------------------------------------------------------

def test_merge_replicates_stats_construction():
    stats = MergeReplicatesStats(
        authoritative_count=10,
        fallback_count=8,
        merged_count=12,
        mismatched=[Variant("F10A"), Variant("F20B")],
    )
    assert stats.authoritative_count == 10
    assert stats.merged_count == 12
    assert len(stats.mismatched) == 2


def test_merge_replicates_stats_empty_mismatched():
    stats = MergeReplicatesStats(
        authoritative_count=5,
        fallback_count=5,
        merged_count=5,
        mismatched=[],
    )
    assert stats.mismatched == []


# ---------------------------------------------------------------------------
# B-4: MergeStats.warnings — default=[] + round-trip safety
# ---------------------------------------------------------------------------

def test_merge_stats_warnings_default_empty():
    # warnings field must default to [] (existing JSON without 'warnings' key
    # must still load safely — workspace schema_version 0.3 round-trip).
    s = MergeStats(
        n_total_wells=96, n_with_activity=96, n_with_genotype=90,
        n_ngs_success=88, n_wt=4,
        n_duplicate_warnings=0, n_excluded_from_export=10,
    )
    assert s.warnings == []


def test_merge_stats_warnings_populated():
    w = SwapWarning(
        severity="error",
        code="label_swap_cycle",
        variants=["10A", "10B"],
        wells=["A01", "A02"],
        values=[0.5, 0.7],
        message="swap detected",
    )
    s = MergeStats(
        n_total_wells=96, n_with_activity=96, n_with_genotype=90,
        n_ngs_success=88, n_wt=4,
        n_duplicate_warnings=0, n_excluded_from_export=10,
        warnings=[w],
    )
    assert len(s.warnings) == 1
    assert s.warnings[0].severity == "error"


def test_merge_stats_json_roundtrip_no_warnings():
    """Existing workspace files (no 'warnings' key) must validate safely."""
    legacy_json = json.dumps({
        "n_total_wells": 96,
        "n_with_activity": 90,
        "n_with_genotype": 85,
        "n_ngs_success": 83,
        "n_wt": 4,
        "n_duplicate_warnings": 0,
        "n_excluded_from_export": 5,
    })
    s = MergeStats.model_validate_json(legacy_json)
    assert s.warnings == []


def test_merge_stats_json_roundtrip_with_warnings():
    """MergeStats with warnings must survive model_dump_json → model_validate_json."""
    w = SwapWarning(
        severity="warning",
        code="value_collision",
        variants=["20A", "20B"],
        wells=["B01"],
        values=[1.234],
        message="collision",
    )
    s = MergeStats(
        n_total_wells=10, n_with_activity=10, n_with_genotype=9,
        n_ngs_success=8, n_wt=1,
        n_duplicate_warnings=0, n_excluded_from_export=0,
        warnings=[w],
    )
    serialised = s.model_dump_json()
    s2 = MergeStats.model_validate_json(serialised)
    assert len(s2.warnings) == 1
    assert s2.warnings[0].code == "value_collision"
    assert s2.warnings[0].values == [1.234]
