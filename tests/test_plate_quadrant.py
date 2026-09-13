"""Echo 384 source-plate halves (kuma_core/kuro/plate_quadrant.py).

The reference is the worklist the lab actually ran, not a slide. See
``OBSERVED_FORWARD`` below for the provenance of the fixture, and the module
docstring of ``plate_quadrant`` for why the interleaved layout it replaced was
wrong.
"""

from __future__ import annotations

import pytest

from kuma_core.kuro.plate_mapper import _to_384_well_fwd, _to_384_well_rev
from kuma_core.kuro.plate_quadrant import (
    QUADRANTS,
    check_quadrants_available,
    fold_persisted_placement,
    quadrant_wells,
    to_384_well,
    validate_quadrant,
)

_ROWS_96 = "ABCDEFGH"

# Observed occupancy of a real Echo source plate. Parsed 2026-09-13 from sheet
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


class TestObservedPlate:
    """Known-answer check against the plate the lab built."""

    def test_every_observed_forward_well_is_reproduced(self):
        # 교차(interleaved) 기하는 여기서 갈린다. dest A2 는 관측이 source A2 인데
        # 열을 2배하면 A3 가 되므로 첫 열 바깥의 모든 웰이 어긋난다.
        for dest, source in OBSERVED_FORWARD:
            assert _to_384_well_fwd(dest, quadrant="A1") == source, dest

    def test_observed_forward_count_matches_the_workbook(self):
        assert len(OBSERVED_FORWARD) == 95
        assert len({s for _, s in OBSERVED_FORWARD}) == 95

    def test_every_observed_reverse_well_is_reachable(self):
        reverse_wells = set(quadrant_wells("A1", reverse=True))
        assert OBSERVED_REVERSE <= reverse_wells

    def test_consecutive_mutants_step_two_rows_down_one_column(self):
        # 워크북 첫 두 전송이 V5F_F -> A1, V10L_F -> C1 이다. 목적 플레이트는
        # column-major 이므로 A1 다음 변이는 B1 이고 그 소스가 C1 이어야 한다.
        assert _to_384_well_fwd("A1", quadrant="A1") == "A1"
        assert _to_384_well_fwd("B1", quadrant="A1") == "C1"

    def test_nothing_lands_outside_the_left_half(self):
        for well in _all_96_wells():
            for mapped in (
                _to_384_well_fwd(well, quadrant="A1"),
                _to_384_well_rev(well, quadrant="A1"),
            ):
                assert 1 <= int(mapped[1:]) <= 12, mapped


class TestGeometry:
    def test_each_half_starts_at_the_well_it_is_named_after(self):
        assert to_384_well("A1", "A1") == "A1"
        assert to_384_well("A1", "A13") == "A13"

    def test_forward_rows_are_the_odd_ones_and_columns_run_1_to_12(self):
        wells = quadrant_wells("A1", reverse=False)

        assert {w[0] for w in wells} == set("ACEGIKMO")
        assert {int(w[1:]) for w in wells} == set(range(1, 13))

    def test_reverse_rows_are_the_even_ones_in_the_same_columns(self):
        wells = quadrant_wells("A1", reverse=True)

        assert {w[0] for w in wells} == set("BDFHJLNP")
        assert {int(w[1:]) for w in wells} == set(range(1, 13))

    def test_the_right_half_is_columns_13_to_24(self):
        wells = quadrant_wells("A13")

        assert {int(w[1:]) for w in wells} == set(range(13, 25))
        assert {w[0] for w in wells} == set("ABCDEFGHIJKLMNOP")

    def test_far_corner_of_each_half(self):
        assert to_384_well("H12", "A1") == "O12"
        assert to_384_well("H12", "A1", reverse=True) == "P12"
        assert to_384_well("H12", "A13") == "O24"
        assert to_384_well("H12", "A13", reverse=True) == "P24"

    def test_each_half_holds_192_wells(self):
        for half in QUADRANTS:
            assert len(set(quadrant_wells(half))) == 192

    def test_the_two_halves_tile_the_plate_without_overlap(self):
        all_wells = [w for half in QUADRANTS for w in quadrant_wells(half)]

        assert len(all_wells) == 384
        assert len(set(all_wells)) == 384

    def test_there_are_exactly_two_halves(self):
        assert QUADRANTS == ("A1", "A13")

    def test_column_major_order_is_preserved(self):
        wells = quadrant_wells("A1", reverse=False)
        assert wells[:3] == ["A1", "C1", "E1"]
        assert wells[8] == "A2"


class TestOldGeometryIsNotAHalf:
    """The old placement spanned the plate, so it folds onto no half.

    The old module cannot be imported next to the new one, so its rule is
    inlined here from
    ``git show 4d38efe2~1:kuma_core/kuro/plate_quadrant.py``: rows doubled with
    a 0/1 row offset and ``col_384 = (col - 1) * 2 + 1 + col_offset`` with
    ``col_offset`` 0 for A1/B1 and 1 for A2/B2. The interleaved layout arrived
    in ``c285d5d6`` (#211, v0.14.0) and the workbook in
    ``tests/test_plate_quadrant.py::OBSERVED_FORWARD`` contradicts it.
    """

    @staticmethod
    def _old_well(well_96: str, quadrant: str) -> str:
        row_offset = 0 if quadrant[0] == "A" else 1
        col_offset = 0 if quadrant[1:] == "1" else 1
        col = int(well_96[1:])
        row = "ABCDEFGHIJKLMNOP"[_ROWS_96.index(well_96[0]) * 2 + row_offset]
        return f"{row}{(col - 1) * 2 + 1 + col_offset}"

    @pytest.mark.parametrize(
        "well,old,new",
        [
            # Observed by running the old rule above. A1 is the one well the
            # two geometries agree on, which is why the drift stayed invisible.
            ("A1", "A1", "A1"),
            ("A2", "A3", "A2"),
            ("D7", "G13", "G7"),
            ("H12", "O23", "O12"),
        ],
    )
    def test_a_stored_value_points_somewhere_else_now(self, well, old, new):
        assert self._old_well(well, "A1") == old
        assert to_384_well(well, "A1") == new

    @pytest.mark.parametrize("quadrant", ["A1", "A2", "B1", "B2"])
    def test_every_old_value_spanned_the_full_plate_width(self, quadrant):
        columns = {int(self._old_well(w, quadrant)[1:]) for w in _all_96_wells()}

        assert min(columns) <= 2
        assert max(columns) >= 23

    @pytest.mark.parametrize("pair", [("A1", "B1"), ("A2", "B2")])
    def test_an_old_round_left_96_wells_in_each_new_half(self, pair):
        # 모듈 docstring 이 적은 192 중 96/96 을 여기서 계산해 고정한다. 옛 라운드
        # 하나가 양쪽 절반을 반씩 채웠으므로 어느 절반도 새 라운드를 통째로 받지
        # 못한다.
        occupied = {
            self._old_well(well, half) for half in pair for well in _all_96_wells()
        }

        assert len(occupied) == 192
        assert len([w for w in occupied if int(w[1:]) <= 12]) == 96
        assert len([w for w in occupied if int(w[1:]) >= 13]) == 96


class TestPersistedPlacement:
    """``fold_persisted_placement`` is the one definition of the load rule."""

    @pytest.mark.parametrize("stored", ["A2", "B1", "B2"])
    def test_an_old_quadrant_is_dropped_rather_than_folded(self, stored):
        placement = fold_persisted_placement(stored, [])

        assert placement.quadrant is None
        assert placement.legacy_seen == (stored,)
        assert placement.used_quadrants == ["A1", "A13"]

    @pytest.mark.parametrize(
        "stored", [["A1", "B1"], ["A2"], ["B1"], ["B2"], ["A2", "B2"]],
    )
    def test_an_old_used_list_spends_both_halves(self, stored):
        placement = fold_persisted_placement(None, stored)

        assert placement.used_quadrants == ["A1", "A13"]
        assert placement.legacy_seen

    def test_an_old_value_anywhere_dates_the_whole_placement(self):
        # quadrant 가 옛 값이면 used 의 "A1" 도 옛 이름이다. 두 필드를 함께 읽어야
        # 그 "A1" 을 좌측 절반으로 오독하지 않는다.
        placement = fold_persisted_placement("B2", ["A1"])

        assert placement.quadrant is None
        assert placement.legacy_seen == ("B2", "A1")
        assert placement.used_quadrants == ["A1", "A13"]

    @pytest.mark.parametrize(
        "quadrant,used",
        [("A1", []), ("A13", ["A1"]), (None, ["A1", "A13"]), (None, [])],
    )
    def test_a_current_placement_passes_through_untouched(self, quadrant, used):
        placement = fold_persisted_placement(quadrant, used)

        assert placement.quadrant == quadrant
        assert placement.used_quadrants == [q for q in QUADRANTS if q in used]
        assert placement.legacy_seen == ()

    def test_a_bare_a1_is_read_as_the_current_half(self):
        """``A1`` names a half now and named an odd-column set before.

        The task asked for every old value in ``used_quadrants`` to spend both
        halves, and also for a current project to pass through untouched. Those
        collide on this one input and the current reading wins: the other one
        would mark every project this version saves as full. The module
        docstring carries the same note.
        """
        assert fold_persisted_placement(None, ["A1"]).used_quadrants == ["A1"]
        assert fold_persisted_placement("A1", ["A13"]).quadrant == "A1"
        assert fold_persisted_placement("A1", ["A13"]).legacy_seen == ()

    def test_unknown_strings_are_dropped_without_being_called_legacy(self):
        placement = fold_persisted_placement("C9", ["A13", "Z4", "a13"])

        assert placement.quadrant is None
        assert placement.used_quadrants == ["A13"]
        assert placement.legacy_seen == ()

    @pytest.mark.parametrize("stored", ["A2", "B1", "B2"])
    def test_the_geometry_refuses_an_old_value_instead_of_moving_wells(self, stored):
        # fold 를 거치지 않고 옛 값이 기하에 닿으면 소스 웰이 말없이 옮겨진다.
        for call in (
            lambda: validate_quadrant(stored),
            lambda: to_384_well("A1", stored),
            lambda: quadrant_wells(stored),
            lambda: check_quadrants_available(stored),
        ):
            with pytest.raises(ValueError, match="predates"):
                call()

    def test_the_default_matches_the_no_quadrant_path_everywhere(self):
        # quadrant 미지정 경로가 A1 절반과 96 웰 전부에서 같은 답을 내야 한다.
        # 다르면 기존 프로젝트의 소스 웰이 조용히 움직인다.
        for well in _all_96_wells():
            assert _to_384_well_fwd(well) == _to_384_well_fwd(well, quadrant="A1")
            assert _to_384_well_rev(well) == _to_384_well_rev(well, quadrant="A1")


class TestUsedQuadrants:
    def test_a_free_plate_resolves_the_half(self):
        assert check_quadrants_available("A1") == "A1"

    def test_second_round_on_a_part_used_plate(self):
        assert check_quadrants_available("A13", used_quadrants=["A1"]) == "A13"

    def test_refuses_a_half_already_spent(self):
        with pytest.raises(ValueError, match="already used"):
            check_quadrants_available("A1", used_quadrants=["A1"])

    @pytest.mark.parametrize("stored", [["A1", "B1"], ["A2"], ["B1"], ["B2"]])
    @pytest.mark.parametrize("target", ["A1", "A13"])
    def test_an_old_used_value_blocks_both_halves(self, stored, target):
        # 옛 값 하나가 플레이트 전폭에 걸쳐 있었으므로 남는 절반이 없다. 이전
        # 판은 ["A1","B1"] 을 좌측 하나로 접어 우측을 비어 있다고 선언했고, 그
        # 절반에 실제로 들어 있던 프라이머 96개를 덮어쓰게 두었다.
        with pytest.raises(ValueError, match="already used"):
            check_quadrants_available(target, used_quadrants=stored)

    def test_the_refusal_says_whether_the_half_was_stated_or_folded(self):
        with pytest.raises(ValueError, match="stated for this plate"):
            check_quadrants_available("A1", used_quadrants=["A1"])

        with pytest.raises(ValueError, match="folded from the stored value"):
            check_quadrants_available("A1", used_quadrants=["B1"])

    def test_error_names_the_half_still_free(self):
        with pytest.raises(ValueError, match="Still free: A13"):
            check_quadrants_available("A1", used_quadrants=["A1"])

    def test_error_says_the_plate_is_full_when_an_old_value_spent_it(self):
        with pytest.raises(ValueError, match="this plate is full"):
            check_quadrants_available("A1", used_quadrants=["B1"])

    def test_error_says_so_when_the_plate_is_full(self):
        with pytest.raises(ValueError, match="plate is full"):
            check_quadrants_available("A1", used_quadrants=list(QUADRANTS))


class TestRefusals:
    @pytest.mark.parametrize("bad", ["C1", "A3", "", "a", "Z9", "A24"])
    def test_unknown_half(self, bad):
        with pytest.raises(ValueError, match="Unknown quadrant"):
            to_384_well("A1", bad)

    def test_half_name_is_case_insensitive(self):
        assert to_384_well("A1", "a13") == "A13"

    @pytest.mark.parametrize("bad", ["I1", "A13", "A0", "AX"])
    def test_bad_96_well_address(self, bad):
        with pytest.raises(ValueError):
            to_384_well(bad, "A1")
