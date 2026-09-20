"""Echo 384 source-plate column parities (kuma_core/kuro/plate_quadrant.py).

Two things are pinned here and they disagree with each other on purpose.

``OBSERVED_FORWARD`` is the occupancy of a real Echo worklist, which reads as
twelve consecutive columns. The column-parity geometry this module implements
does not reproduce it past the first column. On 2026-09-20 the operator
confirmed the interleaved layout is what the instrument does, so the geometry
is the rule and the workbook is recorded counter-evidence whose cause is
(미확인). ``TestWorkbookDisagrees`` pins exactly where the two part, so a later
reader finds the conflict already measured instead of rediscovering half of it.
"""

from __future__ import annotations

import pytest

from kuma_core.kuro.plate_mapper import _to_384_well_fwd, _to_384_well_rev
from kuma_core.kuro.plate_quadrant import (
    FOLDED_QUADRANTS,
    LEGACY_QUADRANTS,
    QUADRANTS,
    check_quadrants_available,
    fold_persisted_placement,
    quadrant_wells,
    to_384_well,
    validate_quadrant,
)

_ROWS_96 = "ABCDEFGH"

# Observed occupancy of a real Echo source plate, recorded as counter-evidence
# rather than as the expected output of this module. Parsed 2026-09-13 from sheet
# "Echo mapping file" of
# $WORKSPACE_ROOT/020.admin/projects/040.mapping_files_echo/
#   "Project2-1. primer dispensing (Echo525).xlsx"
# 190 transfers over 161 source wells, 95 of them forward and 66 reverse. The
# workbook lives outside this repository, so the observation is pinned here
# rather than read at test time.
#
# (96 destination well, 384 source well) for every forward primer in that file.
# Destination H12 is absent because the campaign had 95 mutants, not 96.
OBSERVED_FORWARD: tuple[tuple[str, str], ...] = (
    ("A1", "A1"), ("B1", "C1"), ("C1", "E1"), ("D1", "G1"),
    ("E1", "I1"), ("F1", "K1"), ("G1", "M1"), ("H1", "O1"),
    ("A2", "A2"), ("B2", "C2"), ("C2", "E2"), ("D2", "G2"),
    ("E2", "I2"), ("F2", "K2"), ("G2", "M2"), ("H2", "O2"),
    ("A3", "A3"), ("B3", "C3"), ("C3", "E3"), ("D3", "G3"),
    ("E3", "I3"), ("F3", "K3"), ("G3", "M3"), ("H3", "O3"),
    ("A4", "A4"), ("B4", "C4"), ("C4", "E4"), ("D4", "G4"),
    ("E4", "I4"), ("F4", "K4"), ("G4", "M4"), ("H4", "O4"),
    ("A5", "A5"), ("B5", "C5"), ("C5", "E5"), ("D5", "G5"),
    ("E5", "I5"), ("F5", "K5"), ("G5", "M5"), ("H5", "O5"),
    ("A6", "A6"), ("B6", "C6"), ("C6", "E6"), ("D6", "G6"),
    ("E6", "I6"), ("F6", "K6"), ("G6", "M6"), ("H6", "O6"),
    ("A7", "A7"), ("B7", "C7"), ("C7", "E7"), ("D7", "G7"),
    ("E7", "I7"), ("F7", "K7"), ("G7", "M7"), ("H7", "O7"),
    ("A8", "A8"), ("B8", "C8"), ("C8", "E8"), ("D8", "G8"),
    ("E8", "I8"), ("F8", "K8"), ("G8", "M8"), ("H8", "O8"),
    ("A9", "A9"), ("B9", "C9"), ("C9", "E9"), ("D9", "G9"),
    ("E9", "I9"), ("F9", "K9"), ("G9", "M9"), ("H9", "O9"),
    ("A10", "A10"), ("B10", "C10"), ("C10", "E10"), ("D10", "G10"),
    ("E10", "I10"), ("F10", "K10"), ("G10", "M10"), ("H10", "O10"),
    ("A11", "A11"), ("B11", "C11"), ("C11", "E11"), ("D11", "G11"),
    ("E11", "I11"), ("F11", "K11"), ("G11", "M11"), ("H11", "O11"),
    ("A12", "A12"), ("B12", "C12"), ("C12", "E12"), ("D12", "G12"),
    ("E12", "I12"), ("F12", "K12"), ("G12", "M12"),
)

# Every source well a reverse primer was drawn from in the same file. Reverse
# primers are deduplicated, so there are fewer of them than mutants and they
# cannot be matched to a destination one for one.
OBSERVED_REVERSE: frozenset[str] = frozenset({
    "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8",
    "B9", "D1", "D2", "D3", "D4", "D5", "D6", "D7",
    "D8", "D9", "F1", "F2", "F3", "F4", "F5", "F6",
    "F7", "F8", "H1", "H2", "H3", "H4", "H5", "H6",
    "H7", "H8", "J1", "J2", "J3", "J4", "J5", "J6",
    "J7", "J8", "L1", "L2", "L3", "L4", "L5", "L6",
    "L7", "L8", "N1", "N2", "N3", "N4", "N5", "N6",
    "N7", "N8", "P1", "P2", "P3", "P4", "P5", "P6",
    "P7", "P8",
})


def _all_96_wells() -> list[str]:
    return [f"{row}{col}" for col in range(1, 13) for row in _ROWS_96]


def _half_well(well_96: str, half: str, *, reverse: bool = False) -> str:
    """The half-layout rule of v0.16.61, inlined so the two can be compared.

    Read back from ``git show a9ad1472:kuma_core/kuro/plate_quadrant.py``: rows
    doubled with a 0/1 forward/reverse offset and the 96 column carried over
    plus a half offset of 0 for ``A1`` and 12 for ``A13``. The two modules
    cannot be imported side by side, so the rule is copied rather than called.
    """
    col_offset = 0 if half == "A1" else 12
    row = _ROWS_384[_ROWS_96.index(well_96[0]) * 2 + (1 if reverse else 0)]
    return f"{row}{int(well_96[1:]) + col_offset}"


_ROWS_384 = "ABCDEFGHIJKLMNOP"


class TestWorkbookDisagrees:
    """Where the recorded worklist and the column-parity geometry part.

    Pinned rather than resolved. The operator statement of 2026-09-20 decides
    which one this module implements; this class only keeps the size and shape
    of the disagreement visible.
    """

    def test_observed_forward_count_matches_the_workbook(self):
        assert len(OBSERVED_FORWARD) == 95
        assert len({s for _, s in OBSERVED_FORWARD}) == 95

    def test_the_two_agree_on_the_first_column_only(self):
        agree = [
            dest for dest, source in OBSERVED_FORWARD
            if to_384_well(dest, "A1") == source
        ]

        # Column 1 is where (col - 1) * 2 + 1 == col, so the first eight
        # destinations match and nothing after them does. That single column
        # is how the drift stayed invisible for one release.
        assert agree == ["A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1"]

    def test_the_workbook_column_for_dest_a2_is_not_the_interleaved_one(self):
        assert dict(OBSERVED_FORWARD)["A2"] == "A2"
        assert to_384_well("A2", "A1") == "A3"

    def test_the_workbook_occupies_twelve_consecutive_columns(self):
        columns = {int(source[1:]) for _, source in OBSERVED_FORWARD}
        assert columns == set(range(1, 13))
        assert {int(w[1:]) for w in OBSERVED_REVERSE} <= set(range(1, 13))

    def test_the_geometry_occupies_every_other_column_instead(self):
        columns = {int(w[1:]) for w in quadrant_wells("A1")}
        assert columns == set(range(1, 25, 2))


class TestGeometry:
    def test_each_round_starts_at_the_well_it_is_named_after(self):
        assert to_384_well("A1", "A1") == "A1"
        assert to_384_well("A1", "A2") == "A2"

    def test_a_stamp_skips_every_other_column(self):
        # 기하 변경의 판별점. 절반 배치에서는 이 값이 "A2" 였다.
        assert to_384_well("A2", "A1") == "A3"
        assert to_384_well("A3", "A1") == "A5"
        assert to_384_well("A2", "A2") == "A4"

    def test_forward_rows_are_the_even_ones(self):
        wells = quadrant_wells("A1", reverse=False)

        assert {w[0] for w in wells} == set("ACEGIKMO")
        assert {int(w[1:]) for w in wells} == set(range(1, 25, 2))

    def test_reverse_rows_are_the_odd_ones_in_the_same_columns(self):
        wells = quadrant_wells("A1", reverse=True)

        assert {w[0] for w in wells} == set("BDFHJLNP")
        assert {int(w[1:]) for w in wells} == set(range(1, 25, 2))

    def test_the_second_round_is_the_even_columns(self):
        wells = quadrant_wells("A2")

        assert {int(w[1:]) for w in wells} == set(range(2, 25, 2))
        assert {w[0] for w in wells} == set(_ROWS_384)

    def test_far_corner_of_each_round(self):
        assert to_384_well("H12", "A1") == "O23"
        assert to_384_well("H12", "A1", reverse=True) == "P23"
        assert to_384_well("H12", "A2") == "O24"
        assert to_384_well("H12", "A2", reverse=True) == "P24"

    def test_each_round_holds_192_wells(self):
        for name in QUADRANTS:
            assert len(set(quadrant_wells(name))) == 192

    def test_the_two_rounds_tile_the_plate_without_overlap(self):
        all_wells = [w for name in QUADRANTS for w in quadrant_wells(name)]

        assert len(all_wells) == 384
        assert len(set(all_wells)) == 384

    def test_there_are_exactly_two_rounds(self):
        # 행 축은 선택지가 아니다. 옛 4지선다는 A1/B1 과 A2/B2 가 같은 라운드를
        # forward/reverse 만 바꿔 부른 이름이어서 행 축이 중복이었다.
        assert QUADRANTS == ("A1", "A2")

    def test_column_major_order_is_preserved(self):
        wells = quadrant_wells("A1", reverse=False)
        assert wells[:3] == ["A1", "C1", "E1"]
        assert wells[8] == "A3"

    def test_the_default_matches_the_no_quadrant_path_on_the_first_column(self):
        # quadrant 미지정 경로는 열을 건너뛰지 않는다. 1열에서만 A1 과 일치하고
        # 그 차이가 곧 이번 기하 변경이다.
        for row in _ROWS_96:
            assert _to_384_well_fwd(f"{row}1") == _to_384_well_fwd(f"{row}1", quadrant="A1")
            assert _to_384_well_rev(f"{row}1") == _to_384_well_rev(f"{row}1", quadrant="A1")
        assert _to_384_well_fwd("A2") != _to_384_well_fwd("A2", quadrant="A1")


class TestHalfLayoutIsNotAParity:
    """A half from v0.16.61 covers part of both rounds."""

    @pytest.mark.parametrize(
        "well,half,parity",
        [
            # A1 is the one well the two vocabularies agree on, which is why a
            # stored "A1" cannot be dated by its own text.
            ("A1", "A1", "A1"),
            ("A2", "A2", "A3"),
            ("D7", "G7", "G13"),
            ("H12", "O12", "O23"),
        ],
    )
    def test_a_stored_half_points_somewhere_else_now(self, well, half, parity):
        assert _half_well(well, "A1") == half
        assert to_384_well(well, "A1") == parity

    @pytest.mark.parametrize("half", ["A1", "A13"])
    def test_one_half_sits_on_96_wells_of_each_round(self, half):
        occupied = {
            _half_well(well, half, reverse=reverse)
            for well in _all_96_wells()
            for reverse in (False, True)
        }

        assert len(occupied) == 192
        for name in QUADRANTS:
            overlap = occupied & set(quadrant_wells(name))
            # 12 연속 열 중 홀수 6, 짝수 6 이 각각 16 행에 걸린다. 어느 round 도
            # 깨끗하지 않고, 그래서 half 저장본은 둘 다 소진으로 만든다.
            assert len(overlap) == 96

    def test_a13_is_the_only_name_that_dates_a_placement_by_itself(self):
        assert LEGACY_QUADRANTS == frozenset({"A13"})


class TestInterleavedEraNamesFold:
    """``B1`` and ``B2`` name these same rounds and move no coordinate."""

    def test_the_fold_table_is_the_row_axis_the_picker_dropped(self):
        assert FOLDED_QUADRANTS == {"B1": "A1", "B2": "A2"}

    @pytest.mark.parametrize("stored,folded", [("B1", "A1"), ("B2", "A2")])
    def test_a_folded_name_reaches_the_same_columns(self, stored, folded):
        assert validate_quadrant(stored) == folded
        assert set(quadrant_wells(stored)) == set(quadrant_wells(folded))

    @pytest.mark.parametrize("stored,folded", [("B1", "A1"), ("B2", "A2")])
    def test_folding_is_reported_as_ordinary_rather_than_legacy(self, stored, folded):
        # 이 폴딩은 좌표를 하나도 움직이지 않으므로 작업자가 할 일이 없다.
        # legacy_seen 에 실으면 아무 행동도 요구하지 않는 경고를 띄우게 된다.
        placement = fold_persisted_placement(stored, [])

        assert placement.quadrant == folded
        assert placement.legacy_seen == ()


class TestPersistedPlacement:
    """``fold_persisted_placement`` is the one definition of the load rule."""

    def test_a_stored_half_name_is_dropped_rather_than_folded(self):
        placement = fold_persisted_placement("A13", [])

        assert placement.quadrant is None
        assert placement.legacy_seen == ("A13",)
        assert placement.used_quadrants == ["A1", "A2"]

    @pytest.mark.parametrize("stored", [["A13"], ["A1", "A13"]])
    def test_a_half_in_the_used_list_spends_both_rounds(self, stored):
        placement = fold_persisted_placement(None, stored)

        assert placement.used_quadrants == list(QUADRANTS)
        assert placement.legacy_seen

    def test_a_half_name_anywhere_dates_the_whole_placement(self):
        # quadrant 가 half 이름이면 used 의 "A1" 도 1~12 열 블록이다. 두 필드를
        # 함께 읽어야 그 "A1" 을 홀수 열로 오독하지 않는다.
        placement = fold_persisted_placement("A13", ["A1"])

        assert placement.quadrant is None
        assert placement.legacy_seen == ("A13", "A1")
        assert placement.used_quadrants == list(QUADRANTS)

    @pytest.mark.parametrize(
        "quadrant,used",
        [("A1", []), ("A2", ["A1"]), (None, ["A1", "A2"]), (None, []), ("A1", ["A2"])],
    )
    def test_a_current_placement_passes_through_untouched(self, quadrant, used):
        placement = fold_persisted_placement(quadrant, used)

        assert placement.quadrant == quadrant
        assert placement.used_quadrants == [q for q in QUADRANTS if q in used]
        assert placement.legacy_seen == ()

    def test_an_interleaved_used_list_folds_and_de_duplicates(self):
        placement = fold_persisted_placement("A2", ["B1", "A1", "B2"])

        assert placement.quadrant == "A2"
        assert placement.used_quadrants == ["A1", "A2"]
        assert placement.legacy_seen == ()

    def test_a_bare_a1_is_read_as_the_current_round(self):
        """``A1`` names the odd columns now and named columns 1-12 before.

        The core is handed values rather than files, so it has no way to date
        this one input. The current reading wins, because the other one would
        mark every project this version saves as full. The version test that
        can separate them lives in ``src/lib/echoQuadrant.ts``, where the saved
        app version is available.
        """
        assert fold_persisted_placement(None, ["A1"]).used_quadrants == ["A1"]
        assert fold_persisted_placement("A1", ["A2"]).quadrant == "A1"
        assert fold_persisted_placement("A1", ["A2"]).legacy_seen == ()

    def test_unknown_strings_are_dropped_without_being_called_legacy(self):
        placement = fold_persisted_placement("C9", ["A2", "Z4", "a2"])

        assert placement.quadrant is None
        assert placement.used_quadrants == ["A2"]
        assert placement.legacy_seen == ()

    def test_the_geometry_refuses_a_half_name_instead_of_moving_wells(self):
        # fold 를 거치지 않고 half 이름이 기하에 닿으면 소스 웰이 말없이 옮겨진다.
        for call in (
            lambda: validate_quadrant("A13"),
            lambda: to_384_well("A1", "A13"),
            lambda: quadrant_wells("A13"),
            lambda: check_quadrants_available("A13"),
        ):
            with pytest.raises(ValueError, match="source-plate half"):
                call()


class TestUsedQuadrants:
    def test_a_free_plate_resolves_the_round(self):
        assert check_quadrants_available("A1") == "A1"

    def test_second_round_on_a_part_used_plate(self):
        assert check_quadrants_available("A2", used_quadrants=["A1"]) == "A2"

    def test_an_interleaved_used_name_still_blocks_its_round(self):
        # 옛 "B1" 은 홀수 열 라운드의 reverse 쪽 이름이다. 접지 않으면 그 라운드가
        # 비어 있다고 읽혀 프라이머 위에 덮어쓰게 된다.
        with pytest.raises(ValueError, match="already used"):
            check_quadrants_available("A1", used_quadrants=["B1"])

    def test_refuses_a_round_already_spent(self):
        with pytest.raises(ValueError, match="already used"):
            check_quadrants_available("A1", used_quadrants=["A1"])

    @pytest.mark.parametrize("target", ["A1", "A2"])
    def test_a_stored_half_in_the_used_list_blocks_both_rounds(self, target):
        with pytest.raises(ValueError, match="already used"):
            check_quadrants_available(target, used_quadrants=["A13"])

    def test_the_refusal_says_whether_the_round_was_stated_or_folded(self):
        with pytest.raises(ValueError, match="stated for this plate"):
            check_quadrants_available("A1", used_quadrants=["A1"])

        with pytest.raises(ValueError, match="folded from the stored value"):
            check_quadrants_available("A1", used_quadrants=["A13"])

    def test_error_names_the_round_still_free(self):
        with pytest.raises(ValueError, match="Still free: A2"):
            check_quadrants_available("A1", used_quadrants=["A1"])

    def test_error_says_the_plate_is_full_when_a_half_spent_it(self):
        with pytest.raises(ValueError, match="this plate is full"):
            check_quadrants_available("A1", used_quadrants=["A13"])

    def test_error_says_so_when_the_plate_is_full(self):
        with pytest.raises(ValueError, match="plate is full"):
            check_quadrants_available("A1", used_quadrants=list(QUADRANTS))


class TestRefusals:
    @pytest.mark.parametrize("bad", ["C1", "A3", "", "a", "Z9", "A24"])
    def test_unknown_round(self, bad):
        with pytest.raises(ValueError, match="Unknown quadrant"):
            to_384_well("A1", bad)

    def test_round_name_is_case_insensitive(self):
        assert to_384_well("A1", "a2") == "A2"
        assert to_384_well("A1", "b1") == "A1"

    @pytest.mark.parametrize("bad", ["I1", "A13", "A0", "AX"])
    def test_bad_96_well_address(self, bad):
        with pytest.raises(ValueError):
            to_384_well(bad, "A1")
