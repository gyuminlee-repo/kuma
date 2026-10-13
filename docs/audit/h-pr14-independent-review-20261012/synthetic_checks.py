"""Independent assertions against untouched remote source, no dependency stubs."""
import sys, json, math, re, typing, traceback, hashlib, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT/'source'),str(ROOT/'source/python-core')]
from kuma_core.kuro.strict_spatial import exact_pdb_context, select_single_sites
from kuma_core.kuro.evolvepro import load_evolvepro_csv
from kuma_core.kuro.alphafold import _THREE_TO_ONE
from sidecar_kuro.models import FetchActiveSiteResult
OUT=ROOT/'fixtures'; OUT.mkdir(exist_ok=True)
results=[]
def test(name,fn):
 try:
  detail=fn(); results.append({'name':name,'status':'PASS','detail':detail}); print('PASS',name,detail)
 except Exception as e:
  results.append({'name':name,'status':'FAIL','detail':str(e)}); traceback.print_exc(); print('FAIL',name)
def rejects(fn,phrase):
 try: fn()
 except ValueError as e: assert phrase in str(e),str(e); return str(e)
 raise AssertionError('Expected ValueError')
AF='TITLE     ALPHAFOLD MONOMER V2.0 PREDICTION FOR SYNTHETIC TEST\n'
def pdb(scores=(90,30,49.99,50,90),seq=('MET','ALA','CYS','ASP','GLU'),header=AF,nan=None):
 return header+'\n'.join(f'ATOM  {i:5d}  CA  {aa:3s} A{i:4d}    {float("nan") if i==nan else float(i*10):8.3f}{0.:8.3f}{0.:8.3f}  1.00{b:6.2f}           C' for i,(aa,b) in enumerate(zip(seq,scores),1))
ROWS=[('A2G',100.),('C3G',90.),('D4G',80.),('E5G',70.)]
def confidence():
 ctx=exact_pdb_context(pdb(),'MACDE','SYNTHETIC'); selected,r=select_single_sites(ROWS,'MACDE',ctx,2)
 assert selected==[('D4G',80.),('E5G',70.)]
 assert r['comparison']['top_n_variants']==['D4G','E5G']
 assert r['coordinate_confidence']['excluded_variant_count']==2
 assert r['input_variant_count']==4
 return r['coordinate_confidence']
test('pLDDT_49.99_excluded_50_included_and_fps_start',confidence)
test('all_low_confidence_rejects_without_fallback',lambda:rejects(lambda:select_single_sites(ROWS,'MACDE',exact_pdb_context(pdb((30,)*5),'MACDE','X'),1),'exceeds 0'))
test('post_filter_budget_too_large',lambda:rejects(lambda:select_single_sites(ROWS,'MACDE',exact_pdb_context(pdb(),'MACDE','X'),3),'exceeds 2'))
def missing():
 ctx=exact_pdb_context(pdb((90,)*5,nan=2),'MACDE','X');s,r=select_single_sites(ROWS,'MACDE',ctx,3)
 assert 'A2G' not in dict(s); assert r['excluded']==[{'variant':'A2G','reason':'missing_or_nonfinite_coordinate'}]
 return r['excluded']
test('nonfinite_coordinate_excluded',missing)
test('all_missing_coordinates_reject',lambda:rejects(lambda:select_single_sites(ROWS,'MACDE',{'mapping':[]},1),'exceeds 0'))
def experimental():
 s,r=select_single_sites(ROWS,'MACDE',exact_pdb_context(pdb(header='TITLE     SYNTHETIC X-RAY STRUCTURE\n'),'MACDE','X'),2)
 assert s[0][0]=='A2G';assert r['coordinate_confidence']['source']=='unavailable';assert not r['excluded']
test('experimental_bfactor_not_filtered',experimental)
for value in ['      ',' -1.00','101.00','   nan','   inf']:
 test('invalid_plddt_'+repr(value),lambda value=value:rejects(lambda:exact_pdb_context(pdb().replace(' 30.00',value),'MACDE','X'),'pLDDT'))
def mapping():
 ctx=exact_pdb_context(pdb((90,)*5),'ACDE','X')
 assert [(m['reference_position'],m['structure_position']) for m in ctx['mapping']]==[(1,2),(2,3),(3,4),(4,5)]
 assert select_single_sites([('C2G',3.),('E4G',2.)],'ACDE',ctx,2)[1]['selected_positions']==[2,4]
 return ctx['mapping']
test('reference_subsequence_offset',mapping)
for variant in ['V2G','A9G','A2G:C3G']:
 test('reject_identity_'+variant,lambda variant=variant:rejects(lambda:select_single_sites([(variant,1.)],'MACDE',exact_pdb_context(pdb(),'MACDE','X'),1),'Strict' if ':' in variant else 'reference'))
test('missing_CA_number_not_silently_remapped',lambda:rejects(lambda:exact_pdb_context('\n'.join(l for l in pdb().splitlines() if not l.startswith('ATOM      3')),'MACDE','X'),'contiguous'))
test('ambiguous_reference_reject',lambda:rejects(lambda:exact_pdb_context(pdb((90,)*5,('ALA',)*5),'AAA','X'),'unique exact'))
def ctx(mode='unique_sites',cap=None):return {'mapping':[{'reference_position':p,'coordinate':(x,0.,0.)} for p,x in zip(range(2,6),(0.,1.,10.,11.))],'budget_mode':mode,'site_cap':cap,'score_order':'desc'}
def baseline(order):
 data=[('A2C',10.),('A2D',9.),('A3C',8.),('A4C',7.),('A5C',6.)] if order=='desc' else [('A2C',-1.),('A2D',-2.),('A3C',-3.),('A4C',-4.),('A5C',-5.)]
 c=ctx();c['score_order']=order;s,r=select_single_sites(data,'MAAAA',c,2);b=r['comparison']
 assert [v for v,_ in s]==['A2C','A5C'];assert b['top_n_variants']==['A2C','A2D'];assert b['representative_top_n']['top_n_variants']==['A2C','A3C']
 assert b['score_gap_to_top_n']==1.5;assert b['selected']['coverage_mean_distance']==.5;assert b['top_n']['coverage_mean_distance']==5.5
 return b
for order in ['asc','desc']:test('raw_top_n_'+order,lambda order=order:baseline(order))
def capacity():
 data=[(f'A{p}{a}',float(100-p)) for p in range(2,7) for a in 'CDEFGHIKLMNPQRSTVWY']
 c={'budget_mode':'distinct_variants','mapping':[{'reference_position':p,'coordinate':(float(p),0.,0.)} for p in range(2,7)]}
 s,r=select_single_sites(data,'MAAAAA',c,95);assert set(s)==set(data);assert r['selected_site_count']==5;assert r['geometry_variant_min_pair_distance']==0
 rejects(lambda:select_single_sites(data,'MAAAAA',c,96),'capacity');c['site_cap']=1
 rejects(lambda:select_single_sites(data,'MAAAAA',c,6),'exceeds 5');assert len(select_single_sites(data,'MAAAAA',c,5)[0])==5
 return '95 variants / 5 sites, 96 rejected; cap=1 gives capacity=5'
test('distinct_variant_capacity_95_96_and_cap',capacity)
for n in [0,-1,True,1.5]:test('invalid_count_'+str(n),lambda n=n:rejects(lambda:select_single_sites(ROWS,'MACDE',exact_pdb_context(pdb(),'MACDE','X'),n),'positive explicit count'))
def csv_flow():
 f=OUT/'candidates.csv';f.write_text('variant,y_pred\nM1G,110\nA2G,100\nC3G,90\nD4G,80\nE5G,70\nD4G,80\n',encoding='utf-8')
 c=exact_pdb_context(pdb(),'MACDE','SYNTHETIC');c.update(candidate_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),score_order='desc')
 r=load_evolvepro_csv(f,top_n=2,ref_seq='MACDE',structural_diversity=True,strict_spatial_context=c)
 assert r['variants']==['D4G','E5G'];assert {'A2G','C3G'}<=set(r['pool_variants'])
 assert r['strict_spatial']['start_position_omitted_count']==1;assert r['strict_spatial']['duplicate_variant_omitted_count']==1
 (OUT/'csv-result.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
 return {'selected':r['variants'],'pool':r['pool_variants']}
test('real_csv_loader_preserves_low_confidence_candidates',csv_flow)
def annotation():
 allowed=set(typing.get_args(FetchActiveSiteResult.model_fields['annotation_status'].annotation));line=next(l for l in (ROOT/'source/src/types/validators.ts').read_text().splitlines() if 'value.annotation_status' in l)
 assert allowed==set(re.findall(r'item === "([a-z_]+)"',line));return sorted(allowed)
test('annotation_literal_matches_TS',annotation)
(ROOT/'synthetic-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('SUMMARY',len(results),'checks',sum(r['status']=='FAIL' for r in results),'failed')
sys.exit(any(r['status']=='FAIL' for r in results))
