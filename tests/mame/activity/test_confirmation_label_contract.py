"""Synthetic boundary checks: source labels never silently become other wells."""
from pathlib import Path

import pytest
from openpyxl import Workbook

from kuma_core.mame.activity.build_evolvepro_input import (
    _RowLedger, _confirmation, _strip_confirmation_rep_suffix, _read_long, _WT_RE,
)
from kuma_core.mame.activity.constants import WT_PATTERN
from kuma_core.mame.activity.detect_measurement_source import detect_measurement_source
from kuma_core.mame.activity.plate_layout_xlsx import _normalise_well


def report(path: Path, labels: list[str]) -> Path:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for label in labels:
        sheet.append(["Signal:", "FID1B"])
        sheet.append(["Area", "Sample Name"])
        sheet.append([100, label])
        sheet.append(["Sum", 100])
        sheet.append([])
    book.save(path)
    return path


@pytest.mark.parametrize("label", ["WT", "wt", "Wt_1", "wt12", "WT_12"])
def test_wt_reader_and_classifier_share_contract(tmp_path: Path, label: str):
    assert _WT_RE is WT_PATTERN
    path = report(tmp_path / "report.xlsx", [label, "S11I-1"])
    assert _confirmation(path) == {"11I": [1.0]}
    detected = detect_measurement_source(path)
    assert detected.candidates == ["confirmationVariantLabels"]
    assert detected.evidence["n_sample_rows"] == 1
    assert detected.evidence["n_recognized_rows"] == 1
    assert detected.evidence["n_control_rows"] == 1
    assert "n_skipped_rows" not in detected.evidence
    assert detected.evidence["n_unique_labels"] == 1


@pytest.mark.parametrize("label", ["A0", "A00", "A13", "I1", "1-2", "A001", "A-1", "", "A1junk", "A1\n"])
def test_invalid_wells_are_refused_before_normalising(label: str):
    with pytest.raises(ValueError, match="96-well"):
        _normalise_well(label)


def test_every_96_coordinate_has_one_canonical_identity():
    wells = {_normalise_well(f"{row.lower()}{column}") for row in "ABCDEFGH" for column in range(1, 13)}
    assert len(wells) == 96
    assert wells == {f"{row}{column:02d}" for row in "ABCDEFGH" for column in range(1, 13)}


@pytest.mark.parametrize("label", ["S11I-0", "S11I--1", "S11I-1-2", "arbitrary-1", "S11I_Q12V-1", "A13-1", "1-2"])
def test_suffix_is_not_stripped_from_arbitrary_names(label: str):
    assert _strip_confirmation_rep_suffix(label) == label


@pytest.mark.parametrize("label, expected", [("S11I-1", "S11I"), ("11I-2", "11I"), ("A1-1", "A1"), ("h12-20", "h12")])
def test_explicit_canonical_replicate_suffix(label: str, expected: str):
    assert _strip_confirmation_rep_suffix(label) == expected


def test_well_confirmation_role_is_the_slot_and_mapping_is_unambiguous(tmp_path: Path):
    path = report(tmp_path / "wells.xlsx", ["WT", "a1", "A01-2", "H12-1"])
    primary = detect_measurement_source(path)
    assert primary.candidates == ["rawReport"]
    assert not primary.ambiguous
    confirmation = detect_measurement_source(path, slot="confirmation")
    assert confirmation.candidates == ["confirmationWellLabels"]
    assert not confirmation.ambiguous
    assert _confirmation(path, {"A01": "11I", "H12": "12V"}) == {"11I": [1.0, 1.0], "12V": [1.0]}
    # A well the mapping does not name has nothing tying it to this run: it is
    # set aside with its position, never mapped onto a neighbour.
    ledger = _RowLedger()
    assert _confirmation(path, {"A01": "11I"}, ledger=ledger) == {"11I": [1.0, 1.0]}
    assert [(row.source, row.sample_name, row.reason, row.block_index, row.row_index) for row in ledger.rows] == [
        ("remeasure_report_xlsx", "H12-1", "unmapped_well", 4, 18),
    ]


def test_confirmation_rejects_mixed_namespaces_and_empty_control_only(tmp_path: Path):
    with pytest.raises(ValueError, match="cannot mix"):
        _confirmation(report(tmp_path / "mixed.xlsx", ["WT", "A1", "S11I"]), {"A01": "11I"})
    with pytest.raises(ValueError, match="no measurement rows"):
        _confirmation(report(tmp_path / "empty.xlsx", ["WT"]))


def test_generic_reader_cannot_normalise_invalid_well_into_mapping(tmp_path: Path):
    path = tmp_path / "invalid.csv"
    path.write_text("well,value\nWT,1\nI1,2\n")
    ledger = _RowLedger()
    with pytest.raises(ValueError, match="no measurement rows outside WT records"):
        _read_long(path, "raw", {"I01": "11I"}, {}, [], ledger=ledger)
    assert [(row.sample_name, row.reason, row.row_index) for row in ledger.rows] == [("I1", "unrecognized_sample", 3)]


def test_conflicting_layout_identity_is_not_last_row_wins(tmp_path: Path):
    from kuma_core.mame.activity.build_evolvepro_input import _layout_maps
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Mutant", "Well Pos."])
    sheet.append(["S11I", "A1"])
    sheet.append(["Q12V", "A01"])
    path = tmp_path / "conflict.xlsx"
    book.save(path)
    with pytest.raises(ValueError, match="well.*conflicting sample identities"):
        _layout_maps(path)


def test_template_bundle_and_preview_use_exact_synthetic_workbook():
    import json
    root = Path(__file__).resolve().parents[3]
    name = "17_mame_well_labeled_confirmation.xlsx"
    template = root / "templates" / name
    bundled = root / "src-tauri" / "samples" / "mame" / name
    assert template.read_bytes() == bundled.read_bytes()
    resources = json.loads((root / "src-tauri" / "tauri.conf.json").read_text())["bundle"]["resources"]
    assert resources[f"samples/mame/{name}"] == f"samples/mame/{name}"
    assert detect_measurement_source(template).candidates == ["rawReport"]
    assert detect_measurement_source(template, slot="confirmation").candidates == ["confirmationWellLabels"]
    assert _confirmation(template, {"A01": "11I", "B01": "12V"}) == {"11I": [1.0, 1.0], "12V": [1.0]}


@pytest.mark.parametrize("first", ["WT", "WT_1", "blank", "unknown", "A11I"])
def test_layout_conflicts_are_rejected_before_skipping_control_or_unknown(first: str, tmp_path: Path):
    from kuma_core.mame.activity.build_evolvepro_input import _layout_maps
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Mutant", "Well Pos."])
    sheet.append([first, "A1"])
    sheet.append(["S11I", "A01"])
    path = tmp_path / "conflicting_layout.xlsx"
    book.save(path)
    with pytest.raises(ValueError, match="conflicting sample identities"):
        _layout_maps(path)


def test_replicated_raw_well_export_round_trips_through_gc_reader(tmp_path: Path):
    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
    from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["well_id", "mutant_id", "verdict"])
    sheet.append(["A1", "S11I", "PASS"])
    verdict = tmp_path / "verdict.xlsx"
    book.save(verdict)
    raw = report(tmp_path / "raw.xlsx", ["WT", "a1", "A1-1"])
    gc = tmp_path / "gc.xlsx"
    first = build_evolvepro_input(tmp_path / "first.xlsx", round1_report_xlsx=raw, verdict_xlsx=verdict, gc_export_xlsx=gc)
    second = build_evolvepro_input(tmp_path / "second.xlsx", gc_data_xlsx=gc, verdict_xlsx=verdict)
    assert read_evolvepro_rows(first.output_path) == read_evolvepro_rows(second.output_path)
    assert first.variant_replicates == second.variant_replicates == {"11I": [1.0, 1.0]}


@pytest.mark.parametrize("sample", ["A11I", "A11I-1"])
def test_confirmation_full_identity_cannot_conflict_with_declared_reference(sample: str, tmp_path: Path):
    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["well_id", "mutant_id", "verdict"])
    sheet.append(["A1", "S11I", "PASS"])
    verdict = tmp_path / "verdict.xlsx"
    book.save(verdict)
    primary = tmp_path / "primary.csv"
    primary.write_text("variant,value\n11I,1\n")
    confirmation = report(tmp_path / "confirmation.xlsx", ["WT", sample])
    output = tmp_path / "out.xlsx"
    with pytest.raises(ValueError, match="conflicts with declared identity"):
        build_evolvepro_input(output, activity_path=primary, activity_scale="relative_to_wt", remeasure_report_xlsx=confirmation, verdict_xlsx=verdict)
    assert not output.exists()
    for valid in ["S11I", "S11I-1", "11I", "11I-1"]:
        confirmation = report(tmp_path / "confirmation.xlsx", ["WT", valid])
        result = build_evolvepro_input(output, activity_path=primary, activity_scale="relative_to_wt", remeasure_report_xlsx=confirmation, verdict_xlsx=verdict)
        assert result.variant_replicates == {"11I": [1.0]}


@pytest.mark.parametrize("scale, wt_row", [("raw", "WT_1,10\n"), ("relative_to_wt", "")])
def test_long_primary_full_identity_cannot_conflict_with_declared_reference(scale: str, wt_row: str, tmp_path: Path):
    """The primary long-format reader keeps the reference residue a full label
    states, the same check the confirmation reader makes. A89W from another
    reference must not attach to this run's F89W through the short form 89W."""
    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["well_id", "mutant_id", "verdict"])
    sheet.append(["A1", "F89W", "PASS"])
    verdict = tmp_path / "verdict.xlsx"
    book.save(verdict)
    output = tmp_path / "out.xlsx"
    value = "20" if scale == "raw" else "2"
    primary = tmp_path / "primary.csv"
    primary.write_text(f"variant,value\n{wt_row}A89W,{value}\n")
    with pytest.raises(ValueError, match="conflicts with declared identity"):
        build_evolvepro_input(output, activity_path=primary, activity_scale=scale, verdict_xlsx=verdict)
    assert not output.exists()
    for valid in ["F89W", "89W"]:
        primary.write_text(f"variant,value\n{wt_row}{valid},{value}\n")
        result = build_evolvepro_input(output, activity_path=primary, activity_scale=scale, verdict_xlsx=verdict)
        assert result.variant_replicates == {"89W": [2.0]}


def _declared_inputs(tmp_path: Path, layout_mutant: str) -> tuple[Path, Path]:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["well_id", "mutant_id", "verdict"])
    sheet.append(["A1", "F89W", "PASS"])
    verdict = tmp_path / "verdict.xlsx"
    book.save(verdict)
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    sheet.append(["Mutant", "Well Pos."])
    sheet.append([layout_mutant, "A1"])
    sheet.append(["WT", "H12"])
    layout = tmp_path / f"layout_{layout_mutant}.xlsx"
    book.save(layout)
    return verdict, layout


def _block_report(path: Path, rows: list[tuple[str, float]]) -> Path:
    book = Workbook()
    sheet = book.active
    assert sheet is not None
    for label, area in rows:
        sheet.append(["Signal:", "FID1B"])
        sheet.append(["Area", "Sample Name"])
        sheet.append([area, label])
        sheet.append(["Sum", area])
        sheet.append([])
    book.save(path)
    return path


def _primary_input(fmt: str, tmp_path: Path) -> dict[str, object]:
    if fmt == "gc_data_xlsx":
        book = Workbook()
        sheet = book.active
        assert sheet is not None
        sheet.append(["Sample Name", "Area"])
        sheet.append(["A1", 2.0])
        path = tmp_path / "gc.xlsx"
        book.save(path)
        return {"gc_data_xlsx": path}
    if fmt == "round1_report_xlsx":
        return {"round1_report_xlsx": _block_report(tmp_path / "raw.xlsx", [("WT_1", 10), ("A1", 20)])}
    if fmt == "numeric_report_xlsx":
        return {"numeric_report_xlsx": _block_report(tmp_path / "num.xlsx", [("WT1", 10), ("1", 20)])}
    path = tmp_path / "long.csv"
    path.write_text("well,value\nWT_1,10\nA1,20\n")
    return {"activity_path": path}


@pytest.mark.parametrize("fmt", ["gc_data_xlsx", "round1_report_xlsx", "numeric_report_xlsx", "activity_path"])
def test_conflicting_declared_identities_refuse_every_primary_format(fmt: str, tmp_path: Path):
    """Layout A1=A89W and verdict A1=F89W declare two references for 89W. The
    declaration is checked once before any primary reader runs, so the
    well-labelled readers (which compare short identities only) cannot pass it."""
    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input

    verdict, conflicting = _declared_inputs(tmp_path, "A89W")
    output = tmp_path / "out.xlsx"
    with pytest.raises(ValueError, match="conflicting full identities"):
        build_evolvepro_input(output, verdict_xlsx=verdict, layout_xlsx=conflicting, **_primary_input(fmt, tmp_path))  # pyright: ignore[reportArgumentType]
    assert not output.exists()
    _, agreeing = _declared_inputs(tmp_path, "F89W")
    result = build_evolvepro_input(output, verdict_xlsx=verdict, layout_xlsx=agreeing, **_primary_input(fmt, tmp_path))  # pyright: ignore[reportArgumentType]
    assert list(result.variant_replicates) == ["89W"]
