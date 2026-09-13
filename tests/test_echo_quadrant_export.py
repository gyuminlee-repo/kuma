"""Echo mapping CSV with a source-plate half selected.

The source-plate addresses have to land inside the chosen half, because a half
is what one round of a primer set occupies and two rounds fill the plate.

Whether the CSV, the XLSX worklist sheet and the sidecar preview name the same
wells is a separate question, asked in tests/test_echo_writer_consistency.py.
"""

from __future__ import annotations

import csv

import pytest

from kuma_core.kuro.plate_mapper import PlateMapping, export_echo_mapping_csv
from kuma_core.kuro.plate_quadrant import quadrant_wells


@pytest.fixture
def mappings():
    fwd = [
        PlateMapping("A1", "M1_F", "AAATTTCCCGGGAAATTT", "forward", "M1"),
        PlateMapping("B1", "M2_F", "AAATTTCCCGGGAAAGGG", "forward", "M2"),
        PlateMapping("H12", "M3_F", "AAATTTCCCGGGAAACCC", "forward", "M3"),
    ]
    rev = [
        PlateMapping("A1", "M1_R", "TTTAAAGGGCCCTTTAAA", "reverse", "M1"),
        PlateMapping("B1", "M2_R", "TTTAAAGGGCCCTTTGGG", "reverse", "M2"),
        PlateMapping("H12", "M3_R", "TTTAAAGGGCCCTTTCCC", "reverse", "M3"),
    ]
    return fwd, rev


def _source_wells(path):
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    header = rows[0]
    idx = header.index("Source Well")
    name_idx = header.index("Source Well Name")
    return [(r[name_idx], r[idx]) for r in rows[1:]]


class TestHalfAddresses:
    @pytest.mark.parametrize("half", ["A1", "A13"])
    def test_every_source_well_lies_in_the_chosen_half(self, mappings, tmp_path, half):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant=half)

        allowed = set(quadrant_wells(half))
        for _, well in _source_wells(out):
            assert well in allowed, f"{well} outside half {half}"

    @pytest.mark.parametrize(
        "half,columns",
        [("A1", set(range(1, 13))), ("A13", set(range(13, 25)))],
    )
    def test_a_half_uses_twelve_consecutive_columns(
        self, mappings, tmp_path, half, columns
    ):
        # 교차 배치였다면 홀수 또는 짝수 열만 나와 이 집합에 들지 못한다.
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant=half)

        used = {int(w[1:]) for _, w in _source_wells(out)}
        assert used <= columns

    def test_forward_and_reverse_split_across_the_rows_of_one_half(
        self, mappings, tmp_path
    ):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant="A1")

        fwd_wells = {w for name, w in _source_wells(out) if name.endswith("_F")}
        rev_wells = {w for name, w in _source_wells(out) if name.endswith("_R")}

        assert fwd_wells <= set(quadrant_wells("A1", reverse=False))
        assert rev_wells <= set(quadrant_wells("A1", reverse=True))
        assert not (fwd_wells & rev_wells)

    def test_a1_maps_the_first_well_to_384_a1(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant="A1")

        wells = dict(_source_wells(out))
        assert wells["M1_F"] == "A1"
        assert wells["M1_R"] == "B1"
        assert wells["M3_F"] == "O12"

    def test_a13_shifts_the_same_layout_twelve_columns_over(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant="A13")

        wells = dict(_source_wells(out))
        assert wells["M1_F"] == "A13"
        assert wells["M1_R"] == "B13"
        assert wells["M3_F"] == "O24"

    def test_without_a_half_the_layout_is_the_left_one(self, mappings, tmp_path):
        fwd, rev = mappings
        plain = tmp_path / "plain.csv"
        left = tmp_path / "left.csv"
        export_echo_mapping_csv(fwd, rev, plain)
        export_echo_mapping_csv(fwd, rev, left, quadrant="A1")

        assert _source_wells(plain) == _source_wells(left)
        wells = dict(_source_wells(plain))
        assert wells["M1_F"] == "A1"
        assert wells["M1_R"] == "B1"
        assert wells["M3_F"] == "O12"


class TestLegacyStoredValues:
    @pytest.mark.parametrize(
        "stored,expected_fwd",
        [("A1", "A1"), ("B1", "A1"), ("A2", "A13"), ("B2", "A13")],
    )
    def test_a_saved_project_still_exports(
        self, mappings, tmp_path, stored, expected_fwd
    ):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant=stored)

        assert dict(_source_wells(out))["M1_F"] == expected_fwd


class TestUsedHalfRefusal:
    def test_refuses_to_dispense_onto_a_spent_half(self, mappings, tmp_path):
        fwd, rev = mappings

        with pytest.raises(ValueError, match="already used"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv",
                quadrant="A1", used_quadrants=["A1", "B1"],
            )

    def test_second_round_onto_the_free_half_is_allowed(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        export_echo_mapping_csv(
            fwd, rev, out, quadrant="A13", used_quadrants=["A1", "B1"],
        )

        wells = dict(_source_wells(out))
        assert wells["M1_F"] == "A13"

    def test_a_legacy_partner_value_still_blocks_its_half(self, mappings, tmp_path):
        # 저장된 프로젝트의 "B1" 은 좌측 절반을 뜻하므로 A1 요청을 막아야 한다.
        fwd, rev = mappings

        with pytest.raises(ValueError, match="already used"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv",
                quadrant="A1", used_quadrants=["B1"],
            )

    def test_refusal_happens_before_the_file_is_written(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        with pytest.raises(ValueError):
            export_echo_mapping_csv(
                fwd, rev, out, quadrant="A1", used_quadrants=["B1"],
            )

        assert not out.exists()
