import io
import json
from unittest.mock import patch

from kuma_core.kuro.uniprot_features import fetch_active_site_features
from sidecar_kuro.models import FetchActiveSiteResult


def test_evidence_location_and_ligand_survive_rpc_schema():
    feature = {"type": "Binding site", "description": "Synthetic fixture",
               "location": {"start": {"value": 4}, "end": {"value": 6}},
               "ligand": {"name": "fixture ligand"},
               "evidences": [{"evidenceCode": "ECO:0000269", "source": "PubMed", "id": "fixture"}]}
    payload = {"features": [feature], "entryAudit": {"sequenceVersion": 3}}
    with patch("kuma_core.kuro.uniprot_features._urllib_req.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
        result = FetchActiveSiteResult(**fetch_active_site_features("P12345")).model_dump()
    assert result["binding_positions"] == [4]  # legacy start-position contract
    assert result["features"][0]["location"] == feature["location"]
    assert result["features"][0]["evidences"] == feature["evidences"]
    assert result["features"][0]["ligand"] == feature["ligand"]
    assert result["features"][0]["coordinate_frame"] == "accession"
    assert result["sequence_version"] == 3
    assert result["annotation_status"] == "present"


def test_unknown_location_is_retained_without_fabricated_integer():
    payload = {"features": [{"type": "Active site", "location": {"start": {"modifier": "UNKNOWN"}}}]}
    with patch("kuma_core.kuro.uniprot_features._urllib_req.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
        result = fetch_active_site_features("P12345")
    assert result["active_site_positions"] == []
    assert len(result["features"]) == 1
    assert result["annotation_status"] == "present"


def test_no_annotation_and_query_failure_are_distinct():
    with patch("kuma_core.kuro.uniprot_features._urllib_req.urlopen", return_value=io.BytesIO(b'{"features": []}')):
        empty = fetch_active_site_features("P12345")
    failed = fetch_active_site_features("invalid:accession")
    assert empty["annotation_status"] == "no_matching_features"
    assert failed["annotation_status"] == "error"
    assert not empty["has_annotation"] and not failed["has_annotation"]
