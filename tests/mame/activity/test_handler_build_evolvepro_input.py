"""Unified Step 3 RPC integration tests."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

openpyxl = pytest.importorskip("openpyxl")

from sidecar_mame.handlers.activity import handle_build_evolvepro_input


_RESULT_KEYS = {
    "output_path", "n_variants", "n_authoritative", "n_fallback_only",
    "warnings", "mismatched", "n_ngs_excluded", "ngs_excluded",
    "gc_export_path", "label_audit", "manifest_path", "primary_format",
    "input_count", "evaluable_count", "exclusion_reason_counts",
    "normalization_sources", "evidence_hash", "artifact_hashes",
    "wt_values", "variant_replicates", "excluded_rows", "wt_rows",
}


def _layout(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    ws.append(["V5F", "A1"])
    ws.append(["V10L", "B1"])
    wb.save(path)
    return path


def _verdict(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["well_id", "mutant_id", "verdict"])
    ws.append(["A01", "V5F", "PASS"])
    ws.append(["B01", "V10L", "PASS"])
    wb.save(path)
    return path


def _gc(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    ws.append(["A1", 1.25])
    ws.append(["B1", 0.75])
    wb.save(path)
    return path


def _agilent(path: Path) -> Path:
    # The two WT blocks differ (mean 2.0), so a response that divided them by
    # their own mean is distinguishable from one that passed them through or
    # divided by some other constant.
    wb = openpyxl.Workbook()
    ws = wb.active
    for sample, area in (("WT_1", 1.6), ("WT_2", 2.4), ("A1", 3.0), ("B1", 1.0)):
        ws.append(["Signal:", "FID1B"])
        ws.append(["Area", "Sample Name"])
        ws.append([area, sample])
        ws.append(["Sum", area])
        ws.append([])
    wb.save(path)
    return path


def _assert_domain_response(response: dict, output: Path, count: int) -> None:
    assert set(response) == _RESULT_KEYS
    assert response["output_path"] == str(output)
    assert response["n_variants"] == count
    assert response["n_authoritative"] == 0
    assert response["n_fallback_only"] == count
    assert response["n_ngs_excluded"] == 0
    assert response["ngs_excluded"] == []
    assert response["gc_export_path"] == ""
    assert response["label_audit"] is not None
    assert Path(response["manifest_path"]).exists()
    assert response["input_count"] == count
    assert response["evaluable_count"] == count
    assert response["evidence_hash"].startswith("sha256:")
    assert response["artifact_hashes"][str(output)].startswith("sha256:")
    json.dumps(response)


def test_handler_builds_well_mapped_gc_primary_with_domain_shape(tmp_path: Path):
    output = tmp_path / "out.xlsx"
    response = handle_build_evolvepro_input({
        "gc_data_xlsx": str(_gc(tmp_path / "gc.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
        "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
        "output_xlsx": str(output),
    })

    _assert_domain_response(response, output, 2)


def test_handler_builds_raw_agilent_primary_with_layout_mapping(tmp_path: Path):
    output = tmp_path / "out.xlsx"
    response = handle_build_evolvepro_input({
        "round1_report_xlsx": str(_agilent(tmp_path / "round1.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
        "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
        "output_xlsx": str(output),
    })

    _assert_domain_response(response, output, 2)
    assert output.exists()


def test_handler_forwards_wt_replicates_from_the_raw_report(tmp_path: Path):
    """The response is the only route out: the workbook drops the WT rows."""
    output = tmp_path / "out.xlsx"
    response = handle_build_evolvepro_input({
        "round1_report_xlsx": str(_agilent(tmp_path / "round1.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
        "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
        "output_xlsx": str(output),
    })

    assert response["wt_values"] == pytest.approx([0.8, 1.2])


def test_handler_reports_no_wt_replicates_for_a_prenormalized_sheet(tmp_path: Path):
    output = tmp_path / "out.xlsx"
    response = handle_build_evolvepro_input({
        "gc_data_xlsx": str(_gc(tmp_path / "gc.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
        "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
        "output_xlsx": str(output),
    })

    assert response["wt_values"] == []


def test_handler_forwards_complete_build_arguments_to_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Every handler argument must reach the core, including numeric confirmation."""
    primary = tmp_path / "numeric-primary.xlsx"
    confirmation = tmp_path / "numeric-confirmation.xlsx"
    verdict = tmp_path / "verdict.xlsx"
    expected = tmp_path / "expected.xlsx"
    for path in (primary, confirmation, verdict, expected):
        path.touch()

    output = tmp_path / "output.xlsx"
    gc_export = tmp_path / "gc-export.xlsx"
    params = {
        "activity_path": None,
        "activity_scale": "relative_to_wt",
        "gc_data_xlsx": None,
        "round1_report_xlsx": None,
        "numeric_report_xlsx": str(primary),
        "remeasure_report_xlsx": None,
        "remeasure_numeric_xlsx": str(confirmation),
        "remeasure_well_xlsx": None,
        "verdict_xlsx": str(verdict),
        "resequence_evidence": None,
        "layout_xlsx": None,
        "expected_xlsx": str(expected),
        "output_xlsx": str(output),
        "mismatch_threshold": 0.25,
        "gc_export_xlsx": str(gc_export),
        "allow_label_mismatch": True,
        "excluded_rows": [],
    }
    forwarded: dict[str, object] = {}

    def spy(output_xlsx: str, **kwargs: object) -> SimpleNamespace:
        forwarded["output_xlsx"] = output_xlsx
        forwarded.update(kwargs)
        return SimpleNamespace(
            output_path=output,
            n_variants=0,
            n_authoritative=0,
            n_fallback_only=0,
            warnings=[],
            mismatched=[],
            n_ngs_excluded=0,
            ngs_excluded=[],
            gc_export_path=None,
            label_audit=None,
            manifest_path=None,
            primary_format="numeric",
            input_count=0,
            evaluable_count=0,
            exclusion_reason_counts={},
            normalization_sources={},
            evidence_hash="",
            artifact_hashes={},
            wt_values=[],
            variant_replicates={},
            excluded_rows=[],
            wt_rows=[],
        )

    core_module = importlib.import_module(
        "kuma_core.mame.activity.build_evolvepro_input"
    )
    monkeypatch.setattr(core_module, "build_evolvepro_input", spy)

    handle_build_evolvepro_input(params)

    assert forwarded == params


def test_handler_rejects_missing_required_verdict(tmp_path: Path):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        handle_build_evolvepro_input({
            "gc_data_xlsx": str(_gc(tmp_path / "gc.xlsx")),
            "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
            "output_xlsx": str(tmp_path / "out.xlsx"),
        })


def test_method_registered_in_dispatcher():
    from sidecar_mame.dispatcher import _METHODS

    assert _METHODS["mame.activity.build_evolvepro_input"] is handle_build_evolvepro_input


def test_handler_passes_operator_excluded_rows_and_reports_them(tmp_path: Path):
    """excluded_rows travels from the RPC to the manifest as operator_excluded."""
    output = tmp_path / "out.xlsx"
    params = {
        "round1_report_xlsx": str(_agilent(tmp_path / "round1.xlsx")),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
        "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
        "output_xlsx": str(output),
        # WT_2 sits in block 2, sheet row 8.
        "excluded_rows": [{
            "source": "round1_report_xlsx", "block_index": 2, "row_index": 8,
            "sample_name": "WT_2", "area": 2.4,
        }],
    }
    response = handle_build_evolvepro_input(params)
    assert set(response) == _RESULT_KEYS
    assert response["exclusion_reason_counts"] == {"operator_excluded": 1}
    assert [row["sample_name"] for row in response["wt_rows"]] == ["WT_1"]
    assert response["excluded_rows"][0]["reason"] == "operator_excluded"
    manifest = json.loads(Path(response["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["excluded_rows"][0]["block_index"] == 2

    params["excluded_rows"][0]["area"] = 2.5
    with pytest.raises(ValueError, match="no longer holds the row"):
        handle_build_evolvepro_input(params)
    params["excluded_rows"][0]["unexpected"] = 1
    with pytest.raises(ValueError):
        handle_build_evolvepro_input(params)


def test_preview_handler_lists_every_row_and_writes_nothing(tmp_path: Path):
    from sidecar_mame.dispatcher import _METHODS
    from sidecar_mame.handlers.activity import handle_preview_gc_rows

    assert _METHODS["mame.activity.preview_gc_rows"] is handle_preview_gc_rows
    report = _agilent(tmp_path / "round1.xlsx")
    before = sorted(path.name for path in tmp_path.iterdir())
    response = handle_preview_gc_rows({
        "round1_report_xlsx": str(report),
        "layout_xlsx": str(_layout(tmp_path / "layout.xlsx")),
        "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
    })
    assert set(response) == {"rows", "refusal", "selection_refusal"}
    assert response["refusal"] is None
    assert [(row["sample_name"], row["status"]) for row in response["rows"]] == [
        ("WT_1", "wt"), ("WT_2", "wt"), ("A1", "used"), ("B1", "used"),
    ]
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(before + ["layout.xlsx", "verdict.xlsx"])
    json.dumps(response)
    assert response["selection_refusal"] is None

    wt = [
        {key: row[key] for key in ("source", "row_index", "block_index", "sample_name", "area")}
        for row in response["rows"] if row["status"] == "wt"
    ]
    params = {
        "round1_report_xlsx": str(report),
        "layout_xlsx": str(tmp_path / "layout.xlsx"),
        "verdict_xlsx": str(tmp_path / "verdict.xlsx"),
    }
    selected = handle_preview_gc_rows({**params, "excluded_rows": wt})
    assert selected["selection_refusal"] is not None
    assert selected["rows"] == response["rows"]
    one = handle_preview_gc_rows({**params, "excluded_rows": wt[:1]})
    assert one["selection_refusal"] is None
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(before + ["layout.xlsx", "verdict.xlsx"])


def test_preview_handler_refuses_what_the_build_refuses(tmp_path: Path):
    from pydantic import ValidationError
    from sidecar_mame.handlers.activity import handle_preview_gc_rows

    with pytest.raises(ValidationError):
        handle_preview_gc_rows({
            "round1_report_xlsx": str(_agilent(tmp_path / "a.xlsx")),
            "gc_data_xlsx": str(_gc(tmp_path / "gc.xlsx")),
            "verdict_xlsx": str(_verdict(tmp_path / "verdict.xlsx")),
        })
