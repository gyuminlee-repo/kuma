"""Contract tests for the 2026-08 audit follow-up on kuro EVOLVEpro/benchmark.

Four defects are pinned here. Every case ships with a control so that a
degenerate implementation (reject everything, drop everything, return 0.0)
cannot pass:

1. An unknown score must not become a measured 0.0 (evolvepro loader).
2. A duplicated variant must consume one selection slot, not two.
3. Start-codon exclusion must see whitespace-separated combo tokens.
4. structural_spread must not average the missing-coordinate sentinel, and
   the top-percentile threshold must round up rather than down.
"""

from __future__ import annotations

import csv

import pytest

from kuma_core.kuro.benchmark import _structural_spread, evaluate_selection
from kuma_core.kuro.evolvepro import (
    _load_evolvepro_rows,
    _variant_has_position_one,
    load_evolvepro_csv,
)


def _write_csv(rows: list[list[str]], path) -> str:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return str(path)


# ---------------------------------------------------------------------------
# Defect 1: unknown score vs measured zero
# ---------------------------------------------------------------------------

def test_measured_zero_is_kept_as_a_real_score(tmp_path):
    """Control: 0.0 is a legitimate fitness and must survive loading."""
    path = _write_csv([
        ["variant", "y_pred"],
        ["A10C", "0.0"],
        ["B20D", "0.9"],
    ], tmp_path / "zero.csv")

    rows = _load_evolvepro_rows(path)
    by_variant = {v: raw for v, _, raw in rows}

    if "A10C" not in by_variant:
        pytest.fail(f"measured 0.0 row was dropped: {by_variant}")
    if by_variant["A10C"] != 0.0:
        pytest.fail(f"expected raw 0.0 for A10C, got {by_variant['A10C']}")


@pytest.mark.parametrize("bad_cell", ["", "   ", "n/a", "NaN", "inf", "-inf"])
def test_unknown_score_is_not_reported_as_zero(tmp_path, bad_cell):
    """Blank/unparseable/non-finite cells must not enter the ranking as 0.0."""
    path = _write_csv([
        ["variant", "y_pred"],
        ["A10C", bad_cell],
        ["B20D", "0.9"],
    ], tmp_path / "unknown.csv")

    rows = _load_evolvepro_rows(path)
    by_variant = {v: raw for v, _, raw in rows}

    if "B20D" not in by_variant:
        pytest.fail(f"control row with a valid score was dropped: {by_variant}")
    if "A10C" in by_variant:
        pytest.fail(
            f"unknown score {bad_cell!r} was substituted with "
            f"{by_variant['A10C']!r} instead of being rejected"
        )


def test_score_free_file_still_loads_every_row(tmp_path):
    """Control: a file whose score column is empty everywhere stays score-free."""
    path = _write_csv([
        ["variant", "y_pred"],
        ["A10C", ""],
        ["B20D", ""],
    ], tmp_path / "scorefree.csv")

    rows = _load_evolvepro_rows(path)
    if len(rows) != 2:
        pytest.fail(f"score-free file must keep all rows, got {rows}")


def test_y_preds_report_the_loaded_scores(tmp_path):
    """Control: reported y_preds match the file, including a genuine 0.0."""
    path = _write_csv([
        ["variant", "y_pred"],
        ["A10C", "0.9"],
        ["B20D", "0.0"],
    ], tmp_path / "report.csv")

    result = load_evolvepro_csv(path, top_n=10)
    reported = dict(zip(result["variants"], result["y_preds"]))

    if reported != {"A10C": 0.9, "B20D": 0.0}:
        pytest.fail(f"y_preds do not match the file: {reported}")


# ---------------------------------------------------------------------------
# Defect 2: duplicate variants consuming two slots
# ---------------------------------------------------------------------------

def test_duplicate_variant_takes_one_slot(tmp_path):
    """A repeated variant must not occupy two of the top_n slots."""
    path = _write_csv([
        ["variant", "y_pred"],
        ["A10C", "0.9"],
        ["A10C", "0.8"],
        ["B20D", "0.5"],
    ], tmp_path / "dup_slot.csv")

    result = load_evolvepro_csv(path, top_n=2)
    variants = result["variants"]

    if len(set(variants)) != len(variants):
        pytest.fail(f"duplicate variant consumed two slots: {variants}")
    if "B20D" not in variants:
        pytest.fail(f"the duplicate crowded out a distinct variant: {variants}")


def test_duplicate_variant_score_matches_the_kept_row(tmp_path):
    """The reported score must come from the row that was kept, not the last one."""
    path = _write_csv([
        ["variant", "y_pred"],
        ["A10C", "0.9"],
        ["A10C", "0.1"],
        ["B20D", "0.5"],
    ], tmp_path / "dup_score.csv")

    result = load_evolvepro_csv(path, top_n=2)
    reported = dict(zip(result["variants"], result["y_preds"]))

    if reported.get("A10C") != 0.9:
        pytest.fail(f"kept row and reported score disagree: {reported}")


def test_distinct_variants_are_not_collapsed(tmp_path):
    """Control: deduplication must not merge genuinely different variants."""
    path = _write_csv([
        ["variant", "y_pred"],
        ["A10C", "0.9"],
        ["A10D", "0.8"],
        ["B20D", "0.5"],
    ], tmp_path / "distinct.csv")

    result = load_evolvepro_csv(path, top_n=3)
    if sorted(result["variants"]) != ["A10C", "A10D", "B20D"]:
        pytest.fail(f"distinct variants were collapsed: {result['variants']}")


# ---------------------------------------------------------------------------
# Defect 3: start-codon exclusion vs whitespace-separated combos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("variant", ["M1A A2V", "A2V M1A", "M1A/A2V", "M1A,A2V", "M1A"])
def test_position_one_detected_across_all_separators(variant):
    if not _variant_has_position_one(variant):
        pytest.fail(f"position-1 substitution not detected in {variant!r}")


@pytest.mark.parametrize("variant", ["A2V L59M", "A2V/L59M", "WT", "L59M:W60T", "A21V"])
def test_non_position_one_combos_are_kept(variant):
    """Control: the filter must not reject variants that spare position 1."""
    if _variant_has_position_one(variant):
        pytest.fail(f"{variant!r} wrongly flagged as a start-codon variant")


def test_whitespace_combo_removed_by_loader(tmp_path):
    path = _write_csv([
        ["variant", "y_pred"],
        ["M1A A2V", "0.99"],
        ["L59M W60T", "0.50"],
    ], tmp_path / "combo.csv")

    result = load_evolvepro_csv(path, top_n=10)

    if "M1A A2V" in result["variants"]:
        pytest.fail(
            f"whitespace-separated start-codon combo survived: {result['variants']}"
        )
    if "L59M W60T" not in result["variants"]:
        pytest.fail(f"control combo was wrongly removed: {result['variants']}")
    if result["start_codon_removed"] != 1:
        pytest.fail(
            f"expected 1 start-codon removal, got {result['start_codon_removed']}"
        )


# ---------------------------------------------------------------------------
# Defect 4a: the missing-coordinate sentinel must not inflate structural_spread
# ---------------------------------------------------------------------------

def _coords(n: int) -> list[tuple[float, float, float] | None]:
    # Index 0 is unused (positions are 1-based); residues sit 1 A apart on x.
    return [None] + [(float(i), 0.0, 0.0) for i in range(1, n + 1)]


def test_missing_coordinate_does_not_inflate_structural_spread():
    """A variant with no coordinate must be excluded, not scored as far away."""
    coords = _coords(5)
    coords[3] = None  # chain break at residue 3

    known_only = [("A1C", 0.9), ("A2C", 0.8)]
    with_unknown = [("A1C", 0.9), ("A2C", 0.8), ("A3C", 0.7)]

    spread_known = _structural_spread(known_only, ca_coords=coords)
    spread_unknown = _structural_spread(with_unknown, ca_coords=coords)

    if spread_unknown != pytest.approx(spread_known):
        pytest.fail(
            "the missing-coordinate sentinel entered the mean: "
            f"{spread_unknown} vs {spread_known} without the unknown residue"
        )


def test_structural_spread_still_reflects_real_distance():
    """Control: known coordinates must still produce a non-zero, ordered spread."""
    coords = _coords(20)

    near = _structural_spread([("A1C", 0.9), ("A2C", 0.8)], ca_coords=coords)
    far = _structural_spread([("A1C", 0.9), ("A20C", 0.8)], ca_coords=coords)

    if near <= 0.0:
        pytest.fail(f"expected a positive spread for known coordinates, got {near}")
    if not far > near:
        pytest.fail(f"distant residues must spread more: far={far}, near={near}")


# ---------------------------------------------------------------------------
# Defect 4b: the top-percentile threshold must round up
# ---------------------------------------------------------------------------

def test_top_percentile_rounds_up():
    """Top 10% of 19 variants is 2 variants, not 1."""
    ground_truth = {f"A{i}C": float(100 - i) for i in range(1, 20)}
    assert len(ground_truth) == 19

    ranked = sorted(ground_truth.items(), key=lambda kv: kv[1], reverse=True)
    top_two = [(v, s) for v, s in ranked[:2]]

    metrics = evaluate_selection(top_two, ground_truth, top_percentile=10.0)

    if metrics.get("hits") != 2:
        pytest.fail(
            f"expected the top 2 of 19 to count as the top 10%, got {metrics.get('hits')} "
            f"hits at threshold {metrics.get('threshold')}"
        )


def test_top_percentile_exact_division_unchanged():
    """Control: an exact division must not be inflated by the rounding change."""
    ground_truth = {f"A{i}C": float(100 - i) for i in range(1, 21)}
    assert len(ground_truth) == 20

    ranked = sorted(ground_truth.items(), key=lambda kv: kv[1], reverse=True)
    metrics = evaluate_selection(ranked[:3], ground_truth, top_percentile=10.0)

    if metrics.get("hits") != 2:
        pytest.fail(
            f"top 10% of 20 must be exactly 2, got {metrics.get('hits')} hits at "
            f"threshold {metrics.get('threshold')}"
        )
