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
    rows, _ = merge_activity_with_genotype(kuro_design, mame_genotype, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.mutation_source == "kuro_design"
    assert rec.ngs_success is True
    assert rec.mutation == "F89W"
    assert rec.fold_change is not None and abs(rec.fold_change - 2.0) < 1e-6
    assert rec.log2_fc is not None and abs(rec.log2_fc - 1.0) < 1e-6


def test_genotype_disagrees_with_design():
    kuro = {("P01", "B03"): "F89W"}
    mame = {("P01", "B03"): "WT"}
    activity = _make_records([("P01", "B03", 1.0, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                   replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, _ = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
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
    rows, _ = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
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
    rows, _ = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.replicate_n == 3
    assert rec.activity_raw_mean is not None and abs(rec.activity_raw_mean - 2.3) < 0.01
    assert rec.activity_raw_sd is not None


def test_stats_counts():
    kuro = {("P01", "A02"): "L70V", ("P01", "B03"): "F89W"}
    mame = {("P01", "A02"): "L70V", ("P01", "B03"): "WT"}  # B03 NGS 실패
    activity = _make_records([("P01", "A02", 1.5, 1), ("P01", "B03", 1.0, 1)])
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                   replicate_idx=1, is_wt=True, source_file="t.csv"))
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    assert len(rows) >= 1
    assert stats.n_total_wells == 3
    assert stats.n_ngs_success == 1
    assert stats.n_wt == 1


def test_well_id_padding_mismatch_still_joins():
    """Unpadded design/genotype/WT ('B3'/'A1') must join padded activity ('B03'/'A01').

    Regression: the merge previously normalized only the activity CSV well_id, so
    an unpadded design/genotype/WT well silently failed to match a padded activity
    well — dropping the NGS call + design mutation for that well.
    """
    kuro_design = {("P01", "B3"): "F89W"}  # unpadded
    mame_genotype = {("P01", "B3"): "F89W"}  # unpadded
    activity = _make_records([("P01", "B03", 2.0, 1)])  # padded
    plate_meta = PlateMeta(
        plates=[PlateConfig(plate_id="P01", wt_wells=["A1"])]  # unpadded WT
    )
    activity.append(
        ActivityRecord(
            plate_id="P01", well_id="A01", value=1.0,  # padded activity
            replicate_idx=1, is_wt=True, source_file="t.csv",
        )
    )
    rows, _ = merge_activity_with_genotype(
        kuro_design, mame_genotype, activity, plate_meta
    )
    # Exactly one canonical B03 row (no duplicate B3/B03 split), joined to design.
    b03 = [r for r in rows if r.well_id == "B03"]
    assert len(b03) == 1
    rec = b03[0]
    assert rec.mutation_source == "kuro_design"
    assert rec.ngs_success is True
    assert rec.mutation == "F89W"
    assert rec.activity_raw_mean is not None  # activity actually joined
    # Unpadded WT ('A1') matched padded activity ('A01') → WT recognized.
    a01 = next(r for r in rows if r.well_id == "A01")
    assert a01.mutation == "WT"
    # No stray unpadded keys leaked into output.
    assert not any(r.well_id in ("B3", "A1") for r in rows)
