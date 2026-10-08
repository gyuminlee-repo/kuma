"""Synthetic-only contract for the opt-in trusted-coordinate diagnostic."""
from __future__ import annotations

import itertools
import math

import pytest

from kuma_core.kuro.spatial_dispersion import (
    ResidueIdentity, ResiduePoint, prepare_trusted_residues,
    select_farthest_first, select_top_score, select_random, measure_dispersion,
)


def point(pos, xyz, score=0., chain="A", number=None, insertion=""):
    return ResiduePoint(pos, ResidueIdentity("1", chain, pos if number is None else number, insertion), xyz, score)


def prepare(points):
    return prepare_trusted_residues(points, frame_id="synthetic:reference:1/A")


def line():
    return [point(1, (0.,0.,0.), 4.), point(2, (2.,0.,0.), 3.),
            point(3, (5.,0.,0.), 2.), point(4, (10.,0.,0.), 1.)]


def test_hand_computed_fps_and_metrics():
    data = prepare(line())
    assert select_farthest_first(data, 3) == (1, 4, 3)
    m = measure_dispersion(data, (1, 4, 3))
    assert m.min_pair_distance == 5.
    assert dict(m.selected_nearest_neighbor) == {1:5., 3:5., 4:5.}
    assert dict(m.candidate_nearest_selected) == {1:0., 2:2., 3:0., 4:0.}
    assert m.coverage_mean == .5 and m.coverage_max == 2.
    assert m.total_score_loss == 2. and m.mean_score_loss == pytest.approx(2/3)
    assert select_top_score(data, 3) == (1, 2, 3)
    assert measure_dispersion(data, (1, 2, 3)).total_score_loss == 0.


def test_empty_singleton_and_full_coverage():
    empty = prepare([])
    assert select_farthest_first(empty, 0) == ()
    m = measure_dispersion(empty, ())
    assert m.min_pair_distance is None and m.coverage_mean is None
    data = prepare(line())
    zero = measure_dispersion(data, ())
    assert zero.coverage_max is None
    assert all(v is None for _, v in zero.candidate_nearest_selected)
    one = measure_dispersion(data, (1,))
    assert one.min_pair_distance is None
    assert one.selected_nearest_neighbor == ((1, None),)
    all_points = measure_dispersion(data, select_farthest_first(data, 4))
    assert all_points.coverage_mean == all_points.coverage_max == 0.


@pytest.mark.parametrize("k", [-1, 5, 1.5, True])
def test_invalid_budget_rejected(k):
    for selector in (select_farthest_first, select_top_score):
        with pytest.raises(ValueError):
            selector(prepare(line()), k)
    with pytest.raises(ValueError):
        select_random(prepare(line()), k, seed=3)


def test_permutation_and_defined_distance_ties():
    points = [point(3,(-2.,0.,0.),2.), point(2,(2.,0.,0.),2.), point(1,(0.,0.,0.),3.)]
    for order in itertools.permutations(points):
        data = prepare(order)
        assert select_farthest_first(data, 3) == (1, 2, 3)
        assert select_top_score(data, 3) == (1, 2, 3)
        assert select_random(data, 2, seed=12) == select_random(prepare(points), 2, seed=12)
    # Distance tie first uses score, then stable reference position.
    assert select_farthest_first(prepare([points[0], point(2,(2.,0.,0.),1.), points[2]]), 2) == (1, 3)


def test_rigid_transform_and_scaling_without_near_ties():
    baseline = prepare(line())
    selected = select_farthest_first(baseline, 3)
    bm = measure_dispersion(baseline, selected)
    assert bm.min_pair_distance is not None and bm.coverage_mean is not None
    for scale in [1., 7.]:
        transformed = []
        for p in line():
            assert p.coordinate is not None
            transformed.append(point(p.position, (-p.coordinate[1]*scale+100., p.coordinate[0]*scale-30., p.coordinate[2]*scale+8.), p.score))
        data = prepare(transformed)
        assert select_farthest_first(data, 3) == selected
        m = measure_dispersion(data, selected)
        assert m.min_pair_distance == pytest.approx(bm.min_pair_distance*scale)
        assert m.coverage_mean == pytest.approx(bm.coverage_mean*scale)
        assert m.total_score_loss == bm.total_score_loss


def test_missing_nonfinite_and_exact_duplicates_reported():
    p = point(1,(0.,0.,0.),4.)
    data = prepare([p,p,point(2,None),point(3,(math.nan,0.,0.)),point(4,(math.inf,0.,0.))])
    assert tuple(p.position for p in data.eligible) == (1,)
    assert data.duplicate_rows == 1
    assert data.excluded == ((2,"missing_ca"),(3,"nonfinite_ca"),(4,"nonfinite_ca"))
    assert select_farthest_first(data, 1) == (1,)
    with pytest.raises(ValueError):
        select_farthest_first(data, 2)


@pytest.mark.parametrize("other", [point(1,(1.,0.,0.),1.), point(1,(0.,0.,0.),2.), point(1,(0.,0.,0.),1.,number=8)])
def test_conflicting_duplicate_position_rejected(other):
    with pytest.raises(ValueError, match="conflicting"):
        prepare([point(1,(0.,0.,0.),1.),other])


def test_residue_identity_and_frame_guards():
    # 10 and 10A are distinct residues, even at equal CA coordinates.
    data = prepare([point(1,(0.,0.,0.),number=10),point(2,(0.,0.,0.),number=10,insertion="A")])
    assert measure_dispersion(data,(1,2)).min_pair_distance == 0.
    assert data.eligible[1].residue_id.insertion_code == "A"
    with pytest.raises(ValueError, match="residue"):
        prepare([point(1,(0.,0.,0.),number=10),point(2,(1.,0.,0.),number=10)])
    with pytest.raises(ValueError, match="single"):
        prepare([point(1,(0.,0.,0.)),point(2,(1.,0.,0.),chain="B")])
    with pytest.raises(ValueError, match="frame"):
        prepare_trusted_residues([],frame_id="")


@pytest.mark.parametrize("p", [point(0,(0.,0.,0.)),point(True,(0.,0.,0.)),point(1,(0.,0.),1.),point(1,(0.,0.,0.),math.nan)])
def test_invalid_point_rejected(p):
    with pytest.raises(ValueError):
        prepare([p])


def test_selected_positions_are_unique_and_eligible():
    data=prepare(line())
    for positions in [(1,1),(99,), (True,)]:
        with pytest.raises(ValueError):
            measure_dispersion(data,positions)
    assert measure_dispersion(data,(4,1,3)) == measure_dispersion(data,(1,3,4))


def test_hairpin_and_labelled_outlier_are_geometry_only():
    hairpin=prepare([point(1,(0.,0.,0.),3.),point(100,(.1,0.,0.),2.),point(2,(8.,0.,0.),1.)])
    assert select_farthest_first(hairpin,2)==(1,2)
    core=line()
    outlier=point(9,(1000.,0.,0.),-10.)
    data=prepare(core+[outlier])
    assert 9 in select_farthest_first(data,2)
    assert 9 not in select_top_score(data,2)
    assert measure_dispersion(data,select_farthest_first(data,2)).total_score_loss > 0.


def test_no_nan_or_infinite_metrics_for_extreme_inputs():
    data=prepare([point(1,(1e308,0.,0.)),point(2,(-1e308,0.,0.))])
    with pytest.raises(ValueError, match="distance"):
        select_farthest_first(data,2)
    with pytest.raises(ValueError, match="distance"):
        measure_dispersion(data,(1,2))


def test_conflicting_nonfinite_duplicates_do_not_collapse():
    with pytest.raises(ValueError, match="conflicting"):
        prepare([point(1,(math.inf,0.,0.)),point(1,(math.nan,0.,0.))])
    with pytest.raises(ValueError, match="conflicting"):
        prepare([point(1,(math.nan,0.,0.)),point(1,(math.nan,1.,0.))])


def test_finite_loss_and_mean_do_not_overflow_intermediate_sums():
    data=prepare([point(1,(0.,0.,0.),1e308),point(2,(1.,0.,0.),1e308),point(3,(2.,0.,0.),7e307)])
    metrics=measure_dispersion(data,(1,3))
    assert metrics.selected_score_sum == pytest.approx(1.7e308)
    assert metrics.total_score_loss == pytest.approx(3e307)
    data=prepare([point(1,(0.,0.,0.)),point(2,(1e308,0.,0.)),point(3,(1e308,0.,0.))])
    assert measure_dispersion(data,(1,)).coverage_mean == pytest.approx(1e308*(2/3))


def test_singleton_needs_no_distances_but_legacy_unsafe_span_is_rejected():
    data=prepare([point(1,(1e308,0.,0.),1.),point(2,(-1e308,0.,0.))])
    assert select_farthest_first(data,1)==(1,)
    data=prepare([point(1,(0.,0.,0.),1.),point(2,(1e308,0.,0.)),point(3,(-1e308,0.,0.))])
    with pytest.raises(ValueError, match="numeric range"):
        select_farthest_first(data,2)


def test_mixed_sign_finite_score_total_uses_safe_fallback():
    data=prepare([point(1,(0.,0.,0.),1e308),point(2,(1.,0.,0.),1e308),point(3,(2.,0.,0.),-1e308)])
    metrics=measure_dispersion(data,(1,2,3))
    assert metrics.selected_score_sum == 1e308
    assert metrics.total_score_loss == 0.


def test_comparison_contract_and_legacy_reuse_on_synthetic_fixtures():
    from scripts.compare_spatial_dispersion import run_comparison
    import json

    result=run_comparison()
    json.dumps(result,allow_nan=False)
    assert result["contract"]["version"]==1
    assert result["contract"]["random_seeds"]==list(range(32))
    for fixture in result["fixtures"].values():
        methods=fixture["methods"]
        assert methods["fps"]["selected_positions"] == methods["legacy_structural_fullpool"]["selected_positions"]
        assert methods["fps"]["selected_positions"] == methods["reference_fps"]["selected_positions"]
        for method in methods.values():
            assert method["metrics"]["n_selected"] == fixture["k"]
            assert method["metrics"]["n_eligible"] == fixture["n_eligible"]
        assert methods["top_score"]["metrics"]["total_score_loss"]==0.
        assert len(fixture["random_32"]["selected_positions_by_seed"])==32
    fixture=result["fixtures"]["line_score_cluster"]
    assert fixture["methods"]["fps"]["metrics"]["coverage_max"]==3.
    assert fixture["methods"]["legacy_pareto_pool2"]["metrics"]["coverage_max"]==10.
    assert result["fixtures"]["duplicate_and_missing"]["excluded"]==((9,"missing_ca"),)


def test_production_fps_reuses_existing_selector_with_dense_single_positions(monkeypatch):
    from kuma_core.kuro import spatial_dispersion as module
    real=module.structural_diversity_select
    captured={}
    def spy(rows,k,**kwargs):
        captured.update(rows=rows,k=k,**kwargs)
        return real(rows,k,**kwargs)
    monkeypatch.setattr(module,"structural_diversity_select",spy)
    data=prepare([point(10**9,(0.,0.,0.),2.),point(10**9+1,(4.,0.,0.),1.)])
    assert select_farthest_first(data,2)==(10**9,10**9+1)
    assert captured["rows"]==[("A1G",2.),("A2G",1.)]
    assert len(captured["ca_coords"])==3
    assert captured["kappa"]==0. and captured["anchor_variants"]==()


def test_non_axis_aligned_rigid_rotation_with_separated_distances():
    base=prepare(line())
    selected=select_farthest_first(base,3)
    expected=measure_dispersion(base,selected)
    for theta in (.37,1.11):
        rotated=[]
        for p in line():
            assert p.coordinate is not None
            x,y,z=p.coordinate
            rotated.append(point(p.position,(x*math.cos(theta)-y*math.sin(theta)+.8,x*math.sin(theta)+y*math.cos(theta)-2.,z+7.),p.score))
        data=prepare(rotated)
        assert select_farthest_first(data,3)==selected
        measured=measure_dispersion(data,selected)
        assert measured.min_pair_distance==pytest.approx(expected.min_pair_distance)
        assert measured.coverage_mean==pytest.approx(expected.coverage_mean)
