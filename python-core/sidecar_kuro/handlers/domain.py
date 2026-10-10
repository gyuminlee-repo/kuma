"""Thin adapters for explicit optional-domain jobs and bounded file import."""
from __future__ import annotations

import threading
from pathlib import Path

from kuma_core.kuro.domain_jobs import DomainJobService, DomainSource
from kuma_core.kuro.optional_runtime import OptionalRuntimeManager
from kuma_core.shared.config_paths import kuma_home
from sidecar_kuro.core import _validate_filepath
from sidecar_kuro.models import (
    DomainAnnotationAttempt, DomainAnnotationAttemptParams,
    DomainAnnotationJob, DomainAnnotationJobParams, DomainAnnotationResult,
    DomainAnnotationSourceParams, DomainRuntimeInstallParams, DomainRuntimeParams,
    DomainRuntimeStatus, ImportDomainAnnotationFileParams, ImportDomainAnnotationResultParams,
    StartDomainAnnotationParams,
)

_service: DomainJobService | None = None
_service_lock = threading.Lock()
_shutting_down = False


def _get_service() -> DomainJobService:
    global _service
    with _service_lock:
        if _shutting_down:
            raise ValueError("Optional domain service is shutting down")
        if _service is None:
            # Host-owned app data only; neither catalog nor root comes from RPC.
            _service = DomainJobService(OptionalRuntimeManager(kuma_home().resolve()))
        return _service


def _source(params: DomainAnnotationSourceParams) -> DomainSource:
    bundle = _validate_filepath(params.prediction_bundle_path, allowed_extensions={".zip"})
    return DomainSource(str(bundle), params.prediction_bundle_sha256,
                        params.prediction_model_id, params.prediction_chain_id, params.ref_seq)


def handle_domain_runtime_status(params: dict) -> dict:
    DomainRuntimeParams(**params)
    return DomainRuntimeStatus(**_get_service().runtime_status()).model_dump()


def handle_domain_runtime_install(params: dict) -> dict:
    request = DomainRuntimeInstallParams(**params)
    # The manager checks the trusted catalog before opening any archive.
    return DomainRuntimeStatus(**_get_service().install(request.archive_path)).model_dump()


def handle_domain_runtime_remove(params: dict) -> dict:
    DomainRuntimeParams(**params)
    return DomainRuntimeStatus(**_get_service().remove()).model_dump()


def handle_start_domain_annotation(params: dict) -> dict:
    request = StartDomainAnnotationParams(**params)
    return DomainAnnotationJob(**_get_service().start(_source(request), attempt_id=request.attempt_id)).model_dump()


def handle_poll_domain_annotation(params: dict) -> dict:
    request = DomainAnnotationJobParams(**params)
    return DomainAnnotationJob(**_get_service().poll(request.job_id)).model_dump()


def handle_cancel_domain_annotation(params: dict) -> dict:
    request = DomainAnnotationJobParams(**params)
    return DomainAnnotationJob(**_get_service().cancel(request.job_id)).model_dump()


def handle_import_domain_annotation_result(params: dict) -> dict:
    request = ImportDomainAnnotationResultParams(**params)
    return DomainAnnotationResult(**_get_service().import_result(request.job_id, _source(request))).model_dump()


def handle_import_domain_annotation_file(params: dict) -> dict:
    request = ImportDomainAnnotationFileParams(**params)
    if Path(request.filepath).suffix.lower() != ".json":
        raise ValueError("Domain result must be a JSON file")
    return DomainAnnotationResult(**_get_service().import_file(request.filepath, _source(request))).model_dump()


def stop_domain_jobs(timeout: float = 5.0) -> bool:
    """Do not construct a service or touch runtime files just to shut down."""
    global _shutting_down
    with _service_lock:
        _shutting_down = True
        service = _service
    return service is None or service.stop(timeout)


def handle_get_domain_annotation_attempt(params: dict) -> dict:
    request = DomainAnnotationAttemptParams(**params)
    return DomainAnnotationAttempt(**_get_service().recover_attempt(request.attempt_id)).model_dump()


def handle_cancel_domain_annotation_attempt(params: dict) -> dict:
    request = DomainAnnotationAttemptParams(**params)
    return DomainAnnotationAttempt(**_get_service().cancel_attempt(request.attempt_id)).model_dump()
