#!/usr/bin/env python3
"""Bounded, geometry-only offline pilot. See frozen protocol beside results.

python scripts/benchmark_spatial_methods.py --pdb-dir /path/to/public/pdb > results.json
No network, model, biological recommendation or application default mutation.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kuma_core.kuro.evolvepro import structural_diversity_select

# (identity, coordinate or None, synthetic surrogate score or None)
def points(coords):
    return [(str(i + 1), tuple(x), float(len(coords)-i)) for i, x in enumerate(coords)]


def development():
    core = points([(0,0,0),(1,0,0),(0,1,0),(2,1,0),(1,2,0),(2,2,0)])
    return {
        'line_score_cluster': (points([(x,0,0) for x in (0,1,2,3,10,11,20,21)]),3,'development',None),
        'two_lobes': (points([(0,0,0),(1,0,0),(0,1,0),(10,0,0),(11,0,0),(10,1,0),(5,2,0)]),3,'development',None),
        'core_without_outlier': (core,3,'development',None),
        'core_with_outlier': (core+[('7',(100.,0.,0.),-5.)],3,'development','7'),
        'core_with_moved_outlier': (core+[('7',(1000.,0.,0.),-5.)],3,'development','7'),
        'folded_hairpin': ([('1',(0.,0.,0.),3.),('100',(.1,0.,0.),2.),('2',(8.,0.,0.),1.)],2,'development',None),
        'duplicate_and_missing': (core+[core[0],('9',None,8.)],3,'development',None),
    }


def heldout():
    result = {}
    for family in ('sphere','helix','anisotropic'):
        for seed in (101,202,303):
            for n,k in ((24,3),(96,12),(256,24)):
                rng = random.Random(seed)
                coords=[]
                for i in range(n):
                    if family == 'sphere':
                        z=rng.uniform(-1,1); theta=rng.uniform(0,2*math.pi); radius=10+rng.uniform(-.2,.2)
                        coords.append((radius*math.sqrt(1-z*z)*math.cos(theta),radius*math.sqrt(1-z*z)*math.sin(theta),radius*z))
                    elif family == 'helix':
                        t=6*math.pi*i/(n-1)
                        coords.append((5*math.cos(t)+rng.uniform(-.1,.1),5*math.sin(t)+rng.uniform(-.1,.1),t+rng.uniform(-.1,.1)))
                    else:
                        coords.append((rng.gauss(0,12),rng.gauss(0,3),rng.gauss(0,.5)))
                result[f'{family}_seed{seed}_n{n}']=(points(coords),k,'heldout_'+family,None)
    return result


def canonical(rows):
    by_id={}; missing=[]; duplicates=0
    for identity,xyz,score in rows:
        row=(identity,xyz,score)
        if identity in by_id:
            if row != by_id[identity]: raise ValueError('conflicting identity')
            duplicates+=1; continue
        by_id[identity]=row
        if xyz is None or not all(math.isfinite(x) for x in xyz): missing.append(identity)
        if score is not None and not math.isfinite(score): raise ValueError('nonfinite score')
    def key(row):
        # Synthetic reference positions sort numerically; full author IDs sort lexicographically.
        try: return (0,int(row[0]))
        except ValueError: return (1,row[0])
    eligible=sorted((r for r in by_id.values() if r[0] not in missing),key=key)
    if len(eligible)>2000: raise ValueError('U exceeds pilot matrix budget')
    return eligible,{'N_raw_rows':len(rows),'U_eligible_unique':len(eligible),'duplicate_rows':duplicates,'missing_ids':missing}


def fps(rows,k):
    ranked=sorted(range(len(rows)),key=lambda i: (-(rows[i][2] or 0.),i))
    encoded=[(f'A{i+1}G',rows[i][2] or 0.) for i in ranked]
    coordinates: list[tuple[float, float, float] | None] = [None]
    coordinates.extend(r[1] for r in rows)
    selected,_=structural_diversity_select(encoded,k,ca_coords=coordinates,kappa=0.,anchor_variants=())
    return [int(r[0][1:-1])-1 for r in selected]


def matrix(rows):
    n=len(rows); d=[[0.]*n for _ in rows]
    for i in range(n):
        for j in range(i): d[i][j]=d[j][i]=math.dist(rows[i][1],rows[j][1])
    return d


def separation(selected,d):
    return min((d[i][j] for i,j in itertools.combinations(selected,2)),default=0.)


def refine(selected,d,max_proposals=5000,max_passes=3):
    selected=list(selected); count=0; accepted=0; passes=0; changed=False
    while passes<max_passes and count<max_proposals:
        passes+=1; changed=False; current=separation(selected,d)
        for slot in range(len(selected)):
            kept=selected[:slot]+selected[slot+1:]
            kept_min=separation(kept,d) if len(kept)>1 else math.inf
            for candidate in range(len(d)):
                if candidate in selected: continue
                if count>=max_proposals: break
                count+=1
                value=min(kept_min,min((d[candidate][j] for j in kept),default=0.))
                if value>current:
                    selected[slot]=candidate; accepted+=1; changed=True; break
            if changed or count>=max_proposals: break
        if not changed: break
    return selected,{'proposals':count,'accepted_swaps':accepted,'passes':passes,'budget_exhausted':max_passes<=0 or count>=max_proposals or (changed and passes>=max_passes),'termination':'bounded; no global optimality claim'}


def exact(d,k):
    if len(d)>12 or math.comb(len(d),k)>50000: raise ValueError('exact budget exceeded')
    best=None; value=-1.
    for subset in itertools.combinations(range(len(d)),k):
        score=separation(subset,d)
        if score>value: best=list(subset); value=score
    if best is None: raise ValueError("no feasible exact subset")
    return best


def metrics(rows,selected,d):
    nearest=[min((d[i][j] for j in selected if i!=j),default=0.) for i in selected]
    coverage=[min(d[i][j] for j in selected) for i in range(len(rows))]
    result={'min_pair_distance':separation(selected,d),'selected_nearest_neighbors':nearest,'coverage_mean':statistics.fmean(coverage),'coverage_max':max(coverage)}
    if all(r[2] is not None for r in rows):
        result['synthetic_score_sum_gap']=sum(sorted((r[2] for r in rows),reverse=True)[:len(selected)])-sum(rows[i][2] for i in selected)
    return result


def execute(raw,k,method,seed=None,parse_ms=0.):
    start=time.perf_counter(); rows,info=canonical(raw)
    if not 1<=k<=len(rows): raise ValueError(f'infeasible k={k}; U={len(rows)}')
    details={}; calls=0
    if method=='fps':
        chosen=fps(rows,k); calls=k*len(rows)-k*(k+1)//2
    elif method=='random': chosen=random.Random(seed).sample(range(len(rows)),k)
    elif method=='top_score': chosen=sorted(range(len(rows)),key=lambda i: (-rows[i][2],i))[:k]
    elif method=='one_swap':
        chosen=fps(rows,k); calls=k*len(rows)-k*(k+1)//2
        d=matrix(rows); calls+=len(rows)*(len(rows)-1)//2
        chosen,details=refine(chosen,d)
    elif method=='exact':
        d=matrix(rows); calls=len(rows)*(len(rows)-1)//2; chosen=exact(d,k)
    else: raise ValueError(method)
    elapsed=(time.perf_counter()-start)*1000
    result={'selected_ids':[rows[i][0] for i in chosen],'runtime_ms':elapsed,'end_to_end_ms':elapsed+parse_ms,'pair_distance_evaluations':calls,'count_kind':'analytical production FPS plus explicit matrix pairs; metrics excluded',**details}
    result['metrics']=metrics(rows,chosen,matrix(rows))
    return result


def parse_pdb(path,code):
    start=time.perf_counter(); payload=path.read_bytes(); text=payload.decode('ascii'); rows=[]; seen=set(); model='1'; excluded_altloc=0
    for line in text.splitlines():
        if line.startswith('MODEL '):
            model=line[10:14].strip()
            if model!='1': break
        if line.startswith('ENDMDL'): break
        if not (line.startswith('ATOM  ') and line[12:16].strip()=='CA' and line[21:22]=='A'): continue
        if line[16:17] not in (' ','A'):
            excluded_altloc+=1; continue
        identity=f'{model}:A:{line[22:26].strip()}:{line[26:27].strip()}'
        if identity in seen: raise ValueError('ambiguous duplicate CA identity '+identity)
        seen.add(identity); rows.append((identity,tuple(float(line[a:b]) for a,b in ((30,38),(38,46),(46,54))),None))
    if not rows: raise ValueError('no chain A model 1 CA points')
    metadata={'source':f'https://files.rcsb.org/download/{code}.pdb','sha256':hashlib.sha256(payload).hexdigest(),'model':'1','chain':'A','assembly_policy':'deposited chain A only; no biological assembly transform','reference_mapping':'identity to observed author residue IDs only; no user-sequence mapping','excluded_altloc_records':excluded_altloc,'header':text.splitlines()[0],'assembly_declarations':[line.strip() for line in text.splitlines() if line.startswith('REMARK 350') and ('BIOMOLECULE:' in line or 'BIOLOGICAL UNIT:' in line)],'parse_ms':(time.perf_counter()-start)*1000}
    return rows,metadata


def run(pdb_dir):
    cases={**development(),**heldout()}; public_meta={}; blocked=[]
    for code in ('3N0F','3N0G','1UBQ','1TIM'):
        path=pdb_dir/(code+'.pdb')
        try: raw,meta=parse_pdb(path,code)
        except (OSError,ValueError) as exc:
            blocked.append({'structure':code,'reason':str(exc)}); continue
        for k in (12,95):
            name=f'{code}_A_k{k}'; cases[name]=(raw,k,'public_3N0FG' if code in ('3N0F','3N0G') else 'public_'+code,None); public_meta[name]=meta
    result={'protocol_sha256':hashlib.sha256((ROOT/'docs/audit/spatial-method-pilot-20261009/protocol.md').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'python':platform.python_version(),'platform':platform.platform(),'blocked_public_inputs':blocked,'cases':{}}
    for name,(raw,k,group,outlier) in cases.items():
        rows,info=canonical(raw); item={**info,'k':k,'group':group,'input_sha256':hashlib.sha256(json.dumps(raw).encode()).hexdigest(),'public_metadata':public_meta.get(name),'synthetic_outlier':outlier}
        result['cases'][name]=item
        if k>len(rows): item['status']='infeasible'; item['reason']=f'k={k} exceeds U={len(rows)}; no replacement or top-up'; continue
        item['status']='evaluated'; parse_ms=public_meta.get(name,{}).get('parse_ms',0.)
        methods=['fps','one_swap']
        if all(r[2] is not None for r in rows): methods+=['top_score']
        if len(rows)<=12 and math.comb(len(rows),k)<=50000: methods+=['exact']
        item['methods']={m:execute(raw,k,m,parse_ms=parse_ms) for m in methods}
        trials=[execute(raw,k,'random',seed=s,parse_ms=parse_ms) for s in range(32)]
        item['random_32']={'seeds':list(range(32)),'trials':trials,'summary':{metric:{'min':min(t['metrics'][metric] for t in trials),'mean':statistics.fmean(t['metrics'][metric] for t in trials),'max':max(t['metrics'][metric] for t in trials)} for metric in ('min_pair_distance','coverage_mean','coverage_max')}}
        for m,value in item['methods'].items():
            if outlier: value['includes_labelled_outlier']=outlier in value['selected_ids']
        assert item['methods']['one_swap']['metrics']['min_pair_distance']>=item['methods']['fps']['metrics']['min_pair_distance']
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--pdb-dir',type=Path,required=True); args=parser.parse_args()
    print(json.dumps(run(args.pdb_dir),indent=2,allow_nan=False))
