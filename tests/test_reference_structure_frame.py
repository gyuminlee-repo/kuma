"""Reference-frame structure use: terminal overlap, ESMFold pLDDT scale, key registration."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from kuma_core.kuro import esmfold
from kuma_core.kuro.interface import reference_structure_overlap
from kuma_core.kuro.strict_spatial import (
    SOURCE_ESMFOLD,
    StrictFrameMismatchError,
    exact_pdb_context,
    select_single_sites,
)
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
    assert context["confidence_source"] == "esmfold_plddt"
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


SEQ_HASH = "ab" * 32
KEY = "ESMFOLD:" + SEQ_HASH.upper()
_LOAD_CACHED = "kuma_core.kuro.esmfold.load_cached_prediction"


@pytest.fixture
def empty_slot(monkeypatch):
    """The sidecar's single coordinate slot, empty and restored after the test."""
    for name in ("ca_coords", "ca_coords_accession", "ca_coords_seq"):
        monkeypatch.setattr(sidecar_core._state, name, None)


def _predict(pdb: str) -> dict:
    with patch("kuma_core.kuro.esmfold.predict_structure",
               return_value=(pdb, 90.0, len(REF), False, SEQ_HASH)), \
            patch.object(external, "_progress", lambda *a, **k: None):
        return external.handle_predict_structure_esmfold({"sequence": REF})


def test_prediction_registers_coordinates_under_a_structure_key(empty_slot):
    pdb = _pdb(REF, [90.0] * len(REF))
    result = _predict(pdb)
    assert result["structure_key"] == KEY
    with patch(_LOAD_CACHED, return_value=pdb):
        coords = sidecar_core._get_cached_ca_coords(KEY)
        assert coords is not None and len(coords) == len(REF) + 1
        assert sidecar_core._get_cached_ca_seq(KEY) == REF


def test_prediction_does_not_evict_a_structure_loaded_meanwhile(empty_slot):
    other = _coords("MKTAYIAKQRQ")
    with sidecar_core._state_lock:
        sidecar_core._state.ca_coords = other
        sidecar_core._state.ca_coords_accession = "P12345"
        sidecar_core._state.ca_coords_seq = "MKTAYIAKQRQ"
    _predict(_pdb(REF, [90.0] * len(REF)))
    assert sidecar_core._get_cached_ca_coords("P12345") is other


# -- an ESMFOLD key resolves from the disk cache, not from the slot ---------------


def _load_params(tmp_path) -> dict:
    csv = tmp_path / "df_test.csv"
    csv.write_text("variant,y_pred\nE5A,0.9\nF6A,0.8\nG7A,0.7\nH8A,0.6\nI9A,0.5\n")
    return {"filepath": str(csv), "top_n": 3, "structural_diversity": True,
            "structure_accession": KEY, "ref_seq": REF}


def test_restored_esmfold_key_with_an_empty_slot_still_selects_on_3d(empty_slot, tmp_path):
    pdb = _pdb(REF, [90.0] * len(REF))
    with patch(_LOAD_CACHED, return_value=pdb):
        result = misc.handle_load_evolvepro_csv(_load_params(tmp_path))
    assert result["structure_coordinates_used"] is True
    assert result["structure_frame_mismatch"] is False


def test_esmfold_key_missing_from_the_cache_is_reported_as_one_dimensional(empty_slot, tmp_path):
    with patch(_LOAD_CACHED, return_value=None):
        result = misc.handle_load_evolvepro_csv(_load_params(tmp_path))
    assert result["structure_coordinates_used"] is False


def test_benchmark_resolves_an_esmfold_key_from_the_cache(empty_slot):
    pdb = _pdb(REF, [90.0] * len(REF))
    truth = {"E5A": 0.9, "F6A": 0.8, "G7A": 0.7, "H8A": 0.6}
    params = {"landscape": [{"variant": v, "fitness": f} for v, f in truth.items()],
              "ground_truth": truth, "n_select": 2, "n_random_trials": 2,
              "structure_accession": KEY, "ref_seq": REF}
    with patch(_LOAD_CACHED, return_value=pdb):
        result = misc.handle_run_benchmark(params)
    assert result["structure_coordinates_used"] is True


# -- minimum coverage of a truncated overlap -------------------------------------

REF20 = REF[:20]


def test_overlap_at_exactly_half_the_reference_is_accepted():
    assert reference_structure_overlap(REF20[:10], REF20) == {
        "offset": 0, "covered": 10, "reference_length": 20}


def test_overlap_below_half_the_reference_is_a_frame_mismatch():
    assert reference_structure_overlap(REF20[:9], REF20) is None
    _, (projected, mismatch, coverage) = _project(REF20[:9], REF20)
    assert projected is None and mismatch and coverage is None


def test_single_residue_substring_is_not_a_frame():
    assert reference_structure_overlap("W", REF) is None


def test_structure_sequence_case_does_not_decide_the_frame():
    assert reference_structure_overlap(REF.lower(), REF) == {
        "offset": 0, "covered": len(REF), "reference_length": len(REF)}


# -- the frame refusal carries its own code --------------------------------------


def test_strict_context_refuses_a_non_reference_structure_with_the_frame_error():
    with pytest.raises(StrictFrameMismatchError):
        exact_pdb_context(_pdb(REF[:5], [90.0] * 5), REF, "ESMFOLD:ABC", source=SOURCE_ESMFOLD)


def test_dispatcher_sends_the_frame_refusal_under_its_own_code():
    from sidecar_kuro import dispatcher

    sent: list = []

    def handler(params):
        raise StrictFrameMismatchError("no placement")

    with patch.object(dispatcher, "_error", lambda rid, code, msg: sent.append((rid, code, msg))):
        dispatcher._dispatch_handler(7, "load_evolvepro_csv", handler, {})
    assert sent == [(7, -32010, "no placement")]
