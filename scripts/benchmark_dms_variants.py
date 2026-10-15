#!/usr/bin/env python3
"""Label-isolated, frozen-predictor public DMS pilot; no model inference.

Prepare: --source-dir DIRECTORY --prepare OUTPUT.json
Evaluate: --inputs OUTPUT.json --output RESULTS.json
Preparation never runs selection or aggregates measured outcomes.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from dataclasses import dataclass
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import random
import re
import statistics
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kuma_core.kuro.evolvepro import structural_diversity_select
from kuma_core.kuro.strict_spatial import exact_pdb_context

ASSAYS = ('GFP_AEQVI_Sarkisyan_2016', 'RL40A_YEAST_Roscoe_2013')
SCORER = 'ESM2_650M'
PROTOCOL = ROOT / 'docs/audit/dms-variant-pilot-20261009/protocol.md'
PATTERN = re.compile(r'([ACDEFGHIKLMNPQRSTVWY])([1-9][0-9]*)([ACDEFGHIKLMNPQRSTVWY])')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


@dataclass(frozen=True)
class Candidate:
    """The complete selector-facing contract: deliberately no measured label."""
    variant: str
    position: int
    score: float
    coordinate: tuple[float, float, float]


def prepare(source: Path) -> dict:
    start = time.perf_counter()
    refs = {r['DMS_id']: r for r in csv.DictReader((source/'ref.txt').open())}
    manifest = json.loads((source/'manifest.json').read_text())
    result: dict[str, Any] = {'schema': 1, 'scorer': SCORER, 'score_direction': 'higher',
        'source_license': 'MIT; https://zenodo.org/records/15293562', 'sources': manifest,
        'reference_sha256': digest(source/'ref.txt'), 'config_sha256': digest(source/'config.json'), 'assays': {}}
    for assay in ASSAYS:
        ref = refs[assay]
        context = exact_pdb_context((source/ref['pdb_file']).read_text(), ref['target_seq'], ref['UniProt_ID'])
        coords = {m['reference_position']: tuple(m['coordinate']) for m in context['mapping']}
        # Read outcomes into a separate lookup. Their values never determine selection.
        outcomes: dict[str, dict] = {}
        measurement_rows = 0
        for row in csv.DictReader((source/'measurements_'/f'{assay}.csv').open()):
            measurement_rows += 1
            label = {'value': finite(row['DMS_score']), 'binary': finite(row['DMS_score_bin'])}
            if label['binary'] not in (None, 0., 1.):
                raise ValueError('unexpected binary outcome')
            key = row['mutant']
            if key in outcomes and outcomes[key] != label:
                raise ValueError('conflicting duplicate measurements')
            outcomes[key] = label
        seen: dict[str, float | None] = {}
        candidates = []
        omitted: Counter = Counter()
        raw_count = 0
        for row in csv.DictReader((source/'scores_'/f'{assay}.csv').open()):
            raw_count += 1
            variant = row['mutant']
            score = finite(row[SCORER])
            if variant in seen:
                if seen[variant] != score:
                    raise ValueError('conflicting duplicate predictor scores')
                omitted['duplicate_score_row'] += 1
                continue
            seen[variant] = score
            match = PATTERN.fullmatch(variant)
            if match is None:
                omitted['not_canonical_single_substitution'] += 1
                continue
            position = int(match[2])
            reason = None
            if match[1] == match[3]: reason = 'no_op'
            elif not 1 <= position <= len(ref['target_seq']) or ref['target_seq'][position-1] != match[1]: reason = 'reference_mismatch'
            elif score is None: reason = 'missing_or_nonfinite_predictor'
            elif position not in coords: reason = 'missing_coordinate'
            elif variant not in outcomes: reason = 'no_measurement_id'
            if reason:
                omitted[reason] += 1
                continue
            candidates.append({'variant': variant, 'position': position, 'score': score, 'coordinate': coords[position]})
        candidates.sort(key=lambda r: r['variant'])
        selected_outcomes = {c['variant']: outcomes[c['variant']] for c in candidates}
        result['assays'][assay] = {
            'role': 'pilot' if assay == ASSAYS[0] else 'independent_protein_policy_holdout',
            'assay_type': ref['selection_assay'], 'source_paper': ref['title'],
            'source_author': ref['first_author'], 'source_year': ref['year'],
            'N_score_rows': raw_count, 'N_measurement_rows': measurement_rows,
            'eligible_variant_count': len(candidates), 'eligible_site_count': len({c['position'] for c in candidates}),
            'omissions': dict(omitted), 'reference_sha256': context['reference_sha256'],
            'structure_sha256': context['source_sha256'], 'exact_mapping_size': len(coords),
            'functional_memberships': None, 'functional_status': 'no verified membership snapshot used',
            'candidates': candidates, 'outcomes': selected_outcomes,
        }
    result['common_preparation_ms'] = (time.perf_counter()-start)*1000
    return result


def validate(raw: list[dict], count: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()
    by_site: dict[int, tuple[float, float, float]] = {}
    for row in raw:
        if set(row) != {'variant', 'position', 'score', 'coordinate'}:
            raise ValueError('selector contract contains unexpected fields, including possible labels')
        xyz = tuple(row['coordinate'])
        if len(xyz) != 3 or not all(math.isfinite(v) for v in xyz) or not math.isfinite(row['score']):
            raise ValueError('nonfinite candidate')
        variant = row['variant']; position = row['position']
        match = PATTERN.fullmatch(variant)
        if match is None or int(match[2]) != position or match[1] == match[3] or variant in seen:
            raise ValueError('invalid or duplicate variant identity')
        coordinate = (xyz[0], xyz[1], xyz[2])
        if position in by_site and by_site[position] != coordinate:
            raise ValueError('conflicting site coordinate')
        by_site[position] = coordinate; seen.add(variant)
        candidates.append(Candidate(variant, position, float(row['score']), coordinate))
    if len(candidates) > 2500 or len(by_site) > 500:
        raise ValueError('pilot input guard exceeded; no truncation')
    if type(count) is not int or not 0 < count <= len(candidates):
        raise ValueError('infeasible distinct-variant budget')
    return sorted(candidates, key=lambda c: c.variant)


def greedy_facility(candidates: list[Candidate], count: int) -> list[Candidate]:
    """Greedy unique-site facility objective; score only breaks geometry ties."""
    sites = sorted({c.position for c in candidates})
    groups = {p: sorted((c for c in candidates if c.position == p), key=lambda c: (-c.score, c.variant)) for p in sites}
    coords = {c.position: c.coordinate for c in candidates}
    distances = {p: [math.dist(coords[p], coords[q]) for q in sites] for p in sites}
    nearest: list[float] | None = None
    selected: list[Candidate] = []
    for _ in range(count):
        best: Candidate | None = None; best_gain = -math.inf
        for p in sites:
            if not groups[p]: continue
            candidate = groups[p][0]
            # Algebraically equivalent to scaled similarity gains; no D=0 divide.
            gain = -math.fsum(distances[p]) if nearest is None else math.fsum(max(0., old-d) for old, d in zip(nearest, distances[p]))
            if best is None or (-gain, -candidate.score, candidate.variant) < (-best_gain, -best.score, best.variant):
                best = candidate; best_gain = gain
        if best is None: raise ValueError('infeasible facility budget')
        selected.append(best); groups[best.position].pop(0)
        nearest = distances[best.position].copy() if nearest is None else [min(old, d) for old, d in zip(nearest, distances[best.position])]
    return selected


def select(raw: list[dict], method: str, count: int = 95, seed: int = 0) -> tuple[list[str], float]:
    start = time.perf_counter(); candidates = validate(raw, count)
    if method == 'top_score':
        selected = sorted(candidates, key=lambda c: (-c.score, c.variant))[:count]
    elif method == 'random':
        selected = random.Random(seed).sample(candidates, count)
    elif method == 'facility':
        selected = greedy_facility(candidates, count)
    elif method == 'fps':
        coords: list[tuple[float, float, float] | None] = [None] * (max(c.position for c in candidates)+1)
        for c in candidates: coords[c.position] = c.coordinate
        ordered = sorted(candidates, key=lambda c: (-c.score, c.position, c.variant))
        rows, _ = structural_diversity_select([(c.variant,c.score) for c in ordered], count, ca_coords=coords, anchor_variants=(), kappa=0.)
        lookup = {c.variant:c for c in candidates}
        selected = [lookup[v] for v, _ in rows]
    else: raise ValueError('unknown method')
    if len(selected) != count or len({c.variant for c in selected}) != count:
        raise ValueError('selector changed distinct-variant budget')
    return [c.variant for c in selected], (time.perf_counter()-start)*1000


def measure(raw: list[dict], outcomes: dict, selected: list[str]) -> dict:
    pool = validate(raw, len(selected)); lookup = {c.variant:c for c in pool}
    chosen = [lookup[v] for v in selected]
    sites = {c.position:c.coordinate for c in pool}
    selected_sites = {c.position:c.coordinate for c in chosen}
    coverage = [min(math.dist(x,y) for y in selected_sites.values()) for x in sites.values()]
    unique_min = min((math.dist(a,b) for a,b in itertools.combinations(selected_sites.values(),2)),default=None)
    inclusive_min = 0. if len(selected_sites)<len(chosen) else unique_min
    observed = [outcomes[v]['value'] for v in selected if outcomes[v]['value'] is not None]
    binary = [outcomes[v]['binary'] for v in selected if outcomes[v]['binary'] is not None]
    score_sum = math.fsum(c.score for c in chosen)
    top_sum = math.fsum(sorted((c.score for c in pool),reverse=True)[:len(selected)])
    return {'selected_variant_count': len(chosen), 'selected_site_count':len(selected_sites),
        'duplicate_site_variant_count':len(chosen)-len(selected_sites),
        'unique_site_coverage_mean':statistics.fmean(coverage), 'unique_site_coverage_max':max(coverage),
        'unique_site_min_pair_distance':unique_min, 'variant_inclusive_min_pair_distance':inclusive_min,
        'predictor_mean':score_sum/len(chosen), 'predictor_sum_gap_to_top':top_sum-score_sum,
        'predictor_mean_gap_to_top':(top_sum-score_sum)/len(chosen),
        'measured_observed_count':len(observed), 'measured_mean':statistics.fmean(observed) if observed else None,
        'measured_median':statistics.median(observed) if observed else None,
        'binary_observed_count':len(binary), 'binary_positive_count':sum(binary),
        'binary_positive_fraction':statistics.fmean(binary) if binary else None,
        'functional_coverage':None}


def run(data: dict, input_hash: str) -> dict:
    result: dict[str, Any] = {'schema':1, 'protocol_sha256':digest(PROTOCOL), 'script_sha256':digest(Path(__file__)),
        'input_sha256':input_hash, 'python':platform.python_version(), 'platform':platform.platform(),
        'budget_variants':95, 'site_cap':None, 'scorer':SCORER, 'random_seeds':list(range(32)),
        'common_source_preparation_ms':data['common_preparation_ms'], 'assays':{}}
    # Freeze selections for BOTH proteins before consulting ANY outcomes.
    frozen: dict[str, dict[str, Any]] = {}
    for name, assay in data['assays'].items():
        raw=assay['candidates']
        methods={m:select(raw,m) for m in ('top_score','fps','facility')}
        randoms=[select(raw,'random',seed=seed) for seed in range(32)]
        frozen[name]={'methods':methods,'random':randoms}
    for name, assay in data['assays'].items():
        raw=assay['candidates']; outcomes=assay['outcomes']
        methods={m:{'selected_ids':ids,'selection_ms':elapsed,'metrics':measure(raw,outcomes,ids)} for m,(ids,elapsed) in frozen[name]['methods'].items()}
        randoms=[{'seed':seed,'selected_ids':ids,'selection_ms':elapsed,'metrics':measure(raw,outcomes,ids)} for seed,(ids,elapsed) in enumerate(frozen[name]['random'])]
        summary={}
        for key in ('measured_mean','binary_positive_fraction','selected_site_count','unique_site_coverage_mean','unique_site_coverage_max','predictor_mean'):
            values=[v['metrics'][key] for v in randoms if v['metrics'][key] is not None]
            summary[key]={'observed_trials':len(values),'min':min(values) if values else None,'mean':statistics.fmean(values) if values else None,'max':max(values) if values else None}
        result['assays'][name]={k:v for k,v in assay.items() if k not in ('candidates','outcomes')}
        result['assays'][name].update({'cap_one_feasible':assay['eligible_site_count']>=95,'methods':methods,'random_32':{'summary':summary,'trials':randoms}})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path);parser.add_argument('--prepare',type=Path)
    parser.add_argument('--inputs',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.prepare and args.source_dir:
        args.prepare.write_text(json.dumps(prepare(args.source_dir),separators=(',',':'),allow_nan=False)+'\n')
    elif args.inputs and args.output:
        args.output.write_text(json.dumps(run(json.loads(args.inputs.read_text()),digest(args.inputs)),separators=(',',':'),allow_nan=False)+'\n')
    else: parser.error('use --source-dir/--prepare or --inputs/--output')
