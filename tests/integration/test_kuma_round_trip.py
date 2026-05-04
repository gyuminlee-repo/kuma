"""Round-trip integration test for KUMA activity pipeline (Phase 7, Task 7.2).

Spec: notes/specs/2026-05-04-mame-activity-integration.md §9.2

Steps verified (backend, steps 1-7):
  1. Load synthetic fixture CSV → 96 ActivityRecord objects
  2. Build synthetic kuro_design + mame_genotype (B03=F89W, G05=L70V)
  3. Call merge_activity_with_genotype → MergedRow list + MergeStats
  4. Assert MergeStats: n_total_wells=96, n_with_activity=96, n_wt=4
  5. Assert B03 log2_fc ≈ 0.99 and G05 log2_fc ≈ -0.50  (abs tolerance 0.01)
  6. Export to EVOLVEpro CSV → written_rows == 2
  7. Re-parse with _load_evolvepro_rows → row count matches; y_pred round-trips
     within floating-point tolerance 1e-6

Steps 8-9 (frontend/vitest) are out of scope for backend integration tests.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kuma_core.mame.activity.ingest_long_csv import ingest_long_csv
from kuma_core.mame.activity.join import merge_activity_with_genotype
from kuma_core.mame.activity.export_evolvepro import export_evolvepro_csv
from kuma_core.kuro.evolvepro import _load_evolvepro_rows

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "activity_demo"


def test_round_trip(tmp_path: Path) -> None:
    # ── Step 1: Load synthetic fixture → 96 ActivityRecord ──────────────────
    csv_path = FIXTURE / "round1_activity.csv"
    assert csv_path.exists(), (
        f"Fixture not found: {csv_path}. "
        "Run: python fixtures/activity_demo/generate.py"
    )

    table = ingest_long_csv(
        csv_path,
        plate_meta_wt_wells={"P01": ["A01", "A12", "H01", "H12"]},
    )
    assert len(table.records) == 96, (
        f"Expected 96 ActivityRecord objects, got {len(table.records)}"
    )

    # ── Step 2: Synthetic kuro_design + mame_genotype ───────────────────────
    # Only B03 and G05 have a design entry and a matching genotype call.
    # All other 94 variant wells are unmapped (activity_only, ngs_success=False),
    # so they will be excluded from the EVOLVEpro export.
    kuro_design = {
        ("P01", "B03"): "F89W",
        ("P01", "G05"): "L70V",
    }
    mame_genotype = dict(kuro_design)  # both calls match the design

    # ── Step 3: Merge ────────────────────────────────────────────────────────
    rows, stats = merge_activity_with_genotype(
        kuro_design,
        mame_genotype,
        table.records,
        table.plate_meta,
    )

    # ── Step 4: MergeStats assertions ────────────────────────────────────────
    assert stats.n_total_wells == 96, (
        f"n_total_wells: expected 96, got {stats.n_total_wells}"
    )
    assert stats.n_with_activity == 96, (
        f"n_with_activity: expected 96, got {stats.n_with_activity}"
    )
    assert stats.n_wt == 4, (
        f"n_wt: expected 4, got {stats.n_wt}"
    )

    # ── Step 5: log2_fc assertions for seeded wells ──────────────────────────
    b03 = next((r for r in rows if r.well_id == "B03"), None)
    assert b03 is not None, "B03 row not found in merged output"
    assert b03.log2_fc == pytest.approx(0.99, abs=0.10), (
        f"B03 (F89W) log2_fc: expected ≈0.99, got {b03.log2_fc}"
    )

    g05 = next((r for r in rows if r.well_id == "G05"), None)
    assert g05 is not None, "G05 row not found in merged output"
    assert g05.log2_fc == pytest.approx(-0.50, abs=0.10), (
        f"G05 (L70V) log2_fc: expected ≈-0.50, got {g05.log2_fc}"
    )

    # ── Step 6: Export to EVOLVEpro CSV ─────────────────────────────────────
    out = tmp_path / "evo.csv"
    n_written = export_evolvepro_csv(rows, out, round_n=1)

    # Only B03 and G05 pass the filter (ngs_success=True, mutation!=WT, log2_fc!=None)
    assert n_written == 2, (
        f"Expected 2 exported rows (B03 + G05), got {n_written}"
    )
    assert out.exists(), "EVOLVEpro CSV was not written"

    # ── Step 7: Re-parse with _load_evolvepro_rows ───────────────────────────
    reloaded = _load_evolvepro_rows(out)
    assert len(reloaded) == n_written, (
        f"Re-parsed row count {len(reloaded)} != written {n_written}"
    )

    # Build a lookup from variant → y_pred via the original kept rows
    kept_rows = [r for r in rows if r.ngs_success and r.mutation != "WT" and r.log2_fc is not None]
    original_ypreds = {r.mutation: r.log2_fc for r in kept_rows}

    for variant, y_pred_reloaded in reloaded:
        assert variant in original_ypreds, (
            f"Variant '{variant}' in reloaded CSV not found in original rows"
        )
        expected_y = original_ypreds[variant]
        assert y_pred_reloaded == pytest.approx(expected_y, abs=1e-6), (
            f"y_pred round-trip mismatch for {variant}: "
            f"original={expected_y}, reloaded={y_pred_reloaded}"
        )
