"""Coordinate confidence and score Top-N baseline for strict spatial selection.

Fixtures are synthetic. The AlphaFold-shaped header copies the TITLE layout of
AlphaFold DB PDB files; the sequence and coordinates are invented.
"""
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
    assert comparison["universe"] == "eligible-variants-before-budget-and-cap-policy"
    assert comparison["top_n_variants"] == ["A1C", "A1D"]
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
