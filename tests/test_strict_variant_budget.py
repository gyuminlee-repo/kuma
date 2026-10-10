import math
import json
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
    assert report["comparison"]["top_n_variants"] == ["A2C"]
    assert report["comparison"]["selected"]["mean_score_rank"] == 1
    assert report["comparison"]["candidate_site_count"] == 1
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
        assert report["comparison"]["selected"]["score_mean"] == 4.
        assert report["comparison"]["score_gap_to_top_n"] == 0.
        assert report["selection_policy"] == "distinct-variant-full-pool-fps-v1"
        params["strict_spatial_site_cap"] = 1
        with pytest.raises(ValueError, match="capacity"):
            handle_load_evolvepro_csv(params)


@pytest.mark.parametrize("order", ["desc", "asc"])
def test_score_top_n_comparison_is_same_pool_and_hand_calculated(order):
    variants = ["A2C", "A2D", "A3C", "A4C", "A5C"]
    scores = [10., 9., 8., 7., 6.] if order == "desc" else [-1., -2., -3., -4., -5.]
    ctx = {"budget_mode": "distinct_variants", "score_available": True, "score_order": order,
           "mapping": [{"reference_position": p, "coordinate": (x, 0., 0.)}
                       for p, x in zip(range(2, 6), [0., 1., 10., 11.])]}
    selected, report = select_single_sites(list(zip(variants, scores)), "MAAAA", ctx, 2)
    assert [v for v, _ in selected] == ["A2C", "A5C"]
    comparison = report["comparison"]
    assert comparison["top_n_variants"] == ["A2C", "A2D"]
    assert comparison["top_n_overlap_count"] == 1
    assert comparison["score_gap_to_top_n"] == 1.5
    assert comparison["selected"]["mean_score_rank"] == 3.
    assert comparison["selected"]["site_count"] == 2
    assert comparison["top_n"]["site_count"] == 1
    assert comparison["selected"]["max_variants_per_site"] == 1
    assert comparison["top_n"]["max_variants_per_site"] == 2
    assert comparison["selected"]["coverage_mean_distance"] == .5
    assert comparison["top_n"]["coverage_mean_distance"] == 5.5
    assert comparison["selected"]["coverage_max_distance"] == 1.
    assert comparison["top_n"]["coverage_max_distance"] == 11.
    assert comparison["top_n"]["minimum_site_distance"] is None
    assert comparison["selected"]["score_mean"] == (8. if order == "desc" else 3.)
    ctx["site_cap"] = 1
    _, capped = select_single_sites(list(zip(variants, scores)), "MAAAA", ctx, 2)
    assert capped["comparison"]["top_n_variants"] == ["A2C", "A3C"]
    assert capped["comparison"]["selected"]["mean_score_rank"] == 2.5


def test_unknown_scores_have_no_top_score_baseline_but_real_zero_scores_do():
    rows = [("A1C", 0.), ("A1D", 0.), ("A2C", 0.)]
    ctx = {**context(2), "score_available": False}
    _, report = select_single_sites(rows, "AA", ctx, 1)
    comparison = report["comparison"]
    assert comparison["top_n"] is None
    assert comparison["top_n_variants"] is None
    assert comparison["score_gap_to_top_n"] is None
    assert comparison["selected"]["mean_score_rank"] is None
    assert comparison["selected"]["minimum_site_distance"] is None
    ctx["score_available"] = True
    _, real_zero = select_single_sites(rows, "AA", ctx, 1)
    assert real_zero["comparison"]["selected"]["mean_score_rank"] == 2.
    assert real_zero["comparison"]["selected"]["score_mean"] == 0.
    assert real_zero["comparison"]["score_gap_to_top_n"] == 0.


def test_finite_extreme_scores_do_not_break_selection_or_json():
    ctx = context(6)
    for entry, x in zip(ctx["mapping"], [0., 1., 2., 100., 200., 300.]):
        entry["coordinate"] = (x, 0., 0.)
    rows = [(f"A{p}C", 1.7e308 if p <= 3 else -1.7e308) for p in range(1, 7)]
    selected, report = select_single_sites(rows, "AAAAAA", ctx, 3)
    assert len(selected) == 3
    assert report["comparison"]["score_gap_to_top_n"] is None
    json.dumps(report, allow_nan=False)


def df_test_params(tmp_path, rows, count):
    """Synthetic df_test-compatible data; no actual EVOLVEpro run is implied."""
    path = tmp_path / "df_test.csv"
    path.write_text("Unnamed: 0,variant,y_pred,y_actual\n" + "\n".join(
        f"{i},{variant},{score}," for i, (variant, score) in enumerate(rows)))
    pdb = "\n".join(
        f"ATOM  {p:5d}  CA  {name:3s} A{p:4d}    {float(p):8.3f}{0.:8.3f}{0.:8.3f}  1.00 90.00           C"
        for p, name in enumerate(["MET"] + ["ALA"] * 8, 1))
    return {"filepath": str(path), "ref_seq": "MAAAAAAAA", "top_n": count,
            "structure_accession": "P12345", "structural_diversity": True,
            "strict_spatial": True, "strict_spatial_budget": "distinct_variants"}, pdb


@pytest.mark.parametrize("count", [1, 12, 95, 100, 152, 153])
def test_full_df_test_pool_variable_n_not_fixed_to_95(tmp_path, count):
    variants = [f"A{p}{aa}" for p in range(2, 10) for aa in "CDEFGHIKLMNPQRSTVWY"]
    rows = [(variant, 1000. - i) for i, variant in enumerate(variants)]
    params, pdb = df_test_params(tmp_path, list(reversed(rows)), count)
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb):
        if count > len(rows):
            with pytest.raises(ValueError, match="capacity"):
                handle_load_evolvepro_csv(params)
            return
        result = handle_load_evolvepro_csv(params)
    selected = result["variants"]
    assert len(set(selected)) == count
    assert set(selected) <= set(variants)
    assert result["strict_spatial"]["eligible_variant_count"] == 152
    comparison = result["strict_spatial"]["comparison"]
    assert comparison["top_n_variants"] == variants[:count]
    assert comparison["selected"]["mean_score_rank"] == pytest.approx(
        sum(variants.index(v) + 1 for v in selected) / count)
    mutated = {params["ref_seq"][:int(v[1:-1])-1] + v[-1] + params["ref_seq"][int(v[1:-1]):]
               for v in selected}
    assert len(mutated) == count
    if count == 1:
        assert comparison["selected"]["minimum_site_distance"] is None
    if count == len(rows):
        assert set(selected) == set(variants)
        assert comparison["selected"] == comparison["top_n"]
        assert comparison["top_n_overlap_count"] == count
        assert comparison["score_gap_to_top_n"] == 0


def test_df_test_aliases_no_op_and_final_sequences_are_not_extra_slots(tmp_path):
    rows = [("2C", 5), ("02C", 5), ("A2C", 5), ("A2A", 10), ("A3D", 4)]
    params, pdb = df_test_params(tmp_path, rows, 2)
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb):
        result = handle_load_evolvepro_csv(params)
    assert set(result["variants"]) == {"A2C", "A3D"}
    assert result["strict_spatial"]["duplicate_variant_omitted_count"] == 2
    assert result["strict_spatial"]["excluded"] == [
        {"variant": "A2A", "reason": "unchanged_amino_acid"}]
    assert result["strict_spatial"]["comparison"]["top_n_overlap_count"] == 2


@pytest.mark.parametrize("variant", ["V2C", "WT", "not-a-variant", "A2C:A3D"])
def test_df_test_unsupported_or_wrong_wt_is_not_silently_selected(tmp_path, variant):
    params, pdb = df_test_params(tmp_path, [(variant, 1)], 1)
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb), pytest.raises(ValueError):
        handle_load_evolvepro_csv(params)


def test_df_test_conflicting_alias_scores_fail(tmp_path):
    params, pdb = df_test_params(tmp_path, [("2C", 5), ("A2C", 4)], 1)
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb), pytest.raises(ValueError, match="Conflicting"):
        handle_load_evolvepro_csv(params)


def test_top_n_uses_eligible_rows_not_unparseable_scores(tmp_path):
    params, pdb = df_test_params(tmp_path, [("A2C", 10), ("A3C", "bad"), ("A4C", ""),
                                          ("A5C", "inf"), ("A6C", 9)], 2)
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=pdb):
        result = handle_load_evolvepro_csv(params)
    report = result["strict_spatial"]
    assert report["parsing_omitted_count"] == 3
    assert report["comparison"]["top_n_variants"] == ["A2C", "A6C"]
    assert report["comparison"]["selected"] == report["comparison"]["top_n"]


def test_unique_site_comparison_uses_representative_pool():
    ctx = context(3)
    ctx["budget_mode"] = "unique_sites"
    rows = [("A1C", 10.), ("A1D", 9.), ("A2C", 8.), ("A3C", 7.)]
    selected, report = select_single_sites(rows, "AAA", ctx, 2)
    comparison = report["comparison"]
    assert selected == [("A1C", 10.), ("A3C", 7.)]
    assert comparison["top_n_variants"] == ["A1C", "A2C"]
    assert comparison["candidate_site_count"] == 3
    assert comparison["selected"]["mean_score_rank"] == 2
    assert comparison["top_n"]["site_count"] == 2
