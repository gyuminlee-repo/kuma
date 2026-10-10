"""Explicit, local-only optional structural annotations; never selection inputs.

The application supplies only its trusted, empty-by-default runtime catalog.
Requests cannot select a command, catalog, environment, runtime root, or limits.
Jobs are session-only, retain at most four bounded results, and never resume on
inspection/restoration. External envelopes prove consistency, not execution.
"""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from kuma_core.kuro.domain_af3 import prepare_af3_domain_input
from kuma_core.kuro.domain_annotation import DomainAnnotation, DomainAnnotationError, DomainInput, MAX_RESULT_BYTES
from kuma_core.kuro.domain_merizo import (
    decode_merizo_result, domain_input_manifest, prepare_colabfold_domain_input,
)
from kuma_core.kuro.optional_runtime import OptionalRuntimeError, OptionalRuntimeManager, RuntimeCancelled
from kuma_core.kuro.prediction_bundle import load_prediction_bundle

MAX_RETAINED_JOBS = 4
MAX_ATTEMPTS = 1024
RUN_TIMEOUT_SECONDS = 300.0
MAX_OUTPUT_BYTES = 1024 * 1024
TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled"})
JobState = Literal["queued", "running", "cancelling", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class DomainSource:
    prediction_bundle_path: str
    prediction_bundle_sha256: str
    prediction_model_id: str
    prediction_chain_id: str
    ref_seq: str


def prepare_source(source: DomainSource) -> tuple[DomainInput, dict[str, str]]:
    """Reopen the pinned original source and complete all-atom reference mapping."""
    reference = source.ref_seq.strip().rstrip("*")
    context = load_prediction_bundle(
        source.prediction_bundle_path, source.prediction_model_id,
        source.prediction_chain_id, reference,
        expected_bundle_sha256=source.prediction_bundle_sha256,
    )
    prepared = (prepare_af3_domain_input(context, reference) if context.format == "af3_server"
                else prepare_colabfold_domain_input(context, reference))
    return prepared, {
        "bundle_sha256": context.bundle_sha256,
        "source_sha256": prepared.source_sha256,
        "reference_sha256": prepared.reference_sha256,
        "model_id": context.model_id,
        "chain_id": context.chain_id,
    }


def read_result_file(path: Path) -> str:
    """Read at most 8 MiB from one stable regular file, refusing special files."""
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or getattr(before, "st_file_attributes", 0) & 0x400
            or before.st_size > MAX_RESULT_BYTES):
        raise DomainAnnotationError("Domain result must be a bounded regular file without links")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if ((opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or opened.st_size > MAX_RESULT_BYTES):
            raise DomainAnnotationError("Domain result changed while opening")
        raw = handle.read(MAX_RESULT_BYTES + 1)
        after = os.fstat(handle.fileno())
        named = path.lstat()
        if (len(raw) > MAX_RESULT_BYTES or len(raw) != opened.st_size
                or (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
                != (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
                or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)):
            raise DomainAnnotationError("Domain result changed or exceeds the size limit")
    try:
        return raw.decode("utf-8")
    except UnicodeError as exc:
        raise DomainAnnotationError("Domain result must be UTF-8 JSON") from exc


def annotation_result(annotation: DomainAnnotation, binding: dict[str, str], *,
                      job_id: str | None, provenance: Literal["managed", "imported"]) -> dict[str, Any]:
    return {
        "job_id": job_id, "binding": dict(binding), "binding_sha256": annotation.binding_sha256,
        "engine": "merizo", "coordinate_frame": "reference", "provenance": provenance,
        "provenance_note": (
            "Managed runtime bytes and exact input/result identity verified; biological accuracy is not established."
            if provenance == "managed" else
            "Exact input/result identity verified; external execution provenance is self-declared and biological accuracy is not established."
        ),
        "domains": [{"segments": [asdict(segment) for segment in domain.segments],
                     "positions": list(domain.reference_positions)} for domain in annotation.domains],
        "unassigned_positions": list(annotation.unassigned_positions),
        "assigned_residues": annotation.assigned_residues, "total_residues": annotation.total_residues,
        "coverage": annotation.coverage, "confidence": annotation.confidence,
    }


@dataclass
class _Job:
    job_id: str
    binding: dict[str, str]
    binding_sha256: str
    state: JobState = "queued"
    message: str = "Waiting to verify the optional runtime."
    cancelled: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    result_text: str | None = None

    def snapshot(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "state": self.state,
                "message": self.message, "binding": dict(self.binding)}


@dataclass
class _Attempt:
    attempt_id: str
    state: Literal["pending", "job", "cancelled", "failed"]
    message: str
    job_id: str | None = None
    cancelled: bool = False


class DomainJobService:
    """Single active runtime operation, immutable scientific binding per job.

    The manager/runner injection is internal construction for tests only. No RPC
    may pass either. A runner must never return or raise while a child is live.
    """
    def __init__(self, manager: OptionalRuntimeManager, *,
                 runner: Callable[..., None] | None = None) -> None:
        self._manager = manager
        self._runner = runner
        self._lock = threading.RLock()
        self._busy = False
        self._closed = False
        self._operation_cancelled = threading.Event()
        self._operation_done = threading.Event()
        self._operation_done.set()
        self._jobs: dict[str, _Job] = {}
        # Never evict attempt tombstones: an old delayed start must not execute
        # after a reset or a lost response. Saturation fails closed until restart.
        self._attempts: dict[str, _Attempt] = {}
        self._pending_attempt_id: str | None = None

    def runtime_status(self) -> dict[str, Any]:
        status = self._manager.status()
        # Do not disclose or accept a runtime executable path over RPC.
        return {"state": status.state, "engine": "merizo", "platform": status.platform,
                "version": status.version if status.state == "installed" else None, "message": status.message,
                "install_available": status.state not in {"licensing_blocked", "unsupported_platform"},
                "available_version": status.version}

    def _reserve(self) -> None:
        with self._lock:
            if self._closed:
                raise OptionalRuntimeError("Optional domain service is shutting down")
            if self._busy:
                raise OptionalRuntimeError("Another optional runtime operation is in progress")
            self._busy = True
            self._operation_cancelled.clear()
            self._operation_done.clear()

    def _release(self) -> None:
        with self._lock:
            self._busy = False
            self._operation_done.set()

    def install(self, archive_path: str) -> dict[str, Any]:
        self._reserve()
        try:
            self._manager.install(archive_path, cancelled=self._operation_cancelled.is_set)
            return self.runtime_status()
        finally:
            self._release()

    def remove(self) -> dict[str, Any]:
        self._reserve()
        try:
            self._manager.remove(cancelled=self._operation_cancelled.is_set)
            return self.runtime_status()
        finally:
            self._release()

    @staticmethod
    def _validate_attempt_id(attempt_id: str) -> None:
        if not isinstance(attempt_id, str) or not re.fullmatch(r"[0-9a-f]{32}", attempt_id):
            raise DomainAnnotationError("Invalid domain start attempt identity")

    def start(self, source: DomainSource, *, attempt_id: str | None = None) -> dict[str, Any]:
        # The optional default is internal construction convenience only; RPC
        # requires a client UUID before sending the request, for exact recovery.
        attempt_id = uuid.uuid4().hex if attempt_id is None else attempt_id
        self._validate_attempt_id(attempt_id)
        with self._lock:
            if attempt_id in self._attempts:
                raise DomainAnnotationError("Domain start attempt already used; recover its exact status")
            if len(self._attempts) >= MAX_ATTEMPTS:
                raise DomainAnnotationError("Domain attempt registry is full; restart the sidecar before a new run")
            attempt = _Attempt(attempt_id, "pending", "Preparing the exact domain annotation input.")
            self._attempts[attempt_id] = attempt
            try:
                self._reserve()
            except Exception as exc:
                attempt.state, attempt.message = "failed", str(exc)[:2000]
                raise
            self._pending_attempt_id = attempt_id
        try:
            status = self._manager.status(cancelled=self._operation_cancelled.is_set)
            if status.state != "installed":
                raise OptionalRuntimeError(status.message)
            prepared, binding = prepare_source(source)
            job = _Job(uuid.uuid4().hex, binding, prepared.binding_sha256)
            with self._lock:
                if self._operation_cancelled.is_set() or attempt.cancelled:
                    raise RuntimeCancelled("Domain annotation cancelled before job launch")
                while len(self._jobs) >= MAX_RETAINED_JOBS:
                    oldest = next(iter(self._jobs))
                    if self._jobs[oldest].state not in TERMINAL_STATES:
                        raise OptionalRuntimeError("Previous domain job has not stopped")
                    del self._jobs[oldest]
                self._jobs[job.job_id] = job
                attempt.state, attempt.message, attempt.job_id = "job", "Domain job created.", job.job_id
                self._pending_attempt_id = None
                thread = threading.Thread(target=self._run, args=(job, prepared),
                                          name="optional-domain-" + job.job_id, daemon=True)
                try:
                    thread.start()
                except BaseException:
                    del self._jobs[job.job_id]
                    raise
                return job.snapshot()
        except BaseException as exc:
            with self._lock:
                attempt.state = "cancelled" if isinstance(exc, RuntimeCancelled) else "failed"
                attempt.message = (str(exc) or type(exc).__name__)[:2000]
                attempt.job_id = None
                self._pending_attempt_id = None
                self._release()
            raise

    def recover_attempt(self, attempt_id: str) -> dict[str, Any]:
        self._validate_attempt_id(attempt_id)
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is None:
                return {"attempt_id": attempt_id, "state": "unknown", "job": None,
                        "message": "No start or cancellation registered for this attempt."}
            job = self._jobs.get(attempt.job_id or "")
            state = "expired" if attempt.state == "job" and job is None else attempt.state
            return {"attempt_id": attempt_id, "state": state,
                    "job": job.snapshot() if job is not None else None,
                    "message": "Domain result expired; this attempt cannot restart." if state == "expired" else attempt.message}

    def cancel_attempt(self, attempt_id: str) -> dict[str, Any]:
        self._validate_attempt_id(attempt_id)
        with self._lock:
            attempt = self._attempts.get(attempt_id)
            if attempt is None:
                if len(self._attempts) >= MAX_ATTEMPTS:
                    raise DomainAnnotationError("Domain attempt registry is full; cancellation could not be registered")
                self._attempts[attempt_id] = _Attempt(
                    attempt_id, "cancelled", "Start cancelled before admission; this attempt cannot launch.",
                    cancelled=True)
            else:
                attempt.cancelled = True
                if attempt.job_id in self._jobs:
                    assert attempt.job_id is not None
                    self.cancel(attempt.job_id)
                elif self._pending_attempt_id == attempt_id:
                    self._operation_cancelled.set()
                    attempt.message = "Cancellation requested; waiting for input preparation to stop."
            return self.recover_attempt(attempt_id)

    def _run(self, job: _Job, prepared: DomainInput) -> None:
        cancelled_errors: tuple[type[Exception], ...] = (RuntimeCancelled,)
        state: JobState = "failed"
        message = "Optional domain annotation failed."
        result_text: str | None = None
        try:
            from kuma_core.kuro.domain_process import DomainProcessCancelled, run_managed_process
            cancelled_errors = (RuntimeCancelled, DomainProcessCancelled)
            # The OS lock covers re-verification, launch, all descendants, result
            # collection and cleanup. It must not be released by a cancel request.
            with self._manager.operation_lock() as operation_lease:
                status = self._manager.verify(cancelled=job.cancelled.is_set)
                if status.state != "installed" or not status.executable_path:
                    raise OptionalRuntimeError(status.message)
                with tempfile.TemporaryDirectory(prefix="kuma-domain-") as directory:
                    work = Path(directory).resolve()
                    pdb, manifest, result = work / "input.pdb", work / "input.json", work / "result.json"
                    pdb.write_text(prepared.normalized_pdb, encoding="utf-8")
                    manifest.write_text(json.dumps(domain_input_manifest(prepared), allow_nan=False), encoding="utf-8")
                    with self._lock:
                        if job.cancelled.is_set():
                            raise RuntimeCancelled("Domain annotation cancelled before launch")
                        job.state = "running"
                        job.message = "Running optional CPU structural-domain annotation."
                    runner = self._runner or run_managed_process
                    runner([status.executable_path, "--input-pdb", str(pdb),
                            "--input-manifest", str(manifest), "--output", str(result), "--device", "cpu"],
                           cwd=work, cancelled=job.cancelled.is_set, timeout_seconds=RUN_TIMEOUT_SECONDS,
                           output_limit=MAX_OUTPUT_BYTES, result_path=result, result_limit=MAX_RESULT_BYTES,
                           on_stopping=lambda text: self._stopping(job, text),
                           operation_lease=operation_lease)
                    if job.cancelled.is_set():
                        raise RuntimeCancelled("Domain annotation cancelled after confirmed process exit")
                    result_text = read_result_file(result)
                    decode_merizo_result(result_text, prepared, current_binding_sha256=job.binding_sha256)
            state, message = "succeeded", "Domain annotation is ready for current-input validation."
        except cancelled_errors:
            state, message = "cancelled", "Domain annotation cancelled; process termination confirmed."
        except Exception as exc:
            message = (str(exc) or type(exc).__name__)[:2000]
        finally:
            with self._lock:
                # Cancel racing result decode still wins before publication.
                if state == "succeeded" and job.cancelled.is_set():
                    state, message = "cancelled", "Domain annotation cancelled; process termination confirmed."
                job.state, job.message = state, message
                job.result_text = result_text if state == "succeeded" else None
                self._release()
                job.done.set()

    def _stopping(self, job: _Job, message: str) -> None:
        with self._lock:
            job.state, job.message = "cancelling", message[:2000]

    def _job(self, job_id: str) -> _Job:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise DomainAnnotationError("Unknown or expired domain job; start an explicit new run") from exc

    def poll(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return self._job(job_id).snapshot()

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._job(job_id)
            if job.state not in TERMINAL_STATES:
                job.cancelled.set()
                job.state = "cancelling"
                job.message = "Cancellation requested; waiting for confirmed process termination."
            return job.snapshot()

    def import_result(self, job_id: str, source: DomainSource) -> dict[str, Any]:
        with self._lock:
            job = self._job(job_id)
            if job.state != "succeeded" or job.result_text is None:
                raise DomainAnnotationError("Domain job has no successful result to import")
            text = job.result_text
        prepared, binding = prepare_source(source)
        if binding != job.binding or prepared.binding_sha256 != job.binding_sha256:
            raise DomainAnnotationError("Stale domain result for a superseded source/reference/model/chain")
        annotation = decode_merizo_result(text, prepared, current_binding_sha256=job.binding_sha256)
        with self._lock:
            if self._jobs.get(job_id) is not job or job.state != "succeeded":
                raise DomainAnnotationError("Domain job expired while validating its result")
            return annotation_result(annotation, binding, job_id=job_id, provenance="managed")

    def import_file(self, filepath: str, source: DomainSource) -> dict[str, Any]:
        prepared, binding = prepare_source(source)
        text = read_result_file(Path(filepath))
        annotation = decode_merizo_result(text, prepared, current_binding_sha256=prepared.binding_sha256)
        return annotation_result(annotation, binding, job_id=None, provenance="imported")

    def stop(self, timeout: float = 5.0) -> bool:
        """Cancel and await any active install/remove/preparation/job operation.

        Installation and removal cancel at their manager's existing safe points;
        committed atomic mutations still finish before shutdown is acknowledged.
        No public install-cancel RPC is implied by this shutdown-only path.
        """
        with self._lock:
            self._closed = True
            self._operation_cancelled.set()
            for job in self._jobs.values():
                if job.state not in TERMINAL_STATES:
                    self.cancel(job.job_id)
        return self._operation_done.wait(timeout)
