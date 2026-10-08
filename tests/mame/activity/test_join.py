from kuma_core.mame.activity.join import merge_activity_with_genotype
from kuma_core.mame.activity.export_evolvepro import export_evolvepro_csv
from kuma_core.mame.activity.models import (
    ActivityRecord,
    PlateMeta,
    PlateConfig,
    WtReplicateRecord,
)


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


# ── Dedicated WT replicate rows as the fold-change denominator ────────────────

def _wt_rows(plate_id: str, values: list[float]):
    return [
        WtReplicateRecord(plate_id=plate_id, sample_name=f"WT_{i + 1}",
                          value=v, replicate_idx=i + 1, source_file="t.csv")
        for i, v in enumerate(values)
    ]


def _wt_denominator_case():
    """Plate WT well says 1.0, dedicated WT replicates say 2.0, mutant is 2.0.

    Denominator (a) -> fold_change 1.0; denominator (b) -> fold_change 2.0.
    The two definitions therefore cannot be confused by this fixture.
    """
    kuro = {("P01", "B03"): "F89W"}
    mame = {("P01", "B03"): "F89W"}
    activity = _make_records([("P01", "B03", 2.0, 1)])
    activity.append(ActivityRecord(plate_id="P01", well_id="A01", value=1.0,
                                   replicate_idx=1, is_wt=True, source_file="t.csv"))
    plate_meta = PlateMeta(plates=[PlateConfig(plate_id="P01", wt_wells=["A01"])])
    return kuro, mame, activity, plate_meta


def test_dedicated_wt_rows_define_denominator():
    kuro, mame, activity, plate_meta = _wt_denominator_case()
    rows, stats = merge_activity_with_genotype(
        kuro, mame, activity, plate_meta, _wt_rows("P01", [2.0, 2.0, 2.0])
    )
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.fold_change is not None and abs(rec.fold_change - 1.0) < 1e-9
    assert rec.log2_fc is not None and abs(rec.log2_fc - 0.0) < 1e-9
    assert stats.n_wt_replicate_rows == 3
    assert stats.n_plates_wt_from_replicates == 1


def test_plate_wt_wells_denominator_would_differ():
    """Same fixture without dedicated rows keeps the plate-WT-well definition."""
    kuro, mame, activity, plate_meta = _wt_denominator_case()
    rows, stats = merge_activity_with_genotype(kuro, mame, activity, plate_meta)
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.fold_change is not None and abs(rec.fold_change - 2.0) < 1e-9
    assert stats.n_wt_replicate_rows == 0
    assert stats.n_plates_wt_from_replicates == 0


def test_dedicated_wt_rows_are_plate_scoped():
    """A plate without dedicated rows keeps the fallback denominator."""
    kuro = {("P01", "B03"): "F89W", ("P02", "B03"): "L70V"}
    mame = dict(kuro)
    activity = _make_records([("P01", "B03", 2.0, 1), ("P02", "B03", 2.0, 1)])
    for pid in ("P01", "P02"):
        activity.append(ActivityRecord(plate_id=pid, well_id="A01", value=1.0,
                                       replicate_idx=1, is_wt=True, source_file="t.csv"))
    plate_meta = PlateMeta(plates=[
        PlateConfig(plate_id="P01", wt_wells=["A01"]),
        PlateConfig(plate_id="P02", wt_wells=["A01"]),
    ])
    rows, stats = merge_activity_with_genotype(
        kuro, mame, activity, plate_meta, _wt_rows("P01", [2.0, 2.0, 2.0])
    )
    p01 = next(r for r in rows if r.plate_id == "P01" and r.well_id == "B03")
    p02 = next(r for r in rows if r.plate_id == "P02" and r.well_id == "B03")
    assert p01.fold_change is not None and abs(p01.fold_change - 1.0) < 1e-9
    assert p02.fold_change is not None and abs(p02.fold_change - 2.0) < 1e-9
    assert stats.n_plates_wt_from_replicates == 1


def test_dedicated_wt_rows_never_become_wells():
    """WT replicate rows must not surface as merged rows or reach the export."""
    kuro, mame, activity, plate_meta = _wt_denominator_case()
    rows, _ = merge_activity_with_genotype(
        kuro, mame, activity, plate_meta, _wt_rows("P01", [2.0, 2.0, 2.0])
    )
    assert not any(r.well_id.startswith("WT") for r in rows)
    assert {r.well_id for r in rows} == {"A01", "B03"}


def test_dedicated_wt_rows_excluded_from_evolvepro_export(tmp_path):
    kuro, mame, activity, plate_meta = _wt_denominator_case()
    rows, _ = merge_activity_with_genotype(
        kuro, mame, activity, plate_meta, _wt_rows("P01", [2.0, 2.0, 2.0])
    )
    out = tmp_path / "evolvepro.csv"
    n = export_evolvepro_csv(rows, out, round_n=1)
    body = out.read_text()
    assert "WT_1" not in body and "WT_2" not in body and "WT_3" not in body
    # Only the designed mutant survives the export filter.
    assert n == 1
    assert "F89W" in body


def test_zero_wt_mean_yields_none_fold_change():
    """All-zero dedicated WT rows are not a usable denominator; keep None."""
    kuro, mame, activity, plate_meta = _wt_denominator_case()
    rows, stats = merge_activity_with_genotype(
        kuro, mame, activity, plate_meta, _wt_rows("P01", [0.0, 0.0])
    )
    rec = next(r for r in rows if r.well_id == "B03")
    assert rec.fold_change is None
    assert rec.log2_fc is None
    assert stats.n_wt_replicate_rows == 2
