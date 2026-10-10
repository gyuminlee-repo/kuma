"""Synthetic ColabFold-compatible bundles; no prediction or external calls."""
import hashlib
import json
from unittest.mock import patch
from zipfile import ZipFile

import pytest

from sidecar_kuro.handlers.misc import handle_load_evolvepro_csv


def bundle_fixture(tmp_path):
    path = tmp_path / 'prediction.zip'
    tag = 'rank_001_alphafold2_ptm_model_1_seed_000'
    model = f'job_unrelaxed_{tag}.pdb'
    pdb = '\n'.join(
        f'ATOM  {p:5d}  CA  {aa:3s} A{p:4d}    {float(p):8.3f}{0.:8.3f}{0.:8.3f}  1.00{confidence:6.2f}           C'
        for p, aa, confidence in [(1, 'MET', 90), (2, 'ALA', 80), (3, 'LYS', 70)]) + '\n'
    with ZipFile(path, 'w') as z:
        z.writestr(model, pdb)
        z.writestr(f'job_scores_{tag}.json', json.dumps({'plddt': [90,80,70], 'pae': [[0,1,2],[3,0,4],[5,6,0]]}))
        z.writestr('job.a3m', '>query\nMAK\n')
    csv = tmp_path / 'df_test.csv'
    csv.write_text('variant,y_pred\nA2C,4\nA2D,3\nK3A,2\n')
    params = dict(filepath=str(csv), top_n=2, ref_seq='MAK', strict_spatial=True,
                  structural_diversity=True, strict_spatial_budget='distinct_variants',
                  prediction_bundle_path=str(path), prediction_model_id=model,
                  prediction_chain_id='A', prediction_bundle_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return path, params


def test_inspection_and_selection_share_local_bundle_identity(tmp_path):
    from sidecar_kuro.handlers.misc import handle_inspect_prediction_bundle
    path, params = bundle_fixture(tmp_path)
    inventory = handle_inspect_prediction_bundle({'filepath': str(path)})
    assert inventory['schema_version'] == 1
    assert inventory['bundle_sha256'] == params['prediction_bundle_sha256']
    assert inventory['models'][0]['chains'][0]['sequence'] == 'MAK'
    assert inventory['models'][0]['producer_rank'] == 1
    assert inventory['recommended_model_id'] == params['prediction_model_id']
    assert inventory['recommendation_reason'] == 'producer_rank'
    with patch('kuma_core.kuro.alphafold.fetch_pdb_text', side_effect=AssertionError('No network')):
        result = handle_load_evolvepro_csv(params)
    strict = result['strict_spatial']
    assert result['variants'] == ['A2C', 'K3A']
    assert strict['pdb_text'].splitlines()[0][17:20] == 'MET'
    source = strict['prediction_bundle']
    assert source['bundle_sha256'] == inventory['bundle_sha256']
    assert source['plddt_by_reference'] == [90.,80.,70.]
    assert source['pae']['mean'] == 3.5
    assert source['pae']['max'] == 6
    assert source['pae']['directional'] is True
    assert source['interdomain_confidence'] == 'not_assessed'
    assert source['display_sha256'] == hashlib.sha256(strict['pdb_text'].encode()).hexdigest()
    assert [(r['reference_position'], r['viewer_position']) for r in strict['mapping']] == [(1,1),(2,2),(3,3)]


@pytest.mark.parametrize('kind', ['af3', 'colabfold'])
@pytest.mark.parametrize('top_present', [False, True])
def test_inspection_rpc_serializes_producer_recommendation(tmp_path, kind, top_present):
    from sidecar_kuro.handlers.misc import handle_inspect_prediction_bundle
    from tests.test_prediction_bundle import bundle, ranked_members

    index = ('0' if top_present else '1') if kind == 'af3' else ('001' if top_present else '002')
    model, members = ranked_members(kind, index)
    inventory = handle_inspect_prediction_bundle({'filepath': str(bundle(tmp_path, members))})
    assert inventory['recommended_model_id'] == (model if top_present else None)
    assert inventory['recommendation_reason'] == ('producer_rank' if top_present else 'missing_top_rank')
    assert inventory['models'][0]['producer_rank'] == (1 if top_present else 2)
    assert 'recommended_chain_id' not in inventory
    # Preserve explicit selection: a model recommendation is not a loaded chain.
    assert [chain['chain_id'] for chain in inventory['models'][0]['chains']] == ['A', 'B']


@pytest.mark.parametrize('missing', ['prediction_model_id','prediction_chain_id','prediction_bundle_sha256'])
def test_import_requires_explicit_complete_inspected_selection(tmp_path, missing):
    _, params = bundle_fixture(tmp_path)
    del params[missing]
    with pytest.raises(ValueError, match='[Bb]undle|[Ii]mport|prediction'):
        handle_load_evolvepro_csv(params)


def test_changed_bundle_is_not_silently_reused(tmp_path):
    path, params = bundle_fixture(tmp_path)
    with ZipFile(path, 'a') as z:
        z.writestr('extra.txt', 'changed')
    with pytest.raises(ValueError, match='hash|changed|digest'):
        handle_load_evolvepro_csv(params)


def test_import_is_opt_in_and_reference_is_exact(tmp_path):
    _, params = bundle_fixture(tmp_path)
    with pytest.raises(ValueError, match='strict|Strict'):
        handle_load_evolvepro_csv({**params, 'strict_spatial': False})
    with pytest.raises(ValueError, match='exact|homolog|reference|Reference'):
        handle_load_evolvepro_csv({**params, 'ref_seq': 'MCK'})


def test_af3_adapter_preserves_full_identity_and_missing_ca(tmp_path):
    from tests.test_prediction_bundle import AF_MODEL, AF_DATA, af_data, bundle, cif
    from kuma_core.kuro.prediction_context import prediction_context
    path = bundle(tmp_path, {AF_MODEL: cif(), AF_DATA: af_data(), 'terms_of_use.md': 'Synthetic source notice'})
    ctx = prediction_context(str(path), AF_MODEL, 'A', 'ACD', hashlib.sha256(path.read_bytes()).hexdigest())
    assert [(m['reference_position'], m['structure_position'], m['chain_id'], m['insertion_code'])
            for m in ctx['mapping']] == [(1,-3,'author-A',''),(3,10,'author-A','A')]
    assert [(m['viewer_position'],m['viewer_chain_id'],m['viewer_insertion_code'])
            for m in ctx['mapping']] == [(1,'A',''),(3,'A','')]
    assert [int(line[22:26]) for line in ctx['pdb_text'].splitlines() if line.startswith('ATOM')] == [1,3]
    metadata = ctx['prediction_bundle']
    assert metadata['plddt_by_reference'] == [90.,None,70.]
    assert metadata['missing_reference_positions'] == [2]
    assert metadata['source_notices'][0]['sha256'] == hashlib.sha256(b'Synthetic source notice').hexdigest()
    assert metadata['source_notices'][0]['text'] == 'Synthetic source notice'
    assert metadata['pae']['mean'] == 4.5  # native directed off-diagonal six values
    assert metadata['pae']['dimension'] == 3
    assert 'output-terms' in metadata['terms_url']


def test_ca_trace_rejects_unrepresentable_coordinates(tmp_path):
    from tests.test_prediction_bundle import AF_MODEL, AF_DATA, af_data, bundle, cif
    from kuma_core.kuro.prediction_context import prediction_context
    text = cif().replace('CA . 1 0 0 90', 'CA . 12345678 0 0 90')
    path = bundle(tmp_path, {AF_MODEL: text, AF_DATA: af_data()})
    with pytest.raises(ValueError, match='display range'):
        prediction_context(str(path), AF_MODEL, 'A', 'ACD', hashlib.sha256(path.read_bytes()).hexdigest())


def test_pae_absence_stays_unknown_in_app_context(tmp_path):
    from tests.test_prediction_bundle import AF_MODEL, AF_DATA, af_data, bundle, cif
    from kuma_core.kuro.prediction_context import prediction_context
    data = af_data()
    del data['pae']
    path = bundle(tmp_path, {AF_MODEL: cif(), AF_DATA: data})
    metadata = prediction_context(str(path), AF_MODEL, 'A', 'ACD', hashlib.sha256(path.read_bytes()).hexdigest())['prediction_bundle']
    assert metadata['pae']['status'] == 'unavailable'
    assert metadata['pae']['mean'] is None
    assert metadata['pae']['max'] is None
    assert metadata['pae']['source'] is None
    assert metadata['warnings']
