"""Decoding numeric Agilent sample IDs into variants.

Both activity files of a round arrive in the FID1B block layout whose sample
names are bare numbers, so the variant names come from the plate layout:

  primary screen   ID i -> i-th non-WT layout row, well order
  confirmation     ID j -> j-th above-WT variant of the primary screen,
                   same well order

The cases below pin the order, the wild-type threshold, and the refusals. The
refusals matter most: a positional decode that guesses attaches a real
measurement to the wrong variant, and every consumer treats the label as truth.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.activity.numeric_id_decode import (
    WT_RELATIVE,
    above_wt_subset,
    decode_confirmation,
    decode_primary_screen,
    layout_variant_order,
)

# Layout well order deliberately puts three substitutions on one position (53)
# so the tie-break is exercised: ID order must follow the plate, not the amino
# acid letter.
_LAYOUT = [
    ("V5F", "A1"),
    ("K53R", "B1"),
    ("K53S", "C1"),
    ("K53N", "D1"),
    ("R87P", "E1"),
    ("WT", "H12"),
]


def _append_block(ws, sample_name: str, area: float) -> None:
    ws.append(["Signal:", "FID1B"])
    ws.append(["Area", "Sample Name"])
    ws.append([area, sample_name])
    ws.append(["Sum", area])
    ws.append([])


def _new_sheet():
    """Workbook plus its active sheet, which openpyxl always creates."""
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    return wb, ws


def _layout(tmp_path: Path, rows=_LAYOUT) -> Path:
    wb, ws = _new_sheet()
    ws.append(["Mutant", "Well Pos."])
    for mutant, well in rows:
        ws.append([mutant, well])
    p = tmp_path / "layout.xlsx"
    wb.save(p)
    return p


def _report(
    tmp_path: Path,
    base_areas: dict[int, list[float]],
    wt_areas: list[float],
    name: str = "report.xlsx",
) -> Path:
    """FID1B blocks: replicate 1 unsuffixed, later replicates '-2', '-3'."""
    wb, ws = _new_sheet()
    n_reps = max(len(v) for v in base_areas.values())
    for rep in range(n_reps):
        for base_id in sorted(base_areas):
            areas = base_areas[base_id]
            if rep < len(areas):
                suffix = "" if rep == 0 else f"-{rep + 1}"
                _append_block(ws, f"{base_id}{suffix}", areas[rep])
        if rep < len(wt_areas):
            _append_block(ws, f"WT{rep + 1}", wt_areas[rep])
    p = tmp_path / name
    wb.save(p)
    return p


# Relative activities chosen so exactly ids 1, 3 and 5 clear wild-type.
_PRIMARY_REL = {1: 1.50, 2: 0.80, 3: 1.20, 4: 0.99, 5: 1.05}
_WT = 2.0


def _primary(tmp_path: Path) -> Path:
    return _report(
        tmp_path,
        {i: [rel * _WT] for i, rel in _PRIMARY_REL.items()},
        [_WT, _WT, _WT],
        name="primary.xlsx",
    )


class TestLayoutOrder:
    def test_skips_wt_and_keeps_plate_order(self, tmp_path):
        order, warnings = layout_variant_order(_layout(tmp_path))
        assert [o[0] for o in order] == ["5F", "53R", "53S", "53N", "87P"]
        assert warnings == []

    def test_multi_substitution_row_is_dropped_with_a_warning(self, tmp_path):
        # 'A40P_E61Y' has no single-position short form, so it cannot take an ID.
        rows = [("V5F", "A1"), ("A40P_E61Y", "B1"), ("R87P", "C1")]
        order, warnings = layout_variant_order(_layout(tmp_path, rows))
        assert [o[0] for o in order] == ["5F", "87P"]
        assert len(warnings) == 1
        assert "A40P_E61Y" in warnings[0]


class TestPrimaryScreen:
    def test_ids_follow_layout_well_order(self, tmp_path):
        result = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        assert [(r.id, r.variant) for r in result.rows] == [
            (1, "5F"),
            (2, "53R"),
            (3, "53S"),
            (4, "53N"),
            (5, "87P"),
        ]

    def test_same_position_tie_break_is_the_plate_not_the_letter(self, tmp_path):
        result = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        at_53 = [r.variant for r in result.rows if r.variant.startswith("53")]
        assert at_53 == ["53R", "53S", "53N"]
        assert at_53 != sorted(at_53)

    def test_areas_are_divided_by_the_wt_block_mean(self, tmp_path):
        result = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        assert result.wt_mean == pytest.approx(_WT)
        assert {r.id: r.mean for r in result.rows} == pytest.approx(_PRIMARY_REL)

    def test_carries_mutant_and_well_through(self, tmp_path):
        result = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        first = result.rows[0]
        assert (first.mutant, first.well) == ("V5F", "A01")

    def test_missing_wt_blocks_refuse(self, tmp_path):
        report = _report(tmp_path, {i: [1.0] for i in range(1, 6)}, [])
        with pytest.raises(ValueError, match="no WT block areas"):
            decode_primary_screen(report, _layout(tmp_path))

    def test_id_beyond_the_layout_refuses(self, tmp_path):
        report = _report(tmp_path, {i: [1.0] for i in range(1, 7)}, [_WT])
        with pytest.raises(ValueError, match=r"IDs must be 1\.\.5"):
            decode_primary_screen(report, _layout(tmp_path))

    def test_partial_id_set_refuses_rather_than_shifting(self, tmp_path):
        # ID 3 absent. A positional decode would silently rename 4 and 5.
        report = _report(tmp_path, {1: [1.0], 2: [1.0], 4: [1.0], 5: [1.0]}, [_WT])
        with pytest.raises(ValueError, match="line up one to one"):
            decode_primary_screen(report, _layout(tmp_path))


class TestAboveWtSubset:
    def test_selects_everything_over_wild_type_in_plate_order(self, tmp_path):
        primary = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        assert [s[0] for s in above_wt_subset(primary)] == ["5F", "53S", "87P"]

    def test_threshold_is_wild_type_itself(self, tmp_path):
        assert WT_RELATIVE == 1.0
        primary = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        below = {r.variant for r in primary.rows if r.mean <= WT_RELATIVE}
        assert below.isdisjoint({s[0] for s in above_wt_subset(primary)})


class TestConfirmation:
    def _confirmation(self, tmp_path, base_areas, wt=(1.0, 1.0)) -> Path:
        return _report(tmp_path, base_areas, list(wt), name="confirm.xlsx")

    def test_ids_index_the_above_wt_subset(self, tmp_path):
        primary = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        # Three above-WT variants, three replicates each.
        confirm = self._confirmation(
            tmp_path, {1: [1.4, 1.5, 1.6], 2: [1.1, 1.2, 1.3], 3: [0.9, 1.0, 1.1]}
        )
        result = decode_confirmation(confirm, primary)
        assert [(r.id, r.variant) for r in result.rows] == [
            (1, "5F"),
            (2, "53S"),
            (3, "87P"),
        ]
        assert result.rows[0].mean == pytest.approx(1.5)

    def test_replicate_count_is_not_fixed(self, tmp_path):
        primary = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        confirm = self._confirmation(
            tmp_path, {1: [1.0, 2.0], 2: [1.0, 2.0], 3: [1.0, 2.0]}
        )
        result = decode_confirmation(confirm, primary)
        assert [len(r.relative) for r in result.rows] == [2, 2, 2]

    def test_subset_size_mismatch_refuses(self, tmp_path):
        # Four IDs against three above-WT variants: the confirmation covered a
        # different set, which cannot be inferred.
        primary = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        confirm = self._confirmation(
            tmp_path, {1: [1.0], 2: [1.0], 3: [1.0], 4: [1.0]}
        )
        with pytest.raises(ValueError, match=r"IDs must be 1\.\.3"):
            decode_confirmation(confirm, primary)

    def test_no_variant_above_wt_refuses(self, tmp_path):
        flat = _report(
            tmp_path,
            {i: [0.5 * _WT] for i in range(1, 6)},
            [_WT],
            name="flat.xlsx",
        )
        primary = decode_primary_screen(flat, _layout(tmp_path))
        confirm = self._confirmation(tmp_path, {1: [1.0]})
        with pytest.raises(ValueError, match="exceeded wild-type"):
            decode_confirmation(confirm, primary)

    def test_confirmation_has_its_own_wt_divisor(self, tmp_path):
        # The two reports are separate runs, so each normalises by its own WT.
        primary = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        confirm = self._confirmation(
            tmp_path, {1: [4.0], 2: [4.0], 3: [4.0]}, wt=(4.0,)
        )
        result = decode_confirmation(confirm, primary)
        assert result.wt_mean == pytest.approx(4.0)
        assert all(r.mean == pytest.approx(1.0) for r in result.rows)


class TestOrderIsNotActivityRank:
    """Guards the decode against the assumption it replaced.

    The retired decoder read ID i as the i-th row of a previous EVOLVEpro file
    sorted by descending activity. On real campaign files that order differs
    from the plate order for every single ID, so a decode that ever agrees with
    it on this fixture would mean the rule regressed.
    """

    def test_plate_order_differs_from_descending_activity(self, tmp_path):
        primary = decode_primary_screen(_primary(tmp_path), _layout(tmp_path))
        by_plate = [r.variant for r in primary.rows]
        by_activity = [
            r.variant for r in sorted(primary.rows, key=lambda r: -r.mean)
        ]
        assert by_plate == ["5F", "53R", "53S", "53N", "87P"]
        assert by_activity == ["5F", "53S", "87P", "53N", "53R"]
        assert by_plate != by_activity
