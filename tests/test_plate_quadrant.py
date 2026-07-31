"""Echo 384 source-plate quadrants (kuma_core/kuro/plate_quadrant.py).

The reference is the grid in the 260731 revision deck: a 96-head stamp lights up
odd rows crossed with odd columns, and the four starting wells are A1, A2, B1,
B2. These tests pin that geometry.
"""

from __future__ import annotations

import pytest

from kuma_core.kuro.plate_quadrant import (
    QUADRANTS,
    check_quadrants_available,
    paired_quadrant,
    quadrant_wells,
    to_384_well,
)


class TestGeometry:
    @pytest.mark.parametrize(
        "quadrant,expected",
        [("A1", "A1"), ("A2", "A2"), ("B1", "B1"), ("B2", "B2")],
    )
    def test_each_quadrant_starts_at_the_well_it_is_named_after(self, quadrant, expected):
        assert to_384_well("A1", quadrant) == expected

    def test_a1_is_odd_rows_crossed_with_odd_columns(self):
        # 슬라이드 그리드가 보여주는 패턴이다. 96-head 가 닿을 수 있는 유일한 형태.
        wells = quadrant_wells("A1")
        rows = {w[0] for w in wells}
        cols = {int(w[1:]) for w in wells}

        assert rows == set("ACEGIKMO")
        assert cols == {1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23}

    def test_b2_is_even_rows_crossed_with_even_columns(self):
        wells = quadrant_wells("B2")

        assert {w[0] for w in wells} == set("BDFHJLNP")
        assert {int(w[1:]) for w in wells} == {2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24}

    def test_far_corner_of_a_quadrant(self):
        assert to_384_well("H12", "A1") == "O23"
        assert to_384_well("H12", "B2") == "P24"

    def test_each_quadrant_holds_exactly_96_wells(self):
        for quadrant in QUADRANTS:
            assert len(set(quadrant_wells(quadrant))) == 96

    def test_the_four_quadrants_tile_the_plate_without_overlap(self):
        all_wells = [w for q in QUADRANTS for w in quadrant_wells(q)]

        assert len(all_wells) == 384
        assert len(set(all_wells)) == 384

    def test_column_major_order_is_preserved(self):
        # 96-well 순서(A1,B1,...,H1,A2,...)가 그대로 384 주소로 옮겨진다.
        wells = quadrant_wells("A1")
        assert wells[:3] == ["A1", "C1", "E1"]
        assert wells[8] == "A3"


class TestPairing:
    def test_forward_and_reverse_stay_on_adjacent_rows(self):
        # 기존 row-doubling 관례(2r / 2r+1)를 quadrant 에서도 유지한다.
        assert paired_quadrant("A1") == "B1"
        assert paired_quadrant("B1") == "A1"
        assert paired_quadrant("A2") == "B2"
        assert paired_quadrant("B2") == "A2"

    def test_a_pair_shares_columns(self):
        fwd = {int(w[1:]) for w in quadrant_wells("A1")}
        rev = {int(w[1:]) for w in quadrant_wells("B1")}
        assert fwd == rev

    def test_two_pairs_means_two_rounds_per_plate(self):
        pairs = {frozenset((q, paired_quadrant(q))) for q in QUADRANTS}
        assert len(pairs) == 2


class TestUsedQuadrants:
    def test_a_free_plate_resolves_the_pair(self):
        assert check_quadrants_available("A1") == ("A1", "B1")

    def test_second_round_on_a_part_used_plate(self):
        assert check_quadrants_available("A2", used_quadrants=["A1", "B1"]) == ("A2", "B2")

    def test_refuses_a_forward_quadrant_already_spent(self):
        with pytest.raises(ValueError, match="already used"):
            check_quadrants_available("A1", used_quadrants=["A1"])

    def test_refuses_when_only_the_reverse_partner_is_spent(self):
        # forward 는 비어 있어도 짝이 막혀 있으면 그 round 는 못 넣는다.
        with pytest.raises(ValueError, match="already used"):
            check_quadrants_available("A1", used_quadrants=["B1"])

    def test_error_names_the_quadrants_still_free(self):
        with pytest.raises(ValueError, match="Still free: A2, B2"):
            check_quadrants_available("A1", used_quadrants=["B1"])

    def test_error_says_so_when_the_plate_is_full(self):
        with pytest.raises(ValueError, match="plate is full"):
            check_quadrants_available("A1", used_quadrants=list(QUADRANTS))


class TestRefusals:
    @pytest.mark.parametrize("bad", ["C1", "A3", "", "a", "Z9"])
    def test_unknown_quadrant(self, bad):
        with pytest.raises(ValueError, match="Unknown quadrant"):
            to_384_well("A1", bad)

    def test_quadrant_name_is_case_insensitive(self):
        assert to_384_well("A1", "b2") == "B2"

    @pytest.mark.parametrize("bad", ["I1", "A13", "A0", "AX"])
    def test_bad_96_well_address(self, bad):
        with pytest.raises(ValueError):
            to_384_well(bad, "A1")
