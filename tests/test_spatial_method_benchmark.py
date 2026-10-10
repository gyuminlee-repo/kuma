"""Offline pilot algorithm checks, not biological outcome tests."""
import importlib.util
import itertools
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'scripts/benchmark_spatial_methods.py'
spec=importlib.util.spec_from_file_location('pilot',path)
assert spec is not None and spec.loader is not None
pilot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)


def test_development_and_heldout_counts():
    assert len(pilot.development())==7
    assert len(pilot.heldout())==27
    assert pilot.heldout()==pilot.heldout()


def test_dedup_missing_conflict_and_infeasible():
    raw,k,_,_=pilot.development()['duplicate_and_missing']
    rows,info=pilot.canonical(raw)
    assert (len(rows),info['duplicate_rows'],info['missing_ids'])==(6,1,['9'])
    with pytest.raises(ValueError,match='conflicting'): pilot.canonical([('1',(0,0,0),1),('1',(1,0,0),1)])
    with pytest.raises(ValueError,match='infeasible'): pilot.execute(raw,95,'fps')


@pytest.mark.parametrize('name',list(pilot.development()))
def test_refinement_monotonic_bounded_and_exact_reference(name):
    raw,k,_,_=pilot.development()[name]
    rows,_=pilot.canonical(raw); d=pilot.matrix(rows)
    initial=pilot.fps(rows,k); chosen,details=pilot.refine(initial,d)
    assert len(set(chosen))==k
    assert pilot.separation(chosen,d)>=pilot.separation(initial,d)
    assert details['proposals']<=5000 and details['accepted_swaps']<=3
    exact=pilot.exact(d,k)
    assert pilot.separation(exact,d)>=pilot.separation(chosen,d)
    assert pilot.separation(exact,d)==max(pilot.separation(s,d) for s in itertools.combinations(range(len(rows)),k))


def test_exact_refuses_large_and_random_reproducible():
    rows=pilot.points([(i,0,0) for i in range(13)])
    with pytest.raises(ValueError,match='budget'): pilot.exact(pilot.matrix(rows),3)
    assert pilot.execute(rows,3,'random',seed=5)['selected_ids']==pilot.execute(rows,3,'random',seed=5)['selected_ids']


def test_distance_count_and_coverage():
    rows=pilot.points([(0,0,0),(2,0,0),(4,0,0)])
    result=pilot.execute(rows,2,'fps')
    assert result['pair_distance_evaluations']==3
    assert result['metrics']['min_pair_distance']==4
    assert result['metrics']['coverage_mean']==pytest.approx(2/3)


def test_refine_zero_budget_preserves_start():
    rows=pilot.points([(0,0,0),(2,0,0),(4,0,0)])
    initial=pilot.fps(rows,2)
    chosen,details=pilot.refine(initial,pilot.matrix(rows),max_proposals=0)
    assert chosen==initial and details['proposals']==0


def test_refine_zero_pass_budget_preserves_start():
    rows=pilot.points([(0,0,0),(2,0,0),(4,0,0)])
    initial=pilot.fps(rows,2)
    chosen,details=pilot.refine(initial,pilot.matrix(rows),max_passes=0)
    assert chosen==initial and details["passes"]==0 and details["budget_exhausted"]
