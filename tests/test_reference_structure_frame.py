"""Reference-frame structure use: terminal overlap, ESMFold pLDDT scale, key registration."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from kuma_core.kuro import esmfold
from kuma_core.kuro.interface import reference_structure_overlap
from kuma_core.kuro.strict_spatial import SOURCE_ESMFOLD, exact_pdb_context, select_single_sites
from sidecar_kuro import core as sidecar_core
from sidecar_kuro.handlers import external, misc

REF = "MACDEFGHIKLMNPQRSTVWY"  # 21 residues, no repeated 4-mer
_THREE = {"A": "ALA", "C": "CYS", "D": "ASP", "E": "GLU", "F": "PHE", "G": "GLY", "H": "HIS",
          "I": "ILE", "K": "LYS", "L": "LEU", "M": "MET", "N": "ASN", "P": "PRO", "Q": "GLN",
          "R": "ARG", "S": "SER", "T": "THR", "V": "VAL", "W": "TRP", "Y": "TYR"}


def _coords(seq: str) -> list:
    return [None] + [(float(i), 0.0, 0.0) for i in range(1, len(seq) + 1)]


def _pdb(seq: str, bfactors: list[float]) -> str:
    lines = []
    for i, (aa, b) in enumerate(zip(seq, bfactors), start=1):
        lines.append(
            f"ATOM  {i:5d}  CA  {_THREE[aa]} A{i:4d}    {float(i):8.3f}{0.0:8.3f}{0.0:8.3f}{1.0:6.2f}{b:6.2f}           C"
        )
    return "\n".join(lines) + "\nEND\n"


def _project(structure_seq: str, ref: str = REF):
    coords = _coords(structure_seq)
    with patch.object(misc, "_get_cached_ca_seq", return_value=structure_seq):
        return coords, misc._frame_checked_ca_projection(coords, "file:model", ref)


# ── terminal truncation is an exact overlap ───────────────────────────────


def test_overlap_function_places_a_shorter_structure_with_a_negative_offset():
    result = reference_structure_overlap(REF[3:], REF)
    assert result == {"offset": -3, "covered": len(REF) - 3, "reference_length": len(REF)}


def test_n_terminally_truncated_structure_is_used_with_none_for_missing_positions():
    coords, (projected, mismatch, coverage) = _project(REF[3:])
    assert not mismatch
    assert projected[:4] == [None, None, None, None]
    assert projected[4:] == coords[1:]
    assert len(projected) == len(REF) + 1
    assert coverage == {"covered": len(REF) - 3, "reference_length": len(REF)}


def test_c_terminally_truncated_structure_is_used_with_none_for_missing_positions():
    coords, (projected, mismatch, coverage) = _project(REF[:15])
    assert not mismatch
    assert projected[:16] == coords
    assert projected[16:] == [None] * (len(REF) - 15)
    assert coverage == {"covered": 15, "reference_length": len(REF)}


def test_complete_structure_reports_no_partial_coverage():
    _, (projected, mismatch, coverage) = _project(REF)
    assert projected is not None and not mismatch and coverage is None


@pytest.mark.parametrize(
    "structure_seq",
    [
        REF[:7] + "A" + REF[8:],           # one substitution
        REF[:8] + REF[10:],                # internal gap
        REF[:10] + "GG" + REF[10:],        # internal insertion
    ],
)
def test_substitution_or_internal_difference_stays_refused(structure_seq):
    _, (projected, mismatch, coverage) = _project(structure_seq)
    assert projected is None and mismatch and coverage is None


def test_repeated_placement_of_a_fragment_stays_refused():
    ref = "ACDEFGACDEFGHIK"
    _, (projected, mismatch, coverage) = _project("ACDEFG", ref)
    assert projected is None and mismatch and coverage is None


def test_two_value_wrapper_is_unchanged():
    with patch.object(misc, "_get_cached_ca_seq", return_value=REF[3:]):
        projected, mismatch = misc._frame_checked_ca_coords(_coords(REF[3:]), "file:model", REF)
    assert not mismatch and projected[1:4] == [None, None, None]


# ── ESMFold pLDDT scale ───────────────────────────────────────────────────


def test_zero_to_one_plddt_is_rescaled_to_percent():
    pdb = _pdb(REF, [0.9] * len(REF))
    scaled = esmfold.normalise_plddt_scale(pdb)
    assert esmfold._mean_plddt(scaled) == pytest.approx(90.0)


def test_percent_plddt_is_left_alone():
    pdb = _pdb(REF, [92.5] * len(REF))
    assert esmfold.normalise_plddt_scale(pdb) == pdb


class _Response:
    def __init__(self, body: str):
        self._body = body.encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_predict_structure_returns_percent_scale_for_a_unit_scale_server_reply(tmp_path):
    reply = _pdb(REF, [0.8] * len(REF))
    with patch.object(esmfold, "kuma_cache_dir", return_value=tmp_path), \
            patch.object(esmfold.urllib.request, "urlopen", return_value=_Response(reply)):
        pdb, mean, _, cache_hit, seq_hash = esmfold.predict_structure(REF)
        assert not cache_hit and mean == pytest.approx(80.0)
        # a cache hit must come back on the same scale
        cached, cached_mean, _, hit, _ = esmfold.predict_structure(REF)
    assert hit and cached_mean == pytest.approx(80.0) and cached == pdb
    assert esmfold.structure_key(seq_hash) == "ESMFOLD:" + seq_hash.upper()


def test_low_confidence_rule_uses_percent_scale_for_esmfold_structures():
    # residue 5 is low confidence (0.3 -> 30), the rest confident (0.9 -> 90)
    raw = _pdb(REF, [0.3 if i == 4 else 0.9 for i in range(len(REF))])
    pdb = esmfold.normalise_plddt_scale(raw)
    context = exact_pdb_context(pdb, REF, "ESMFOLD:ABC", source=SOURCE_ESMFOLD)
    assert context["confidence_source"] == "alphafold_plddt"
    rows = [("E5A", 3.0), ("F6A", 2.0), ("G7A", 1.0)]
    _, report = select_single_sites(rows, REF, context, 2)
    assert {"variant": "E5A", "reason": "low_confidence_coordinate"} in report["excluded"]
    assert report["coordinate_confidence"]["threshold"] == 50.0


def test_strict_context_accepts_a_terminally_truncated_structure():
    pdb = _pdb(REF[3:], [90.0] * (len(REF) - 3))
    context = exact_pdb_context(pdb, REF, "ESMFOLD:ABC", source=SOURCE_ESMFOLD)
    assert [m["reference_position"] for m in context["mapping"]] == list(range(4, len(REF) + 1))
    assert context["mapping"][0]["structure_position"] == 1


# ── ESMFold prediction registers a structure key the selection can use ─────


def test_prediction_registers_coordinates_under_a_structure_key():
    pdb = _pdb(REF, [90.0] * len(REF))
    seq_hash = "ab" * 32
    with patch("kuma_core.kuro.esmfold.predict_structure",
               return_value=(pdb, 90.0, len(REF), False, seq_hash)), \
            patch.object(external, "_progress", lambda *a, **k: None):
        result = external.handle_predict_structure_esmfold({"sequence": REF})
    key = "ESMFOLD:" + seq_hash.upper()
    assert result["structure_key"] == key
    coords = sidecar_core._get_cached_ca_coords(key)
    assert coords is not None and len(coords) == len(REF) + 1
    assert sidecar_core._get_cached_ca_seq(key) == REF
