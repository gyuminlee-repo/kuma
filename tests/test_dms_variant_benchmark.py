"""Tiny artificial controls for the public DMS replay; no assay tuning."""
import importlib.util
from pathlib import Path
import pytest

path=Path(__file__).resolve().parents[1]/'scripts/benchmark_dms_variants.py'
spec=importlib.util.spec_from_file_location('dms_pilot',path)
assert spec is not None and spec.loader is not None
pilot=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=pilot
spec.loader.exec_module(pilot)


def raw():
    return [{'variant':v,'position':p,'score':s,'coordinate':xyz} for v,p,s,xyz in [
        ('A1C',1,5.,(0.,0.,0.)),('A1D',1,4.,(0.,0.,0.)),
        ('A2C',2,3.,(2.,0.,0.)),('A3C',3,2.,(10.,0.,0.))]]


def test_tiny_facility_initial_medoid_and_next_gain():
    chosen,_=pilot.select(raw(),'facility',count=2)
    assert chosen==['A2C','A3C']


def test_saturated_geometry_keeps_other_variants():
    chosen,_=pilot.select(raw(),'facility',count=4)
    assert len(set(chosen))==4 and set(chosen)=={r['variant'] for r in raw()}
    assert chosen[-1]=='A1D'


@pytest.mark.parametrize('method',['fps','top_score','random','facility'])
def test_budget_distinct_and_label_independence(method):
    data={'candidates':raw(),'outcomes':{r['variant']:{'value':float(i),'binary':i%2} for i,r in enumerate(raw())}}
    first=pilot.select(data['candidates'],method,count=3,seed=7)[0]
    permuted=list(reversed(list(data['outcomes'].values())))
    data['outcomes']=dict(zip(data['outcomes'],permuted))
    second=pilot.select(data['candidates'],method,count=3,seed=7)[0]
    data['outcomes']={}
    third=pilot.select(data['candidates'],method,count=3,seed=7)[0]
    assert first==second==third and len(set(first))==3
    with pytest.raises(ValueError,match='infeasible'):pilot.select(raw(),method,count=95)


def test_selector_rejects_label_field():
    rows=raw();rows[0]['DMS_score']=100
    with pytest.raises(ValueError,match='unexpected fields'):pilot.select(rows,'fps',count=3)


def test_missing_outcome_is_unknown_not_failure():
    outcomes: dict[str, dict[str, float | None]]={r['variant']:{'value':None,'binary':None} for r in raw()}
    outcomes['A1C']={'value':2.,'binary':1}
    metrics=pilot.measure(raw(),outcomes,['A1C','A1D'])
    assert metrics['selected_variant_count']==2 and metrics['selected_site_count']==1
    assert metrics['measured_observed_count']==1 and metrics['measured_mean']==2
    assert metrics['binary_observed_count']==1 and metrics['binary_positive_fraction']==1
    assert metrics['variant_inclusive_min_pair_distance']==0
    assert metrics['functional_coverage'] is None


def test_all_zero_geometry_score_tie_fill():
    rows=raw()
    for r in rows:r['coordinate']=(0.,0.,0.)
    chosen,_=pilot.select(rows,'facility',count=4)
    assert chosen==['A1C','A1D','A2C','A3C']


def test_conflicts_and_guard_fail_closed():
    rows=raw();rows[1]['coordinate']=(1.,0.,0.)
    with pytest.raises(ValueError,match='conflicting site'):pilot.select(rows,'fps',count=3)
    rows=[{'variant':f'A{i}C','position':i,'score':0.,'coordinate':(float(i),0.,0.)} for i in range(1,502)]
    with pytest.raises(ValueError,match='guard exceeded'):pilot.select(rows,'facility',count=95)


def test_input_permutation_invariance():
    for method in ['fps','top_score','facility','random']:
        assert pilot.select(raw(),method,count=3,seed=2)[0]==pilot.select(list(reversed(raw())),method,count=3,seed=2)[0]


def test_fps_uses_numeric_position_tie_order():
    rows=[{'variant':f'A{p}C','position':p,'score':0.,'coordinate':(0.,0.,0.)} for p in (10,2,1)]
    assert pilot.select(rows,'fps',count=3)[0]==['A1C','A2C','A10C']
