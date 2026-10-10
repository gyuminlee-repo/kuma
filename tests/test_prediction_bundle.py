"""Synthetic offline prediction bundles; no third-party structures redistributed."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
import zipfile
from pathlib import Path
from types import SimpleNamespace
from collections.abc import Mapping

import pytest

from kuma_core.kuro.prediction_bundle import (
    PredictionBundleError, inspect_prediction_bundle, load_prediction_bundle,
)
from kuma_core.kuro.residue_mapping import ResidueId

AF_MODEL = "fold_demo_model_0.cif"
AF_DATA = "fold_demo_full_data_0.json"
CF_TAG = "rank_001_alphafold2_ptm_model_1_seed_000"
CF_MODEL = f"demo_unrelaxed_{CF_TAG}.pdb"
CF_DATA = f"demo_scores_{CF_TAG}.json"
CF_A3M = "#2,1\t1,1\n>query\nACW\n"


def cif() -> str:
    return """data_synthetic
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
B 2
#
loop_
_entity_poly_seq.entity_id
_entity_poly_seq.num
_entity_poly_seq.mon_id
1 1 ALA
1 2 CYS
1 3 ASP
2 1 TRP
#
loop_
_atom_site.group_PDB
_atom_site.id
_atom_site.label_asym_id
_atom_site.pdbx_PDB_model_num
_atom_site.label_seq_id
_atom_site.auth_asym_id
_atom_site.auth_seq_id
_atom_site.pdbx_PDB_ins_code
_atom_site.label_comp_id
_atom_site.label_atom_id
_atom_site.label_alt_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.B_iso_or_equiv
ATOM 1 A 1 1 author-A -3 ? ALA N . 0 0 0 50
ATOM 2 A 1 1 author-A -3 ? ALA CA . 1 0 0 90
ATOM 3 A 1 3 author-A 10 A ASP CA . 3 0 0 70
ATOM 4 B 1 1 author-B 8 ? TRP CA . 4 0 0 80
#
loop_
_pdbx_poly_seq_scheme.asym_id
_pdbx_poly_seq_scheme.seq_id
_pdbx_poly_seq_scheme.pdb_seq_num
_pdbx_poly_seq_scheme.pdb_strand_id
_pdbx_poly_seq_scheme.pdb_ins_code
A 1 -3 author-A .
A 2 10 author-A .
A 3 10 author-A A
B 1 8 author-B .
#
"""


def af_data() -> dict:
    return {"atom_chain_ids": ["A", "A", "A", "B"],
            "atom_plddts": [50, 90, 70, 80],
            "token_chain_ids": ["A", "A", "A", "B"],
            "token_res_ids": [1, 2, 3, 1],
            "pae": [[0, 1, 2, 3], [4, 0, 5, 6], [7, 8, 0, 9], [10, 11, 12, 0]]}


def pdb() -> str:
    lines = []
    for i, (chain, number, name, confidence) in enumerate(
        [("A", 1, "ALA", 90), ("A", 2, "CYS", 20), ("B", 203, "TRP", 80)], 1
    ):
        lines.append(f"ATOM  {i:5d}  CA  {name} {chain}{number:4d}    "
                     f"{float(i):8.3f}{0.:8.3f}{0.:8.3f}{1.:6.2f}{confidence:6.2f}           C  ")
    return "MODEL        1\n" + "\n".join(lines) + "\nTER\nENDMDL\nEND\n"


def cf_data() -> dict:
    return {"plddt": [90, 20, 80], "pae": [[0, 1, 2], [3, 0, 4], [5, 6, 0]]}


def bundle(tmp_path: Path, members: Mapping[str, object] | None = None) -> Path:
    path = tmp_path / "predictions.zip"
    members = members if members is not None else {AF_MODEL: cif(), AF_DATA: af_data()}
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, json.dumps(value) if isinstance(value, dict) else str(value))
    return path


def ranked_members(
    kind: str, index: str, *, job: str = "demo", directory: str = "",
) -> tuple[str, dict[str, object]]:
    prefix = f"{directory}/" if directory else ""
    if kind == "af3":
        model = f"{prefix}fold_{job}_model_{index}.cif"
        return model, {model: cif(), f"{prefix}fold_{job}_full_data_{index}.json": af_data()}
    tag = f"rank_{index}_alphafold2_ptm_model_1_seed_000"
    model = f"{prefix}{job}_unrelaxed_{tag}.pdb"
    return model, {model: pdb(), f"{prefix}{job}_scores_{tag}.json": cf_data(),
                   f"{prefix}{job}.a3m": CF_A3M}


def test_af3_inspection_explicit_models_chains_and_hash(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    result = inspect_prediction_bundle(path)
    assert result.format == "af3_server"
    assert result.bundle_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.models[0].model_id == AF_MODEL
    assert result.models[0].producer_rank == 1
    assert result.recommended_model_id == AF_MODEL
    assert result.recommendation_reason == "producer_rank"
    assert [(c.chain_id, c.author_chain_id, c.sequence, c.length)
            for c in result.models[0].chains] == [("A", "author-A", "ACD", 3), ("B", "author-B", "W", 1)]


def test_af3_full_polymer_missing_ca_identity_direction_and_provenance(tmp_path: Path) -> None:
    path = bundle(tmp_path, {AF_MODEL: cif(), AF_DATA: af_data(), "terms_of_use.md": "Keep source notice"})
    result = load_prediction_bundle(path, AF_MODEL, "A", "ACD")
    assert result.mapping.method == "exact"
    assert [r.residue_id for r in result.mapping.residues] == [
        ResidueId("1", "author-A", -3), ResidueId("1", "author-A", 10), ResidueId("1", "author-A", 10, "A")]
    assert [r.coordinate for r in result.mapping.residues] == [(1., 0., 0.), None, (3., 0., 0.)]
    assert result.plddt.values == (90., None, 70.)  # CA-specific, not atom array indexed as residues.
    assert "CA" in result.plddt.provenance.source
    assert result.pae is not None
    assert result.pae.values == ((0., 1., 2.), (4., 0., 5.), (7., 8., 0.))
    assert result.structure_text == cif()
    assert result.structure_sha256 == hashlib.sha256(cif().encode()).hexdigest()
    assert result.confidence_sha256 == hashlib.sha256(json.dumps(af_data()).encode()).hexdigest()
    assert result.notices[0].text == "Keep source notice"
    assert any(link.url == "https://alphafoldserver.com/output-terms" for link in result.source_terms)


def test_model_index_pairing_and_explicit_selection(tmp_path: Path) -> None:
    other = cif().replace("1 0 0 90", "9 0 0 90")
    path = bundle(tmp_path, {AF_MODEL: cif(), AF_DATA: af_data(),
                            "fold_demo_model_1.cif": other, "fold_demo_full_data_1.json": af_data()})
    result = load_prediction_bundle(path, "fold_demo_model_1.cif", "A", "ACD")
    assert result.mapping.residues[0].coordinate == (9., 0., 0.)
    with pytest.raises(PredictionBundleError, match="model"):
        load_prediction_bundle(path, "", "A", "ACD")
    with pytest.raises(PredictionBundleError, match="chain"):
        load_prediction_bundle(path, AF_MODEL, "", "ACD")


def test_colabfold_scores_use_residue_encounter_order_and_exact_tag(tmp_path: Path) -> None:
    path = bundle(tmp_path, {CF_MODEL: pdb(), CF_DATA: cf_data(), "demo.a3m": CF_A3M})
    result = load_prediction_bundle(path, CF_MODEL, "B", "W")
    assert result.format == "colabfold"
    assert result.mapping.residues[0].residue_id == ResidueId("1", "B", 203)
    assert result.plddt.values == (80.,)
    assert result.pae is not None and result.pae.values == ((0.,),)
    assert result.structure_format == "pdb"


def test_colabfold_relaxed_and_unrelaxed_are_distinct_models(tmp_path: Path) -> None:
    relaxed = CF_MODEL.replace("_unrelaxed_", "_relaxed_")
    path = bundle(tmp_path, {CF_MODEL: pdb(), relaxed: pdb(), CF_DATA: cf_data(), "demo.a3m": CF_A3M})
    inventory = inspect_prediction_bundle(path)
    assert {m.model_id for m in inventory.models} == {CF_MODEL, relaxed}
    assert [m.producer_rank for m in inventory.models] == [1, 1]
    assert inventory.recommended_model_id is None
    assert inventory.recommendation_reason == "ambiguous_ranking"


@pytest.mark.parametrize("kind", ["af3", "colabfold"])
@pytest.mark.parametrize("reverse_archive_order", [False, True])
def test_recommendation_uses_producer_rank_not_confidence_or_archive_order(
    tmp_path: Path, kind: str, reverse_archive_order: bool,
) -> None:
    top, members = ranked_members(kind, "0" if kind == "af3" else "001")
    _, lower = ranked_members(kind, "1" if kind == "af3" else "002")
    # The top producer rank deliberately has worse local pLDDT; do not rerank it.
    if kind == "af3":
        data = af_data()
        data["atom_plddts"][1] = 10
        members[AF_DATA] = data
        members[top] = cif().replace("1 0 0 90", "1 0 0 10")
    else:
        data = cf_data()
        data["plddt"][0] = 10
        members[CF_DATA] = data
        members[top] = pdb().replace(" 90.00", " 10.00")
        # A lower relaxed model sorts before the top unrelaxed model by name.
        lower = {name.replace("_unrelaxed_", "_relaxed_"): value
                 for name, value in lower.items()}
    members.update(lower)
    if reverse_archive_order:
        members = dict(reversed(list(members.items())))
    inventory = inspect_prediction_bundle(bundle(tmp_path, members))
    assert inventory.recommended_model_id == top
    assert inventory.recommendation_reason == "producer_rank"
    assert {m.producer_rank for m in inventory.models} == {1, 2}
    if kind == "colabfold":
        assert inventory.models[0].model_id != top


@pytest.mark.parametrize("kind", ["af3", "colabfold"])
@pytest.mark.parametrize("multiple_models", [False, True])
def test_missing_top_rank_never_defaults_to_first_or_best_available(
    tmp_path: Path, kind: str, multiple_models: bool,
) -> None:
    _, members = ranked_members(kind, "1" if kind == "af3" else "002")
    if multiple_models:
        _, more = ranked_members(kind, "2" if kind == "af3" else "003")
        members.update(more)
    inventory = inspect_prediction_bundle(bundle(tmp_path, members))
    assert inventory.models[0].producer_rank == 2
    assert inventory.recommended_model_id is None
    assert inventory.recommendation_reason == "missing_top_rank"


@pytest.mark.parametrize("kind", ["af3", "colabfold"])
@pytest.mark.parametrize("different_directory", [False, True])
@pytest.mark.parametrize("second_top", [False, True])
def test_separate_producer_job_scopes_never_share_a_recommendation(
    tmp_path: Path, kind: str, different_directory: bool, second_top: bool,
) -> None:
    top_index = "0" if kind == "af3" else "001"
    lower_index = "1" if kind == "af3" else "002"
    _, members = ranked_members(kind, top_index)
    _, other = ranked_members(kind, top_index if second_top else lower_index,
                              job="demo" if different_directory else "other",
                              directory="other" if different_directory else "")
    inventory = inspect_prediction_bundle(bundle(tmp_path, {**members, **other}))
    assert inventory.recommended_model_id is None
    assert inventory.recommendation_reason == "ambiguous_ranking"


def test_duplicate_af3_coordinate_variants_are_ambiguous(tmp_path: Path) -> None:
    inventory = inspect_prediction_bundle(bundle(tmp_path, {
        AF_MODEL: cif(), AF_MODEL.replace(".cif", ".mmcif"): cif(), AF_DATA: af_data(),
    }))
    assert [m.producer_rank for m in inventory.models] == [1, 1]
    assert inventory.recommended_model_id is None
    assert inventory.recommendation_reason == "ambiguous_ranking"


def test_duplicate_lower_rank_also_blocks_colabfold_recommendation(tmp_path: Path) -> None:
    _, members = ranked_members("colabfold", "001")
    lower, more = ranked_members("colabfold", "002")
    members.update(more)
    members[lower.replace("_unrelaxed_", "_relaxed_")] = pdb()
    inventory = inspect_prediction_bundle(bundle(tmp_path, members))
    assert sorted(m.producer_rank for m in inventory.models if m.producer_rank is not None) == [1, 2, 2]
    assert inventory.recommended_model_id is None
    assert inventory.recommendation_reason == "ambiguous_ranking"


@pytest.mark.parametrize("kind,index,expected", [
    ("af3", "0", 1), ("af3", "1", 2), ("af3", "2", 3), ("af3", "3", 4), ("af3", "4", 5),
    ("colabfold", "001", 1), ("colabfold", "1234", 1234),
    ("colabfold", "9007199254740991", 9007199254740991),
])
def test_documented_rank_values_are_one_based(tmp_path: Path, kind: str, index: str, expected: int) -> None:
    model, members = ranked_members(kind, index)
    inventory = inspect_prediction_bundle(bundle(tmp_path, members))
    assert inventory.models[0].producer_rank == expected
    assert inventory.recommended_model_id == (model if expected == 1 else None)


def test_noncanonical_af3_filename_cannot_supply_a_top_rank(tmp_path: Path) -> None:
    # The existing importer accepts this paired alias, but the documented
    # producer filename separates a nonempty job prefix with an underscore.
    model = AF_MODEL.replace("_model_", "model_")
    inventory = inspect_prediction_bundle(bundle(tmp_path, {model: cif(), AF_DATA: af_data()}))
    assert inventory.models[0].producer_rank is None
    assert inventory.recommended_model_id is None
    assert inventory.recommendation_reason == "ambiguous_ranking"


@pytest.mark.parametrize("kind,index", [
    ("af3", "5"), ("af3", "00"), ("af3", "٠"),
    ("colabfold", "000"), ("colabfold", "0001"), ("colabfold", "٠٠١"),
    ("colabfold", "9007199254740992"), ("colabfold", "9" * 17),
])
def test_unrecognized_rank_is_unknown_and_cannot_enable_a_default(
    tmp_path: Path, kind: str, index: str,
) -> None:
    unknown, members = ranked_members(kind, index)
    _, top = ranked_members(kind, "0" if kind == "af3" else "001")
    path = bundle(tmp_path, {**members, **top})
    inventory = inspect_prediction_bundle(path)
    assert next(m for m in inventory.models if m.model_id == unknown).producer_rank is None
    assert inventory.recommended_model_id is None
    assert inventory.recommendation_reason == "ambiguous_ranking"
    # Ranking metadata does not remove previously supported explicit selections.
    assert load_prediction_bundle(path, unknown, "A", "ACD" if kind == "af3" else "AC")


@pytest.mark.parametrize("kind", ["af3", "colabfold"])
@pytest.mark.parametrize("bad_rank", ["top", "lower"])
@pytest.mark.parametrize("failure", ["missing_pair", "malformed_model", "malformed_confidence"])
def test_recommendation_never_skips_invalid_top_or_other_models(
    tmp_path: Path, kind: str, bad_rank: str, failure: str,
) -> None:
    top, members = ranked_members(kind, "0" if kind == "af3" else "001")
    lower, lower_members = ranked_members(kind, "1" if kind == "af3" else "002")
    members.update(lower_members)
    target = top if bad_rank == "top" else lower
    confidence = target.replace("_model_", "_full_data_").replace(".cif", ".json") if kind == "af3" else (
        target.replace("_unrelaxed_", "_scores_").replace(".pdb", ".json"))
    if failure == "missing_pair":
        del members[confidence]
    elif failure == "malformed_model":
        members[target] = "malformed structure"
    else:
        members[confidence] = {"plddt": [], "atom_plddts": []}
    with pytest.raises(PredictionBundleError):
        inspect_prediction_bundle(bundle(tmp_path, members))


@pytest.mark.parametrize("prefix", ["", "nested/"])
def test_unprefixed_af3_top_rank_preserves_exact_model_id(tmp_path: Path, prefix: str) -> None:
    model = f"{prefix}model_0.cif"
    inventory = inspect_prediction_bundle(bundle(tmp_path, {
        model: cif(), f"{prefix}full_data_0.json": af_data(),
    }))
    assert inventory.recommended_model_id == model
    assert inventory.models[0].producer_rank == 1


def test_exact_terminal_tag_is_supported_but_substitution_fails(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    result = load_prediction_bundle(path, AF_MODEL, "A", "HACDH")
    assert [r.polymer_position for r in result.mapping.residues] == [None, 1, 2, 3, None]
    with pytest.raises(PredictionBundleError, match="exact|opt-in"):
        load_prediction_bundle(path, AF_MODEL, "A", "ACE")


def test_hash_change_is_rejected(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    with pytest.raises(PredictionBundleError, match="changed|hash"):
        load_prediction_bundle(path, AF_MODEL, "A", "ACD", expected_bundle_sha256="0" * 64)


@pytest.mark.parametrize("kind", ["af3", "colabfold"])
def test_missing_pae_is_explicit_unknown(tmp_path: Path, kind: str) -> None:
    data = af_data() if kind == "af3" else cf_data()
    del data["pae"]
    model, confidence, text = (AF_MODEL, AF_DATA, cif()) if kind == "af3" else (CF_MODEL, CF_DATA, pdb())
    members: dict[str, object] = {model: text, confidence: data}
    if kind == "colabfold": members["demo.a3m"] = CF_A3M
    path = bundle(tmp_path, members)
    result = load_prediction_bundle(path, model, "A", "ACD" if kind == "af3" else "AC")
    assert result.pae is None
    assert any("PAE" in warning for warning in result.warnings)


@pytest.mark.parametrize("bad", [None, [], [[0]], [[0, 1, 2, 3]] * 3,
                                  [[0, -1, 2, 3]] * 4, [[0, True, 2, 3]] * 4,
                                  [[0, float("nan"), 2, 3]] * 4])
def test_provided_invalid_pae_is_never_silently_discarded(tmp_path: Path, bad: object) -> None:
    data = af_data()
    data["pae"] = bad
    with pytest.raises(PredictionBundleError):
        inspect_prediction_bundle(bundle(tmp_path, {AF_MODEL: cif(), AF_DATA: data}))


@pytest.mark.parametrize("change", ["wrong_token", "duplicate_token", "wrong_atom_order", "wrong_atom_count", "wrong_bfactor", "nonfinite", "too_high", "multiple_models", "unknown_monomer"])
def test_af3_malformed_confidence_and_identity_fail_closed(tmp_path: Path, change: str) -> None:
    data = af_data()
    text = cif()
    if change == "wrong_token": data["token_res_ids"][1] = 20
    elif change == "duplicate_token": data["token_res_ids"][1] = 1
    elif change == "wrong_atom_order": data["atom_chain_ids"] = ["B", "A", "A", "A"]
    elif change == "wrong_atom_count": data["atom_plddts"].pop()
    elif change == "wrong_bfactor": data["atom_plddts"][1] = 91
    elif change == "nonfinite": data["atom_plddts"][1] = float("inf")
    elif change == "too_high": data["atom_plddts"][1] = 101
    elif change == "multiple_models": text = text.replace("ATOM 4 B 1", "ATOM 4 B 2")
    else: text = text.replace("CYS", "UNK")
    with pytest.raises(PredictionBundleError):
        inspect_prediction_bundle(bundle(tmp_path, {AF_MODEL: text, AF_DATA: data}))


@pytest.mark.parametrize("change", ["missing_residue", "duplicate_ca", "alternate", "unknown", "wrong_score", "extra_model"])
def test_colabfold_incomplete_or_ambiguous_pdb_rejects(tmp_path: Path, change: str) -> None:
    text = pdb()
    if change == "missing_residue": text = "\n".join(line for line in text.splitlines() if "CYS" not in line)
    elif change == "duplicate_ca": text = text.replace("TER", text.splitlines()[1] + "\nTER")
    elif change == "alternate": text = text.replace(" CA  ALA", " CA AALA")
    elif change == "unknown": text = text.replace("ALA", "UNK")
    elif change == "wrong_score": text = text.replace(" 90.00", " 91.00")
    else: text += pdb().replace("MODEL        1", "MODEL        2")
    with pytest.raises(PredictionBundleError):
        inspect_prediction_bundle(bundle(tmp_path, {CF_MODEL: text, CF_DATA: cf_data(), "demo.a3m": CF_A3M}))


@pytest.mark.parametrize("name", ["../evil", "/evil", "C:/evil", "a\\evil", "a/../evil", "a//evil", "a/./evil"])
@pytest.mark.parametrize("separator", ["/", "\\"])
def test_unsafe_paths_fail_even_when_not_selected(
    tmp_path: Path, name: str, separator: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exercise Windows normalization even on POSIX CI without changing os
    # globally for pathlib, pytest, or the production importer.
    monkeypatch.setattr(zipfile, "os", SimpleNamespace(**{**vars(os), "sep": separator}))
    path = bundle(tmp_path)
    with zipfile.ZipFile(path, "a") as archive:
        info = zipfile.ZipInfo(name)
        # ZipInfo normalizes backslashes on Windows. Restore the adversarial
        # filename so the serialized archive really contains the unsafe path.
        info.filename = name
        archive.writestr(info, "bad")
    with zipfile.ZipFile(path) as archive:
        assert archive.infolist()[-1].orig_filename == name
    with pytest.raises(PredictionBundleError, match="path"):
        inspect_prediction_bundle(path)


def test_casefold_duplicate_members_reject(tmp_path: Path) -> None:
    with pytest.raises(PredictionBundleError, match="duplicate|Duplicate"):
        inspect_prediction_bundle(bundle(tmp_path, {AF_MODEL: cif(), AF_MODEL.upper(): cif(), AF_DATA: af_data()}))


def test_symlink_zip_member_rejects(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    with zipfile.ZipFile(path, "a") as archive:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target")
    with pytest.raises(PredictionBundleError, match="symlink|regular"):
        inspect_prediction_bundle(path)


def test_encrypted_zip_metadata_rejects(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    raw = bytearray(path.read_bytes())
    for magic, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        pos = raw.index(magic)
        bits = struct.unpack_from("<H", raw, pos + offset)[0]
        struct.pack_into("<H", raw, pos + offset, bits | 1)
    path.write_bytes(raw)
    with pytest.raises(PredictionBundleError, match="Encrypted"):
        inspect_prediction_bundle(path)


@pytest.mark.parametrize("payload", ['{"atom_plddts": [], "atom_plddts": []}',
                                      '{"x": NaN}', '{"x": 1e999}', '[' * 100 + '0' + ']' * 100])
def test_malicious_json_is_rejected(tmp_path: Path, payload: str) -> None:
    with pytest.raises(PredictionBundleError):
        inspect_prediction_bundle(bundle(tmp_path, {AF_MODEL: cif(), AF_DATA: payload}))


def test_archive_bomb_size_and_member_count_are_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import kuma_core.kuro.prediction_bundle as module
    path = bundle(tmp_path)
    monkeypatch.setattr(module, "MAX_MEMBERS", 1)
    with pytest.raises(PredictionBundleError, match="member"):
        inspect_prediction_bundle(path)
    monkeypatch.setattr(module, "MAX_MEMBERS", 256)
    monkeypatch.setattr(module, "MAX_MEMBER_BYTES", 5)
    with pytest.raises(PredictionBundleError, match="size|limit"):
        inspect_prediction_bundle(path)


def test_mixed_or_unpaired_models_fail_not_pick_best(tmp_path: Path) -> None:
    for members in ({AF_MODEL: cif()}, {CF_MODEL: pdb()},
                    {AF_MODEL: cif(), AF_DATA: af_data(), CF_MODEL: pdb(), CF_DATA: cf_data(), "demo.a3m": CF_A3M}):
        with pytest.raises(PredictionBundleError):
            inspect_prediction_bundle(bundle(tmp_path, members))


def test_colabfold_requires_independent_complete_query(tmp_path: Path) -> None:
    for a3m in (None, ">query\nA-W\n", "#2,1\t1,1\n>query\nAC-\n", "#2,1\t1,1\n>query\nAC\n",
                "#2,1\t1,1\n>query\nAGW\n", "#2,1\t0,1\n>query\nACW\n"):
        members: dict[str, object] = {CF_MODEL: pdb(), CF_DATA: cf_data()}
        if a3m is not None:
            members["demo.a3m"] = a3m
        with pytest.raises(PredictionBundleError):
            inspect_prediction_bundle(bundle(tmp_path, members))


def test_colabfold_plain_monomer_query_and_four_digit_seed(tmp_path: Path) -> None:
    model = CF_MODEL.replace("seed_000", "seed_2024")
    confidence = CF_DATA.replace("seed_000", "seed_2024")
    text = "\n".join(line for line in pdb().splitlines() if "TRP" not in line)
    path = bundle(tmp_path, {model: text, confidence: {"plddt": [90, 20]}, "demo.a3m": ">query\nAC\n"})
    context = load_prediction_bundle(path, model, "A", "AC")
    assert context.mapping.polymer.sequence == "AC"
    assert context.sequence_member == "demo.a3m"
    assert context.sequence_sha256 == hashlib.sha256(b">query\nAC\n").hexdigest()
    assert context.pae is None


def test_colabfold_copies_expand_in_declared_unique_chain_order(tmp_path: Path) -> None:
    original = pdb().splitlines()
    a_rows = [line for line in original if "ALA" in line or "CYS" in line]
    copied = [line[:21] + "B" + line[22:] for line in a_rows]
    w_row = [line[:21] + "C" + line[22:] for line in original if "TRP" in line]
    text = "MODEL        1\n" + "\n".join(a_rows + copied + w_row) + "\nENDMDL\n"
    path = bundle(tmp_path, {CF_MODEL: text, CF_DATA: {"plddt": [90, 20, 90, 20, 80]},
                            "demo.a3m": "#2,1\t2,1\n>query\nACW\n"})
    inventory = inspect_prediction_bundle(path)
    assert [(c.chain_id, c.sequence) for c in inventory.models[0].chains] == [("A", "AC"), ("B", "AC"), ("C", "W")]
    assert load_prediction_bundle(path, CF_MODEL, "C", "W").plddt.values == (80.,)


def test_seed_or_job_pairing_cannot_fall_back_to_another_model(tmp_path: Path) -> None:
    for confidence in (CF_DATA.replace("seed_000", "seed_001"), CF_DATA.replace("demo_", "other_")):
        with pytest.raises(PredictionBundleError, match="paired"):
            inspect_prediction_bundle(bundle(tmp_path, {CF_MODEL: pdb(), confidence: cf_data(), "demo.a3m": CF_A3M}))


def test_top_rank_unpaired_pae_is_never_used_as_model_specific_pae(tmp_path: Path) -> None:
    data = cf_data()
    del data["pae"]
    path = bundle(tmp_path, {CF_MODEL: pdb(), CF_DATA: data, "demo.a3m": CF_A3M,
                            "demo_predicted_aligned_error_v1.json": {"pae": [[0, 999], [999, 0]]}})
    assert load_prediction_bundle(path, CF_MODEL, "A", "AC").pae is None


@pytest.mark.parametrize("change", ["same_chain_swap", "non_ca_nan", "duplicate_field", "second_block"])
def test_af3_atom_and_document_ambiguity_rejects(tmp_path: Path, change: str) -> None:
    data, text = af_data(), cif()
    if change == "same_chain_swap": data["atom_plddts"][:2] = [90, 50]
    elif change == "non_ca_nan": text = text.replace("ALA N . 0 0 0", "ALA N . nan 0 0")
    elif change == "duplicate_field": text += "_struct_asym.id A\n"
    else: text += "data_extra\n_struct_asym.id A\n"
    with pytest.raises(PredictionBundleError):
        inspect_prediction_bundle(bundle(tmp_path, {AF_MODEL: text, AF_DATA: data}))


def test_af3_reordered_tokens_use_explicit_label_identity_not_array_offset(tmp_path: Path) -> None:
    data = af_data()
    data["token_chain_ids"] = ["B", "A", "A", "A"]
    data["token_res_ids"] = [1, 3, 1, 2]
    path = bundle(tmp_path, {AF_MODEL: cif(), AF_DATA: data})
    result = load_prediction_bundle(path, AF_MODEL, "A", "ACD")
    assert result.pae is not None
    assert result.pae.values == ((0., 9., 8.), (12., 0., 11.), (5., 6., 0.))


@pytest.mark.parametrize("limit,value", [("MAX_ARCHIVE_BYTES", 5), ("MAX_TOTAL_BYTES", 5),
                                       ("MAX_COMPRESSION_RATIO", 1), ("MAX_PAE_CELLS", 4),
                                       ("MAX_ATOMS", 2), ("MAX_RESIDUES", 2)])
def test_resource_limits_are_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str, value: int) -> None:
    import kuma_core.kuro.prediction_bundle as module
    path = bundle(tmp_path)
    monkeypatch.setattr(module, limit, value)
    with pytest.raises(PredictionBundleError):
        inspect_prediction_bundle(path)


def test_forged_central_directory_count_is_rejected_before_zipfile_parsing(tmp_path: Path) -> None:
    path = bundle(tmp_path)
    raw = bytearray(path.read_bytes())
    offset = raw.rfind(b"PK\x05\x06")
    struct.pack_into("<HH", raw, offset + 8, 1, 1)
    path.write_bytes(raw)
    with pytest.raises(PredictionBundleError, match="directory"):
        inspect_prediction_bundle(path)


def test_duplicate_unicode_normalized_paths_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(PredictionBundleError, match="Duplicate"):
        inspect_prediction_bundle(bundle(tmp_path, {AF_MODEL: cif(), AF_DATA: af_data(), "é.txt": "a", "e\u0301.txt": "b"}))


def test_zip_is_read_without_extracting_members(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("ZIP extraction must never occur")
    monkeypatch.setattr(zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    path = bundle(tmp_path)
    assert inspect_prediction_bundle(path).models[0].model_id == AF_MODEL
    assert sorted(p.name for p in tmp_path.iterdir()) == ["predictions.zip"]


@pytest.mark.parametrize("format_name", ["af3", "colabfold"])
def test_modified_monomers_are_not_normalized_into_standard_proteins(tmp_path: Path, format_name: str) -> None:
    if format_name == "af3":
        members: dict[str, object] = {AF_MODEL: cif().replace("ALA", "MSE"), AF_DATA: af_data()}
    else:
        members = {CF_MODEL: pdb().replace("ALA", "MSE"), CF_DATA: cf_data(),
                   "demo.a3m": CF_A3M.replace("ACW", "MCW")}
    with pytest.raises(PredictionBundleError, match="modified|nonstandard|Unsupported"):
        inspect_prediction_bundle(bundle(tmp_path, members))
