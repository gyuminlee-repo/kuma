"""Optional-domain RPC adapters do not authorize catalog/executable overrides."""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from pydantic import ValidationError

from kuma_core.kuro.domain_jobs import DomainJobService
from kuma_core.kuro.optional_runtime import OptionalRuntimeManager
from sidecar_kuro.handlers import domain
from tests.test_domain_jobs import source_fixture, result_fixture


def test_registry_contains_explicit_domain_actions_without_automatic_import_hooks():
    from sidecar_kuro.dispatcher import _METHODS, _ASYNC_METHODS
    assert _METHODS["domain_runtime_status"] is domain.handle_domain_runtime_status
    assert _METHODS["domain_runtime_install"] is domain.handle_domain_runtime_install
    assert _METHODS["domain_runtime_remove"] is domain.handle_domain_runtime_remove
    assert _METHODS["start_domain_annotation"] is domain.handle_start_domain_annotation
    assert _METHODS["poll_domain_annotation"] is domain.handle_poll_domain_annotation
    assert _METHODS["cancel_domain_annotation"] is domain.handle_cancel_domain_annotation
    assert _METHODS["import_domain_annotation_result"] is domain.handle_import_domain_annotation_result
    assert _METHODS["import_domain_annotation_file"] is domain.handle_import_domain_annotation_file
    assert "poll_domain_annotation" not in _ASYNC_METHODS
    assert "cancel_domain_annotation" not in _ASYNC_METHODS


def test_empty_catalog_handler_status_and_forbidden_overrides(tmp_path, monkeypatch):
    service = DomainJobService(OptionalRuntimeManager(tmp_path / "app"))
    monkeypatch.setattr(domain, "_service", service)
    status = domain.handle_domain_runtime_status({})
    assert status["state"] == "licensing_blocked"
    assert status["install_available"] is False
    assert "executable_path" not in status
    for handler, request in ((domain.handle_domain_runtime_status, {"catalog": {}}),
                             (domain.handle_domain_runtime_remove, {"force": True}),
                             (domain.handle_domain_runtime_install,
                              {"archive_path": "anything.zip", "licensing_override": True})):
        with pytest.raises(ValidationError):
            handler(request)
    with pytest.raises(ValueError, match="cleared"):
        domain.handle_domain_runtime_install({"archive_path": "anything.zip"})
    assert not (tmp_path / "app").exists()


def test_file_import_rpc_returns_annotation_only_with_current_input_binding(tmp_path, monkeypatch):
    source = source_fixture(tmp_path)
    result_path = tmp_path / "result.json"
    result_fixture(source, result_path)
    monkeypatch.setattr(domain, "_service", DomainJobService(OptionalRuntimeManager(tmp_path / "app")))
    request = {"filepath": str(result_path), **asdict(source)}
    result = domain.handle_import_domain_annotation_file(request)
    assert result["job_id"] is None
    assert result["provenance"] == "imported"
    assert result["binding"]["bundle_sha256"] == source.prediction_bundle_sha256
    assert all(key not in result for key in ("selected_variants", "fitness", "top_n", "csv", "selection_policy"))
    json.dumps(result, allow_nan=False)
    with pytest.raises(ValidationError):
        domain.handle_import_domain_annotation_file({**request, "executable_path": "evil"})
    with pytest.raises(ValueError, match="JSON"):
        domain.handle_import_domain_annotation_file({**request, "filepath": "result.txt"})


def test_inspection_and_shutdown_do_not_construct_runtime_service(tmp_path, monkeypatch):
    from sidecar_kuro.handlers.misc import handle_inspect_prediction_bundle
    source = source_fixture(tmp_path)
    monkeypatch.setattr(domain, "_service", None)
    monkeypatch.setattr(domain, "_shutting_down", False)
    handle_inspect_prediction_bundle({"filepath": source.prediction_bundle_path})
    assert domain._service is None
    assert domain.stop_domain_jobs(timeout=0)
    assert domain._service is None


def test_cancel_attempt_before_async_start_handler_admission_prevents_late_launch(tmp_path, monkeypatch):
    """The reader's FIFO does not order the start worker ahead of cancellation."""
    import threading
    from sidecar_kuro import dispatcher
    from tests.test_domain_jobs import service_fixture
    source = source_fixture(tmp_path)
    calls = []
    service, _ = service_fixture(tmp_path, lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(domain, "_service", service)
    entered, release, answered = threading.Event(), threading.Event(), threading.Event()
    original = domain._source
    responses = {}
    def slow_source(request):
        entered.set()
        assert release.wait(5)
        return original(request)
    monkeypatch.setattr(domain, "_source", slow_source)
    monkeypatch.setattr(dispatcher, "_SYNC_DISPATCH", False)
    def ok(req_id, result):
        responses[req_id] = {"result": result}
    def error(req_id, code, message):
        responses[req_id] = {"error": message}
        answered.set()
    monkeypatch.setattr(dispatcher, "_ok", ok)
    monkeypatch.setattr(dispatcher, "_error", error)
    monkeypatch.setattr(dispatcher, "_append_crash_log", lambda *args: None)
    attempt_id = "a" * 32
    dispatcher.dispatch({"id": 1, "method": "start_domain_annotation",
                         "params": {**asdict(source), "attempt_id": attempt_id}})
    assert entered.wait(5)
    dispatcher.dispatch({"id": 2, "method": "cancel_domain_annotation_attempt",
                         "params": {"attempt_id": attempt_id}})
    assert responses[2]["result"]["state"] == "cancelled"
    release.set()
    assert answered.wait(5)
    assert "already used" in responses[1]["error"]
    assert calls == []
    assert service._jobs == {}


def test_frozen_domain_async_requires_native_reader_but_legacy_policy_stays(monkeypatch):
    import threading
    from sidecar_kuro import dispatcher
    results = []
    main_thread = threading.get_ident()
    worker_done = threading.Event()
    def handler(_):
        results.append(threading.get_ident())
        worker_done.set()
        return {}
    monkeypatch.setattr(dispatcher, "_SYNC_DISPATCH", True)
    monkeypatch.setattr(dispatcher, "_DOMAIN_ASYNC_READY", False)
    monkeypatch.setitem(dispatcher._METHODS, "domain_runtime_status", handler)
    errors = []
    monkeypatch.setattr(dispatcher, "_error", lambda *args: errors.append(args))
    monkeypatch.setattr(dispatcher, "_ok", lambda *args: None)
    dispatcher.dispatch({"id": 1, "method": "domain_runtime_status", "params": {}})
    assert errors and not results
    monkeypatch.setattr(dispatcher, "_DOMAIN_ASYNC_READY", True)
    dispatcher.dispatch({"id": 2, "method": "domain_runtime_status", "params": {}})
    assert worker_done.wait(5)
    assert results[0] != main_thread
    monkeypatch.setitem(dispatcher._METHODS, "search_uniprot", handler)
    dispatcher.dispatch({"id": 3, "method": "search_uniprot", "params": {}})
    assert results[-1] == main_thread


def test_shutdown_before_service_construction_blocks_late_handler(tmp_path, monkeypatch):
    monkeypatch.setattr(domain, "_service", None)
    monkeypatch.setattr(domain, "_shutting_down", False)
    assert domain.stop_domain_jobs(timeout=0)
    with pytest.raises(ValueError, match="shutting down"):
        domain.handle_domain_runtime_status({})
    assert domain._service is None
