"""Tests for the ``mame.activity.build_evolvepro_input`` RPC handler.

Synthetic xlsx fixtures only (no external absolute paths). Verifies that the
handler validates params, returns the documented response shape, and that the
method is registered in the dispatcher.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from sidecar_mame.handlers.activity import handle_build_evolvepro_input


def _make_layout(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    ws.append(["V5F", "A1"])
    ws.append(["V10L", "B1"])
    ws.append(["WT", "H12"])
    wb.save(str(tmp_path / "layout.xlsx"))
    return tmp_path / "layout.xlsx"


def _make_gc(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    ws.append(["A1", 1.0])
    ws.append(["B1", 1.1])
    wb.save(str(tmp_path / "gc.xlsx"))
    return tmp_path / "gc.xlsx"


def _block(ws, name: str, area: float) -> None:
    ws.append(["Signal:", "FID1B"])
    ws.append(["Area", "Sample Name"])
    ws.append([area, name])
    ws.append(["Sum", area])
    ws.append([])


def _make_rep_batch(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    # rep1 for IDs 1,2; WT1; rep2; WT2; rep3; WT3
    for rep in range(3):
        for base_id in (1, 2):
            suffix = "" if rep == 0 else f"-{rep + 1}"
            _block(ws, f"{base_id}{suffix}", 1.0 + 0.1 * rep)
        _block(ws, f"WT{rep + 1}", 1.0)
    wb.save(str(tmp_path / "rep.xlsx"))
    return tmp_path / "rep.xlsx"


def _make_prev(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Variant", "activity"])
    ws.append(["5F", 1.8])
    ws.append(["10L", 1.4])
    ws.append(["WT", 1.0])
    wb.save(str(tmp_path / "prev.xlsx"))
    return tmp_path / "prev.xlsx"


def _make_expected(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "expected_mutations"
    ws.append([
        "mutant_id",
        "position",
        "wt_aa",
        "mt_aa",
        "wt_codon",
        "mt_codon",
        "group_id",
        "primer_set_ref",
        "notation_type",
        "status",
    ])
    ws.append(["V5F", 5, "V", "F", "", "", "", "V5F", "substitution", "DESIGNED"])
    ws.append(["V10L", 10, "V", "L", "", "", "", "V10L", "substitution", "DESIGNED"])
    wb.save(str(tmp_path / "expected.xlsx"))
    return tmp_path / "expected.xlsx"


def test_handler_returns_documented_shape(tmp_path: Path):
    out = tmp_path / "out.xlsx"
    res = handle_build_evolvepro_input({
        "layout_xlsx": str(_make_layout(tmp_path)),
        "gc_data_xlsx": str(_make_gc(tmp_path)),
        "rep_batch_xlsx": str(_make_rep_batch(tmp_path)),
        "prev_evolvepro_xlsx": str(_make_prev(tmp_path)),
        "output_xlsx": str(out),
    })

    for key in (
        "output_path",
        "n_variants",
        "n_authoritative",
        "n_fallback_only",
        "mapping_audit",
        "mapping_audit_path",
        "prev_descending",
        "warnings",
        "swap_warnings",
        "label_audit",
    ):
        assert key in res, f"missing response key: {key}"

    assert res["output_path"] == str(out)
    assert Path(res["output_path"]).exists()
    assert res["n_variants"] == 2
    assert res["n_authoritative"] == 2
    assert isinstance(res["mapping_audit"], list)
    assert res["mapping_audit"][0] == {"id": 1, "variant": "5F", "well": "A01"}
    assert isinstance(res["warnings"], list)
    assert isinstance(res["swap_warnings"], list)
    assert Path(res["mapping_audit_path"]).exists()
    # No verdict_xlsx supplied -> the label audit never ran.
    assert res["label_audit"] is None
    json.dumps(res)  # the whole response, including label_audit, must serialise


def test_handler_numeric_primary_writes_mapping_audit_in_decode_order(tmp_path: Path):
    out = tmp_path / "numeric.xlsx"

    res = handle_build_evolvepro_input({
        "round1_rep_batch_xlsx": str(_make_rep_batch(tmp_path)),
        "expected_mutations_xlsx": str(_make_expected(tmp_path)),
        "remeasure_rep_batch_xlsx": str(_make_rep_batch(tmp_path)),
        "output_xlsx": str(out),
    })

    expected_rows = [
        {"id": 1, "variant": "5F", "well": "A1"},
        {"id": 2, "variant": "10L", "well": "B1"},
    ]
    assert res["primary_source"] == "numeric_report"
    assert res["confirmation_source"] == "numeric_subset"
    assert res["mapping_audit"] == expected_rows
    audit_path = Path(res["mapping_audit_path"])
    assert audit_path.exists()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["mapping"] == expected_rows


def test_handler_rejects_missing_input(tmp_path: Path):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        handle_build_evolvepro_input({
            "layout_xlsx": str(tmp_path / "does_not_exist.xlsx"),
            "gc_data_xlsx": str(_make_gc(tmp_path)),
            "rep_batch_xlsx": str(_make_rep_batch(tmp_path)),
            "prev_evolvepro_xlsx": str(_make_prev(tmp_path)),
            "output_xlsx": str(tmp_path / "out.xlsx"),
        })


def test_method_registered_in_dispatcher():
    from sidecar_mame.dispatcher import _METHODS

    assert "mame.activity.build_evolvepro_input" in _METHODS
    assert _METHODS["mame.activity.build_evolvepro_input"] is (
        handle_build_evolvepro_input
    )


def test_handler_rank_mode_two_files_is_provisional(tmp_path: Path):
    """layout + GC data alone must build, flagged provisional (no confirmation)."""
    out = tmp_path / "out.xlsx"
    res = handle_build_evolvepro_input({
        "layout_xlsx": str(_make_layout(tmp_path)),
        "gc_data_xlsx": str(_make_gc(tmp_path)),
        "output_xlsx": str(out),
    })

    assert res["mode"] == "rank"
    assert res["confidence"] == "provisional"
    assert res["output_path"] == str(out)
    assert Path(res["output_path"]).exists()
    assert res["n_variants"] == 2
    assert res["n_authoritative"] == 0
    assert res["n_fallback_only"] == 2

# ---------------------------------------------------------------------------
# Phase 2: label_audit passthrough + allow_label_mismatch plumbing
# ---------------------------------------------------------------------------


def _make_verdict_with_observed_aa(tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    """Write a minimal verdict xlsx. rows: [(well_id, mutant_id, verdict, observed_aa)]."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["well_id", "mutant_id", "verdict", "observed_aa"])
    for well, mutant_id, verdict, observed_aa in rows:
        ws.append([well, mutant_id, verdict, observed_aa])
    wb.save(str(tmp_path / "verdict.xlsx"))
    return tmp_path / "verdict.xlsx"


def test_handler_label_audit_populated_and_serialises(tmp_path: Path):
    """verdict_xlsx + layout_xlsx together run the label audit; the response
    carries a JSON-serialisable dict (no leftover dataclass/tuple values)."""
    out = tmp_path / "out.xlsx"
    layout = _make_layout(tmp_path)  # V5F@A1, V10L@B1, WT@H12
    gc = _make_gc(tmp_path)
    # A01 (V5F) concordant; B01 (V10L) discordant (no observed change at all).
    verdict = _make_verdict_with_observed_aa(
        tmp_path,
        [
            ("A01", "V5F", "PASS", "V5F"),
            ("B01", "V10L", "WRONG_AA", ""),
        ],
    )

    res = handle_build_evolvepro_input({
        "layout_xlsx": str(layout),
        "gc_data_xlsx": str(gc),
        "output_xlsx": str(out),
        "verdict_xlsx": str(verdict),
    })

    assert res["label_audit"] is not None
    audit = res["label_audit"]
    for key in (
        "discordant",
        "n_checked",
        "n_unevaluable",
        "is_closed_permutation",
        "cycles",
        "geometry",
    ):
        assert key in audit, f"missing label_audit key: {key}"

    assert audit["n_checked"] == 2
    assert len(audit["discordant"]) == 1
    finding = audit["discordant"][0]
    assert finding["well"] == "B01"
    assert finding["category"] == "not_introduced"
    assert finding["observed"] == []
    assert isinstance(finding["observed"], list)  # tuple flattened to list

    # Full response (nested dataclasses + tuples included) must be JSON-safe.
    json.dumps(res)


def _make_rep_batch_areas(
    tmp_path: Path, base_areas: dict[int, list[float]], wt_areas: list[float]
) -> Path:
    """Rep-batch xlsx with per-base-ID replicate areas (for swap fixtures)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    n_reps = max(len(v) for v in base_areas.values())
    for rep in range(n_reps):
        for base_id in sorted(base_areas):
            areas = base_areas[base_id]
            if rep >= len(areas):
                continue
            suffix = "" if rep == 0 else f"-{rep + 1}"
            _block(ws, f"{base_id}{suffix}", areas[rep])
        if rep < len(wt_areas):
            _block(ws, f"WT_{rep + 1}", wt_areas[rep])
    wb.save(str(tmp_path / "rep_batch_swap.xlsx"))
    return tmp_path / "rep_batch_swap.xlsx"


def _make_layout_3(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    ws.append(["V5F", "A1"])
    ws.append(["V10L", "B1"])
    ws.append(["S11E", "C1"])
    ws.append(["WT", "H12"])
    wb.save(str(tmp_path / "layout3.xlsx"))
    return tmp_path / "layout3.xlsx"


def _make_gc_3(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    ws.append(["A1", 1.0])
    ws.append(["B1", 1.1])
    ws.append(["C1", 0.9])
    wb.save(str(tmp_path / "gc3.xlsx"))
    return tmp_path / "gc3.xlsx"


def _make_prev_3(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Variant", "activity"])
    ws.append(["5F", 1.8])
    ws.append(["10L", 1.4])
    ws.append(["11E", 1.0])
    ws.append(["WT", 1.0])
    wb.save(str(tmp_path / "prev3.xlsx"))
    return tmp_path / "prev3.xlsx"


def _closed_cycle_params(tmp_path: Path, out: Path) -> dict:
    """Numeric-index confirmation whose closed 2-cycle (10L<->11E) reciprocally
    swaps prev-round values, same fixture shape as
    tests/mame/activity/test_label_audit.py::_closed_swap_fixture."""
    return {
        "layout_xlsx": str(_make_layout_3(tmp_path)),
        "gc_data_xlsx": str(_make_gc_3(tmp_path)),
        "rep_batch_xlsx": str(
            _make_rep_batch_areas(
                tmp_path,
                {1: [1.1, 1.1, 1.1], 2: [1.0, 1.0, 1.0], 3: [1.4, 1.4, 1.4]},
                [1.0, 1.0, 1.0],
            )
        ),
        "prev_evolvepro_xlsx": str(_make_prev_3(tmp_path)),
        "output_xlsx": str(out),
    }


def test_handler_closed_cycle_blocks_export_by_default(tmp_path: Path):
    out = tmp_path / "out.xlsx"
    params = _closed_cycle_params(tmp_path, out)

    with pytest.raises(ValueError, match="Label swap detected"):
        handle_build_evolvepro_input(params)
    assert not out.exists()


def test_handler_allow_label_mismatch_true_proceeds(tmp_path: Path):
    out = tmp_path / "out.xlsx"
    params = _closed_cycle_params(tmp_path, out)
    params["allow_label_mismatch"] = True

    res = handle_build_evolvepro_input(params)

    assert out.exists()
    assert any(w["severity"] == "error" for w in res["swap_warnings"])
    json.dumps(res)
