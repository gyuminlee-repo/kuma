#!/usr/bin/env python3
"""Explicit, experimental CPU invocation of an independently installed Chainsaw.

No installer, network service, downloaded weights or bundled third-party code.
Run with the external environment's Python. Review its licenses separately.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kuma_core.kuro.domain_annotation import (
    CHAINSAW_COMMIT, CHAINSAW_WEIGHTS_SHA256, DomainAnnotationError, DomainInput,
    MAX_SOURCE_BYTES, decode_domain_result, parse_stride_assignments, prepare_domain_input, validate_stride_input,
)
from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId

MAX_STRIDE_BYTES = 4 * 1024 * 1024


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise DomainAnnotationError(f"Input exceeds byte limit: {path.name}")
    return raw


def prepare_export(directory: Path) -> DomainInput:
    """Check the manifest and normalized structure without claiming original provenance."""
    manifest = json.loads(bounded(directory / "input.manifest.json", 4 * 1024 * 1024))
    raw = bounded(directory / "input.pdb", MAX_SOURCE_BYTES)
    if not isinstance(manifest, dict) or sha(raw) != manifest.get("normalized_sha256"):
        raise DomainAnnotationError("Exported PDB hash mismatch")
    if manifest.get("schema") != "kuma-chainsaw-input-v1":
        raise DomainAnnotationError("Unsupported exported manifest")
    sequence = manifest["sequence"]
    rows = manifest["residues"]
    if not isinstance(sequence, str) or not isinstance(rows, list) or len(rows) != len(sequence):
        raise DomainAnnotationError("Incomplete export sequence/mapping")
    identities = tuple(ResidueId(row["model_id"], row["chain_id"], row["author_number"], row["insertion_code"]) for row in rows)
    # Validate actual normalized atom identities/backbone too, before importing any ML code.
    normalized_polymer = PolymerRecord(sequence, "normalized export", "normalized export", "1", "A",
                                      tuple(ResidueId("1", "A", i) for i in range(1, len(sequence) + 1)))
    checked = prepare_domain_input(raw.decode("utf-8"), normalized_polymer, sequence, source_sha256=sha(raw))
    if checked.normalized_pdb != raw.decode("utf-8"):
        raise DomainAnnotationError("Export is not canonical normalized input.pdb")
    prepared = DomainInput(raw.decode("utf-8"), manifest["source_sha256"], manifest["reference_sha256"],
                           manifest["normalized_sha256"], manifest["binding_sha256"], sequence,
                           manifest["polymer_source"], manifest["frame_id"], manifest["model_id"],
                           manifest["chain_id"], identities)
    prepared.check_consistency()
    if prepared.manifest() != manifest:
        raise DomainAnnotationError("Export manifest is not a complete bijective v1 mapping")
    return prepared


def verify_source(source: Path) -> dict[str, str]:
    pins = json.loads((Path(__file__).with_name("chainsaw-source-pins.json")).read_text())
    if pins["commit"] != CHAINSAW_COMMIT:
        raise DomainAnnotationError("Adapter source pin disagreement")
    hashes: dict[str, str] = {}
    for name, expected in pins["files"].items():
        # Only own-code fixed relative filenames; no downloaded manifest controls paths.
        actual = sha(bounded(source / name, 16 * 1024 * 1024))
        if actual != expected:
            raise DomainAnnotationError(f"Pinned Chainsaw source/model mismatch: {name}")
        hashes[name] = actual
    return hashes


def capture_stride(executable: Path, pdbfile: str, chain: str, ssfile: str,
                   sequence: str, *, timeout: float = 180) -> dict[str, Any]:
    if chain != "A":
        raise DomainAnnotationError("External STRIDE must use normalized chain A")
    actual_input = bounded(Path(pdbfile), MAX_SOURCE_BYTES)
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        with subprocess.Popen([str(executable), pdbfile, "-rA"], stdout=out, stderr=err) as process:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    process.kill(); process.wait()
                    raise DomainAnnotationError("STRIDE timed out")
                if max(os.fstat(out.fileno()).st_size, os.fstat(err.fileno()).st_size) > MAX_STRIDE_BYTES:
                    process.kill(); process.wait()
                    raise DomainAnnotationError("STRIDE output exceeds byte limit")
                time.sleep(0.01)
            returncode = process.returncode
        out.seek(0); err.seek(0)
        stdout_raw, stderr_raw = out.read(MAX_STRIDE_BYTES + 1), err.read(MAX_STRIDE_BYTES + 1)
    if len(stdout_raw) > MAX_STRIDE_BYTES or len(stderr_raw) > MAX_STRIDE_BYTES:
        raise DomainAnnotationError("STRIDE output exceeds byte limit")
    if returncode != 0 or stderr_raw.strip():
        raise DomainAnnotationError(f"STRIDE failed or reported diagnostics (exit {returncode})")
    stdout = stdout_raw.decode("utf-8")
    positions = parse_stride_assignments(stdout, sequence)
    if bounded(Path(pdbfile), MAX_SOURCE_BYTES) != actual_input:
        raise DomainAnnotationError("STRIDE input changed during execution")
    # Hand exactly captured bytes back to unchanged upstream feature construction.
    Path(ssfile).write_bytes(stdout_raw)
    return {"status": "ok", "exit_code": returncode, "warnings": [],
            "residue_count": len(positions), "assigned_positions": positions,
            "stdout": stdout, "stdout_sha256": sha(stdout_raw), "stderr": "",
            "stride_input_pdb": actual_input.decode("utf-8"), "stride_input_sha256": sha(actual_input),
            "executable_sha256": sha(bounded(executable, 128 * 1024 * 1024))}


class WarningCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def run(source: Path, stride: Path, prepared: DomainInput) -> dict[str, Any]:
    prepared.check_consistency()
    if len(prepared.sequence) > 2000:
        raise DomainAnnotationError("Experimental CPU wrapper is limited to 2000 residues")
    if any(name == "get_predictions" or name == "src" or name.startswith("src.") for name in sys.modules):
        raise DomainAnnotationError("Use a fresh external Python process for each prediction")
    hashes = verify_source(source)
    if not stride.is_file():
        raise DomainAnnotationError("Explicit existing STRIDE executable is required")
    # Must happen before importing torch. This wrapper intentionally offers no GPU mode.
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = "1"
    sys.path.insert(0, str(source))
    torch = importlib.import_module("torch")
    if torch.__version__ != "2.0.1+cpu" or sys.version_info[:2] != (3, 11):
        raise DomainAnnotationError("Experimental wrapper requires the evaluated Python 3.11 / torch 2.0.1+cpu environment")
    torch.set_num_threads(1); torch.set_num_interop_threads(1); torch.manual_seed(0)
    predict = importlib.import_module("get_predictions")
    features: Any = importlib.import_module("src.featurisers")
    evidence: list[dict[str, Any]] = []
    warnings = WarningCapture()
    logger = logging.getLogger()
    logger.addHandler(warnings)
    original_calculate = features.calculate_ss
    try:
        def checked_stride(pdbfile: str, chain: str, stride_path: str, ssfile: str = "pdb_ss") -> None:
            # Ignore upstream's bundled executable default; user chose this explicit installation.
            validate_stride_input(bounded(Path(pdbfile), MAX_SOURCE_BYTES).decode("utf-8"), prepared.normalized_pdb)
            evidence.append(capture_stride(stride, pdbfile, chain, ssfile, prepared.sequence))
        features.calculate_ss = checked_stride
        model = predict.load_model(model_dir=str(source / "saved_models" / "model_v3"))
        with tempfile.TemporaryDirectory(prefix="kuma-chainsaw-") as temporary:
            input_path = Path(temporary) / "input.pdb"
            input_path.write_text(prepared.normalized_pdb, encoding="utf-8", newline="\n")
            previous_cwd = Path.cwd()
            try:
                # A relative filename prevents internal workspace paths in captured STRIDE CHN records.
                os.chdir(temporary)
                with torch.no_grad():
                    prediction = predict.predict(model, "input.pdb", renumber_pdbs=True, pdbchain="A")
            finally:
                os.chdir(previous_cwd)
            payload = json.loads(prediction.json())
            # Ephemeral filesystem paths have no role in the output identity.
            payload.pop("pdb_path", None)
        if len(evidence) != 1 or warnings.messages:
            raise DomainAnnotationError("Expected one successful STRIDE invocation and no predictor warnings")
        envelope = {"schema": "kuma-chainsaw-result-v1", "tool_commit": CHAINSAW_COMMIT,
                    "weights_sha256": CHAINSAW_WEIGHTS_SHA256, "input": prepared.manifest(),
                    "renumber_pdbs": True, "process": {"status": "ok", "exit_code": 0, "warnings": []},
                    "stride": evidence[0], "prediction": payload,
                    "runtime": {"python": sys.version.split()[0], "torch": torch.__version__,
                                "device": "cpu", "threads": 1, "source_hashes": hashes,
                                "packages": {name: importlib.metadata.version(name) for name in
                                             ("numpy", "scipy", "biopython", "einops", "pydantic", "pandas")}}}
        # A zero-domain, nonfinite or count-loss result never becomes a successful envelope.
        decode_domain_result(json.dumps(envelope), prepared, current_binding_sha256=prepared.binding_sha256)
        return envelope
    finally:
        features.calculate_ss = original_calculate
        logger.removeHandler(warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chainsaw-source", type=Path, required=True)
    parser.add_argument("--stride", type=Path, required=True)
    parser.add_argument("--input-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise DomainAnnotationError("Output already exists; choose a fresh result path")
        prepared = prepare_export(args.input_directory)
        envelope = run(args.chainsaw_source.resolve(), args.stride.resolve(), prepared)
        # Exclusive creation prevents replacing a concurrently created file.
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(envelope, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"status": "validated_external_result", "binding_sha256": prepared.binding_sha256}))
        return 0
    except Exception as exc:
        print(f"External Chainsaw failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
