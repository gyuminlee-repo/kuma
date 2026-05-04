from kuma_core.mame.activity.join import merge_activity_with_genotype
from kuma_core.mame.activity.models import ActivityRecord, PlateMeta, PlateConfig


def _make_records(rows):
    return [
        ActivityRecord(plate_id=p, well_id=w, value=v, replicate_idx=r,
                       is_wt=False, source_file="t.csv")
        for (p, w, v, r) in rows
    ]


def test_kuro_design_match_genotype():
    kuro_design = {("P01", "B03"): "F89W"}
    mame_genotype = {("P01", "B03"): "F89W"}
    activity = _make_records([("P01", "B03", 2.0, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                   replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro_design, mame_genotype, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.mutation_source == "kuro_design"
    assert rec.ngs_success is True
    assert rec.mutation == "F89W"
    assert abs(rec.fold_change - 2.0) < 1e-6
    assert abs(rec.log2_fc - 1.0) < 1e-6


def test_genotype_disagrees_with_design():
    kuro = {("P01", "B03"): "F89W"}
    mame = {("P01", "B03"): "WT"}
    activity = _make_records([("P01", "B03", 1.0, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                   replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.mutation_source == "mame_genotype"
    assert rec.ngs_success is False
    assert rec.expected_mutation == "F89W"
    assert rec.called_mutation == "WT"


def test_activity_only_well():
    kuro = {}
    mame = {}
    activity = _make_records([("P01", "C05", 1.5, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=[])])
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    rec = rows[0]
    assert rec.mutation_source == "activity_only"
    assert rec.mutation is None
    assert rec.ngs_success is False


def test_replicate_aggregation():
    kuro = {("P01", "B03"): "F89W"}
    mame = {("P01", "B03"): "F89W"}
    activity = _make_records([("P01", "B03", 2.0, 1), ("P01", "B03", 2.5, 2),
                               ("P01", "B03", 2.4, 3)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                   replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.replicate_n == 3
    assert abs(rec.activity_raw_mean - 2.3) < 0.01
    assert rec.activity_raw_sd is not None


def test_stats_counts():
    kuro = {("P01", "A02"): "L70V", ("P01", "B03"): "F89W"}
    mame = {("P01", "A02"): "L70V", ("P01", "B03"): "WT"}  # B03 NGS 실패
    activity = _make_records([("P01", "A02", 1.5, 1), ("P01", "B03", 1.0, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                   replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    assert stats.n_total_wells == 3
    assert stats.n_ngs_success == 1
    assert stats.n_wt == 1
