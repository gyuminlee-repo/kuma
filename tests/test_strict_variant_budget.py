import math
from unittest.mock import patch

import pytest

from kuma_core.kuro.strict_spatial import select_single_sites
from sidecar_kuro.handlers.misc import handle_load_evolvepro_csv


def context(n=5, cap=None):
    return {"mapping": [{"reference_position": p, "coordinate": (float(p), 0., 0.)}
                        for p in range(1, n + 1)],
            "budget_mode": "distinct_variants", "site_cap": cap}


def test_95_variants_are_not_95_sites():
    rows = [(f"A{p}{aa}", float(100-p)) for p in range(1, 6)
            for aa in "CDEFGHIKLMNPQRSTVWY"]
    selected, report = select_single_sites(rows, "AAAAA", context(), 95)
    assert len(set(v for v, _ in selected)) == 95
    # M=N cannot change the recommended variant/site multiset.
    assert set(selected) == set(rows)
    assert report["selected_variant_count"] == 95
    assert report["selected_site_count"] == 5
    assert report["geometry_variant_min_pair_distance"] == 0
    assert report["geometry_site_min_pair_distance"] == 1


def test_reselection_never_expands_the_supplied_candidate_pool():
    rows = [("A1C", 9.), ("A1D", 8.), ("A2C", 7.)]
    selected, report = select_single_sites(rows, "AA", context(2), 2)
    assert selected == [("A1C", 9.), ("A2C", 7.)]
    assert set(selected) <= set(rows)
    assert report["selected_site_count"] == 2
    assert {v for v, _ in selected} != {v for v, _ in rows[:2]}


def test_cap_is_explicit_and_capacity_checked():
    rows = [("A1C", 9.), ("A1D", 8.), ("A2C", 7.), ("A2D", 6.)]
    selected, report = select_single_sites(rows, "AA", context(2), 4)
    assert len(selected) == 4
    assert report["site_cap"] is None
    with pytest.raises(ValueError, match="capacity"):
        select_single_sites(rows, "AA", context(2, 1), 3)
    selected, report = select_single_sites(rows, "AA", context(2, 1), 2)
    assert selected == [("A1C", 9.), ("A2C", 7.)]
    assert report["site_cap_excluded_count"] == 2


def test_order_and_rigid_translation_invariance():
    rows = [("A1C", 9.), ("A1D", 8.), ("A2C", 7.), ("A3C", 6.)]
    first, report = select_single_sites(rows, "AAA", context(3), 4)
    translated = context(3)
    for m in translated["mapping"]:
        x, y, z = m["coordinate"]
        m["coordinate"] = (100-y, -50+x, z+3)
    second, other = select_single_sites(list(reversed(rows)), "AAA", translated, 4)
    assert first == second
    assert report["site_multiplicities"] == other["site_multiplicities"]
    assert math.isclose(report["geometry_site_min_pair_distance"], other["geometry_site_min_pair_distance"])


@pytest.mark.parametrize("cap", [0, -1, True, 1.5])
def test_invalid_caps_fail(cap):
    with pytest.raises(ValueError, match="Site cap"):
        select_single_sites([("A1C", 1.)], "A", context(1, cap), 1)


def test_duplicates_and_zero_distance_are_not_additional_sites():
    rows = [("A1C", 2.), ("A1C", 2.), ("A1D", 1.)]
    selected, report = select_single_sites(rows, "A", context(1), 2)
    assert selected == [("A1C", 2.), ("A1D", 1.)]
    assert report["eligible_variant_count"] == 2
    assert report["selected_site_count"] == 1
    assert report["geometry_site_min_pair_distance"] is None
    assert report["geometry_variant_min_pair_distance"] == 0
    assert report["site_multiplicities"] == [{"reference_position": 1, "variant_count": 2}]
    with pytest.raises(ValueError, match="Conflicting"):
        select_single_sites([("A1C", 2.), ("A1C", 3.)], "A", context(1), 1)


def test_invalid_mapping_does_not_become_sequence_distance():
    bad = context(2)
    bad["mapping"][0]["coordinate"] = (float("nan"), 1., 2.)
    selected, report = select_single_sites([("A1C", 9.), ("A2C", 1.)], "AA", bad, 1)
    assert selected == [("A2C", 1.)]
    assert report["excluded"] == [{"variant": "A1C", "reason": "missing_or_nonfinite_coordinate"}]
    bad["mapping"].append(bad["mapping"][0])
    with pytest.raises(ValueError, match="unique"):
        select_single_sites([("A2C", 1.)], "AA", bad, 1)


@pytest.mark.parametrize("xyz", [(True, 0., 1.), ("1", 0., 1.), (1., 2.)])
def test_malformed_coordinate_identity_fails(xyz):
    bad = context(1)
    bad["mapping"][0]["coordinate"] = xyz
    with pytest.raises(ValueError, match="numeric components"):
        select_single_sites([("A1C", 1.)], "A", bad, 1)


def test_rpc_95_variants_low_score_direction_and_cap(tmp_path):
    path = tmp_path / "scores.csv"
    rows = [(f"A{p}{aa}", float(p)) for p in range(2, 7)
            for aa in "CDEFGHIKLMNPQRSTVWY"]
    path.write_text("variant,y_pred\n" + "\n".join(f"{v},{s}" for v, s in rows))
    pdb = "\n".join(f"ATOM  {p:5d}  CA  {name:3s} A{p:4d}    {float(p):8.3f}{0.:8.3f}{0.:8.3f}  1.00 90.00           C"
                     for p, name in enumerate(["MET"] + ["ALA"] * 5, 1))
    params = {"filepath": str(path), "ref_seq": "MAAAAA", "top_n": 95,
              "structure_accession": "P12345", "structural_diversity": True,
              "strict_spatial": True, "strict_spatial_budget": "distinct_variants",
              "score_order": "asc"}
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb):
        result = handle_load_evolvepro_csv(params)
        assert len(result["variants"]) == len(set(result["variants"])) == 95
        assert result["variants"][0].startswith("A2")
        report = result["strict_spatial"]
        assert report["selected_site_count"] == 5
        assert report["score_order"] == "asc"
        assert report["selection_policy"] == "distinct-variant-full-pool-fps-v1"
        params["strict_spatial_site_cap"] = 1
        with pytest.raises(ValueError, match="capacity"):
            handle_load_evolvepro_csv(params)
