"""Two-axis EVOLVEpro input assembly (build_evolvepro_input_axes).

The primary screen (axis A) and the confirmation (axis B) are independent, so
every A/B pair must be expressible:

    axis A, 1-replicate primary screen
        A1 raw Agilent report (well labels) + plate layout
        A2 pre-normalised GC sheet (well labels) + plate layout
        A3 previous EVOLVEpro file (variant labels)
    axis B, n-replicate confirmation
        B1 variant-labeled Agilent report
        B2 numeric base IDs + a rank source (previous EVOLVEpro file)
        none, provisional build

A1 + B2 is the combination the previous two-function API could not express: a
raw Agilent primary screen whose re-measure table carries numeric labels rather
than variant names.

Every fixture below encodes the same round so all six combinations must yield
the identical table: 5F confirmed at 1.0, 10L and 20M kept from the primary
screen at 0.8 and 0.4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

from kuma_core.mame.activity.build_evolvepro_input import (  # noqa: E402
    CONFIRM_NONE,
    CONFIRM_NUMERIC_INDEX,
    CONFIRM_VARIANT_LABELS,
    PRIMARY_GC_SHEET,
    PRIMARY_PREV_EVOLVEPRO,
    PRIMARY_RAW_REPORT,
    build_evolvepro_input,
    build_evolvepro_input_axes,
    build_evolvepro_input_from_reports,
)
from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_rows  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture builders (synthetic, one file per named path)
# ---------------------------------------------------------------------------

def _append_fid1b_block(ws, sample_name: str, area: float) -> None:
    ws.append(["Signal:", "FID1B"])
    ws.append(["Area", "Sample Name"])
    ws.append([area, sample_name])
    ws.append(["Sum", area])
    ws.append([])


def _write_layout(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    for mutant, well in (("V5F", "A1"), ("V10L", "B1"), ("V20M", "C1")):
        ws.append([mutant, well])
    ws.append(["WT", "H12"])
    wb.save(str(path))
    return path


def _write_raw_round1(path: Path) -> Path:
    """A1: well-labeled Agilent report. WT mean 0.5, so area x 2 = relative."""
    wb = openpyxl.Workbook()
    ws = wb.active
    _append_fid1b_block(ws, "WT_1", 0.50)
    _append_fid1b_block(ws, "WT_2", 0.50)
    _append_fid1b_block(ws, "A1", 0.80)  # 5F  -> 1.6
    _append_fid1b_block(ws, "B1", 0.40)  # 10L -> 0.8
    _append_fid1b_block(ws, "C1", 0.20)  # 20M -> 0.4
    wb.save(str(path))
    return path


def _write_gc_sheet(path: Path) -> Path:
    """A2: pre-normalised GC sheet, same baseline as the raw report."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    for well, rel in (("A1", 1.6), ("B1", 0.8), ("C1", 0.4)):
        ws.append([well, rel])
    wb.save(str(path))
    return path


def _write_evolvepro(path: Path) -> Path:
    """A3 baseline and B2 rank source: descending [Variant, activity]."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Variant", "activity"])
    for variant, activity in (("5F", 1.6), ("10L", 0.8), ("20M", 0.4)):
        ws.append([variant, activity])
    ws.append(["WT", 1.0])
    wb.save(str(path))
    return path


def _write_variant_remeasure(path: Path) -> Path:
    """B1: variant-labeled re-measure. WT mean 0.6, 5F reps -> 1.0/1.1/0.9."""
    wb = openpyxl.Workbook()
    ws = wb.active
    _append_fid1b_block(ws, "WT_1", 0.60)
    _append_fid1b_block(ws, "WT_2", 0.60)
    for area in (0.60, 0.66, 0.54):
        _append_fid1b_block(ws, "5F", area)
    wb.save(str(path))
    return path


def _write_rep_batch(path: Path) -> Path:
    """B2: numeric base ID 1 with three replicates. WT mean 1.0."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for suffix, area in (("", 1.0), ("-2", 1.1), ("-3", 0.9)):
        _append_fid1b_block(ws, f"1{suffix}", area)
    for i, area in enumerate((1.0, 1.0, 1.0), start=1):
        _append_fid1b_block(ws, f"WT{i}", area)
    wb.save(str(path))
    return path


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    return {
        "layout": _write_layout(tmp_path / "layout.xlsx"),
        "raw_round1": _write_raw_round1(tmp_path / "raw_round1.xlsx"),
        "gc": _write_gc_sheet(tmp_path / "gc.xlsx"),
        "round1_ep": _write_evolvepro(tmp_path / "round1_ep.xlsx"),
        "rank_ep": _write_evolvepro(tmp_path / "rank_ep.xlsx"),
        "remeasure": _write_variant_remeasure(tmp_path / "remeasure.xlsx"),
        "rep_batch": _write_rep_batch(tmp_path / "rep_batch.xlsx"),
        "out": tmp_path / "out.xlsx",
    }


def _axis_a_kwargs(files: dict[str, Path], axis_a: str) -> dict:
    if axis_a == PRIMARY_RAW_REPORT:
        return {
            "round1_report_xlsx": files["raw_round1"],
            "layout_xlsx": files["layout"],
        }
    if axis_a == PRIMARY_GC_SHEET:
        return {"gc_data_xlsx": files["gc"], "layout_xlsx": files["layout"]}
    return {"round1_evolvepro_xlsx": files["round1_ep"]}


def _axis_b_kwargs(files: dict[str, Path], axis_b: str) -> dict:
    if axis_b == CONFIRM_VARIANT_LABELS:
        return {"remeasure_report_xlsx": files["remeasure"]}
    if axis_b == CONFIRM_NUMERIC_INDEX:
        return {
            "rep_batch_xlsx": files["rep_batch"],
            "rank_evolvepro_xlsx": files["rank_ep"],
        }
    return {}


_AXIS_A = [PRIMARY_RAW_REPORT, PRIMARY_GC_SHEET, PRIMARY_PREV_EVOLVEPRO]
_AXIS_B = [CONFIRM_VARIANT_LABELS, CONFIRM_NUMERIC_INDEX]


# ---------------------------------------------------------------------------
# The six A x B combinations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("axis_a", _AXIS_A)
@pytest.mark.parametrize("axis_b", _AXIS_B)
def test_every_axis_pair_builds_the_same_table(files, axis_a, axis_b):
    result = build_evolvepro_input_axes(
        files["out"],
        **_axis_a_kwargs(files, axis_a),
        **_axis_b_kwargs(files, axis_b),
    )

    assert result.primary_source == axis_a
    assert result.confirmation_source == axis_b
    assert result.confidence == "confirmed"
    assert result.n_variants == 3
    assert result.n_authoritative == 1
    assert result.n_fallback_only == 2

    rows = {v: a for v, a in read_evolvepro_rows(files["out"])}
    assert set(rows) == {"5F", "10L", "20M"}
    assert rows["5F"] == pytest.approx(1.0)   # confirmation replaces baseline
    assert rows["10L"] == pytest.approx(0.8)  # baseline kept
    assert rows["20M"] == pytest.approx(0.4)


def test_raw_report_primary_with_numeric_index_confirmation(files):
    """A1 + B2, the combination the two-function API could not express.

    A raw Agilent primary screen (well labels, needs the plate layout) paired
    with a re-measure table that carries numeric ranks instead of variant names
    (needs the rank source). Neither legacy entry point accepted this pair.
    """
    result = build_evolvepro_input_axes(
        files["out"],
        round1_report_xlsx=files["raw_round1"],
        layout_xlsx=files["layout"],
        rep_batch_xlsx=files["rep_batch"],
        rank_evolvepro_xlsx=files["rank_ep"],
    )

    assert result.primary_source == PRIMARY_RAW_REPORT
    assert result.confirmation_source == CONFIRM_NUMERIC_INDEX
    # The numeric ID 1 resolved to the rank-1 variant of the rank source.
    assert [(m.id, m.variant) for m in result.mapping.rows] == [(1, "5F")]
    assert result.mapping.prev_descending is True
    # Baseline came from the raw report via the layout, so the wells are known.
    assert result.well_by_variant == {"5F": "A01", "10L": "B01", "20M": "C01"}

    rows = {v: a for v, a in read_evolvepro_rows(files["out"])}
    assert rows["5F"] == pytest.approx(1.0)
    assert rows["10L"] == pytest.approx(0.8)
    assert rows["20M"] == pytest.approx(0.4)


def test_bundled_mame_step3_sample_files_build_raw_primary_numeric_confirmation(
    tmp_path: Path,
):
    root = Path(__file__).resolve().parents[3] / "src-tauri" / "samples" / "mame"
    output = tmp_path / "mame_step3_sample_output.xlsx"

    result = build_evolvepro_input_axes(
        output,
        layout_xlsx=root / "06_mame_plate_layout.xlsx",
        round1_report_xlsx=root / "11_mame_gc_fid_round1_raw.xlsx",
        rep_batch_xlsx=root / "12_mame_agilent_numeric_index.xlsx",
        rank_evolvepro_xlsx=root / "08_mame_evolvepro_raw.xlsx",
    )

    assert result.primary_source == PRIMARY_RAW_REPORT
    assert result.confirmation_source == CONFIRM_NUMERIC_INDEX
    assert result.confidence == "confirmed"
    assert result.n_variants >= 6
    assert result.n_authoritative >= 6
    assert result.mapping.prev_descending is True

    rows = {v: a for v, a in read_evolvepro_rows(output)}
    assert set(rows) >= {"65A", "203Y", "65T", "64L", "206K", "66H"}
    assert all(activity > 0 for activity in rows.values())


def test_bundled_mame_step3_sample_files_cover_all_seeded_axis_options(
    tmp_path: Path,
):
    root = Path(__file__).resolve().parents[3] / "src-tauri" / "samples" / "mame"
    expected = {"65A", "203Y", "65T", "64L", "206K", "66H"}

    gc_result = build_evolvepro_input_axes(
        tmp_path / "gc_sheet_output.xlsx",
        layout_xlsx=root / "06_mame_plate_layout.xlsx",
        gc_data_xlsx=root / "10_mame_gc_prenormalised.xlsx",
    )
    assert gc_result.primary_source == PRIMARY_GC_SHEET
    assert gc_result.confirmation_source == CONFIRM_NONE
    assert {v for v, _ in read_evolvepro_rows(tmp_path / "gc_sheet_output.xlsx")} == expected

    variant_result = build_evolvepro_input_axes(
        tmp_path / "variant_labels_output.xlsx",
        layout_xlsx=root / "06_mame_plate_layout.xlsx",
        round1_report_xlsx=root / "11_mame_gc_fid_round1_raw.xlsx",
        remeasure_report_xlsx=root / "09_mame_agilent_rep_batch.xlsx",
    )
    assert variant_result.primary_source == PRIMARY_RAW_REPORT
    assert variant_result.confirmation_source == CONFIRM_VARIANT_LABELS
    assert variant_result.n_authoritative == 6
    assert {
        v for v, _ in read_evolvepro_rows(tmp_path / "variant_labels_output.xlsx")
    } == expected


@pytest.mark.parametrize("axis_a", _AXIS_A)
def test_provisional_build_for_each_primary_source(files, axis_a):
    """Axis B omitted: the baseline alone is written, flagged provisional."""
    result = build_evolvepro_input_axes(
        files["out"], **_axis_a_kwargs(files, axis_a)
    )

    assert result.primary_source == axis_a
    assert result.confirmation_source == CONFIRM_NONE
    assert result.confidence == "provisional"
    assert result.n_authoritative == 0
    assert result.n_fallback_only == 3
    assert result.swap_warnings == []

    rows = {v: a for v, a in read_evolvepro_rows(files["out"])}
    assert rows == pytest.approx({"5F": 1.6, "10L": 0.8, "20M": 0.4})


# ---------------------------------------------------------------------------
# Companion-input enforcement
# ---------------------------------------------------------------------------

def test_raw_report_without_layout_is_rejected(files):
    with pytest.raises(ValueError, match="requires layout_xlsx"):
        build_evolvepro_input_axes(
            files["out"],
            round1_report_xlsx=files["raw_round1"],
            remeasure_report_xlsx=files["remeasure"],
        )


def test_gc_sheet_without_layout_is_rejected(files):
    with pytest.raises(ValueError, match="requires layout_xlsx"):
        build_evolvepro_input_axes(
            files["out"],
            gc_data_xlsx=files["gc"],
            remeasure_report_xlsx=files["remeasure"],
        )


def test_numeric_index_without_rank_source_is_rejected(files):
    with pytest.raises(ValueError, match="requires rank_evolvepro_xlsx"):
        build_evolvepro_input_axes(
            files["out"],
            round1_report_xlsx=files["raw_round1"],
            layout_xlsx=files["layout"],
            rep_batch_xlsx=files["rep_batch"],
        )


def test_no_primary_source_is_rejected(files):
    with pytest.raises(ValueError, match="exactly one primary screen source"):
        build_evolvepro_input_axes(
            files["out"], remeasure_report_xlsx=files["remeasure"]
        )


def test_two_primary_sources_are_rejected(files):
    with pytest.raises(ValueError, match="exactly one primary screen source"):
        build_evolvepro_input_axes(
            files["out"],
            gc_data_xlsx=files["gc"],
            round1_evolvepro_xlsx=files["round1_ep"],
            layout_xlsx=files["layout"],
        )


def test_two_confirmation_sources_are_rejected(files):
    with pytest.raises(ValueError, match="at most one confirmation source"):
        build_evolvepro_input_axes(
            files["out"],
            gc_data_xlsx=files["gc"],
            layout_xlsx=files["layout"],
            remeasure_report_xlsx=files["remeasure"],
            rep_batch_xlsx=files["rep_batch"],
            rank_evolvepro_xlsx=files["rank_ep"],
        )


# ---------------------------------------------------------------------------
# The two public functions keep their behaviour
# ---------------------------------------------------------------------------

def test_legacy_rank_entry_point_matches_axis_a2_b2(files, tmp_path: Path):
    legacy_out = tmp_path / "legacy_rank.xlsx"
    legacy = build_evolvepro_input(
        files["layout"],
        files["gc"],
        legacy_out,
        rep_batch_xlsx=files["rep_batch"],
        prev_evolvepro_xlsx=files["rank_ep"],
    )
    axes = build_evolvepro_input_axes(
        files["out"],
        gc_data_xlsx=files["gc"],
        layout_xlsx=files["layout"],
        rep_batch_xlsx=files["rep_batch"],
        rank_evolvepro_xlsx=files["rank_ep"],
    )

    assert legacy.confidence == "confirmed"
    assert legacy.mapping_audit_path == legacy_out.with_suffix(".mapping.json")
    assert legacy.mapping_audit_path.exists()
    assert (legacy.n_variants, legacy.n_authoritative, legacy.n_fallback_only) == (
        axes.n_variants,
        axes.n_authoritative,
        axes.n_fallback_only,
    )
    assert read_evolvepro_rows(legacy_out) == read_evolvepro_rows(files["out"])


def test_legacy_reports_entry_point_matches_axis_a1_b1(files, tmp_path: Path):
    legacy_out = tmp_path / "legacy_reports.xlsx"
    legacy = build_evolvepro_input_from_reports(
        files["layout"], files["raw_round1"], files["remeasure"], legacy_out
    )
    axes = build_evolvepro_input_axes(
        files["out"],
        round1_report_xlsx=files["raw_round1"],
        layout_xlsx=files["layout"],
        remeasure_report_xlsx=files["remeasure"],
    )

    assert (legacy.n_variants, legacy.n_authoritative, legacy.n_fallback_only) == (
        axes.n_variants,
        axes.n_authoritative,
        axes.n_fallback_only,
    )
    assert legacy.well_by_variant == axes.well_by_variant
    assert legacy.n_ngs_excluded == 0
    assert read_evolvepro_rows(legacy_out) == read_evolvepro_rows(files["out"])


def test_legacy_reports_prev_evolvepro_baseline_matches_axis_a3_b1(
    files, tmp_path: Path
):
    legacy_out = tmp_path / "legacy_prev.xlsx"
    legacy = build_evolvepro_input_from_reports(
        None,
        None,
        files["remeasure"],
        legacy_out,
        prev_evolvepro_xlsx=files["round1_ep"],
    )
    axes = build_evolvepro_input_axes(
        files["out"],
        round1_evolvepro_xlsx=files["round1_ep"],
        remeasure_report_xlsx=files["remeasure"],
    )

    assert legacy.n_variants == axes.n_variants == 3
    assert read_evolvepro_rows(legacy_out) == read_evolvepro_rows(files["out"])


# ---------------------------------------------------------------------------
# RPC layer: params validation and handler dispatch for the axis pairs
# ---------------------------------------------------------------------------

def _params(files: dict[str, Path], **overrides) -> dict:
    base = {"output_xlsx": str(files["out"])}
    base.update({k: str(v) for k, v in overrides.items()})
    return base


def test_params_accept_raw_report_with_numeric_index(files):
    from sidecar_mame.models import BuildEvolveproInputParams

    p = BuildEvolveproInputParams.model_validate(
        _params(
            files,
            layout_xlsx=files["layout"],
            round1_report_xlsx=files["raw_round1"],
            rep_batch_xlsx=files["rep_batch"],
            prev_evolvepro_xlsx=files["rank_ep"],
        )
    )
    assert p.round1_report_xlsx == str(files["raw_round1"])
    assert p.rep_batch_xlsx == str(files["rep_batch"])
    assert p.gc_data_xlsx is None
    assert p.remeasure_report_xlsx is None


def test_params_accept_prev_evolvepro_baseline_with_numeric_index(files):
    """A3 + B2: the two EVOLVEpro inputs play different roles in one call."""
    from sidecar_mame.models import BuildEvolveproInputParams

    p = BuildEvolveproInputParams.model_validate(
        _params(
            files,
            round1_evolvepro_xlsx=files["round1_ep"],
            rep_batch_xlsx=files["rep_batch"],
            prev_evolvepro_xlsx=files["rank_ep"],
        )
    )
    assert p.round1_evolvepro_xlsx == str(files["round1_ep"])
    assert p.prev_evolvepro_xlsx == str(files["rank_ep"])


def test_params_reject_numeric_index_without_rank_source(files):
    from pydantic import ValidationError
    from sidecar_mame.models import BuildEvolveproInputParams

    with pytest.raises(ValidationError, match="requires prev_evolvepro_xlsx"):
        BuildEvolveproInputParams.model_validate(
            _params(
                files,
                layout_xlsx=files["layout"],
                round1_report_xlsx=files["raw_round1"],
                rep_batch_xlsx=files["rep_batch"],
            )
        )


def test_params_reject_rank_source_without_numeric_index(files):
    from pydantic import ValidationError
    from sidecar_mame.models import BuildEvolveproInputParams

    with pytest.raises(ValidationError, match="needs rep_batch_xlsx"):
        BuildEvolveproInputParams.model_validate(
            _params(
                files,
                layout_xlsx=files["layout"],
                round1_report_xlsx=files["raw_round1"],
                prev_evolvepro_xlsx=files["rank_ep"],
            )
        )


def test_params_reject_two_confirmation_sources(files):
    from pydantic import ValidationError
    from sidecar_mame.models import BuildEvolveproInputParams

    with pytest.raises(ValidationError, match="multiple confirmation sources"):
        BuildEvolveproInputParams.model_validate(
            _params(
                files,
                layout_xlsx=files["layout"],
                round1_report_xlsx=files["raw_round1"],
                remeasure_report_xlsx=files["remeasure"],
                rep_batch_xlsx=files["rep_batch"],
                prev_evolvepro_xlsx=files["rank_ep"],
            )
        )


def test_params_reject_two_primary_sources(files):
    from pydantic import ValidationError
    from sidecar_mame.models import BuildEvolveproInputParams

    with pytest.raises(ValidationError, match="multiple primary screen sources"):
        BuildEvolveproInputParams.model_validate(
            _params(
                files,
                layout_xlsx=files["layout"],
                round1_report_xlsx=files["raw_round1"],
                gc_data_xlsx=files["gc"],
                remeasure_report_xlsx=files["remeasure"],
            )
        )


def test_handler_builds_raw_report_with_numeric_index(files):
    """End-to-end A1 + B2 through the RPC handler."""
    from sidecar_mame.handlers.activity import handle_build_evolvepro_input

    resp = handle_build_evolvepro_input(
        _params(
            files,
            layout_xlsx=files["layout"],
            round1_report_xlsx=files["raw_round1"],
            rep_batch_xlsx=files["rep_batch"],
            prev_evolvepro_xlsx=files["rank_ep"],
        )
    )

    assert resp["n_variants"] == 3
    assert resp["n_authoritative"] == 1
    assert resp["n_fallback_only"] == 2
    assert resp["confidence"] == "confirmed"
    assert resp["mapping_audit"] == [{"id": 1, "variant": "5F", "well": "A01"}]
    assert Path(resp["mapping_audit_path"]).exists()
    assert resp["prev_descending"] is True

    rows = {v: a for v, a in read_evolvepro_rows(files["out"])}
    assert rows["5F"] == pytest.approx(1.0)
    assert rows["10L"] == pytest.approx(0.8)
    assert rows["20M"] == pytest.approx(0.4)


def test_handler_builds_prev_evolvepro_baseline_with_numeric_index(files):
    """End-to-end A3 + B2: baseline file and rank file are distinct inputs."""
    from sidecar_mame.handlers.activity import handle_build_evolvepro_input

    resp = handle_build_evolvepro_input(
        _params(
            files,
            round1_evolvepro_xlsx=files["round1_ep"],
            rep_batch_xlsx=files["rep_batch"],
            prev_evolvepro_xlsx=files["rank_ep"],
        )
    )

    assert resp["n_variants"] == 3
    assert resp["n_authoritative"] == 1
    rows = {v: a for v, a in read_evolvepro_rows(files["out"])}
    assert rows["5F"] == pytest.approx(1.0)
