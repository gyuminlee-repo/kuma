"""Public PDB and synthetic external-result contracts; no predictor execution."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from kuma_core.kuro.domain_annotation import (
    CHAINSAW_COMMIT, CHAINSAW_WEIGHTS_SHA256, DomainAnnotationError,
    decode_domain_result, prepare_domain_input,
)
from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId

PDB = Path(__file__).parent / "data" / "domain_annotation" / "1ubq.pdb"
SEQUENCE = "MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG"


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def polymer():
    return PolymerRecord(SEQUENCE, "RCSB 1UBQ SEQRES", "1ubq-public-pdb", "1", "A",
                         tuple(ResidueId("1", "A", i) for i in range(1, 77)))


def prepare(text=None, record=None):
    text = PDB.read_text() if text is None else text
    return prepare_domain_input(text, record or polymer(), SEQUENCE, source_sha256=digest(text))


def envelope(prepared) -> dict[str, Any]:
    monomers = {line[22:26].strip(): line[17:20] for line in prepared.normalized_pdb.splitlines() if line.startswith("ATOM  ")}
    stdout = "\n".join(f"ASG  {monomers[str(i)]} A {i} {i} C Coil 0.00 0.00 0.0" for i in range(1, 77)) + "\n"
    return {"schema": "kuma-chainsaw-result-v1", "tool_commit": CHAINSAW_COMMIT,
            "weights_sha256": CHAINSAW_WEIGHTS_SHA256, "input": prepared.manifest(),
            "renumber_pdbs": True, "process": {"status": "ok", "exit_code": 0, "warnings": []},
            "stride": {"status": "ok", "exit_code": 0, "warnings": [],
                       "residue_count": 76, "assigned_positions": list(range(1, 77)),
                       "stdout": stdout, "stdout_sha256": digest(stdout), "stderr": "",
                       "stride_input_pdb": prepared.normalized_pdb,
                       "stride_input_sha256": prepared.normalized_sha256},
            "prediction": {"chain_id": "input", "sequence_md5": hashlib.md5(SEQUENCE.encode()).hexdigest(),
                           "nres": 76, "ndom": 2, "chopping": "2-10_60-71,12-58",
                           "confidence": 0.9, "time_sec": 0.1}}


def decode(prepared, result):
    return decode_domain_result(json.dumps(result), prepared, current_binding_sha256=prepared.binding_sha256)


def test_public_atom_coordinates_and_all_atom_fields_preserved():
    source = PDB.read_text()
    # Public source bytes are pinned, not re-downloaded at test time.
    assert digest(source) == "d4a6812d8951cf6594e6a0763f089e35f5a80b62acb3c117b2c5565228a7b161"
    prepared = prepare(source)
    before = [line for line in source.splitlines() if line.startswith("ATOM  ") and line[21] == "A"]
    after = [line for line in prepared.normalized_pdb.splitlines() if line.startswith("ATOM  ")]
    assert len(before) == len(after) == 602
    assert all(a[:21] == b[:21] and a[27:] == b[27:] for a, b in zip(before, after, strict=True))
    assert all(line[21] == "A" and line[26] == " " for line in after)
    assert len(prepared.manifest()["residues"]) == 76


def test_discontinuous_domains_unassigned_and_inverse_identity():
    prepared = prepare()
    result = decode(prepared, envelope(prepared))
    assert len(result.domains) == 2
    assert [(s.start, s.end) for s in result.domains[0].segments] == [(2, 10), (60, 71)]
    assert result.domains[0].source_residues[0] == ResidueId("1", "A", 2)
    assert result.assigned_residues == 68
    assert result.coverage == 68 / 76
    assert result.unassigned_positions == (1, 11, 59, 72, 73, 74, 75, 76)
    assert "unverified" in result.interpretation


def test_renumber_and_insertion_are_bijective_without_atom_changes():
    source = PDB.read_text()
    identities = tuple(ResidueId("1", "B", 110 if i == 9 else i + 100, "A" if i == 10 else "") for i in range(1, 77))
    lines = []
    for line in source.splitlines():
        if line.startswith("ATOM  "):
            old = int(line[22:26]); identity = identities[old - 1]
            line = line[:21] + "B" + f"{identity.author_number:4d}" + (identity.insertion_code or " ") + line[27:]
        lines.append(line)
    prepared = prepare("\n".join(lines), replace(polymer(), chain_id="B", residues_by_position=identities))
    result = decode(prepared, envelope(prepared))
    assert result.domains[0].source_residues[7] == ResidueId("1", "B", 110, "")
    assert result.domains[0].source_residues[8] == ResidueId("1", "B", 110, "A")
    assert prepared.normalized_pdb.splitlines()[0][22:27] == "   1 "


@pytest.mark.parametrize("change", ["ca_only", "missing_o", "missing_residue", "duplicate_atom", "altloc", "nan", "wrong_aa"])
def test_reject_unsupported_source(change):
    lines = PDB.read_text().splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("ATOM  "))
    if change == "ca_only":
        lines = [line for line in lines if not line.startswith("ATOM  ") or line[12:16].strip() == "CA"]
    elif change == "missing_o":
        lines = [line for line in lines if not (line.startswith("ATOM  ") and int(line[22:26]) == 1 and line[12:16].strip() == "O")]
    elif change == "missing_residue":
        lines = [line for line in lines if not (line.startswith("ATOM  ") and int(line[22:26]) == 10)]
    elif change == "duplicate_atom":
        lines.insert(first, lines[first])
    elif change == "altloc":
        lines[first] = lines[first][:16] + "A" + lines[first][17:]
    elif change == "nan":
        lines[first] = lines[first][:30] + "     nan" + lines[first][38:]
    else:
        lines[first] = lines[first][:17] + "ALA" + lines[first][20:]
    with pytest.raises(DomainAnnotationError):
        prepare("\n".join(lines))


def test_explicit_model_and_chain_selection():
    atoms = "\n".join(line for line in PDB.read_text().splitlines() if line.startswith("ATOM  "))
    two = "MODEL        1\n" + atoms + "\nENDMDL\nMODEL        2\n" + atoms + "\nENDMDL\n"
    first, second = prepare(two), prepare(two, replace(polymer(), model_id="2", residues_by_position=tuple(ResidueId("2", "A", i) for i in range(1, 77))))
    assert first.normalized_pdb == second.normalized_pdb
    assert first.binding_sha256 != second.binding_sha256
    with pytest.raises(DomainAnnotationError):
        prepare(two.replace("MODEL        2", "MODEL        1"))
    with pytest.raises(DomainAnnotationError):
        prepare(record=replace(polymer(), chain_id="Z", residues_by_position=tuple(ResidueId("1", "Z", i) for i in range(1, 77))))


def test_reject_uncertain_or_nonexact_polymer():
    with pytest.raises(DomainAnnotationError):
        prepare(record=replace(polymer(), residues_by_position=(None,) + polymer().residues_by_position[1:]))
    with pytest.raises(DomainAnnotationError):
        prepare_domain_input(PDB.read_text(), polymer(), "G" + SEQUENCE, source_sha256=digest(PDB.read_text()))
    with pytest.raises(DomainAnnotationError):
        prepare_domain_input(PDB.read_text(), polymer(), SEQUENCE, source_sha256="0" * 64)


@pytest.mark.parametrize("section,key,value", [
    ("process", "exit_code", 1), ("process", "status", "timeout"),
    ("process", "warnings", ["STRIDE failed"]), ("stride", "status", "error"),
    ("stride", "exit_code", 1), ("stride", "stdout", ""),
    ("stride", "stderr", "Error"), ("stride", "stdout_sha256", "0" * 64), ("stride", "residue_count", 75),
    ("stride", "assigned_positions", list(range(1, 76))),
    ("prediction", "nres", 75), ("prediction", "nres", True),
    ("prediction", "chopping", None), ("prediction", "chopping", ""),
    ("prediction", "chopping", "2-71,60-72"), ("prediction", "chopping", "0-71,72-73"),
    ("prediction", "chopping", "2-77,1-1"), ("prediction", "chopping", "102-170,171-175"),
    ("prediction", "chopping", "2-10A,12-58"), ("prediction", "chopping", "10-2,12-58"),
    ("prediction", "ndom", 0), ("prediction", "confidence", float("nan")),
    ("prediction", "confidence", 1.1), ("prediction", "time_sec", -1),
    ("prediction", "sequence_md5", "0" * 32), ("prediction", "chain_id", "wrong"),
    ("input", "chain_id", "B"), ("input", "model_id", "2"),
    ("input", "source_sha256", "0" * 64), ("input", "normalized_sha256", "0" * 64),
])
def test_fail_closed_external_result(section, key, value):
    prepared = prepare(); result = envelope(prepared); result[section][key] = value
    with pytest.raises(DomainAnnotationError):
        decode(prepared, result)


@pytest.mark.parametrize("key,value", [("tool_commit", "latest"), ("weights_sha256", "unknown"), ("renumber_pdbs", 1), ("stride", None)])
def test_required_pinned_envelope(key, value):
    prepared = prepare(); result = envelope(prepared); result[key] = value
    with pytest.raises(DomainAnnotationError):
        decode(prepared, result)


def test_stale_async_binding_and_strict_json():
    prepared = prepare(); text = json.dumps(envelope(prepared))
    with pytest.raises(DomainAnnotationError, match="Stale"):
        decode_domain_result(text, prepared, current_binding_sha256="new-input")
    for bad in ('{"schema": 1, "schema": 2}', '{"unused":1e999}', "[]", "[" * 2000):
        with pytest.raises(DomainAnnotationError):
            decode_domain_result(bad, prepared, current_binding_sha256=prepared.binding_sha256)


def test_cli_export_and_mock_external_result_process(tmp_path):
    """Real CLI subprocess + mock envelope, NOT native Chainsaw/STRIDE testing."""
    import subprocess
    import sys
    import zipfile
    from kuma_core.kuro.prediction_bundle import load_prediction_bundle

    model = "demo_unrelaxed_rank_001_alphafold2_ptm_model_1_seed_000.pdb"
    scores = "demo_scores_rank_001_alphafold2_ptm_model_1_seed_000.json"
    # Public coordinates under a synthetic producer wrapper; not a genuine producer ZIP.
    pdb = "\n".join(line[:60] + " 90.00" + line[66:] for line in PDB.read_text().splitlines() if line.startswith("ATOM  ")) + "\nEND\n"
    bundle = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr(model, pdb)
        archive.writestr(scores, json.dumps({"plddt": [90] * 76}))
        archive.writestr("demo.a3m", ">query\n" + SEQUENCE + "\n")
    reference = tmp_path / "reference.txt"; reference.write_text(SEQUENCE)
    script = Path(__file__).parents[1] / "scripts" / "domain_annotation_interchange.py"
    args = [sys.executable, str(script), "export", "--bundle", str(bundle), "--model", model,
            "--chain", "A", "--reference-file", str(reference)]
    output = tmp_path / "exported"
    run = subprocess.run(args + ["--output-directory", str(output)], text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["prediction_executed"] is False
    assert (output / "input.pdb").is_file()
    assert subprocess.run(args + ["--output-directory", str(output)], capture_output=True).returncode == 2
    context = load_prediction_bundle(bundle, model, "A", SEQUENCE)
    prepared = prepare_domain_input(context.structure_text, context.mapping.polymer, SEQUENCE,
                                    source_sha256=context.structure_sha256)
    result = tmp_path / "result.json"; result.write_text(json.dumps(envelope(prepared)))
    args[2] = "inspect"
    run = subprocess.run(args + ["--result", str(result)], text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["assigned_residues"] == 68
    bad = envelope(prepared); bad["stride"]["exit_code"] = 1
    result.write_text(json.dumps(bad))
    run = subprocess.run(args + ["--result", str(result)], text=True, capture_output=True)
    assert run.returncode == 2 and not run.stdout
    reference.write_text("G" + SEQUENCE)
    run = subprocess.run(args + ["--result", str(result)], text=True, capture_output=True)
    assert run.returncode == 2 and not run.stdout


@pytest.mark.parametrize("mutation", ["empty", "missing", "wrong_chain", "wrong_sequence", "nan"])
def test_captured_stride_assignments_are_checked(mutation):
    prepared = prepare(); result = envelope(prepared)
    stdout = result["stride"]["stdout"]
    if mutation == "empty":
        stdout = ""
    elif mutation == "missing":
        stdout = "\n".join(stdout.splitlines()[:-1])
    elif mutation == "wrong_chain":
        stdout = stdout.replace(" A ", " B ", 1)
    elif mutation == "wrong_sequence":
        stdout = stdout.replace("MET", "ALA", 1)
    else:
        stdout = stdout.replace("0.00", "nan", 1)
    result["stride"]["stdout"] = stdout; result["stride"]["stdout_sha256"] = digest(stdout)
    with pytest.raises(DomainAnnotationError):
        decode(prepared, result)


def test_external_wrapper_preserves_actual_subprocess_evidence(tmp_path):
    import sys
    from scripts.run_external_chainsaw import capture_stride

    prepared = prepare(); stdout = envelope(prepared)["stride"]["stdout"]
    fake = tmp_path / "mock_stride.py"
    fake.write_text("import sys\nsys.stdout.buffer.write(" + repr(stdout.encode("utf-8")) + ")\n")
    target = tmp_path / "ss.txt"
    # Python plus a controlled mock script acts as the executable+input process.
    evidence = capture_stride(Path(sys.executable), str(fake), "A", str(target), SEQUENCE)
    assert evidence["exit_code"] == 0
    assert evidence["stdout"] == stdout and target.read_text() == stdout
    assert evidence["assigned_positions"] == list(range(1, 77))
    assert evidence["executable_sha256"] == hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()


@pytest.mark.parametrize("body", ["raise SystemExit(7)", "print('')", "import sys; sys.stderr.write('STRIDE failed')", "import time; time.sleep(2)"])
def test_external_wrapper_refuses_failed_empty_or_timeout_process(tmp_path, body):
    import sys
    from scripts.run_external_chainsaw import capture_stride

    fake = tmp_path / "failed_stride.py"; fake.write_text(body)
    target = tmp_path / "ss.txt"
    with pytest.raises(DomainAnnotationError):
        capture_stride(Path(sys.executable), str(fake), "A", str(target), SEQUENCE, timeout=0.1)
    assert not target.exists()


def test_external_wrapper_refuses_changed_source_before_model_load(tmp_path):
    from scripts.run_external_chainsaw import verify_source

    (tmp_path / "get_predictions.py").write_text("# altered upstream\n")
    with pytest.raises(DomainAnnotationError, match="source/model mismatch"):
        verify_source(tmp_path)


def test_export_binding_cannot_be_changed_even_with_matching_output_claims():
    prepared = replace(prepare(), binding_sha256="0" * 64)
    with pytest.raises(DomainAnnotationError, match="binding"):
        decode(prepared, envelope(prepared))


def test_recorded_native_public_result_replays_against_original_atoms():
    """Integrity replay of a recorded Linux run, not new model inference in CI."""
    prepared = prepare(record=replace(polymer(), source="RCSB 1UBQ SEQRES; public full-polymer evidence",
                                      frame_id="public-1ubq-original"))
    path = Path(__file__).parents[1] / "docs" / "audit" / "domain-annotation-pilot-20261010" / "1ubq-external-result.json"
    result = decode_domain_result(path.read_text(), prepared, current_binding_sha256=prepared.binding_sha256)
    assert result.assigned_residues == 70 and result.total_residues == 76
    assert [(s.start, s.end) for s in result.domains[0].segments] == [(2, 71)]
    assert result.unassigned_positions == (1, 72, 73, 74, 75, 76)


@pytest.mark.parametrize("change", ["coordinate", "missing", "reordered", "model", "early_ter"])
def test_actual_stride_input_cannot_change_exported_atoms(change):
    prepared = prepare(); result = envelope(prepared)
    lines = prepared.normalized_pdb.splitlines()
    if change == "coordinate":
        lines[0] = lines[0][:30] + " 999.000" + lines[0][38:]
    elif change == "missing":
        lines.pop(0)
    elif change == "reordered":
        lines[0], lines[1] = lines[1], lines[0]
    elif change == "model":
        lines.insert(0, "MODEL        2")
    else:
        lines.insert(1, "TER")
    actual = "\n".join(lines) + "\n"
    result["stride"]["stride_input_pdb"] = actual
    result["stride"]["stride_input_sha256"] = digest(actual)
    with pytest.raises(DomainAnnotationError):
        decode(prepared, result)


def test_actual_stride_input_allows_only_cosmetic_terminator_rewrite():
    prepared = prepare(); result = envelope(prepared)
    actual = prepared.normalized_pdb.replace("TER\nEND\n", "TER                     77".ljust(80) + "\n" + "END".ljust(80) + "\n")
    result["stride"]["stride_input_pdb"] = actual
    result["stride"]["stride_input_sha256"] = digest(actual)
    assert decode(prepared, result).assigned_residues == 68
