"""Test-only native CPU portability probe, not a KUMA provider or installer.

Only the pinned public 1UBQ fixture is accepted. Upstream source is unchanged;
weights are verified before any pickle-based torch.load. No weights are emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import time
from typing import Callable

COMMIT = "41d12fb84e6e8fdb586c2c859d12161dc7bb5bfd"
INPUT_SHA = "d4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161"
WEIGHTS = {
    "weights_part_0.pt": "8b90ad1967c3e445aca7ed3d53135190ceaf8e100d68afd1543e5e8d28547151",
    "weights_part_1.pt": "644f711b9573b44fc25a0bc0631ee9ab43f7fbd796db0a382298755057a2fa38",
    "weights_part_2.pt": "ddafe5fa5dfa729eb8715757004d2d3e4e9798f96ea43c689e799ef91af8c2b8",
}
REFERENCE = "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"
AA: dict[str, str] = dict(zip("ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL".split(), "ARNDCQEGHILKMFPSTWYV"))


# This is a deliberately narrow test matrix, not a claim of general support.
CPU_RUNTIME_MATRIX = {
    ("Linux", "x86_64"): "2.0.1+cpu",
    ("Darwin", "arm64"): "2.0.1",
    ("Windows", "AMD64"): "2.0.1+cpu",
}


def runtime_contract() -> dict[str, str]:
    system, architecture = platform.system(), platform.machine()
    expected = CPU_RUNTIME_MATRIX.get((system, architecture))
    if expected is None:
        raise ValueError(f"Unsupported smoke platform/architecture: {system}/{architecture}")
    return {"system": system, "architecture": architecture, "expected_torch": expected, "device": "cpu"}


def validate_torch_runtime(version: str, cuda_version: str | None, contract: dict[str, str]) -> None:
    if version != contract["expected_torch"] or cuda_version is not None:
        raise ValueError(f"Expected CPU-only torch {contract['expected_torch']} on "
                         f"{contract['system']}/{contract['architecture']}")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare(raw: str) -> tuple[str, list[dict], list[list[float]]]:
    """Bounded fixture normalization retaining ordered all-atom records and inverse labels."""
    atoms = [line for line in raw.splitlines() if line.startswith("ATOM  ") and line[21] == "A"]
    identities: list[tuple[int, str]] = []
    grouped: dict[tuple[int, str], list[str]] = {}
    for line in atoms:
        if len(line) < 78 or line[16] != " ":
            raise ValueError("Unsupported atom/alternate")
        identity = (int(line[22:26]), line[26])
        if identity not in grouped:
            identities.append(identity)
            grouped[identity] = []
        grouped[identity].append(line)
    if len(identities) != 76 or len(atoms) != 602:
        raise ValueError("Public fixture lost residues or atoms")
    sequence = ""
    coordinates: list[list[float]] = []
    for identity in identities:
        rows = grouped[identity]
        names = [row[12:16].strip() for row in rows]
        if len(names) != len(set(names)) or not {"N", "CA", "C", "O"} <= set(names):
            raise ValueError("Incomplete/duplicate backbone")
        if len({row[17:20] for row in rows}) != 1:
            raise ValueError("Mixed residue")
        sequence += AA[rows[0][17:20]]
        ca = rows[names.index("CA")]
        coordinates.append([float(ca[start:start + 8]) for start in (30, 38, 46)])
    if sequence != REFERENCE or not all(math.isfinite(x) for row in coordinates for x in row):
        raise ValueError("Reference/coordinates mismatch")
    index = {identity: i for i, identity in enumerate(identities, 1)}
    normalized = [line[:21] + "A" + f"{index[(int(line[22:26]), line[26])]:4d} " + line[27:] for line in atoms]
    # Inverse restoration must preserve all ATOM bytes, not just a display trace.
    restored = []
    for line in normalized:
        original = identities[int(line[22:26]) - 1]
        restored.append(line[:22] + f"{original[0]:4d}" + original[1] + line[27:])
    if restored != atoms:
        raise ValueError("Atom roundtrip mismatch")
    mapping = [{"normalized_position": i, "reference_position": i, "author_number": number,
                "insertion_code": insertion.strip(), "chain_id": "A", "model_id": "1"}
               for i, (number, insertion) in enumerate(identities, 1)]
    return "\n".join(normalized) + "\nTER\nEND\n", mapping, coordinates


def verify_upstream(source: Path) -> dict[str, str]:
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != COMMIT:
        raise ValueError("Unpinned source HEAD")
    subprocess.run(["git", "-C", str(source), "diff", "--exit-code", "HEAD", "--"], check=True, capture_output=True)
    if subprocess.check_output(["git", "-C", str(source), "ls-files", "--others", "--exclude-standard"], text=True).strip():
        raise ValueError("Untracked source files")
    # Ignored modules/bytecode could otherwise contaminate imports despite a
    # clean tracked diff. Build/probe runs set PYTHONDONTWRITEBYTECODE=1.
    if subprocess.check_output(["git", "-C", str(source), "ls-files", "--others", "--ignored", "--exclude-standard"], text=True).strip():
        raise ValueError("Ignored source files are not allowed in the clean probe checkout")
    return verify_weights(source / "weights")


def verify_weights(directory: Path) -> dict[str, str]:
    """Stream all three exact official weight hashes before pickle model loading."""
    actual = {}
    for file in directory.glob("*.pt"):
        if not file.is_file() or file.is_symlink() or file.stat().st_size > 512 * 1024 * 1024:
            raise ValueError("Unsupported weight file")
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        actual[file.name] = digest.hexdigest()
    if actual != WEIGHTS:
        raise ValueError("Weight file set or SHA mismatch before model loading")
    return actual


def validate_prediction(result: dict) -> None:
    labels, positions, confidence = result["labels"], result["residue_numbers"], result["confidence"]
    if result["nres"] != 76 or positions != list(range(1, 77)) or len(labels) != 76:
        raise ValueError("Prediction count/identity loss")
    if any(type(x) is not int or x < 0 for x in labels):
        raise ValueError("Invalid domain label")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("Invalid confidence")
    if result["ndom"] != len(set(labels) - {0}) or result["ndom"] < 1:
        raise ValueError("Empty or inconsistent domains")


def validate_coordinates(actual: list[list[float]], expected: list[list[float]]) -> None:
    if len(actual) != 76 or len(expected) != 76 or any(
        len(xyz) != 3 or len(reference) != 3
        or any(not math.isfinite(a) or not math.isfinite(b) or abs(a - b) > 0.0001
               for a, b in zip(xyz, reference))
        for xyz, reference in zip(actual, expected)
    ):
        raise ValueError("Feature CA coordinates changed")


def inference(fixture: Path, weights_directory: Path,
              runtime_guard: Callable[[], dict] | None = None) -> dict:
    """Shared native/frozen inference; never relaunch sys.executable here."""
    contract = runtime_contract()
    weights = verify_weights(weights_directory)
    raw = fixture.read_bytes()
    if sha(raw) != INPUT_SHA:
        raise ValueError("Unpinned public input")
    normalized, mapping, coordinates = prepare(raw.decode("ascii"))
    # Synthetic sibling author labels: distinct 110 and 110A, not integer-only identity.
    probe_lines = []
    for line in raw.decode("ascii").splitlines():
        if line.startswith("ATOM  ") and line[21] == "A":
            residue = int(line[22:26])
            number, insertion = (110, "A") if residue == 11 else (residue + 100, " ")
            line = line[:22] + f"{number:4d}" + insertion + line[27:]
        probe_lines.append(line)
    probe, probe_mapping, _ = prepare("\n".join(probe_lines))
    if probe != normalized or probe_mapping[9]["author_number"] != probe_mapping[10]["author_number"]:
        raise ValueError("Insertion normalization failed")
    torch = importlib.import_module("torch")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    validate_torch_runtime(torch.__version__, torch.version.cuda, contract)
    predict = importlib.import_module("predict")
    features_module = importlib.import_module("model.utils.features")
    # The frozen entry checks real module/DLL origins before torch.load.
    runtime_before = runtime_guard() if runtime_guard is not None else None
    start = time.perf_counter()
    network = predict.Merizo().to("cpu")
    network.load_state_dict(predict.read_split_weight_files(str(weights_directory)), strict=True)
    network.eval()
    with tempfile.TemporaryDirectory(prefix="kuma merizo smoke ") as temp:
        pdb = Path(temp) / "public input with spaces.pdb"
        pdb.write_text(normalized, encoding="ascii", newline="\n")
        features = features_module.generate_features_domain(str(pdb), "cpu", "A")
        if features["nres"] != 76 or features["ri"].flatten().tolist() != list(range(1, 77)):
            raise ValueError("Feature residue identity lost")
        if features_module.pdb_to_fasta(features["pdb"]) != REFERENCE:
            raise ValueError("Feature sequence changed")
        ca = features["pdb"][features["pdb"]["n"] == "CA"]
        actual = [[float(row[name]) for name in ("x", "y", "z")] for row in ca]
        validate_coordinates(actual, coordinates)
        with torch.no_grad():
            result = predict.segment(str(pdb), network, "cpu", False, False, 3, False, "A")
        prediction = {"nres": result["nres"], "ndom": int(result["ndom"]),
                      "confidence": float(result["conf_global"]),
                      "labels": result["domain_ids"].flatten().tolist(),
                      "residue_numbers": result["ri"].flatten().tolist()}
        validate_prediction(prediction)
    report = {"status": "passed", "scope": "native_cpu_public_fixture_smoke_only", "platform": platform.platform(),
              "system": contract["system"], "architecture": contract["architecture"], "device": contract["device"],
              "python": platform.python_version(), "torch": torch.__version__, "threads": torch.get_num_threads(),
              "source_commit": COMMIT, "weights_sha256": weights, "input_sha256": INPUT_SHA,
              "normalized_sha256": sha(normalized.encode("ascii")), "atom_count": 602,
              "reference_length": 76, "feature_sequence_and_coordinates_checked": True,
              "insertion_roundtrip_checked": True, "mapping": mapping,
              "elapsed_seconds": time.perf_counter() - start, "prediction": prediction,
              "not_verified": ["KUMA integration", "native GUI", "standalone packaging", "redistribution rights", "biological accuracy"]}
    if runtime_guard is not None:
        report["frozen_runtime_before_load"] = runtime_before
        report["frozen_runtime_after_inference"] = runtime_guard()
    return report


def worker(source: Path, fixture: Path, output: Path) -> None:
    verify_upstream(source)
    sys.path.insert(0, str(source))
    report = inference(fixture, source / "weights")
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def stop_worker_tree(process: subprocess.Popen) -> None:
    """Kill the owned POSIX session, or the existing Windows native worker tree."""
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=10, check=False)
        finally:
            if process.poll() is None:
                process.kill()
    else:
        # The caller creates this process as a session/group leader. Use its
        # original PID even if the root exited while descendants retained pipes.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def supervise_worker(command: list[str], environment: dict[str, str], *,
                     timeout_seconds: float = 300) -> tuple[int, bytes, bytes, bool]:
    """Bounded native invocation; no inference is performed in this parent."""
    posix_group = sys.platform != "win32"
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=environment, shell=False, start_new_session=posix_group)
    stopped = False
    timed_out = False
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_worker_tree(process)
            stopped = True
            # Descendants may have inherited the output pipes. Group termination
            # happens first, then both draining and root reaping remain bounded.
            stdout, stderr = process.communicate(timeout=10)
        if process.returncode is None:
            raise RuntimeError("Native worker was not reaped after completion")
        return process.returncode, stdout, stderr, timed_out
    finally:
        if posix_group and not stopped:
            # Also clean descendants after a normal root exit or a parent error.
            stop_worker_tree(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker(args.source.resolve(), args.fixture.resolve(), args.output.resolve())
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker", "--source", str(args.source.resolve()),
               "--fixture", str(args.fixture.resolve()), "--output", str(args.output.resolve())]
    env = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
           "MPLBACKEND": "Agg", "CUDA_VISIBLE_DEVICES": ""}
    try:
        returncode, stdout, stderr, timed_out = supervise_worker(command, env)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        args.output.write_text(json.dumps({"status": "failed", "stage": "native_process_cleanup",
            "error": f"{type(exc).__name__}: {exc}"[:2000]}) + "\n", encoding="utf-8")
        return 2
    if timed_out:
        args.output.write_text(json.dumps({"status": "timed_out", "timeout_seconds": 300,
            "worker_reaped": True}) + "\n", encoding="utf-8")
        return 2
    print(stdout.decode("utf-8", errors="replace"))
    print(stderr.decode("utf-8", errors="replace"), file=sys.stderr)
    if returncode:
        args.output.write_text(json.dumps({"status": "failed", "exit_code": returncode,
                                           "stderr": stderr.decode("utf-8", errors="replace")[-12000:]}) + "\n", encoding="utf-8")
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
