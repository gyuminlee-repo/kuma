"""Coordinate confidence and score Top-N baseline for strict spatial selection.

Fixtures are synthetic. The AlphaFold-shaped header copies the TITLE layout of
AlphaFold DB PDB files; the sequence and coordinates are invented.
"""
import json
import math
import re
import typing
from pathlib import Path

import pytest
from pydantic import ValidationError

from kuma_core.kuro.strict_spatial import exact_pdb_context, select_single_sites
from sidecar_kuro.models import FetchActiveSiteResult

ROOT = Path(__file__).resolve().parents[1]
AF_HEADER = (
    "HEADER                                            01-JUN-22                     \n"
    "TITLE     ALPHAFOLD MONOMER V2.0 PREDICTION FOR SYNTHETIC TEST PROTEIN          \n"
    "TITLE    2 (X00000)                                                             \n"
)
XRAY_HEADER = (
    "HEADER    SYNTHETIC TEST PROTEIN                  01-JAN-00   0XXX              \n"
    "TITLE     SYNTHETIC CRYSTAL STRUCTURE FOR A TEST FIXTURE                        \n"
    "EXPDTA    X-RAY DIFFRACTION                                                     \n"
)
# Disordered tail first (low pLDDT, spread far away), then a compact core.
TAIL = [((200. + 40. * i, 0., 0.), 30.) for i in range(3)]
CORE = [((float(i % 3) * 4., float(i // 3) * 4., 0.), 90.) for i in range(9)]
SEQUENCE = "MAAAAAAAAAAA"


def atoms(header=""):
    lines = [
        f"ATOM  {i:5d}  CA  {('MET' if i == 1 else 'ALA'):3s} A{i:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00{b:6.2f}           C"
        for i, ((x, y, z), b) in enumerate(TAIL + CORE, 1)
    ]
    return header + "\n".join(lines)


def rows():
    # The highest score sits in the tail so it would also be the FPS start.
    return [("A2C", 50.)] + [(f"A{p}C", float(20 - p)) for p in range(3, 13)]


def test_alphafold_low_confidence_tail_is_excluded_from_distance_selection():
    context = exact_pdb_context(atoms(AF_HEADER), SEQUENCE, "X00000")
    selected, report = select_single_sites(rows(), SEQUENCE, context, 3)
    picked = {int(re.sub(r"\D", "", v[1:-1])) for v, _ in selected}
    assert picked.isdisjoint({1, 2, 3})
    assert {"variant": "A2C", "reason": "low_confidence_coordinate"} in report["excluded"]
    assert {"variant": "A3C", "reason": "low_confidence_coordinate"} in report["excluded"]
    confidence = report["coordinate_confidence"]
    assert confidence["source"] == "alphafold_plddt"
    assert confidence["threshold"] == 50.
    assert confidence["low_confidence_residue_count"] == 3
    assert confidence["excluded_variant_count"] == 2
    # Candidates stay in the source pool: they are only ineligible for geometry.
    assert report["input_variant_count"] == len(rows())


def test_experimental_header_keeps_bfactor_out_of_selection():
    context = exact_pdb_context(atoms(XRAY_HEADER), SEQUENCE, "X00000")
    selected, report = select_single_sites(rows(), SEQUENCE, context, 3)
    assert "A2C" in {v for v, _ in selected}
    assert report["excluded"] == []
    assert report["coordinate_confidence"] == {
        "source": "unavailable", "threshold": None,
        "low_confidence_residue_count": 0, "excluded_variant_count": 0}


def test_alphafold_header_without_readable_plddt_fails():
    text = atoms(AF_HEADER).replace("  1.00 30.00", "  1.00      ", 1)
    with pytest.raises(ValueError, match="pLDDT"):
        exact_pdb_context(text, SEQUENCE, "X00000")


def test_primary_top_n_is_raw_pool_not_site_representatives():
    ctx = {"budget_mode": "unique_sites", "score_available": True, "score_order": "desc",
           "mapping": [{"reference_position": p, "coordinate": (x, 0., 0.)}
                       for p, x in zip(range(1, 5), [0., 1., 10., 11.])]}
    data = [("A1C", 10.), ("A1D", 9.9), ("A1E", 9.8), ("A2C", 5.), ("A3C", 4.), ("A4C", 3.)]
    _, report = select_single_sites(data, "AAAA", ctx, 2)
    comparison = report["comparison"]
    assert comparison["universe"] == "input-variants-before-spatial-eligibility"
    assert comparison["top_n_variants"] == ["A1C", "A1D"]
    # Nothing is excluded here, so the eligible-pool baseline is the same list.
    assert comparison["top_n_excluded"] == []
    assert comparison["eligible_top_n"] == {
        "universe": "eligible-variants-before-budget-and-cap-policy",
        **{key: comparison[key] for key in ("top_n", "top_n_variants", "top_n_overlap_count", "score_gap_to_top_n")}}
    representative = comparison["representative_top_n"]
    assert representative["top_n_variants"] == ["A1C", "A2C"]
    assert comparison["score_gap_to_top_n"] > representative["score_gap_to_top_n"]
    assert comparison["top_n"]["max_variants_per_site"] == 2


def test_annotation_status_literal_matches_frontend_validator():
    allowed = set(typing.get_args(FetchActiveSiteResult.model_fields["annotation_status"].annotation))
    source = (ROOT / "src/types/validators.ts").read_text(encoding="utf-8")
    line = next(l for l in source.splitlines() if "value.annotation_status" in l)
    assert allowed == set(re.findall(r'item === "([a-z_]+)"', line))
    assert FetchActiveSiteResult(accession="X").annotation_status in allowed
    with pytest.raises(ValidationError):
        # A dict keeps the deliberately invalid literal out of the typed constructor.
        FetchActiveSiteResult.model_validate({"accession": "X", "annotation_status": "unknown"})


def test_alphafold_db_source_reads_plddt_without_a_recognised_title(tmp_path, caplog):
    # The strict RPC only fetches from AlphaFold DB, so a changed TITLE format
    # must not silently drop the pLDDT filter.
    from unittest.mock import patch

    from sidecar_kuro.handlers.misc import handle_load_evolvepro_csv

    path = tmp_path / "variants.csv"
    path.write_text("variant,y_pred\n" + "\n".join(f"{v},{s}" for v, s in rows()) + "\n")
    with patch("kuma_core.kuro.alphafold.fetch_pdb_text", return_value=atoms()), caplog.at_level("WARNING"):
        result = handle_load_evolvepro_csv({
            "filepath": str(path), "top_n": 3, "ref_seq": SEQUENCE, "structure_accession": "X00000",
            "strict_spatial": True, "structural_diversity": True})
    report = result["strict_spatial"]
    assert report["confidence_source"] == "alphafold_plddt"
    assert report["coordinate_confidence"]["source"] == "alphafold_plddt"
    assert report["coordinate_confidence"]["low_confidence_residue_count"] == 3
    assert "A2C" not in report["selected_variants"]
    assert "TITLE" in caplog.text


def test_direct_call_without_source_keeps_title_inference():
    assert exact_pdb_context(atoms(), SEQUENCE, "X00000")["confidence_source"] == "unavailable"
    assert exact_pdb_context(atoms(AF_HEADER), SEQUENCE, "X00000")["confidence_source"] == "alphafold_plddt"
    with pytest.raises(ValueError, match="source"):
        exact_pdb_context(atoms(), SEQUENCE, "X00000", source="pdb")


def test_capacity_error_names_low_confidence_exclusions():
    context = exact_pdb_context(atoms(AF_HEADER), SEQUENCE, "X00000")
    with pytest.raises(ValueError) as error:
        select_single_sites(rows(), SEQUENCE, context, 10)
    message = str(error.value)
    assert message.startswith("Strict spatial count 10 exceeds 9 eligible unique sites")
    assert "low_confidence_coordinate=2" in message


LOW = "low_confidence_coordinate"
CORE_XY = [coordinate for coordinate, _ in CORE]


def alphafold_report(count, rows_in=None, **extra):
    context = {**exact_pdb_context(atoms(AF_HEADER), SEQUENCE, "X00000"), **extra}
    return select_single_sites(rows_in or rows(), SEQUENCE, context, count)


def test_primary_top_n_is_taken_from_every_scored_input_variant():
    selected, report = alphafold_report(3)
    comparison = report["comparison"]
    assert comparison["baseline"] == "configured-score-top-n"
    assert comparison["universe"] == "input-variants-before-spatial-eligibility"
    # Plain score ranking of the input: the two best sit in the low-pLDDT tail.
    assert comparison["top_n_variants"] == ["A2C", "A3C", "A4C"]
    assert comparison["top_n_excluded"] == [{"variant": "A2C", "reason": LOW}, {"variant": "A3C", "reason": LOW}]
    assert comparison["top_n"]["variant_count"] == 3
    assert comparison["top_n"]["score_mean"] == (50. + 17. + 16.) / 3
    assert comparison["top_n"]["mean_score_rank"] == 2.
    picked = [v for v, _ in selected]
    assert comparison["top_n_overlap_count"] == len({"A2C", "A3C", "A4C"} & set(picked))
    assert comparison["score_gap_to_top_n"] == pytest.approx(
        comparison["top_n"]["score_mean"] - comparison["selected"]["score_mean"])
    # The former primary baseline is kept as a secondary one.
    eligible = comparison["eligible_top_n"]
    assert eligible["universe"] == "eligible-variants-before-budget-and-cap-policy"
    assert eligible["top_n_variants"] == ["A4C", "A5C", "A6C"]
    assert "top_n_excluded" not in eligible
    assert eligible["top_n"]["mean_score_rank"] == 4.  # ranks 3, 4, 5 of the whole input
    assert comparison["representative_top_n"]["top_n_variants"] == ["A4C", "A5C", "A6C"]
    # Selected ranks count the excluded input variants above them.
    universe = sorted(rows(), key=lambda row: -row[1])
    rank = {v: i for i, (v, _) in enumerate(universe, 1)}
    assert comparison["selected"]["mean_score_rank"] == pytest.approx(sum(rank[v] for v in picked) / 3)
    assert comparison["selected"]["spatial_variant_count"] == 3


def test_top_n_distance_metrics_use_only_members_with_usable_coordinates():
    _, report = alphafold_report(3)
    top = report["comparison"]["top_n"]
    # Only A4C (first core residue, at the origin) has a trusted coordinate.
    nearest = [math.dist(xy, CORE_XY[0]) for xy in CORE_XY]
    assert top["variant_count"] == 3 and top["spatial_variant_count"] == 1
    assert top["site_count"] == 1 and top["max_variants_per_site"] == 1
    assert top["minimum_site_distance"] is None
    assert top["coverage_mean_distance"] == pytest.approx(sum(nearest) / len(nearest))
    assert top["coverage_max_distance"] == pytest.approx(max(nearest))
    # The tail lies 200 A away; had it been used the maximum would exceed that.
    assert top["coverage_max_distance"] < 20.


def test_top_n_without_any_usable_coordinate_reports_no_distance():
    _, report = alphafold_report(2)
    comparison = report["comparison"]
    assert comparison["top_n_variants"] == ["A2C", "A3C"]
    assert [row["variant"] for row in comparison["top_n_excluded"]] == ["A2C", "A3C"]
    top = comparison["top_n"]
    assert top["variant_count"] == 2 and top["spatial_variant_count"] == 0
    assert top["site_count"] == 0 and top["max_variants_per_site"] == 0
    assert top["minimum_site_distance"] is None
    assert top["coverage_mean_distance"] is None and top["coverage_max_distance"] is None
    assert top["score_mean"] == 33.5 and top["mean_score_rank"] == 1.5
    assert comparison["top_n_overlap_count"] == 0
    json.dumps(report, allow_nan=False)


def mixed_exclusion_report(count, **extra):
    ctx = {"budget_mode": "unique_sites", "score_available": True, "score_order": "desc", **extra,
           "mapping": [{"reference_position": p, "coordinate": (float("nan") if p == 2 else float(p), 0., 0.)}
                       for p in range(1, 7)]}
    data = [("A1C", 1.), ("A2C", 10.), ("A3C", 9.), ("A4C", 8.), ("A5C", 7.), ("A6C", 6.),
            ("A4A", 99.), ("A5D", float("nan"))]
    return select_single_sites(data, "AAAAAA", ctx, count, [{"start": 3, "end": 3}])


def test_explicit_and_missing_coordinate_exclusions_enter_top_n_but_unranked_rows_do_not():
    selected, report = mixed_exclusion_report(3)
    comparison = report["comparison"]
    # A4A (unchanged) and A5D (no score) cannot be ranked at all and stay out.
    assert comparison["top_n_variants"] == ["A2C", "A3C", "A4C"]
    assert comparison["top_n_excluded"] == [
        {"variant": "A2C", "reason": "missing_or_nonfinite_coordinate"},
        {"variant": "A3C", "reason": "explicit_exclusion"}]
    assert {"variant": "A4A", "reason": "unchanged_amino_acid"} in report["excluded"]
    assert {"variant": "A5D", "reason": "nonfinite_score"} in report["excluded"]
    assert comparison["top_n"]["spatial_variant_count"] == 1
    assert comparison["eligible_top_n"]["top_n_variants"] == ["A4C", "A5C", "A6C"]
    # Six ranked variants: A2C=1 ... A6C=5, A1C=6.
    rank = {"A2C": 1, "A3C": 2, "A4C": 3, "A5C": 4, "A6C": 5, "A1C": 6}
    assert comparison["selected"]["mean_score_rank"] == pytest.approx(sum(rank[v] for v, _ in selected) / 3)
    assert comparison["eligible_top_n"]["top_n"]["mean_score_rank"] == 4.


def test_ascending_scores_rank_the_whole_input_and_report_raw_means():
    # The loader negates ascending scores before the selector sees them, so
    # rows() stands for raw scores -50, -17, -16, ... with lower being better.
    _, report = alphafold_report(3, score_order="asc")
    comparison = report["comparison"]
    assert comparison["top_n_variants"] == ["A2C", "A3C", "A4C"]
    assert comparison["top_n"]["score_mean"] == -(50. + 17. + 16.) / 3
    assert comparison["score_gap_to_top_n"] >= 0


def test_unavailable_scores_null_every_top_n_field_including_exclusions():
    selected, report = alphafold_report(3, score_available=False)
    comparison = report["comparison"]
    for block in (comparison, comparison["eligible_top_n"], comparison["representative_top_n"]):
        assert block["top_n"] is None and block["top_n_variants"] is None
        assert block["top_n_overlap_count"] is None and block["score_gap_to_top_n"] is None
    assert comparison["top_n_excluded"] is None
    assert comparison["selected"]["mean_score_rank"] is None


def test_tied_scores_share_an_average_rank_across_excluded_and_eligible_rows():
    # A2C and A3C (low pLDDT) tie with A4C and A5C (eligible): ranks 1-4 average to 2.5.
    data = [("A2C", 5.), ("A3C", 5.), ("A4C", 5.), ("A5C", 5.)] + [(f"A{p}C", 1.) for p in range(6, 13)]
    _, report = alphafold_report(2, data)
    comparison = report["comparison"]
    assert comparison["top_n_variants"] == ["A2C", "A3C"]  # ties break by position
    assert comparison["top_n"]["mean_score_rank"] == 2.5
    assert comparison["eligible_top_n"]["top_n_variants"] == ["A4C", "A5C"]
    assert comparison["eligible_top_n"]["top_n"]["mean_score_rank"] == 2.5


def test_changing_the_comparison_leaves_the_selection_as_it_was():
    selected, report = alphafold_report(3)
    assert [v for v, _ in selected] == report["selected_variants"] == ["A4C", "A12C", "A6C"]
    assert report["selected_positions"] == [4, 12, 6]
    assert report["eligible_positions"] == list(range(4, 13))
    assert report["eligible_variant_count"] == 9
    assert report["excluded"] == [{"variant": "A2C", "reason": LOW}, {"variant": "A3C", "reason": LOW}]
    assert report["selection_policy"] == "single-site-full-pool-fps-v1"
