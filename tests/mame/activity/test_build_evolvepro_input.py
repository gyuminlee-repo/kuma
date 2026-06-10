"""Tests for the 4-file EVOLVEpro input build pipeline.

All fixtures are synthetic xlsx files built in tmp_path (no external absolute
paths, no real-data row counts baked in). They reproduce the structural shapes
of the four MAME round inputs:

  (1) plate layout      [Mutant, Well Pos.]
  (2) GC data           [Sample Name (well), Area (relative)]
  (3) Agilent rep-batch FID1B block layout, numeric base/rep IDs + WT blocks
  (4) previous EVOLVEpro [Variant, activity] descending

The structural asserts verify:
  - rep1 is NOT lost (all three replicates preserved per base ID),
  - detect_format discriminates block+numeric (REP_BATCH) from
    block+well-names+'0' (STANDARD, the 251001 regression guard),
  - the rank ID->variant mapping is exactly nonwt_rows[id-1],
  - normalisation is area / mean(WT areas) within 1e-6,
  - the final EVOLVEpro file has the fixed header and the merged row count,
  - the mapping audit JSON round-trips with a prev_descending veto flag.
"""

from __future__ import annotations

from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")


# ---------------------------------------------------------------------------
# Synthetic fixture builders
# ---------------------------------------------------------------------------

def _save(wb, path: Path) -> Path:
    wb.save(str(path))
    return path


def _make_layout(tmp_path: Path, mutants_wells: list[tuple[str, str]]) -> Path:
    """[Mutant, Well Pos.] sheet plus one WT control row."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Mutant", "Well Pos."])
    for mutant, well in mutants_wells:
        ws.append([mutant, well])
    ws.append(["WT", "H12"])
    return _save(wb, tmp_path / "layout.xlsx")


def _make_gc_data(tmp_path: Path, well_area: list[tuple[str, float]]) -> Path:
    """[Sample Name, Area] sheet (well -> relative activity)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample Name", "Area"])
    for well, area in well_area:
        ws.append([well, area])
    return _save(wb, tmp_path / "gc.xlsx")


def _append_fid1b_block(ws, sample_name: str, area: float) -> None:
    """Append one FID1B block (Area-first header, like the real files)."""
    ws.append(["Signal:", "FID1B"])
    ws.append(["Area", "Sample Name"])
    ws.append([area, sample_name])
    ws.append(["Sum", area])
    ws.append([])


def _make_rep_batch(
    tmp_path: Path,
    base_areas: dict[int, list[float]],
    wt_areas: list[float],
) -> Path:
    """FID1B block layout: numeric base IDs with '-2'/'-3' rep suffixes + WT.

    base_areas[i] = [rep1, rep2, rep3]. Blocks are interleaved as rep1 for all
    IDs, then WT1, then rep2 for all IDs, then WT2, etc., mirroring 260327.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    n_reps = max(len(v) for v in base_areas.values())
    for rep in range(n_reps):
        for base_id in sorted(base_areas):
            areas = base_areas[base_id]
            if rep >= len(areas):
                continue
            suffix = "" if rep == 0 else f"-{rep + 1}"
            _append_fid1b_block(ws, f"{base_id}{suffix}", areas[rep])
        if rep < len(wt_areas):
            _append_fid1b_block(ws, f"WT{rep + 1}", wt_areas[rep])
    return _save(wb, tmp_path / "rep_batch.xlsx")


def _make_prev_evolvepro(
    tmp_path: Path, variant_activity: list[tuple[str, float]]
) -> Path:
    """[Variant, activity] sheet plus a trailing WT row (value 1.0)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Variant", "activity"])
    for variant, activity in variant_activity:
        ws.append([variant, activity])
    ws.append(["WT", 1.0])
    return _save(wb, tmp_path / "prev_ep.xlsx")


def _make_standard_like(tmp_path: Path) -> Path:
    """251001-shape FID1B file: '0' calibration + WT_n + well-name samples."""
    wb = openpyxl.Workbook()
    ws = wb.active
    _append_fid1b_block(ws, "0", 72.5)          # calibration (numeric, skip)
    _append_fid1b_block(ws, "WT_1", 0.6893)
    _append_fid1b_block(ws, "WT_2", 0.8091)
    for well in ["A1", "B1", "C1", "D1", "E1", "F1", "A2", "B2"]:
        _append_fid1b_block(ws, well, 1.0)
    return _save(wb, tmp_path / "standard.xlsx")


# ---------------------------------------------------------------------------
# detect_format discrimination (251001 STANDARD regression guard)
# ---------------------------------------------------------------------------

def test_detect_format_block_numeric_is_rep_batch(tmp_path: Path):
    from kuma_core.mame.activity.evolvepro_xlsx import detect_format, XlsxFormat

    path = _make_rep_batch(
        tmp_path,
        {1: [0.60, 0.61, 0.67], 2: [0.65, 0.66, 0.70]},
        [0.68, 0.80, 0.81],
    )
    assert detect_format(path) == XlsxFormat.AGILENT_REP_BATCH


def test_detect_format_block_well_names_stays_standard(tmp_path: Path):
    """251001 shape: well-name samples plus a single '0' calibration row.

    Numeric ratio is far below the threshold, so the block must classify as
    AGILENT_STANDARD (not REP_BATCH). This is the 251001 regression guard.
    """
    from kuma_core.mame.activity.evolvepro_xlsx import detect_format, XlsxFormat

    path = _make_standard_like(tmp_path)
    assert detect_format(path) == XlsxFormat.AGILENT_STANDARD


def test_standard_still_skips_numeric_calibration(tmp_path: Path):
    """The '0' calibration row stays skipped under parse_agilent_standard."""
    from kuma_core.mame.activity.evolvepro_xlsx import parse_agilent_standard

    path = _make_standard_like(tmp_path)
    records = parse_agilent_standard(path)
    numeric = [r for r in records if r.sample_name.isdigit()]
    assert numeric == [], f"calibration not skipped: {numeric}"
    # WT_1, WT_2, and 8 well-name samples remain.
    assert len(records) == 10
    assert sum(1 for r in records if r.is_wt) == 2


# ---------------------------------------------------------------------------
# Block rep-batch parser: all three replicates preserved (no rep1 loss)
# ---------------------------------------------------------------------------

def test_block_rep_batch_preserves_three_replicates(tmp_path: Path):
    from kuma_core.mame.activity.evolvepro_xlsx import (
        parse_agilent_block_rep_batch,
    )

    base = {1: [0.60, 0.61, 0.67], 2: [0.65, 0.66, 0.70], 3: [0.71, 0.72, 0.73]}
    wt = [0.68, 0.80, 0.81]
    path = _make_rep_batch(tmp_path, base, wt)

    result = parse_agilent_block_rep_batch(path)

    assert set(result.reps) == {1, 2, 3}
    # Every base ID must keep all three replicates (rep1 must NOT be dropped).
    for base_id, areas in base.items():
        assert sorted(result.reps[base_id]) == sorted(areas), (
            f"replicate loss for base ID {base_id}"
        )
    assert sorted(result.wt_areas) == sorted(wt)
    assert result.n_blocks == 3 * 3 + 3  # 3 IDs x 3 reps + 3 WT blocks


# ---------------------------------------------------------------------------
# Rank ID->variant mapping
# ---------------------------------------------------------------------------

def test_id_variant_mapping_is_rank_based(tmp_path: Path):
    from kuma_core.mame.activity.evolvepro_xlsx import (
        parse_agilent_block_rep_batch,
        read_evolvepro_rows,
    )
    from kuma_core.mame.activity.build_evolvepro_input import (
        build_id_variant_mapping,
    )

    prev = [("90A", 1.8), ("12V", 1.5), ("33F", 1.2), ("44K", 0.9)]
    prev_path = _make_prev_evolvepro(tmp_path, prev)
    rep_path = _make_rep_batch(
        tmp_path,
        {1: [1.0, 1.0, 1.0], 2: [1.0, 1.0, 1.0], 3: [1.0, 1.0, 1.0]},
        [1.0, 1.0, 1.0],
    )
    block = parse_agilent_block_rep_batch(rep_path)
    rows = read_evolvepro_rows(prev_path)

    mapping = build_id_variant_mapping(block, rows)
    id_to_variant = mapping.id_to_variant()

    nonwt = [v for v, _ in rows if v.upper() != "WT"]
    for base_id in block.reps:
        assert id_to_variant[base_id] == nonwt[base_id - 1]
    assert mapping.prev_descending is True
    assert mapping.n_prev_variants == 4


def test_mapping_flags_non_descending_prev(tmp_path: Path):
    from kuma_core.mame.activity.evolvepro_xlsx import (
        parse_agilent_block_rep_batch,
        read_evolvepro_rows,
    )
    from kuma_core.mame.activity.build_evolvepro_input import (
        build_id_variant_mapping,
    )

    # Second value rises above the first: not descending.
    prev = [("90A", 1.0), ("12V", 1.5), ("33F", 1.2)]
    prev_path = _make_prev_evolvepro(tmp_path, prev)
    rep_path = _make_rep_batch(
        tmp_path, {1: [1.0, 1.0, 1.0]}, [1.0, 1.0, 1.0]
    )
    block = parse_agilent_block_rep_batch(rep_path)
    rows = read_evolvepro_rows(prev_path)

    mapping = build_id_variant_mapping(block, rows)
    assert mapping.prev_descending is False
    assert any("descending" in w for w in mapping.warnings)


# ---------------------------------------------------------------------------
# Normalisation spot check (area / mean(WT areas))
# ---------------------------------------------------------------------------

def test_normalisation_is_area_over_wt_mean(tmp_path: Path):
    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input

    # Single mutant V5F at well A1; rep-batch ID 1 maps to top variant '5F'.
    layout = _make_layout(tmp_path, [("V5F", "A1")])
    gc = _make_gc_data(tmp_path, [("A1", 1.10)])
    wt = [0.8, 1.0, 1.2]  # mean = 1.0
    raw = [2.0, 2.0, 2.0]
    rep = _make_rep_batch(tmp_path, {1: raw}, wt)
    prev = _make_prev_evolvepro(tmp_path, [("5F", 1.5)])
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(layout, gc, rep, prev, out)

    wt_mean = sum(wt) / len(wt)
    expected_auth_mean = sum(r / wt_mean for r in raw) / len(raw)
    # Authoritative wins for '5F'; merged value is its mean (2.0 / 1.0 = 2.0).
    assert result.n_variants == 1
    assert result.n_authoritative == 1
    assert abs(result.replicate_stats.merged_count) == 1
    # Read back and check the written activity equals the authoritative mean.
    from kuma_core.mame.activity.evolvepro_xlsx import read_evolvepro_xlsx
    written = read_evolvepro_xlsx(out)
    assert abs(written["5F"] - expected_auth_mean) <= 1e-6


# ---------------------------------------------------------------------------
# Final EVOLVEpro file: header + row count + audit artifact
# ---------------------------------------------------------------------------

def test_build_output_header_and_rowcount(tmp_path: Path):
    import json
    import python_calamine

    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input

    layout = _make_layout(
        tmp_path, [("V5F", "A1"), ("V10L", "B1"), ("S11E", "C1")]
    )
    gc = _make_gc_data(tmp_path, [("A1", 1.0), ("B1", 1.1), ("C1", 0.9)])
    # Two authoritative IDs, mapped to the top two prev variants.
    rep = _make_rep_batch(
        tmp_path,
        {1: [1.0, 1.1, 1.2], 2: [0.9, 1.0, 1.1]},
        [1.0, 1.0, 1.0],
    )
    prev = _make_prev_evolvepro(
        tmp_path, [("5F", 1.8), ("10L", 1.4), ("11E", 1.0)]
    )
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(layout, gc, rep, prev, out)

    # 3 fallback variants (5F, 10L, 11E); 2 of them also authoritative.
    assert result.n_variants == 3
    assert result.n_authoritative == 2
    assert result.n_fallback_only == 1

    wb = python_calamine.CalamineWorkbook.from_path(str(out))
    rows = list(wb.get_sheet_by_index(0).to_python())
    header = [str(c).strip() for c in rows[0]]
    assert header == ["Variant", "activity"]
    assert len(rows) - 1 == result.n_variants

    # Rows must be sorted descending by activity.
    acts = [float(str(r[1])) for r in rows[1:]]
    assert acts == sorted(acts, reverse=True)

    # Mapping audit JSON exists and round-trips.
    assert result.mapping_audit_path.exists()
    audit = json.loads(result.mapping_audit_path.read_text())
    assert audit["mapping"][0]["id"] == 1
    assert audit["mapping"][0]["variant"] == "5F"
    assert "prev_descending" in audit


def test_build_warns_on_missing_gc_well(tmp_path: Path):
    """A layout mutant with no GC value is excluded from fallback with a warn."""
    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input

    layout = _make_layout(tmp_path, [("V5F", "A1"), ("V10L", "B1")])
    gc = _make_gc_data(tmp_path, [("A1", 1.0)])  # B1 missing
    rep = _make_rep_batch(tmp_path, {1: [1.0, 1.0, 1.0]}, [1.0, 1.0, 1.0])
    prev = _make_prev_evolvepro(tmp_path, [("5F", 1.5)])
    out = tmp_path / "out.xlsx"

    result = build_evolvepro_input(layout, gc, rep, prev, out)
    assert any("V10L" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Anti-fallback: empty WT areas (260327-shape) must fail-fast, not silently
# normalise to a fabricated baseline.
# ---------------------------------------------------------------------------

def test_build_fails_fast_when_wt_areas_empty(tmp_path: Path):
    """No WT blocks in the rep-batch -> ValueError at the normalise step.

    The Agilent rep-batch report normalises raw areas by the mean WT block
    area. When the WT block is missing (260327 WT areas empty), the
    authoritative builder must raise rather than fall back to a fabricated
    baseline that would silently distort every relative activity.
    """
    from kuma_core.mame.activity.build_evolvepro_input import build_evolvepro_input

    layout = _make_layout(tmp_path, [("V5F", "A1")])
    gc = _make_gc_data(tmp_path, [("A1", 1.10)])
    # wt_areas=[] -> rep-batch carries one base ID but no WT blocks to normalise.
    rep = _make_rep_batch(tmp_path, {1: [2.0, 2.0, 2.0]}, wt_areas=[])
    prev = _make_prev_evolvepro(tmp_path, [("5F", 1.5)])
    out = tmp_path / "out.xlsx"

    with pytest.raises(ValueError, match="WT block areas"):
        build_evolvepro_input(layout, gc, rep, prev, out)
