"""Absent mappings and explicitly empty mappings must not be conflated.

``mappings`` is ``Optional[list[PlateMappingItem]] = None`` on every export
params model (``ExportExcelParams``, ``ExportMappingParams``,
``ExportMappingDryRunParams``, ``ExportAllParams``), with no validator coercing
``None`` to ``[]``, so the two are distinguishable at the handler layer:

  * ``None``  -> the caller said nothing, fall back to ``_core._state``.
  * ``[]``    -> the caller states there is no plate layout, honour it.

Under a truthiness test (``if p.mappings:``) the second case silently took the
first branch, exporting whatever the sidecar state happened to hold while the
manifest recorded ``mappings_source: "state"``, contradicting a caller that
believed it had sent a payload.

Every exporter these handlers reach accepts an empty list and writes a
header-only file, so honouring the empty payload is well defined rather than a
broken artifact; the two dry-run handlers already did exactly this.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kuma_core.kuro.mutation import Mutation
from kuma_core.kuro.overlap import OverlapWindow
from kuma_core.kuro.plate_mapper import PlateMapping
from kuma_core.kuro.sdm_engine import SdmPrimerResult
from sidecar_kuro.core import _state, _state_lock
from sidecar_kuro.handlers.export import (
    handle_export_all,
    handle_export_echo_mapping_dry_run,
    handle_export_excel,
    handle_export_janus_mapping_dry_run,
    handle_export_mapping,
)
from sidecar_kuro.models import (
    ExportAllParams,
    ExportExcelParams,
    ExportMappingDryRunParams,
    ExportMappingParams,
)


#: Sequences carried by both the state design result and the state plate map, so
#: the two describe the same primer pair.
_FWD_SEQ = "ACGTACGTACGTAA"
_REV_SEQ = "TTACGTACGTACGT"


def _design_result(raw: str) -> SdmPrimerResult:
    """One real design result, the smallest that survives the export path.

    A real ``SdmPrimerResult`` rather than a stub: the expected_mutations sheet
    reads the full ``Mutation`` field set, ``handle_export_excel`` takes
    ``overlap_mode`` off ``results[0]``, and a stub would only be assignable to
    ``_state.results`` by making the type checker look away.
    """
    return SdmPrimerResult(
        mutation=Mutation(
            raw=raw,
            wt_aa="Q",
            position=232,
            mt_aa="A",
            codon_start=693,
            wt_codon="CAG",
            mt_codon="GCG",
        ),
        forward_seq=_FWD_SEQ,
        reverse_seq=_REV_SEQ,
        forward_binding=_FWD_SEQ,
        reverse_binding=_REV_SEQ,
        overlap_window=OverlapWindow(
            sequence=_FWD_SEQ, start=0, end=len(_FWD_SEQ), codon_offset=0
        ),
        tm_fwd=60.0,
        tm_rev=60.0,
        tm_overlap=55.0,
        tm_condition_met=True,
    )


def _state_mappings() -> list[PlateMapping]:
    """Two wells that exist ONLY in sidecar state, never in any payload here.

    The primer names are the marker the assertions look for: if a handler falls
    back to state after being handed an empty list, these names turn up in the
    export.
    """
    return [
        PlateMapping(
            well="A1",
            primer_name="STATEONLY_F",
            sequence=_FWD_SEQ,
            primer_type="forward",
            mutation="STATEONLY",
        ),
        PlateMapping(
            well="A2",
            primer_name="STATEONLY_R",
            sequence=_REV_SEQ,
            primer_type="reverse",
            mutation="STATEONLY",
        ),
    ]


@pytest.fixture
def populated_state():
    """Sidecar state holding a design, so the fallback branch has something to
    fall back TO. Without it the two branches are indistinguishable.
    """
    with _state_lock:
        saved = (
            list(_state.results),
            list(_state.plate_mappings),
            dict(_state.dedup_info) if _state.dedup_info else {},
            _state.design_provenance,
            list(_state.interventions),
        )
        _state.results = [_design_result("STATEONLY")]
        _state.plate_mappings = _state_mappings()
        _state.dedup_info = {_REV_SEQ: ["STATEONLY"]}
        _state.design_provenance = None
        _state.interventions = []
    yield
    with _state_lock:
        (
            _state.results,
            _state.plate_mappings,
            _state.dedup_info,
            _state.design_provenance,
            _state.interventions,
        ) = saved


# ---------------------------------------------------------------------------
# Ground truth: the models really do keep None and [] apart
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "model",
    [ExportExcelParams, ExportMappingParams, ExportMappingDryRunParams, ExportAllParams],
)
def test_models_do_not_coerce_none_to_empty_list(model, tmp_path):
    """If any model coerced None to [], the distinction below would be fiction."""
    base = {
        ExportExcelParams: {"filepath": str(tmp_path / "x.xlsx")},
        ExportMappingParams: {"filepath": str(tmp_path / "x.csv")},
        ExportMappingDryRunParams: {},
        ExportAllParams: {"output_dir": str(tmp_path)},
    }[model]

    assert model(**base).mappings is None
    assert model(**base, mappings=[]).mappings == []


# ---------------------------------------------------------------------------
# handle_export_excel
# ---------------------------------------------------------------------------

def _xlsx_cell_text(path: Path) -> list[str]:
    import openpyxl

    wb = openpyxl.load_workbook(path)
    text: list[str] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            text.extend(str(c) for c in row if c is not None)
    return text


def test_export_excel_empty_payload_does_not_fall_back_to_state(
    tmp_path, populated_state
):
    out = tmp_path / "empty.xlsx"
    handle_export_excel({"filepath": str(out), "mappings": []})

    # Primer NAMES, not the mutation id. handle_export_excel documents that the
    # design rows always come from _core._state.results on both branches, so the
    # expected_mutations sheet naming the state mutation is correct and is not
    # what this test is about. Only the well layout may arrive as a payload, and
    # the layout is what carries STATEONLY_F / STATEONLY_R.
    cells = _xlsx_cell_text(out)
    leaked = [c for c in cells if "STATEONLY_" in c]
    assert leaked == [], (
        "export_excel with mappings=[] leaked the sidecar state plate map into "
        f"the workbook: {leaked!r}"
    )


def test_export_excel_empty_payload_records_payload_as_mappings_source(
    tmp_path, populated_state
):
    out = tmp_path / "empty_src.xlsx"
    handle_export_excel({"filepath": str(out), "mappings": []})

    extra = json.loads((tmp_path / "empty_src.run.json").read_text())["extra"]
    assert extra["mappings_source"] == "payload", (
        "manifest recorded mappings_source=%r for an explicitly empty payload; "
        "the caller supplied the layout, so the manifest must say payload"
        % extra["mappings_source"]
    )


def test_export_excel_absent_mappings_still_uses_state(tmp_path, populated_state):
    """The None case keeps its old behaviour: fall back, and say so."""
    out = tmp_path / "absent.xlsx"
    handle_export_excel({"filepath": str(out)})

    cells = _xlsx_cell_text(out)
    assert any("STATEONLY_" in c for c in cells), (
        "export_excel with mappings absent failed to fall back to the state "
        f"plate map: {cells!r}"
    )
    extra = json.loads((tmp_path / "absent.run.json").read_text())["extra"]
    assert extra["mappings_source"] == "state"


# ---------------------------------------------------------------------------
# handle_export_mapping
# ---------------------------------------------------------------------------

def test_export_mapping_empty_payload_writes_no_transfer_rows(
    tmp_path, populated_state
):
    out = tmp_path / "echo.csv"
    result = handle_export_mapping({
        "filepath": str(out), "format": "echo", "mappings": [],
    })

    assert result["primer_count"] == 0, (
        "export_mapping with mappings=[] reported %d primers, so it generated a "
        "plate map from sidecar state instead of honouring the empty payload"
        % result["primer_count"]
    )
    body = out.read_text(encoding="utf-8")
    assert "STATEONLY" not in body, (
        f"state plate map leaked into the Echo csv: {body!r}"
    )


def test_export_mapping_empty_payload_records_payload_source(
    tmp_path, populated_state
):
    out = tmp_path / "echo_src.csv"
    handle_export_mapping({
        "filepath": str(out), "format": "echo", "mappings": [],
    })
    extra = json.loads((tmp_path / "echo_src.run.json").read_text())["extra"]
    assert extra["results_source"] == "payload", (
        "manifest recorded results_source=%r for an explicitly empty payload"
        % extra["results_source"]
    )


def test_export_mapping_absent_mappings_still_uses_state(tmp_path, populated_state):
    out = tmp_path / "echo_absent.csv"
    result = handle_export_mapping({"filepath": str(out), "format": "echo"})
    assert result["primer_count"] > 0
    extra = json.loads((tmp_path / "echo_absent.run.json").read_text())["extra"]
    assert extra["results_source"] == "state"


# ---------------------------------------------------------------------------
# handle_export_all
# ---------------------------------------------------------------------------

def test_export_all_empty_payload_does_not_fall_back_to_state(
    tmp_path, populated_state
):
    result = handle_export_all({"output_dir": str(tmp_path), "mappings": []})
    target = Path(result["output_dir"])

    fasta = next(target.glob("*_primers.fasta"))
    body = fasta.read_text(encoding="utf-8")
    assert body == "", (
        "export_all with mappings=[] wrote primers into the fasta, so it used "
        f"the sidecar state plate map: {body!r}"
    )

    run_json = json.loads(next(target.glob("*_run.json")).read_text())
    assert run_json["mappings"] == [], (
        f"run.json carried the state plate map: {run_json['mappings']!r}"
    )
    assert run_json["extra"]["mappings_source"] == "payload", (
        "run.json recorded mappings_source=%r for an explicitly empty payload"
        % run_json["extra"]["mappings_source"]
    )


def test_export_all_absent_mappings_still_uses_state(tmp_path, populated_state):
    result = handle_export_all({"output_dir": str(tmp_path)})
    target = Path(result["output_dir"])

    fasta = next(target.glob("*_primers.fasta"))
    assert "STATEONLY_F" in fasta.read_text(encoding="utf-8")
    run_json = json.loads(next(target.glob("*_run.json")).read_text())
    assert run_json["extra"]["mappings_source"] == "state"


# ---------------------------------------------------------------------------
# Dry runs: already correct, pinned so a future "cleanup" cannot undo them
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "handler",
    [handle_export_echo_mapping_dry_run, handle_export_janus_mapping_dry_run],
)
def test_dry_run_empty_payload_returns_no_rows(handler, populated_state):
    assert handler({"mappings": []})["total"] == 0


@pytest.mark.parametrize(
    "handler",
    [handle_export_echo_mapping_dry_run, handle_export_janus_mapping_dry_run],
)
def test_dry_run_absent_mappings_uses_state(handler, populated_state):
    assert handler({})["total"] > 0
