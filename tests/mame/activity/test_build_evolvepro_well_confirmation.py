"""Well-labeled replicate reports as the Step 4 confirmation source.

The bench re-measures the wells it picked and names each injection
``<well>-<replicate>`` (``A1-1``, ``A1-2``, ``A1-3``). Such a report carries no
``WT1`` block: wild-type is the well the run declared as WT. The GC run is
shared, so the same export also holds other experiments' samples.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

openpyxl = pytest.importorskip("openpyxl")

from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input
from kuma_core.mame.activity.detect_measurement_source import (
    CONFIRMATION_NUMERIC_IDS,
    CONFIRMATION_VARIANT_LABELS,
    CONFIRMATION_WELL_LABELS,
    detect_measurement_source,
)
from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows
from kuma_core.mame.export.excel_writer import _FINAL_HEADER

PLATE = [("V5F", "A01"), ("V10L", "B01"), ("WT", "H12")]

# A synthetic campaign: eleven re-measured wells and the WT well.
SHARED_RUN_WELLS = {
    "A1": "L10M", "F1": "P20Q", "A2": "T30V", "E2": "R40K", "F3": "G50D",
    "B4": "E60D", "C7": "V70I", "D7": "I80V", "E7": "V90I", "C8": "D100E",
    "G9": "H110A", "H12": "WT",
}
# Thirty-six sample names of other experiments that shared the GC run.
SHARED_RUN_UNRELATED = (
    [f"{prefix}-{rep}" for prefix in ("Other-A", "Other-B", "Other-C", "Other-D") for rep in (1, 2, 3)]
    + [
        f"Other2-{medium}{dose}-{rep}"
        for medium in ("X", "Y")
        for dose in ("0.05", "0.025", "0.01", "0.005", "0.0025", "0.0")
        for rep in (1, 2)
    ]
)


def _verdict(path: Path, rows: list[tuple[str, str]]) -> Path:
    """A verdict workbook with the Final sheet header the analyze step writes."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Final"
    ws.append(_FINAL_HEADER)
    for mutant, well in rows:
        row = dict.fromkeys(_FINAL_HEADER, "")
        row.update(well_id=well, mutant_id=mutant, verdict="PASS")
        ws.append([row[column] for column in _FINAL_HEADER])
    wb.save(path)
    return path


def _blocks(path: Path, samples: list[tuple[str, float]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for name, area in samples:
        ws.append(["Signal:", "FID1B"])
        ws.append(["Area", "Sample Name"])
        ws.append([area, name])
        ws.append(["Sum", area])
        ws.append([])
    wb.save(path)
    return path


def _rows(path: Path) -> dict[str, float]:
    return dict(read_evolvepro_rows(path))


@pytest.fixture
def run(tmp_path: Path) -> dict[str, Path]:
    return {
        "verdict": _verdict(tmp_path / "verdict.xlsx", PLATE),
        "screen": _blocks(
            tmp_path / "screen.xlsx", [("WT_1", 10.0), ("A1", 20.0), ("B1", 5.0)]
        ),
    }


def test_replicates_are_normalized_against_the_wt_well(tmp_path: Path, run):
    """WT mean is (9 + 11) / 2 = 10, so A1 reads 1.2, 1.8, 1.5 and means 1.5."""
    confirmation = _blocks(
        tmp_path / "confirm.xlsx",
        [("A1-1", 12.0), ("A1-2", 18.0), ("A1-3", 15.0), ("H12-1", 9.0), ("H12-2", 11.0)],
    )
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(
        out,
        round1_report_xlsx=run["screen"],
        remeasure_well_xlsx=confirmation,
        verdict_xlsx=run["verdict"],
    )

    assert _rows(out) == pytest.approx({"5F": 1.5, "10L": 0.5})
    assert result.variant_replicates["5F"] == pytest.approx([1.2, 1.8, 1.5])
    assert result.variant_replicates["10L"] == pytest.approx([0.5])
    assert (result.n_authoritative, result.n_fallback_only) == (1, 1)
    assert result.normalization_sources == [
        "round1_report_xlsx:report_wt",
        "remeasure_well_xlsx:report_wt",
    ]
    # The primary's own WT spread, untouched by the confirmation's WT well.
    assert result.wt_values == pytest.approx([1.0])
    assert not any("remeasure_well_xlsx" in warning for warning in result.warnings)


def test_a_bare_well_is_replicate_one_and_wt_rows_count_as_wt(tmp_path: Path, run):
    confirmation = _blocks(
        tmp_path / "confirm.xlsx", [("WT1", 10.0), ("A1", 30.0), ("A01-2", 10.0)]
    )
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(
        out,
        round1_report_xlsx=run["screen"],
        remeasure_well_xlsx=confirmation,
        verdict_xlsx=run["verdict"],
    )

    assert result.variant_replicates["5F"] == pytest.approx([3.0, 1.0])
    assert _rows(out)["5F"] == pytest.approx(2.0)


def test_unrelated_samples_and_unmapped_wells_are_skipped_with_a_warning(tmp_path: Path, run):
    confirmation = _blocks(
        tmp_path / "confirm.xlsx",
        [
            ("A1-1", 15.0),
            ("H12-1", 10.0),
            ("C5-1", 99.0),
            ("Other-A-1", 0.1),
            ("Other2-Y0.0-2", 0.2),
        ],
    )
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(
        out,
        round1_report_xlsx=run["screen"],
        remeasure_well_xlsx=confirmation,
        verdict_xlsx=run["verdict"],
    )

    assert _rows(out) == pytest.approx({"5F": 1.5, "10L": 0.5})
    assert (
        "remeasure_well_xlsx excluded 2 row(s) (non_well_sample): "
        "'Other-A-1' (block 4, row 18), 'Other2-Y0.0-2' (block 5, row 23)"
    ) in result.warnings
    assert result.exclusion_reason_counts["non_well_sample"] == 2
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert {
        (row["sample_name"], row["block_index"], row["row_index"], row["reason"])
        for row in manifest["excluded_rows"]
    } >= {("Other-A-1", 4, 18, "non_well_sample"), ("C5-1", 3, 13, "unmapped_well")}
    assert (
        "remeasure_well_xlsx has 1 well(s) absent from verdict_xlsx: C05"
    ) in result.warnings


def test_a_report_without_any_wt_area_is_refused(tmp_path: Path, run):
    confirmation = _blocks(tmp_path / "confirm.xlsx", [("A1-1", 12.0), ("A1-2", 18.0)])

    with pytest.raises(ValueError, match="remeasure_well_xlsx has no WT areas: declare the WT well"):
        build_evolvepro_input(
            tmp_path / "out.xlsx",
            round1_report_xlsx=run["screen"],
            remeasure_well_xlsx=confirmation,
            verdict_xlsx=run["verdict"],
        )
    assert not (tmp_path / "out.xlsx").exists()


@pytest.mark.parametrize(
    "names",
    [
        ("remeasure_report_xlsx", "remeasure_numeric_xlsx", "remeasure_well_xlsx"),
        ("remeasure_report_xlsx", "remeasure_well_xlsx"),
        ("remeasure_numeric_xlsx", "remeasure_well_xlsx"),
    ],
)
def test_confirmation_sources_are_mutually_exclusive(tmp_path: Path, run, names):
    with pytest.raises(ValueError, match="at most one confirmation source"):
        build_evolvepro_input(
            tmp_path / "out.xlsx",
            round1_report_xlsx=run["screen"],
            verdict_xlsx=run["verdict"],
            **{name: run["screen"] for name in names},
        )


def _shared_run_samples(with_unrelated: bool) -> list[tuple[str, float]]:
    """Three replicates per well. Well k has areas k+1, k+1.1, k+1.2; WT is 1."""
    samples: list[tuple[str, float]] = []
    for index, well in enumerate(SHARED_RUN_WELLS):
        base = 1.0 if SHARED_RUN_WELLS[well] == "WT" else index + 2.0
        samples += [(f"{well}-{rep}", base + 0.1 * (rep - 1)) for rep in (1, 2, 3)]
    if with_unrelated:
        samples += [(name, 0.2) for name in SHARED_RUN_UNRELATED]
    return samples


def test_the_shared_run_export_overrides_every_remeasured_variant(tmp_path: Path):
    """The shape of a shared-run export: 36 well labels and 36 unrelated samples."""
    plate = [(mutant, well) for well, mutant in SHARED_RUN_WELLS.items()]
    verdict = _verdict(tmp_path / "verdict.xlsx", plate)
    screen = _blocks(
        tmp_path / "screen.xlsx",
        [("WT1", 1.0)] + [(well, 0.5) for well in SHARED_RUN_WELLS if SHARED_RUN_WELLS[well] != "WT"],
    )
    samples = _shared_run_samples(with_unrelated=True)
    assert len(samples) == 72 and len(SHARED_RUN_UNRELATED) == 36
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(
        out,
        round1_report_xlsx=screen,
        remeasure_well_xlsx=_blocks(tmp_path / "confirm.xlsx", samples),
        verdict_xlsx=verdict,
    )

    # WT well mean is (1.0 + 1.1 + 1.2) / 3 = 1.1.
    expected = {
        mutant[1:]: (index + 2.1) / 1.1
        for index, mutant in enumerate(SHARED_RUN_WELLS.values())
        if mutant != "WT"
    }
    assert len(expected) == 11
    assert _rows(out) == pytest.approx(expected)
    assert (result.n_authoritative, result.n_fallback_only) == (11, 0)
    assert all(len(replicates) == 3 for replicates in result.variant_replicates.values())
    assert sum("excluded 36 row(s) (non_well_sample)" in warning for warning in result.warnings) == 1
    assert result.exclusion_reason_counts["non_well_sample"] == 36

    # The same export with the unrelated samples removed gives the same workbook.
    cleaned_out = tmp_path / "cleaned.xlsx"
    cleaned = build_evolvepro_input(
        cleaned_out,
        round1_report_xlsx=screen,
        remeasure_well_xlsx=_blocks(tmp_path / "cleaned_in.xlsx", _shared_run_samples(with_unrelated=False)),
        verdict_xlsx=verdict,
    )
    assert _rows(cleaned_out) == _rows(out)
    assert not any("excluded" in warning for warning in cleaned.warnings)


def test_a_detected_confirmation_type_is_one_its_builder_path_reads(tmp_path: Path, run):
    """Whatever the confirmation slot names, the matching kwarg accepts."""
    kwarg = {
        CONFIRMATION_WELL_LABELS: "remeasure_well_xlsx",
        CONFIRMATION_VARIANT_LABELS: "remeasure_report_xlsx",
        CONFIRMATION_NUMERIC_IDS: "remeasure_numeric_xlsx",
    }
    files = {
        CONFIRMATION_WELL_LABELS: [("A1-1", 15.0), ("H12-1", 10.0), ("Other-A-1", 0.1)],
        CONFIRMATION_VARIANT_LABELS: [("WT1", 10.0), ("V5F", 15.0)],
        # ID 1 is the one variant the screen put above wild-type.
        CONFIRMATION_NUMERIC_IDS: [("WT1", 10.0), ("1", 14.0), ("1-2", 16.0)],
    }
    layout = tmp_path / "layout.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["Mutant", "Well Pos."])
    for mutant, well in PLATE:
        wb.active.append([mutant, well])
    wb.save(layout)

    for expected, samples in files.items():
        report = _blocks(tmp_path / f"{expected}.xlsx", samples)
        detection = detect_measurement_source(report, slot="confirmation")
        assert detection.candidates == [expected]
        assert detection.ambiguous is False
        out = tmp_path / f"{expected}_out.xlsx"
        confirmation: dict[str, Any] = {kwarg[detection.candidates[0]]: report}
        result = build_evolvepro_input(
            out,
            round1_report_xlsx=run["screen"],
            layout_xlsx=layout,
            verdict_xlsx=run["verdict"],
            **confirmation,
        )
        assert _rows(out) == pytest.approx({"5F": 1.5, "10L": 0.5})
        assert result.n_authoritative == 1
