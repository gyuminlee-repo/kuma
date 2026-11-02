"""The expected_mutations sheet describes the plate that was exported, nothing more.

MAME reads row *i* of ``expected_mutations`` as well *i*. ``handle_export_excel``
used to pair the UI plate (``mappings``) with every backend design result, so a
mutation the plate cap or the operator had dropped came back as a trailing
``DESIGNED`` row: a ghost well after the last real one. ``handle_export_all`` had
already filtered by the mapped mutations; both handlers now share one filter.
"""

from __future__ import annotations

import openpyxl
import pytest

from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.overlap import OverlapWindow
from kuma_core.kuro.sdm_engine import SdmPrimerResult
from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.export import handle_export_all, handle_export_excel

_FWD = "ACGTACGTACGTAA"
_REV = "TTACGTACGTACGT"


def _result(raw: str, position: int, overlap_mode: str = "partial") -> SdmPrimerResult:
    return SdmPrimerResult(
        mutation=Mutation(
            raw=raw, wt_aa=raw[0], position=position, mt_aa=raw[-1],
            codon_start=(position - 1) * 3, wt_codon="GCT", mt_codon="GTT",
        ),
        forward_seq=_FWD + raw, reverse_seq=_REV + raw,
        forward_binding=_FWD, reverse_binding=_REV,
        overlap_window=OverlapWindow(sequence=_FWD, start=0, end=len(_FWD), codon_offset=0),
        tm_fwd=60.0, tm_rev=60.0, tm_overlap=55.0, tm_condition_met=True,
        overlap_mode=overlap_mode,  # pyright: ignore[reportArgumentType]
    )


@pytest.fixture
def two_results_state():
    with _state_lock:
        saved = (list(_state.results), list(_state.plate_mappings), _state.dedup_info)
        # A3V first: run_overlap_mode used to come from results[0] even when the
        # plate did not carry it.
        _state.results = [_result("A3V", 3, "full"), _result("A2V", 2, "partial")]
        _state.plate_mappings = []
        _state.dedup_info = {}
    yield
    with _state_lock:
        _state.results, _state.plate_mappings, _state.dedup_info = saved


def _payload(*raws: str) -> list[dict]:
    out: list[dict] = []
    for i, raw in enumerate(raws):
        out.append({"well": f"A{i + 1}", "primer_name": f"{raw}_F",
                    "sequence": _FWD + raw, "primer_type": "forward", "mutation": raw})
        out.append({"well": f"A{i + 1}", "primer_name": f"{raw}_R",
                    "sequence": _REV + raw, "primer_type": "reverse", "mutation": raw})
    return out


def _expected_ids(path) -> list[str]:
    wb = openpyxl.load_workbook(path)
    ws = wb["expected_mutations"]
    return [row[0] for row in ws.iter_rows(min_row=2, values_only=True)]


def _list_header(path) -> list[str]:
    wb = openpyxl.load_workbook(path)
    return [c for c in next(wb["Fwd List"].iter_rows(max_row=1, values_only=True))]


def test_export_excel_rows_equal_wells_when_plate_drops_a_result(tmp_path, two_results_state):
    out = tmp_path / "plate.xlsx"
    handle_export_excel({"filepath": str(out), "mappings": _payload("A2V")})
    assert _expected_ids(out) == ["A2V"]


def test_export_excel_overlap_mode_comes_from_the_exported_plate(tmp_path, two_results_state):
    out = tmp_path / "plate.xlsx"
    handle_export_excel({"filepath": str(out), "mappings": _payload("A2V")})
    header = _list_header(out)
    assert "Tm_Primer" not in header, header


def test_export_all_rows_equal_wells_when_plate_drops_a_result(tmp_path, two_results_state):
    out_dir = tmp_path / "bundle"
    res = handle_export_all({"output_dir": str(out_dir), "mappings": _payload("A2V"),
                             "artefact_kinds": []})
    xlsx = sorted(out_dir.rglob("*_platemap.xlsx"))
    assert xlsx, res
    assert _expected_ids(xlsx[0]) == ["A2V"]


def test_export_excel_plate_of_only_rescue_wells_still_gets_one_row_per_well(
    tmp_path, two_results_state
):
    # V42I has a primer on the plate and no design result. Filtering the results
    # to the plate leaves none, and the sheet must still carry the well.
    out = tmp_path / "plate.xlsx"
    handle_export_excel({"filepath": str(out), "mappings": _payload("V42I")})
    assert _expected_ids(out) == ["V42I"]
