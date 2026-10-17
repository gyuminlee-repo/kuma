"""Availability probes use only inert identifiers and mocked network boundaries."""
import json
from unittest.mock import Mock

import pytest

from kuma_core.kuro import alphafold
# Extract only the adapter under test so importing scientific dependencies is unnecessary.
import ast
import re
from pathlib import Path
from types import SimpleNamespace
from sidecar_kuro.models import CheckStructuresParams

_tree = ast.parse((Path(__file__).resolve().parents[2] / "python-core/sidecar_kuro/handlers/external.py").read_text(encoding="utf-8"))
_handler = next(node for node in _tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "handle_check_structures_available")
_namespace = {"CheckStructuresParams": CheckStructuresParams, "re": re}
exec(compile(ast.Module(body=[_handler], type_ignores=[]), "external.py", "exec"), _namespace)
external = SimpleNamespace(handle_check_structures_available=_namespace["handle_check_structures_available"])


@pytest.mark.parametrize("network", [{"consent_alphafold": False}, {"offline_mode": True}])
def test_availability_respects_persisted_network_settings(tmp_path, monkeypatch, network):
    preferences = tmp_path / "preferences.json"
    preferences.write_text(json.dumps({"network": network}))
    monkeypatch.setenv("KUMA_PREFERENCES_PATH", str(preferences))
    monkeypatch.setattr(alphafold, "_CACHE_DIR", tmp_path / "cache")
    request = Mock(side_effect=AssertionError("network must be blocked"))
    monkeypatch.setattr(alphafold._urllib_req, "urlopen", request)
    external.handle_check_structures_available({"accessions": ["ENTRY1"]})
    request.assert_not_called()


@pytest.mark.parametrize("network", [{"consent_alphafold": False}, {"offline_mode": True}])
def test_handler_reports_cached_structure_while_network_is_disabled(tmp_path, monkeypatch, network):
    preferences = tmp_path / "preferences.json"
    preferences.write_text(json.dumps({"network": network}))
    monkeypatch.setenv("KUMA_PREFERENCES_PATH", str(preferences))
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "ENTRY1_ca.json").write_text("[]")
    monkeypatch.setattr(alphafold, "_CACHE_DIR", cache)
    request = Mock(side_effect=AssertionError("network must be blocked"))
    monkeypatch.setattr(alphafold._urllib_req, "urlopen", request)
    assert external.handle_check_structures_available({"accessions": ["ENTRY1", "ENTRY2"]}) == {
        "availability": {"ENTRY1": True}}  # ENTRY2 is unknown, not absent
    request.assert_not_called()


def test_core_rechecks_permission_at_network_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(alphafold, "_CACHE_DIR", tmp_path)
    request = Mock(side_effect=AssertionError("network must be blocked"))
    monkeypatch.setattr(alphafold._urllib_req, "urlopen", request)
    assert alphafold.check_structure_available("ENTRY1", network_allowed=lambda: False) is False
    request.assert_not_called()


def test_local_cache_remains_usable_when_network_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(alphafold, "_CACHE_DIR", tmp_path)
    (tmp_path / "ENTRY1_ca.json").write_text("[]")
    request = Mock(side_effect=AssertionError("network must be blocked"))
    monkeypatch.setattr(alphafold._urllib_req, "urlopen", request)
    assert alphafold.check_structure_available("ENTRY1", network_allowed=lambda: False) is True
    request.assert_not_called()


def test_permission_is_rechecked_after_the_handler_schedules_work(tmp_path, monkeypatch):
    from sidecar_kuro.handlers import settings
    monkeypatch.setattr(alphafold, "_CACHE_DIR", tmp_path)
    # The handler holds no decision of its own: every accession asks again at
    # its own network boundary, so a grant withdrawn mid-batch stops the rest.
    states = iter([True, False])
    monkeypatch.setattr(settings, "load_bundle", lambda: SimpleNamespace(network=SimpleNamespace(
        offline_mode=False, consent_alphafold=next(states))))
    request = Mock(side_effect=OSError("inert endpoint"))
    monkeypatch.setattr(alphafold._urllib_req, "urlopen", request)
    monkeypatch.setattr(alphafold, "get_ssl_context", lambda: None)
    availability = external.handle_check_structures_available(
        {"accessions": ["ENTRY1", "ENTRY2"]})["availability"]
    # Only the accession that reached the endpoint has an answer; the refused one is left out.
    assert list(availability.values()) == [False]
    request.assert_called_once()
    assert next(states, None) is None


def test_allowed_probe_uses_mocked_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(alphafold, "_CACHE_DIR", tmp_path)
    response = Mock()
    response.read.return_value = b'[{"pdbUrl":"inert fixture"}]'
    manager = Mock()
    manager.__enter__ = Mock(return_value=response)
    manager.__exit__ = Mock(return_value=False)
    request = Mock(return_value=manager)
    monkeypatch.setattr(alphafold._urllib_req, "urlopen", request)
    monkeypatch.setattr(alphafold, "get_ssl_context", lambda: None)
    assert alphafold.check_structure_available("ENTRY1", network_allowed=lambda: True) is True
    request.assert_called_once()
