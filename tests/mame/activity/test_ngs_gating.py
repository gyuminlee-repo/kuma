"""Strict NGS eligibility behavior for unified Step 3 exports."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

openpyxl = pytest.importorskip("openpyxl")

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows
from kuma_core.mame.activity.verdict_ngs import parse_verdict_rows


def _layout(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    ws.append(["V5F", "A1"])
    ws.append(["V10L", "B1"])
    wb.save(path)
    return path


def _verdict(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["well_id", "mutant_id", "verdict"])
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _activity(path: Path, rows: list[dict[str, object]] | None = None) -> Path:
    pd.DataFrame(rows or [
        {"well": "WT_1", "value": 1.0},
        {"well": "A1", "value": 1.2},
        {"well": "B1", "value": 0.8},
    ]).to_csv(path, index=False)
    return path


def _build(tmp_path: Path, verdict: Path, *, activity: Path | None = None, output: str = "out.xlsx"):
    return build_evolvepro_input(
        tmp_path / output,
        activity_path=activity or _activity(tmp_path / "activity.csv"),
        layout_xlsx=_layout(tmp_path / "layout.xlsx"),
        verdict_xlsx=verdict,
    )


def test_only_explicit_pass_evidence_is_eligible(tmp_path: Path):
    verdict = _verdict(tmp_path / "verdict.xlsx", [
        ("A01", "V5F", "PASS"),
        ("B01", "V10L", "FALLBACK"),
    ])
    result = _build(tmp_path, verdict)

    assert result.n_ngs_excluded == 1
    assert result.ngs_excluded == ["10L"]
    assert dict(read_evolvepro_rows(tmp_path / "out.xlsx")) == pytest.approx({"5F": 1.2})
    assert any("FALLBACK evidence" in warning for warning in result.warnings)


@pytest.mark.parametrize("status", ["WRONG_AA", "FALLBACK"])
def test_failed_or_fallback_verdict_cannot_pass(tmp_path: Path, status: str):
    verdict = _verdict(tmp_path / "verdict.xlsx", [
        ("A01", "V5F", status),
        ("B01", "V10L", "PASS"),
    ])
    result = _build(tmp_path, verdict)

    assert result.ngs_excluded == ["5F"]
    assert dict(read_evolvepro_rows(tmp_path / "out.xlsx")) == pytest.approx({"10L": 0.8})


def test_pass_row_marked_failed_is_excluded(tmp_path: Path):
    verdict = tmp_path / "verdict.xlsx"
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["well_id", "mutant_id", "verdict", "failed", "is_fallback"])
    worksheet.append(["A01", "V5F", "PASS", True, False])
    worksheet.append(["B01", "V10L", "PASS", False, False])
    workbook.save(verdict)

    result = _build(tmp_path, verdict)

    assert result.ngs_excluded == ["5F"]
    assert dict(read_evolvepro_rows(tmp_path / "out.xlsx")) == pytest.approx(
        {"10L": 0.8}
    )
    assert any("failed evidence" in warning for warning in result.warnings)


def test_missing_verdict_evidence_is_excluded_not_trusted(tmp_path: Path):
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "PASS")])
    result = _build(tmp_path, verdict)

    assert result.ngs_excluded == ["10L"]
    assert any("missing evidence" in warning for warning in result.warnings)


def test_conflicting_duplicate_well_evidence_is_non_evaluable(tmp_path: Path):
    verdict = _verdict(tmp_path / "verdict.xlsx", [
        ("A1", "V5F", "PASS"),
        ("A01", "V5F", "WRONG_AA"),
        ("B01", "V10L", "PASS"),
    ])

    parsed = parse_verdict_rows(verdict)
    result = _build(tmp_path, verdict)

    assert parsed["A01"].verdict == "CONFLICT"
    assert result.ngs_excluded == ["5F"]
    assert dict(read_evolvepro_rows(tmp_path / "out.xlsx")) == pytest.approx({"10L": 0.8})


def test_conflicting_duplicates_report_conflict_without_a_layout(tmp_path: Path):
    activity = _activity(
        tmp_path / "variants.csv",
        [
            {"variant": "WT_1", "value": 1.0},
            {"variant": "5F", "value": 1.2},
            {"variant": "10L", "value": 0.8},
        ],
    )
    verdict = _verdict(tmp_path / "verdict.xlsx", [
        ("A1", "V5F", "PASS"),
        ("A01", "V5F", "WRONG_AA"),
        ("B01", "V10L", "PASS"),
    ])

    result = build_evolvepro_input(
        tmp_path / "out.xlsx",
        activity_path=activity,
        verdict_xlsx=verdict,
    )

    assert result.ngs_excluded == ["5F"]
    assert result.exclusion_reason_counts == {"CONFLICT": 1}
    assert any("CONFLICT evidence" in warning for warning in result.warnings)


def test_all_non_evaluable_variants_fail_without_writing_output(tmp_path: Path):
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "WRONG_AA")])

    with pytest.raises(ValueError, match="No variants with explicit PASS"):
        _build(tmp_path, verdict)
    assert not (tmp_path / "out.xlsx").exists()


def test_multi_plate_variant_raw_normalization_is_deterministic(tmp_path: Path):
    rows = [
        {"plate_id": "P2", "variant": "5F", "value": 8.0},
        {"plate_id": "P1", "variant": "10L", "value": 2.0},
        {"plate_id": "P1", "variant": "WT_1", "value": 2.0},
        {"plate_id": "P2", "variant": "WT1", "value": 4.0},
        {"plate_id": "P1", "variant": "5F", "value": 4.0},
        {"plate_id": "P2", "variant": "10L", "value": 4.0},
    ]
    verdict = _verdict(tmp_path / "verdict.xlsx", [("A01", "V5F", "PASS"), ("B01", "V10L", "PASS")])
    first = _build(tmp_path, verdict, activity=_activity(tmp_path / "first.csv", rows), output="first.xlsx")
    second = _build(tmp_path, verdict, activity=_activity(tmp_path / "second.csv", list(reversed(rows))), output="second.xlsx")

    assert first.n_variants == second.n_variants == 2
    assert read_evolvepro_rows(tmp_path / "first.xlsx") == read_evolvepro_rows(tmp_path / "second.xlsx")
    assert dict(read_evolvepro_rows(tmp_path / "first.xlsx")) == pytest.approx({"5F": 2.0, "10L": 1.0})
