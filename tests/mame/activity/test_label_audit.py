"""Tests for well<->mutant label-audit detection (Phase 1: detect only).

Covers:
  1. audit_labels category classification (not_introduced, wrong_residue,
     extra_mutation, sequence_collapse).
  2. audit_labels closed-permutation gate: a genuine closed 3-cycle is
     detected and decomposed; the F12/G12 coincidental (non-reciprocal)
     match is rejected (is_closed_permutation=False).
  3. verdict_ngs.parse_verdict_rows / parse_verdict_wells: the observed_aa
     column is read when present, and parse_verdict_wells's existing
     behaviour (no observed_aa column) is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.activity.label_audit import audit_labels
from kuma_core.mame.activity.verdict_ngs import (
    VerdictRow,
    parse_verdict_rows,
    parse_verdict_wells,
)
from kuma_core.mame.export.well_mapper import seq_to_well

# ---------------------------------------------------------------------------
# audit_labels: category classification
# ---------------------------------------------------------------------------


def test_concordant_well_produces_no_finding():
    layout = {"F06": "A1G"}
    rows = {"F06": VerdictRow(verdict="PASS", observed_aa=("A1G",))}
    audit = audit_labels(layout, rows)
    assert audit.discordant == ()
    assert audit.n_checked == 1
    assert audit.n_unevaluable == 0


def test_not_introduced_category():
    layout = {"B02": "K48D"}
    rows = {"B02": VerdictRow(verdict="WRONG_AA", observed_aa=())}
    audit = audit_labels(layout, rows)
    assert len(audit.discordant) == 1
    finding = audit.discordant[0]
    assert finding.well == "B02"
    assert finding.category == "not_introduced"
    assert finding.observed == ()


def test_wrong_residue_category():
    layout = {"C03": "F89W"}
    rows = {"C03": VerdictRow(verdict="WRONG_AA", observed_aa=("F89Y",))}
    audit = audit_labels(layout, rows)
    assert len(audit.discordant) == 1
    finding = audit.discordant[0]
    assert finding.category == "wrong_residue"
    assert finding.observed == ("F89Y",)
    # No cross-well candidate, no other well's expected mutation is F89Y.
    assert audit.is_closed_permutation is False


def test_extra_mutation_category():
    layout = {"D04": "L20V"}
    rows = {
        "D04": VerdictRow(verdict="WRONG_AA", observed_aa=("L20V", "M55T")),
    }
    audit = audit_labels(layout, rows)
    assert len(audit.discordant) == 1
    finding = audit.discordant[0]
    assert finding.category == "extra_mutation"
    assert finding.observed == ("L20V", "M55T")


def test_sequence_collapse_category_excluded_from_n_checked():
    layout = {"E05": "P10Q"}
    collapsed = tuple(f"X{i}Y" for i in range(1, 22))  # 21 > threshold(20)
    rows = {"E05": VerdictRow(verdict="WRONG_AA", observed_aa=collapsed)}
    audit = audit_labels(layout, rows)
    assert len(audit.discordant) == 1
    finding = audit.discordant[0]
    assert finding.category == "sequence_collapse"
    assert finding.observed == collapsed
    # sequence_collapse wells are excluded from judgement (not counted checked).
    assert audit.n_checked == 0
    assert audit.n_unevaluable == 0


def test_no_verdict_row_is_unevaluable():
    layout = {"A01": "Q1R"}
    audit = audit_labels(layout, {})
    assert audit.discordant == ()
    assert audit.n_checked == 0
    assert audit.n_unevaluable == 1


def test_non_confident_verdict_is_unevaluable():
    layout = {"A01": "Q1R"}
    rows = {"A01": VerdictRow(verdict="LOWDEPTH", observed_aa=())}
    audit = audit_labels(layout, rows)
    assert audit.discordant == ()
    assert audit.n_checked == 0
    assert audit.n_unevaluable == 1


def test_wt_well_excluded_from_audit():
    layout = {"H12": "WT", "A01": "Q1R"}
    rows = {
        "H12": VerdictRow(verdict="WRONG_AA", observed_aa=("Q1Z",)),
        "A01": VerdictRow(verdict="PASS", observed_aa=("Q1R",)),
    }
    audit = audit_labels(layout, rows)
    assert audit.discordant == ()
    assert audit.n_checked == 1  # only A01; H12 (WT) is skipped entirely.


# ---------------------------------------------------------------------------
# Closed-permutation gate
# ---------------------------------------------------------------------------


def test_closed_3_cycle_detected_and_decomposed():
    """G08/H08/A09 rotate Q426D/E/N among each other, a genuine swap."""
    layout = {"G08": "Q426D", "H08": "Q426E", "A09": "Q426N"}
    rows = {
        "G08": VerdictRow(verdict="WRONG_AA", observed_aa=("Q426E",)),
        "H08": VerdictRow(verdict="WRONG_AA", observed_aa=("Q426N",)),
        "A09": VerdictRow(verdict="WRONG_AA", observed_aa=("Q426D",)),
    }
    audit = audit_labels(layout, rows)

    assert audit.is_closed_permutation is True
    assert len(audit.discordant) == 3
    assert {f.category for f in audit.discordant} == {"cross_well"}
    assert len(audit.cycles) == 1
    assert set(audit.cycles[0]) == {"G08", "H08", "A09"}
    assert audit.geometry is not None


def test_f12_g12_coincidental_match_is_not_a_closed_permutation():
    """F12 expects R560S, observes R560P (= G12's own expected, PASS).

    G12 itself matches its own expectation (PASS, observed R560P), so it is
    never a discordant well. The apparent "swap" is one-directional and must
    not be promoted to cross_well: F12 stays wrong_residue (same position,
    different substitution).
    """
    layout = {"F12": "R560S", "G12": "R560P"}
    rows = {
        "F12": VerdictRow(verdict="WRONG_AA", observed_aa=("R560P",)),
        "G12": VerdictRow(verdict="PASS", observed_aa=("R560P",)),
    }
    audit = audit_labels(layout, rows)

    assert audit.is_closed_permutation is False
    assert audit.cycles == ()
    assert audit.geometry is None
    assert len(audit.discordant) == 1
    finding = audit.discordant[0]
    assert finding.well == "F12"
    assert finding.category == "wrong_residue"


def test_extra_cross_well_observation_is_not_a_closed_permutation():
    layout = {"A01": "M1A", "B01": "M2A", "C01": "M3A"}
    rows = {
        "A01": VerdictRow(verdict="WRONG_AA", observed_aa=("M2A", "M3A")),
        "B01": VerdictRow(verdict="WRONG_AA", observed_aa=("M3A",)),
        "C01": VerdictRow(verdict="WRONG_AA", observed_aa=("M1A",)),
    }

    audit = audit_labels(layout, rows)

    assert audit.is_closed_permutation is False
    assert audit.cycles == ()
    assert audit.geometry is None
    assert {f.category for f in audit.discordant} == {"extra_mutation"}


def test_full_plate_one_step_cycle_is_global_offset():
    layout = {seq_to_well(i): f"M{i}A" for i in range(1, 97)}
    rows = {
        seq_to_well(i): VerdictRow(
            verdict="WRONG_AA",
            observed_aa=(f"M{(i % 96) + 1}A",),
        )
        for i in range(1, 97)
    }

    audit = audit_labels(layout, rows)

    assert audit.is_closed_permutation is True
    assert audit.geometry == "global_offset"
    assert len(audit.cycles) == 1
    assert len(audit.cycles[0]) == 96


# ---------------------------------------------------------------------------
# verdict_ngs: parse_verdict_rows / parse_verdict_wells
# ---------------------------------------------------------------------------


def _write_final_sheet(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    """Legacy-shape Final sheet: well_id, mutant_id, verdict (no observed_aa)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Final"
    ws.append(["well_id", "mutant_id", "verdict"])
    for well, mutant, verdict in rows:
        ws.append([well, mutant, verdict])
    wb.save(str(path))
    return path


def _write_final_sheet_with_observed_aa(
    path: Path, rows: list[tuple[str, str, str, str]]
) -> Path:
    """rows: [(well_id, mutant_id, verdict, observed_aa_csv)]."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Final"
    ws.append(["well_id", "mutant_id", "verdict", "observed_aa"])
    for well, mutant, verdict, observed_aa in rows:
        ws.append([well, mutant, verdict, observed_aa])
    wb.save(str(path))
    return path


def test_parse_verdict_wells_unchanged_without_observed_aa_column(tmp_path):
    path = _write_final_sheet(
        tmp_path / "verdict.xlsx",
        [("A1", "Q1R", "PASS"), ("B1", "K48D", "WRONG_AA")],
    )
    result = parse_verdict_wells(path)
    assert result == {"A01": "PASS", "B01": "WRONG_AA"}


def test_parse_verdict_rows_without_observed_aa_column(tmp_path):
    path = _write_final_sheet(
        tmp_path / "verdict.xlsx",
        [("A1", "Q1R", "PASS"), ("B1", "K48D", "WRONG_AA")],
    )
    rows = parse_verdict_rows(path)
    assert rows["A01"] == VerdictRow(verdict="PASS", observed_aa=(), mutant_id="Q1R")
    assert rows["B01"] == VerdictRow(
        verdict="WRONG_AA", observed_aa=(), mutant_id="K48D"
    )
    # Thin-wrapper equivalence.
    assert parse_verdict_wells(path) == {
        w: r.verdict for w, r in rows.items()
    }


def test_parse_verdict_rows_reads_observed_aa_column(tmp_path):
    path = _write_final_sheet_with_observed_aa(
        tmp_path / "verdict.xlsx",
        [
            ("A1", "Q1R", "PASS", "Q1R"),
            ("B1", "K48D", "WRONG_AA", ""),
            ("C1", "L20V", "WRONG_AA", "L20V, M55T"),
        ],
    )
    rows = parse_verdict_rows(path)
    assert rows["A01"].observed_aa == ("Q1R",)
    assert rows["B01"].observed_aa == ()
    assert rows["C01"].observed_aa == ("L20V", "M55T")
    # parse_verdict_wells still returns only the verdict map.
    assert parse_verdict_wells(path) == {
        "A01": "PASS",
        "B01": "WRONG_AA",
        "C01": "WRONG_AA",
    }


