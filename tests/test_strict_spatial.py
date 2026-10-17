from unittest.mock import patch

import pytest

from kuma_core.kuro.strict_spatial import exact_pdb_context, select_single_sites
from sidecar_kuro.handlers.misc import handle_load_evolvepro_csv


def pdb(points=None, chain="A"):
    names = ["MET", "ALA", "CYS", "ASP", "GLU"]
    points = points or [(0., 0., 0.), (1., 0., 0.), (2., 0., 0.), (9., 0., 0.), (10., 0., 0.)]
    return "\n".join(
        f"ATOM  {i:5d}  CA  {name:3s} {chain}{i:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00 90.00           C"
        for i, (name, (x, y, z)) in enumerate(zip(names, points), 1)
    )


def test_mapping_and_representative_are_order_invariant():
    context = exact_pdb_context(pdb(), "ACDE", "P12345")
    assert [(m["reference_position"], m["structure_position"]) for m in context["mapping"]] == [(1, 2), (2, 3), (3, 4), (4, 5)]
    rows = [("A1G", 9.), ("A1V", 8.), ("C2G", 7.), ("D3G", 6.), ("E4G", 5.)]
    selected, report = select_single_sites(rows, "ACDE", context, 2)
    assert selected == [("A1G", 9.), ("E4G", 5.)]
    assert report["same_site_collapsed"] == 1
    assert select_single_sites(list(reversed(rows)), "ACDE", context, 2)[0] == selected


@pytest.mark.parametrize("count", [0, -1, 6])
def test_count_never_silently_changes(count):
    context = exact_pdb_context(pdb(), "MACDE", "P12345")
    with pytest.raises(ValueError):
        select_single_sites([("A2G", 1.)], "MACDE", context, count)


@pytest.mark.parametrize("variant", ["A2G:C3V", "V2G", "A9G"])
def test_invalid_identity_or_multisite_rejected(variant):
    with pytest.raises(ValueError):
        select_single_sites([(variant, 1.)], "MACDE", exact_pdb_context(pdb(), "MACDE", "P12345"), 1)


def test_missing_coordinates_are_excluded_not_sequence_distances():
    text = pdb([(0., 0., 0.), (float("nan"), 0., 0.), (2., 0., 0.), (9., 0., 0.), (10., 0., 0.)])
    context = exact_pdb_context(text, "MACDE", "P12345")
    selected, report = select_single_sites([("A2G", 10.), ("C3G", 1.)], "MACDE", context, 1)
    assert selected == [("C3G", 1.)]
    assert report["excluded"] == [{"variant": "A2G", "reason": "missing_or_nonfinite_coordinate"}]


@pytest.mark.parametrize("text", [pdb() + "\n" + pdb(chain="B"), "MODEL        1\n" + pdb() + "\nENDMDL\nMODEL        2\n" + pdb(), pdb().replace(" A   2", " A   2A")])
def test_unrepresentable_pdb_identity_is_rejected(text):
    with pytest.raises(ValueError):
        exact_pdb_context(text, "MACDE", "P12345")


def test_rpc_strict_uses_full_pool_and_certifies_source(tmp_path):
    path = tmp_path / "variants.csv"
    path.write_text("variant,y_pred\nA2G,10\nA2V,9\nC3G,8\nD4G,7\nE5G,6\n")
    args = dict(filepath=str(path), top_n=2, ref_seq="MACDE", structure_accession="P12345",
                structural_diversity=True, strict_spatial=True, structural_kappa=1.,
                anchor_variants=["D4G"], max_per_position=1, domain_diversity=True)
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb()):
        result = handle_load_evolvepro_csv(args)
    assert result["variants"] == ["A2G", "E5G"]
    report = result["strict_spatial"]
    assert report["selected_variants"] == result["variants"]
    assert report["eligible_site_count"] == 4
    assert report["pdb_text"] == pdb()
    assert len(report["candidate_sha256"]) == 64


def test_strict_duplicate_conflict_and_local_source_fail(tmp_path):
    path = tmp_path / "variants.csv"
    path.write_text("variant,y_pred\nA2G,10\nA2G,9\n")
    args = dict(filepath=str(path), top_n=1, ref_seq="MACDE", structure_accession="P12345",
                structural_diversity=True, strict_spatial=True)
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb()), pytest.raises(ValueError, match="Conflicting"):
        handle_load_evolvepro_csv(args)


def test_no_op_does_not_consume_mutation_budget():
    context = exact_pdb_context(pdb(), "MACDE", "P12345")
    selected, report = select_single_sites([("A2A", 10.), ("C3G", 1.)], "MACDE", context, 1)
    assert selected == [("C3G", 1.)]
    assert report["excluded"] == [{"variant": "A2A", "reason": "unchanged_amino_acid"}]


def test_duplicate_excluded_rows_do_not_make_negative_counts():
    context = exact_pdb_context(pdb(), "MACDE", "P12345")
    _, report = select_single_sites([("A2G", 2.), ("C3G", 1.), ("C3G", 1.)],
                                   "MACDE", context, 1, [{"start": 3, "end": 3}])
    assert report["same_site_collapsed"] == 0


@pytest.mark.parametrize("cells,available", [("0\nC3G,0", True), ("\nC3G,", False)])
def test_actual_frontend_payload_score_semantics(tmp_path, cells, available):
    path = tmp_path / "input.csv"
    path.write_text("variant,y_pred\nA2G," + cells + "\n")
    params = {"filepath": str(path), "top_n": 1, "ref_seq": "MACDE",
              "structure_accession": "P12345", "score_order": "desc",
              "strict_spatial": True, "structural_diversity": True}
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb()):
        result = handle_load_evolvepro_csv(params)
    assert result["strict_spatial"]["score_available"] is available
    assert result["variants"] == ["A2G"]
    params["structure_accession"] = "file:test.pdb"
    with pytest.raises(ValueError, match="AlphaFold"):
        handle_load_evolvepro_csv(params)


def test_parser_omissions_are_separate_from_coordinate_exclusions(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("variant,y_pred\nA2G,3\nC3G,\nD4G,nan\nE5G,2\n")
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb()):
        result = handle_load_evolvepro_csv({"filepath": str(path), "top_n": 1,
            "ref_seq": "MACDE", "structure_accession": "P12345",
            "strict_spatial": True, "structural_diversity": True})
    report = result["strict_spatial"]
    assert report["source_row_count"] == 4
    assert report["parsing_omitted_count"] == 2
    assert report["excluded"] == []
