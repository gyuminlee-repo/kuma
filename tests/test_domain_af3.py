"""Synthetic AF3 interchange contracts, not inference or accuracy evidence."""
from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from kuma_core.kuro.domain_af3 import prepare_af3_domain_input
from kuma_core.kuro.domain_annotation import DomainAnnotationError
from kuma_core.kuro.domain_merizo import (
    MERIZO_COMMIT, MERIZO_WEIGHTS_SHA256, decode_merizo_result, domain_input_manifest,
    expected_ca_coordinates, summarize_domain_selection,
)
from kuma_core.kuro.prediction_bundle import (
    PredictionBundleContext, PredictionBundleError, load_prediction_bundle,
)
from kuma_core.kuro.residue_mapping import ResidueId

MODEL = "fold_synthetic_model_0.cif"
DATA = "fold_synthetic_full_data_0.json"
SEQUENCE = "ACD"
LABEL = "label-AA"
AUTHOR = "author-protein"
ATOM_COLUMNS = (
    "group_PDB", "id", "type_symbol", "label_atom_id", "label_alt_id", "label_comp_id",
    "label_asym_id", "label_seq_id", "auth_asym_id", "auth_seq_id", "pdbx_PDB_ins_code",
    "Cartn_x", "Cartn_y", "Cartn_z", "occupancy", "B_iso_or_equiv", "pdbx_PDB_model_num",
    "auth_atom_id", "auth_comp_id", "label_entity_id", "pdbx_formal_charge",
)


def atoms(*, homomer: bool = False) -> list[dict[str, str]]:
    """All heavy atoms of ACD, artificial coordinates, explicit complete polymer."""
    result: list[dict[str, str]] = []
    for label in (LABEL, "label-BB") if homomer else (LABEL,):
        for pos, (name, number, insertion, sidechain) in enumerate((
            ("ALA", "-3", "?", ("CB",)), ("CYS", "110", ".", ("CB", "SG")),
            ("ASP", "110", "A", ("CB", "CG", "OD1", "OD2")),
        ), 1):
            for atom in ("N", "CA", "C", "O", *sidechain):
                serial = len(result) + 1
                result.append(dict(zip(ATOM_COLUMNS, (
                    "ATOM", str(serial), atom[0], atom, ".", name, label, str(pos),
                    AUTHOR, number, insertion, f"{pos * 2.123:.3f}", f"{serial * 1.111:.3f}",
                    f"{-pos * 3.234:.3f}", "1.00", "90.00", "7", atom, name, "1", "?",
                ), strict=True)))
    return result


def cif(rows: list[dict[str, str]], *, columns: tuple[str, ...] = ATOM_COLUMNS,
        homomer: bool = False) -> str:
    chains = f"{LABEL} 1\n" + ("label-BB 1\n" if homomer else "")
    header = ("data_synthetic\nloop_\n_struct_asym.id\n_struct_asym.entity_id\n" + chains
              + "#\nloop_\n_entity_poly_seq.entity_id\n_entity_poly_seq.num\n_entity_poly_seq.mon_id\n"
              + "1 1 ALA\n1 2 CYS\n1 3 ASP\n#\nloop_\n")
    return (header + "\n".join(f"_atom_site.{column}" for column in columns) + "\n"
            + "\n".join(" ".join(row[column] for column in columns) for row in rows) + "\n#\n")


def bundle(tmp_path: Path, rows: list[dict[str, str]] | None = None, *,
           text: str | None = None, homomer: bool = False, chain: str = LABEL,
           reference: str = SEQUENCE) -> PredictionBundleContext:
    rows = atoms(homomer=homomer) if rows is None else rows
    labels = (LABEL, "label-BB") if homomer else (LABEL,)
    scores = {"atom_chain_ids": [row["label_asym_id"] for row in rows],
              "atom_plddts": [float(row["B_iso_or_equiv"]) for row in rows],
              "token_chain_ids": [label for label in labels for _ in SEQUENCE],
              "token_res_ids": list(range(1, len(SEQUENCE) + 1)) * len(labels)}
    path = tmp_path / "synthetic-af3.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(MODEL, cif(rows, homomer=homomer) if text is None else text)
        archive.writestr(DATA, json.dumps(scores))
    return load_prediction_bundle(path, MODEL, chain, reference)


def result_envelope(prepared: Any) -> dict[str, Any]:
    return {"schema": "kuma-merizo-result-v1", "tool_commit": MERIZO_COMMIT,
            "weights_sha256": MERIZO_WEIGHTS_SHA256, "input": domain_input_manifest(prepared),
            "process": {"status": "ok", "exit_code": 0, "warnings": []},
            "features": {"nres": 3, "sequence": SEQUENCE, "residue_numbers": [1, 2, 3],
                         "ca_coordinates": [list(xyz) for xyz in expected_ca_coordinates(prepared)]},
            "prediction": {"nres": 3, "ndom": 1, "labels": [1, 0, 1],
                           "residue_numbers": [1, 2, 3], "confidence": 0.8, "time_sec": 1}}


def test_full_atom_fidelity_and_label_author_model_bijection(tmp_path: Path) -> None:
    original = atoms()
    context = bundle(tmp_path, original)
    prepared = prepare_af3_domain_input(context, SEQUENCE)
    prepared.check_consistency()
    assert context.structure_text == cif(original)  # No viewer trace or source mutation.
    assert prepared.source_sha256 == hashlib.sha256(cif(original).encode()).hexdigest()
    assert prepared.frame_id == f"prediction:{context.bundle_sha256}:{context.structure_sha256}:{MODEL}"
    assert prepared.model_id == "7" and prepared.chain_id == AUTHOR
    assert prepared.residues == (ResidueId("7", AUTHOR, -3), ResidueId("7", AUTHOR, 110),
                                 ResidueId("7", AUTHOR, 110, "A"))
    assert f'label_asym_id="{LABEL}"' in prepared.polymer_source
    normalized = prepared.normalized_pdb.splitlines()[:-2]
    assert len(normalized) == len(original) == 19
    for source, line in zip(original, normalized, strict=True):
        assert len(line) == 80 and line.startswith("ATOM  ")
        assert int(line[6:11]) == int(source["id"])
        assert line[12:16].strip() == source["label_atom_id"]
        assert line[17:20] == source["label_comp_id"]
        assert line[21:22] == "A" and int(line[22:26]) == int(source["label_seq_id"])
        assert line[26:27] == " " and line[76:78].strip() == source["type_symbol"]
        for column, start, end in (("Cartn_x", 30, 38), ("Cartn_y", 38, 46), ("Cartn_z", 46, 54),
                                    ("occupancy", 54, 60), ("B_iso_or_equiv", 60, 66)):
            assert Decimal(line[start:end]) == Decimal(source[column])
    manifest = domain_input_manifest(prepared)
    assert [(row["normalized_position"], row["reference_position"], row["polymer_position"],
             row["author_number"], row["insertion_code"]) for row in manifest["residues"]] == [
        (1, 1, 1, -3, ""), (2, 2, 2, 110, ""), (3, 3, 3, 110, "A")]


def test_homomer_selection_is_explicit_and_source_bound(tmp_path: Path) -> None:
    first = bundle(tmp_path, homomer=True)
    second = load_prediction_bundle(tmp_path / "synthetic-af3.zip", MODEL, "label-BB", SEQUENCE)
    a = prepare_af3_domain_input(first, SEQUENCE)
    b = prepare_af3_domain_input(second, SEQUENCE)
    assert a.source_sha256 == b.source_sha256 and a.residues == b.residues
    assert a.binding_sha256 != b.binding_sha256 and a.polymer_source != b.polymer_source
    assert len(a.normalized_pdb.splitlines()) == len(b.normalized_pdb.splitlines()) == 21
    assert expected_ca_coordinates(a) != expected_ca_coordinates(b)
    for chain in ("", AUTHOR, "missing"):
        with pytest.raises(PredictionBundleError, match="chain"):
            load_prediction_bundle(tmp_path / "synthetic-af3.zip", MODEL, chain, SEQUENCE)
    with pytest.raises(DomainAnnotationError, match="label-chain"):
        prepare_af3_domain_input(replace(first, chain_id="label-BB"), SEQUENCE)
    with pytest.raises(DomainAnnotationError, match="input mismatch"):
        decode_merizo_result(json.dumps(result_envelope(a)), b, current_binding_sha256=b.binding_sha256)


@pytest.mark.parametrize("change", ["bundle", "member", "hash", "text", "frame", "polymer_source", "label",
                                    "author", "model", "mapping_coordinate", "mapping_position", "mapping_type",
                                    "mapping_count", "sequence_member", "sequence_hash", "format"])
def test_stale_context_identity_is_rejected(tmp_path: Path, change: str) -> None:
    context = bundle(tmp_path)
    polymer = context.mapping.polymer
    if change == "bundle":
        context = replace(context, bundle_sha256="0" * 64)
    elif change == "member":
        context = replace(context, model_id="fold_synthetic_model_1.cif")
    elif change == "hash":
        context = replace(context, structure_sha256="0" * 64)
    elif change == "text":
        context = replace(context, structure_text=context.structure_text + "# stale\n")
    elif change in {"frame", "polymer_source", "label"}:
        field = {"frame": "frame_id", "polymer_source": "source", "label": "label_chain_id"}[change]
        context = replace(context, mapping=replace(context.mapping, polymer=replace(polymer, **{field: "stale"})))
    elif change in {"author", "model"}:
        field = "chain_id" if change == "author" else "model_id"
        changed = replace(polymer, **{field: "stale"}, residues_by_position=tuple(
            replace(residue, **{field: "stale"}) for residue in polymer.residues_by_position if residue is not None))
        context = replace(context, mapping=replace(context.mapping, polymer=changed))
    elif change.startswith("mapping_"):
        entries = context.mapping.residues
        if change == "mapping_count":
            entries = entries[:-1]
        else:
            values: dict[str, Any] = ({"coordinate": (0., 0., 0.)} if change == "mapping_coordinate"
                                      else {"polymer_position": True if change == "mapping_type" else 2})
            entries = (replace(entries[0], **values), *entries[1:])
        context = replace(context, mapping=replace(context.mapping, residues=entries))
    elif change == "sequence_member":
        context = replace(context, sequence_member="unexpected.a3m")
    elif change == "sequence_hash":
        context = replace(context, sequence_sha256="0" * 64)
    else:
        context = replace(context, structure_format="pdb")
    with pytest.raises(DomainAnnotationError):
        prepare_af3_domain_input(context, SEQUENCE)


@pytest.mark.parametrize("column,value", [
    ("Cartn_x", "1.2345"), ("Cartn_y", "-1000.000"), ("Cartn_z", "10000.000"),
    ("occupancy", "0.999"), ("occupancy", "NaN"), ("occupancy", "1e999999999"),
    ("occupancy", "-0.01"), ("occupancy", "1.01"),
    ("B_iso_or_equiv", "90.001"),
    ("type_symbol", "Ca"), ("type_symbol", "C"), ("label_atom_id", "TOOLONG"),
    ("auth_atom_id", "C1"), ("auth_comp_id", "CYS"), ("label_entity_id", "other"),
    ("pdbx_formal_charge", "10"), ("id", "100000"), ("id", "0"), ("id", "2"),
])
def test_importable_but_nonrepresentable_atom_is_refused(tmp_path: Path, column: str, value: str) -> None:
    rows = atoms()
    rows[0][column] = value
    # These fields do not alter the existing importer's CA identity/confidence gate.
    context = bundle(tmp_path, rows)
    with pytest.raises(DomainAnnotationError):
        prepare_af3_domain_input(context, SEQUENCE)


@pytest.mark.parametrize("column", ["type_symbol", "occupancy", "id"])
def test_missing_fidelity_evidence_is_not_invented(tmp_path: Path, column: str) -> None:
    rows = atoms()
    context = bundle(tmp_path, rows, text=cif(rows, columns=tuple(c for c in ATOM_COLUMNS if c != column)))
    with pytest.raises(DomainAnnotationError, match="columns"):
        prepare_af3_domain_input(context, SEQUENCE)


@pytest.mark.parametrize("model", ["?", ".", "0", "-1", "arbitrary"])
def test_missing_or_invalid_coordinate_model_identity_is_refused(tmp_path: Path, model: str) -> None:
    rows = atoms()
    for row in rows:
        row["pdbx_PDB_model_num"] = model
    context = bundle(tmp_path, rows)
    with pytest.raises(DomainAnnotationError, match="coordinate model"):
        prepare_af3_domain_input(context, SEQUENCE)


@pytest.mark.parametrize("change", ["ca_only", "missing_o", "missing_residue", "reordered", "interleaved"])
def test_incomplete_or_nonbijective_selected_atoms_are_refused(tmp_path: Path, change: str) -> None:
    rows = atoms()
    if change == "ca_only":
        rows = [row for row in rows if row["label_atom_id"] == "CA"]
    elif change == "missing_o":
        rows = [row for row in rows if row["label_atom_id"] != "O"]
    elif change == "missing_residue":
        rows = [row for row in rows if row["label_seq_id"] != "2"]
    elif change == "reordered":
        rows = rows[5:] + rows[:5]
    else:
        rows.append(rows.pop(0))
    context = bundle(tmp_path, rows)
    with pytest.raises(DomainAnnotationError):
        prepare_af3_domain_input(context, SEQUENCE)


@pytest.mark.parametrize("change", ["alternate", "modified", "ligand", "nonprotein_entity", "duplicate_atom",
                                    "model", "author_ambiguity", "polymer_identity", "missing_polymer"])
def test_importer_still_refuses_unsupported_mixed_or_ambiguous_sources(tmp_path: Path, change: str) -> None:
    rows = atoms()
    if change == "alternate":
        rows[0]["label_alt_id"] = "A"
    elif change == "modified":
        rows[0]["label_comp_id"] = "MSE"
    elif change == "ligand":
        rows[0]["group_PDB"] = "HETATM"
    elif change == "duplicate_atom":
        rows.append(dict(rows[0]))
    elif change == "model":
        rows[0]["pdbx_PDB_model_num"] = "8"
    elif change == "author_ambiguity":
        rows[0]["auth_seq_id"] = "9"
    text = cif(rows)
    if change == "nonprotein_entity":
        text = text.replace(f"{LABEL} 1\n", f"{LABEL} 1\nligand-X 2\n")
    elif change == "polymer_identity":
        text = text.replace("1 2 CYS\n", "1 2 ALA\n")
    elif change == "missing_polymer":
        text = text.replace("1 2 CYS\n", "")
    with pytest.raises(PredictionBundleError):
        bundle(tmp_path, rows, text=text)


def test_exact_numeric_spelling_charge_hydrogens_and_terminal_atom_preserved(tmp_path: Path) -> None:
    rows = atoms()
    rows[0].update(Cartn_x="2.123000", occupancy="1", B_iso_or_equiv="9e1", pdbx_formal_charge="1")
    for atom, element, charge in (("OXT", "O", "-1"), ("1HD2", "H", "0")):
        rows.append({**rows[-1], "id": str(len(rows) + 1), "label_atom_id": atom,
                     "auth_atom_id": atom, "type_symbol": element, "pdbx_formal_charge": charge})
    prepared = prepare_af3_domain_input(bundle(tmp_path, rows), SEQUENCE)
    lines = prepared.normalized_pdb.splitlines()
    assert lines[0][78:80] == "1+" and lines[-4][78:80] == "1-"
    assert lines[-3][12:16] == "1HD2" and len(lines[:-2]) == len(rows)


def test_complete_reference_required_and_selection_remains_unchanged(tmp_path: Path) -> None:
    context = bundle(tmp_path)
    for reference in ("AC", "XACD", "ACDC", "CCD"):
        with pytest.raises(DomainAnnotationError):
            prepare_af3_domain_input(context, reference)
    fragment = bundle(tmp_path, reference="AC")
    with pytest.raises(DomainAnnotationError, match="reference"):
        prepare_af3_domain_input(fragment, "AC")
    prepared = prepare_af3_domain_input(context, SEQUENCE)
    annotation = decode_merizo_result(json.dumps(result_envelope(prepared)), prepared,
                                      current_binding_sha256=prepared.binding_sha256)
    selected = ["D3A", "A1V", "A1G", "C2A"]
    before = copy.deepcopy(selected)
    summary = summarize_domain_selection(annotation, prepared, selected,
                                         current_binding_sha256=prepared.binding_sha256)
    assert selected == before == summary["selected_variants"]
    assert summary["selected_variant_count"] == 4 and summary["selected_site_count"] == 3
    assert [row["domain_index"] for row in summary["memberships"]] == [1, 1, 1, None]
    assert annotation.domains[0].source_residues == (prepared.residues[0], prepared.residues[2])


@pytest.mark.parametrize("suffix", ["_atom_site.id 99\n", "data_second\n_other.value 1\n",
                                    "_atom_site_anisotrop.id 1\n"])
def test_duplicate_data_blocks_and_unpreserved_anisotropy_are_refused(tmp_path: Path, suffix: str) -> None:
    context = bundle(tmp_path)
    changed_text = context.structure_text + suffix
    changed_hash = hashlib.sha256(changed_text.encode()).hexdigest()
    frame = f"prediction:{context.bundle_sha256}:{changed_hash}:{MODEL}"
    polymer = replace(context.mapping.polymer, frame_id=frame, source=f"{MODEL}; sha256={changed_hash}")
    changed = replace(context, structure_text=changed_text, structure_sha256=changed_hash,
                      mapping=replace(context.mapping, polymer=polymer))
    with pytest.raises(DomainAnnotationError):
        prepare_af3_domain_input(changed, SEQUENCE)
