"""Synthetic domain app jobs only: no ML runtime, weights, or downloads."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import sys
import time
import zipfile
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import pytest

from kuma_core.kuro import domain_jobs
from kuma_core.kuro.domain_annotation import DomainAnnotationError
from kuma_core.kuro.domain_jobs import DomainJobService, DomainSource, prepare_source, read_result_file
from kuma_core.kuro.optional_runtime import OptionalRuntimeError, OptionalRuntimeManager
from tests.test_domain_merizo import MODEL, SCORES, envelope, synthetic
from tests.test_optional_runtime import setup_runtime


def source_fixture(tmp_path: Path, *, sequence: str = "ACDEFG", chain: str = "B") -> DomainSource:
    source, polymer = synthetic(sequence, chain=chain, insertion=False)
    bundle = tmp_path / ("source-" + chain + ".zip")
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(MODEL, source)
        archive.writestr(SCORES, json.dumps({"plddt": [90] * len(polymer.sequence)}))
        archive.writestr("synthetic.a3m", ">query\n" + polymer.sequence + "\n")
    return DomainSource(str(bundle), hashlib.sha256(bundle.read_bytes()).hexdigest(), MODEL, chain, sequence)


def result_fixture(source: DomainSource, filepath: Path) -> None:
    prepared, _ = prepare_source(source)
    filepath.write_text(json.dumps(envelope(prepared, [1, 0, 2, 1, 2, 0])), encoding="utf-8")


def successful_runner(source: DomainSource, *, directories: list[Path] | None = None):
    def run(argv, **kwargs):
        work = kwargs["cwd"]
        if directories is not None:
            directories.append(work)
        assert argv[1:] == ["--input-pdb", str(work / "input.pdb"), "--input-manifest",
                            str(work / "input.json"), "--output", str(work / "result.json"), "--device", "cpu"]
        prepared, _ = prepare_source(source)
        assert (work / "input.pdb").read_text() == prepared.normalized_pdb
        assert len([line for line in prepared.normalized_pdb.splitlines() if line.startswith("ATOM  ")]) == 30
        manifest = json.loads((work / "input.json").read_text())
        assert manifest["binding_sha256"] == prepared.binding_sha256
        assert manifest["source_sha256"] == prepared.source_sha256
        result_fixture(source, kwargs["result_path"])
    return run


def service_fixture(tmp_path: Path, runner=None):
    manager, archive, _ = setup_runtime(tmp_path)
    manager.install(archive)
    return DomainJobService(manager, runner=runner), manager


def terminal(service: DomainJobService, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        current = service.poll(job_id)
        if current["state"] in domain_jobs.TERMINAL_STATES:
            return current
        time.sleep(0.01)
    raise AssertionError("Synthetic job did not stop")


def test_production_catalog_blocked_no_files_or_command_override(tmp_path):
    service = DomainJobService(OptionalRuntimeManager(tmp_path / "app"))
    status = service.runtime_status()
    assert status["state"] == "licensing_blocked"
    assert status["install_available"] is False
    assert "executable_path" not in status
    assert status["available_version"] is None
    assert not (tmp_path / "app").exists()
    with pytest.raises(OptionalRuntimeError, match="cleared"):
        service.install(str(tmp_path / "anything.zip"))
    with pytest.raises(OptionalRuntimeError, match="cleared"):
        service.remove()
    with pytest.raises(OptionalRuntimeError, match="cleared"):
        service.start(source_fixture(tmp_path))
    assert not (tmp_path / "app").exists()


def test_managed_success_complete_original_atoms_unique_identity_and_cleanup(tmp_path):
    source = source_fixture(tmp_path)
    directories = []
    service, _ = service_fixture(tmp_path, successful_runner(source, directories=directories))
    job = service.start(source)
    assert terminal(service, job["job_id"])["state"] == "succeeded"
    assert "domains" not in service.poll(job["job_id"])
    result = service.import_result(job["job_id"], source)
    assert result["provenance"] == "managed"
    assert result["coordinate_frame"] == "reference"
    assert result["binding"] == job["binding"]
    assert result["total_residues"] == 6
    assert result["domains"][0]["segments"] == [{"start": 1, "end": 1}, {"start": 4, "end": 4}]
    assert result["unassigned_positions"] == [2, 6]
    assert result["assigned_residues"] == 4
    assert all(not path.exists() for path in directories)
    again = service.start(source)
    assert again["job_id"] != job["job_id"]
    assert terminal(service, again["job_id"])["state"] == "succeeded"


def test_external_result_import_with_empty_catalog_is_read_only(tmp_path):
    source = source_fixture(tmp_path)
    path = tmp_path / "result.json"
    result_fixture(source, path)
    service = DomainJobService(OptionalRuntimeManager(tmp_path / "app"))
    result = service.import_file(str(path), source)
    assert result["job_id"] is None
    assert result["provenance"] == "imported"
    assert "self-declared" in result["provenance_note"]
    assert not (tmp_path / "app").exists()


def test_cancel_remains_pending_until_runner_confirms_exit_and_lock_blocks_removal(tmp_path):
    source = source_fixture(tmp_path)
    running, finish = threading.Event(), threading.Event()
    def runner(argv, **kwargs):
        from kuma_core.kuro.domain_process import DomainProcessCancelled
        running.set()
        assert finish.wait(10)
        assert kwargs["cancelled"]()
        raise DomainProcessCancelled("confirmed synthetic termination")
    service, manager = service_fixture(tmp_path, runner)
    job = service.start(source)
    assert running.wait(5)
    assert service.cancel(job["job_id"])["state"] == "cancelling"
    assert service.poll(job["job_id"])["state"] == "cancelling"
    with pytest.raises(OptionalRuntimeError, match="in progress"):
        manager.remove()
    for action in (lambda: service.start(source), service.remove, lambda: service.install("fake.zip")):
        with pytest.raises(OptionalRuntimeError, match="in progress"):
            action()
    with pytest.raises(DomainAnnotationError, match="successful"):
        service.import_result(job["job_id"], source)
    assert not service.stop(timeout=0.01)
    finish.set()
    assert terminal(service, job["job_id"])["state"] == "cancelled"
    assert service.stop(timeout=0.01)
    assert manager.remove().state == "missing"


def test_runtime_verified_under_lock_and_corruption_never_launches(tmp_path, monkeypatch):
    source = source_fixture(tmp_path)
    called = []
    service, manager = service_fixture(tmp_path, lambda *args, **kw: called.append(args))
    verify = manager.verify
    def corrupt(**kwargs):
        executable_path = manager.status().executable_path
        assert executable_path is not None
        executable = Path(executable_path)
        executable.write_bytes(b"tampered")
        return verify(**kwargs)
    monkeypatch.setattr(manager, "verify", corrupt)
    job = service.start(source)
    assert terminal(service, job["job_id"])["state"] == "failed"
    assert not called


def test_failed_runner_and_invalid_result_clean_up_and_allow_retry(tmp_path):
    source = source_fixture(tmp_path)
    directories = []
    def runner(argv, **kwargs):
        directories.append(kwargs["cwd"])
        kwargs["result_path"].write_text('{"schema":"wrong"}')
    service, _ = service_fixture(tmp_path, runner)
    job = service.start(source)
    assert terminal(service, job["job_id"])["state"] == "failed"
    assert all(not path.exists() for path in directories)
    service._runner = successful_runner(source)
    retry = service.start(source)
    assert terminal(service, retry["job_id"])["state"] == "succeeded"


def test_current_source_model_reference_chain_and_bundle_are_revalidated(tmp_path):
    source = source_fixture(tmp_path)
    service, _ = service_fixture(tmp_path, successful_runner(source))
    job = service.start(source)
    assert terminal(service, job["job_id"])["state"] == "succeeded"
    for changed in (replace(source, prediction_bundle_sha256="0" * 64),
                    replace(source, ref_seq="CCDEFG"), replace(source, prediction_model_id="other.pdb"),
                    replace(source, prediction_chain_id="A")):
        with pytest.raises(ValueError):
            service.import_result(job["job_id"], changed)
    other = source_fixture(tmp_path, chain="C")
    with pytest.raises(DomainAnnotationError, match="Stale"):
        service.import_result(job["job_id"], other)
    Path(source.prediction_bundle_path).write_bytes(b"changed archive")
    with pytest.raises(ValueError):
        service.import_result(job["job_id"], source)


def test_unknown_expired_jobs_and_bounded_retention(tmp_path, monkeypatch):
    source = source_fixture(tmp_path)
    service, _ = service_fixture(tmp_path, successful_runner(source))
    monkeypatch.setattr(domain_jobs, "MAX_RETAINED_JOBS", 2)
    ids = []
    for _ in range(3):
        job = service.start(source)
        ids.append(job["job_id"])
        assert terminal(service, job["job_id"])["state"] == "succeeded"
    assert len(service._jobs) == 2
    for action in (service.poll, service.cancel):
        with pytest.raises(DomainAnnotationError, match="expired"):
            action(ids[0])
    with pytest.raises(DomainAnnotationError, match="expired"):
        service.import_result(ids[0], source)


def test_result_read_size_utf8_special_symlink_and_hardlink_bounds(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    monkeypatch.setattr(domain_jobs, "MAX_RESULT_BYTES", 16)
    path.write_bytes(b"x" * 17)
    with pytest.raises(DomainAnnotationError, match="bounded"):
        read_result_file(path)
    path.write_bytes(b"\xff")
    with pytest.raises(DomainAnnotationError, match="UTF-8"):
        read_result_file(path)
    path.write_text("{}")
    hard = tmp_path / "hard.json"
    try:
        os.link(path, hard)
    except OSError:
        pass
    else:
        with pytest.raises(DomainAnnotationError, match="links"):
            read_result_file(hard)
        hard.unlink()
    symlink = tmp_path / "symlink.json"
    try:
        symlink.symlink_to(path)
    except OSError:
        pass
    else:
        with pytest.raises(DomainAnnotationError, match="links"):
            read_result_file(symlink)
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "fifo.json"
        os.mkfifo(fifo)
        with pytest.raises(DomainAnnotationError, match="regular"):
            read_result_file(fifo)


def test_request_models_forbid_all_command_catalog_and_override_channels(tmp_path):
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1] / "python-core"))
    from pydantic import ValidationError
    from sidecar_kuro.models import StartDomainAnnotationParams, DomainRuntimeInstallParams
    source = {**asdict(source_fixture(tmp_path)), "attempt_id": "1" * 32}
    assert StartDomainAnnotationParams.model_validate(source).attempt_id == "1" * 32
    for key, value in (("executable_path", "/tmp/a"), ("catalog", {}), ("licensing_override", True),
                       ("timeout_seconds", 999999), ("runner", "anything"), ("app_data_root", "/tmp")):
        with pytest.raises(ValidationError):
            StartDomainAnnotationParams.model_validate({**source, key: value})
        with pytest.raises(ValidationError):
            DomainRuntimeInstallParams.model_validate({"archive_path": "local.zip", key: value})


def test_af3_is_explicitly_unsupported_for_file_import(tmp_path):
    from tests.test_prediction_bundle import AF_MODEL, bundle
    from kuma_core.kuro.domain_merizo import AF3_UNSUPPORTED_REASON
    path = bundle(tmp_path)
    source = DomainSource(str(path), hashlib.sha256(path.read_bytes()).hexdigest(), AF_MODEL, "A", "ACD")
    service = DomainJobService(OptionalRuntimeManager(tmp_path / "app"))
    with pytest.raises(DomainAnnotationError) as error:
        service.import_file(str(tmp_path / "not-read.json"), source)
    assert str(error.value) == AF3_UNSUPPORTED_REASON


@pytest.mark.skipif(sys.platform not in {"linux", "darwin"}, reason="Native POSIX synthetic executable fixture")
def test_real_synthetic_executable_catalog_to_current_bound_annotation(tmp_path):
    """Native harmless process, not Merizo inference or model accuracy evidence."""
    from kuma_core.kuro.domain_merizo import MERIZO_COMMIT, MERIZO_WEIGHTS_SHA256
    from kuma_core.kuro.optional_runtime import RuntimeArtifact, RuntimeFile, current_platform_key
    from io import BytesIO
    source = source_fixture(tmp_path)
    script = (f"#!{sys.executable}\n" + '''import argparse, json
from pathlib import Path
from typing import Any
p=argparse.ArgumentParser()
p.add_argument('--input-pdb'); p.add_argument('--input-manifest'); p.add_argument('--output'); p.add_argument('--device')
a=p.parse_args()
assert a.device=='cpu'
m=json.loads(Path(a.input_manifest).read_text())
lines=Path(a.input_pdb).read_text().splitlines()
assert len([x for x in lines if x.startswith('ATOM  ')])==30
coords=[[float(x[30:38]),float(x[38:46]),float(x[46:54])] for x in lines if x.startswith('ATOM  ') and x[12:16].strip()=='CA']
n=len(m['sequence']); assert n==len(coords)
r={'schema':'kuma-merizo-result-v1','tool_commit':COMMIT,'weights_sha256':WEIGHTS,'input':m,
'process':{'status':'ok','exit_code':0,'warnings':[]},
'features':{'nres':n,'sequence':m['sequence'],'residue_numbers':list(range(1,n+1)),'ca_coordinates':coords},
'prediction':{'nres':n,'ndom':1,'labels':[1]*n,'residue_numbers':list(range(1,n+1)),'confidence':0.5,'time_sec':0.01}}
Path(a.output).write_text(json.dumps(r))
'''.replace("COMMIT", repr(MERIZO_COMMIT)).replace("WEIGHTS", repr(MERIZO_WEIGHTS_SHA256))).encode()
    member = "bin/synthetic-domain"
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(member, script)
    raw = output.getvalue()
    archive_path = tmp_path / "synthetic-only.zip"
    archive_path.write_bytes(raw)
    platform = current_platform_key()
    artifact = RuntimeArtifact("merizo", "synthetic-process-1", platform,
        hashlib.sha256(raw).hexdigest(), len(raw),
        (RuntimeFile(member, hashlib.sha256(script).hexdigest(), len(script), True),), member)
    manager = OptionalRuntimeManager(tmp_path.resolve() / "app", catalog={("merizo", platform): artifact})
    service = DomainJobService(manager)
    assert service.install(str(archive_path))["state"] == "installed"
    job = service.start(source)
    outcome = terminal(service, job["job_id"])
    assert outcome["state"] == "succeeded", outcome
    result = service.import_result(job["job_id"], source)
    assert result["total_residues"] == 6
    assert result["assigned_residues"] == 6
    assert result["coverage"] == 1.0
    assert result["provenance"] == "managed"
    assert service.remove()["state"] == "missing"


def test_start_validation_failure_releases_reservation_for_next_request(tmp_path):
    source = source_fixture(tmp_path)
    service, _ = service_fixture(tmp_path, successful_runner(source))
    with pytest.raises(ValueError):
        service.start(replace(source, prediction_bundle_sha256="0" * 64))
    job = service.start(source)
    assert terminal(service, job["job_id"])["state"] == "succeeded"


def test_cancel_during_runtime_reverification_never_launches(tmp_path, monkeypatch):
    source = source_fixture(tmp_path)
    calls = []
    service, manager = service_fixture(tmp_path, lambda *args, **kwargs: calls.append(args))
    entered, finish = threading.Event(), threading.Event()
    original = manager.verify
    def verify(**kwargs):
        entered.set()
        assert finish.wait(5)
        return original(**kwargs)
    monkeypatch.setattr(manager, "verify", verify)
    job = service.start(source)
    assert entered.wait(5)
    service.cancel(job["job_id"])
    finish.set()
    assert terminal(service, job["job_id"])["state"] == "cancelled"
    assert calls == []


def test_result_read_rejects_replacement_between_lstat_and_open(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    path.write_text("{}")
    replacement = tmp_path / "replacement.json"
    replacement.write_text("{}")
    original = domain_jobs.os.open
    def replaced_open(filename, flags, *args, **kwargs):
        replacement.replace(path)
        return original(filename, flags, *args, **kwargs)
    monkeypatch.setattr(domain_jobs.os, "open", replaced_open)
    with pytest.raises(DomainAnnotationError, match="changed"):
        read_result_file(path)


@pytest.mark.parametrize("method", ["install", "remove"])
def test_shutdown_waits_for_install_or_remove_safe_cancellation(tmp_path, monkeypatch, method):
    from kuma_core.kuro.optional_runtime import RuntimeCancelled
    manager = OptionalRuntimeManager(tmp_path / "app")
    service = DomainJobService(manager)
    entered, finish = threading.Event(), threading.Event()
    errors = []
    def operation(*args, cancelled, **kwargs):
        entered.set()
        assert finish.wait(5)
        assert cancelled()
        raise RuntimeCancelled("cancelled at safe fixture boundary")
    monkeypatch.setattr(manager, method, operation)
    def run():
        try:
            if method == "install":
                service.install("synthetic.zip")
            else:
                service.remove()
        except RuntimeCancelled as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(5)
    assert not service.stop(timeout=0.01)
    finish.set()
    thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert service.stop(timeout=0.01)


def test_shutdown_during_source_preparation_prevents_late_job_start(tmp_path, monkeypatch):
    from kuma_core.kuro.optional_runtime import RuntimeCancelled
    source = source_fixture(tmp_path)
    calls = []
    service, _ = service_fixture(tmp_path, lambda *args, **kwargs: calls.append(args))
    entered, finish = threading.Event(), threading.Event()
    original = domain_jobs.prepare_source
    errors = []
    def prepare(source):
        entered.set()
        assert finish.wait(5)
        return original(source)
    monkeypatch.setattr(domain_jobs, "prepare_source", prepare)
    def run():
        try:
            service.start(source)
        except RuntimeCancelled as exc:
            errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(5)
    assert not service.stop(timeout=0.01)
    finish.set()
    thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert service.stop(timeout=0.01)
    assert service._jobs == {}
    assert calls == []


def test_exact_attempt_tombstone_prevents_delayed_start_and_duplicate_launch(tmp_path):
    source = source_fixture(tmp_path)
    service, _ = service_fixture(tmp_path, successful_runner(source))
    cancelled = "1" * 32
    assert service.recover_attempt(cancelled)["state"] == "unknown"
    assert service.cancel_attempt(cancelled)["state"] == "cancelled"
    with pytest.raises(DomainAnnotationError, match="already used"):
        service.start(source, attempt_id=cancelled)
    assert service._jobs == {}
    attempt = "2" * 32
    job = service.start(source, attempt_id=attempt)
    assert terminal(service, job["job_id"])["state"] == "succeeded"
    recovered = service.recover_attempt(attempt)
    assert recovered["state"] == "job"
    assert recovered["job"]["job_id"] == job["job_id"]
    with pytest.raises(DomainAnnotationError, match="already used"):
        service.start(source, attempt_id=attempt)
    assert len(service._jobs) == 1


def test_attempt_cancel_during_preparation_waits_then_prevents_execution(tmp_path, monkeypatch):
    from kuma_core.kuro.optional_runtime import RuntimeCancelled
    source = source_fixture(tmp_path)
    calls = []
    service, _ = service_fixture(tmp_path, lambda *args, **kwargs: calls.append(args))
    attempt_id = "3" * 32
    entered, finish = threading.Event(), threading.Event()
    original = domain_jobs.prepare_source
    errors = []
    def prepare(source):
        entered.set()
        assert finish.wait(5)
        return original(source)
    monkeypatch.setattr(domain_jobs, "prepare_source", prepare)
    def start():
        try:
            service.start(source, attempt_id=attempt_id)
        except RuntimeCancelled as exc:
            errors.append(exc)
    thread = threading.Thread(target=start)
    thread.start()
    assert entered.wait(5)
    assert service.recover_attempt(attempt_id)["state"] == "pending"
    assert service.cancel_attempt(attempt_id)["state"] == "pending"
    finish.set()
    thread.join(5)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert service.recover_attempt(attempt_id)["state"] == "cancelled"
    assert not calls
    assert not service._jobs


def test_attempt_cancel_of_running_process_reports_nested_cancelling_until_exit(tmp_path):
    source = source_fixture(tmp_path)
    entered, finish = threading.Event(), threading.Event()
    def runner(argv, **kwargs):
        from kuma_core.kuro.domain_process import DomainProcessCancelled
        entered.set()
        assert finish.wait(5)
        raise DomainProcessCancelled("confirmed")
    service, _ = service_fixture(tmp_path, runner)
    attempt_id = "4" * 32
    job = service.start(source, attempt_id=attempt_id)
    assert entered.wait(5)
    current = service.cancel_attempt(attempt_id)
    assert current["state"] == "job"
    assert current["job"]["state"] == "cancelling"
    assert current["job"]["job_id"] == job["job_id"]
    finish.set()
    assert terminal(service, job["job_id"])["state"] == "cancelled"
    assert service.recover_attempt(attempt_id)["job"]["state"] == "cancelled"


def test_attempt_saturation_never_evicts_replay_tombstones(tmp_path, monkeypatch):
    service = DomainJobService(OptionalRuntimeManager(tmp_path / "app"))
    monkeypatch.setattr(domain_jobs, "MAX_ATTEMPTS", 2)
    service.cancel_attempt("1" * 32)
    service.cancel_attempt("2" * 32)
    with pytest.raises(DomainAnnotationError, match="full"):
        service.cancel_attempt("3" * 32)
    with pytest.raises(DomainAnnotationError, match="full"):
        service.start(source_fixture(tmp_path), attempt_id="3" * 32)
    assert service.recover_attempt("1" * 32)["state"] == "cancelled"
    with pytest.raises(DomainAnnotationError, match="already used"):
        service.start(source_fixture(tmp_path), attempt_id="1" * 32)


def test_expired_result_attempt_cannot_be_replayed(tmp_path, monkeypatch):
    source = source_fixture(tmp_path)
    service, _ = service_fixture(tmp_path, successful_runner(source))
    monkeypatch.setattr(domain_jobs, "MAX_RETAINED_JOBS", 1)
    first = service.start(source, attempt_id="1" * 32)
    assert terminal(service, first["job_id"])["state"] == "succeeded"
    second = service.start(source, attempt_id="2" * 32)
    assert terminal(service, second["job_id"])["state"] == "succeeded"
    assert service.recover_attempt("1" * 32)["state"] == "expired"
    assert service.cancel_attempt("1" * 32)["state"] == "expired"
    with pytest.raises(DomainAnnotationError, match="already used"):
        service.start(source, attempt_id="1" * 32)


def test_shutdown_blocks_late_start_or_mutation_before_admission(tmp_path):
    source = source_fixture(tmp_path)
    service, _ = service_fixture(tmp_path, successful_runner(source))
    assert service.stop(timeout=0)
    for action in (lambda: service.start(source, attempt_id="1" * 32),
                   lambda: service.install("synthetic.zip"), service.remove):
        with pytest.raises(OptionalRuntimeError, match="shutting down"):
            action()
    assert service._jobs == {}
    assert service.recover_attempt("1" * 32)["state"] == "failed"
