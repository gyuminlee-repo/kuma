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


class TestStoredValues:
    @pytest.mark.parametrize("stored,expected_fwd", [("A1", "A1"), ("A13", "A13")])
    def test_a_current_project_exports_the_half_it_stored(
        self, mappings, tmp_path, stored, expected_fwd
    ):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant=stored)

        assert dict(_source_wells(out))["M1_F"] == expected_fwd

    @pytest.mark.parametrize("stored", ["A2", "B1", "B2"])
    def test_an_old_value_is_refused_rather_than_placed_in_a_half(
        self, mappings, tmp_path, stored
    ):
        # 옛 값은 새 기하에서 가리키는 곳이 없다. 한쪽 절반으로 접으면 저장된
        # 프로젝트를 다시 열어 export 할 때 소스 웰이 예전과 달라지는데 그 사실을
        # 어디에서도 알리지 않는다. 작업자가 절반을 다시 고르게 한다.
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        with pytest.raises(ValueError, match="predates"):
            export_echo_mapping_csv(fwd, rev, out, quadrant=stored)

        assert not out.exists()


class TestUsedHalfRefusal:
    def test_refuses_to_dispense_onto_a_spent_half(self, mappings, tmp_path):
        fwd, rev = mappings

        with pytest.raises(ValueError, match="already used"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv",
                quadrant="A1", used_quadrants=["A1"],
            )

    def test_second_round_onto_the_free_half_is_allowed(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        export_echo_mapping_csv(fwd, rev, out, quadrant="A13", used_quadrants=["A1"])

        wells = dict(_source_wells(out))
        assert wells["M1_F"] == "A13"

    @pytest.mark.parametrize("target", ["A1", "A13"])
    def test_an_old_used_value_leaves_no_half_free(self, mappings, tmp_path, target):
        # 옛 "B1" 라운드는 홀수 열 전폭을 채웠으므로 양쪽 절반에 96 웰씩 남겼다.
        # 좌측 하나로 접던 이전 판은 우측을 비어 있다고 선언해 덮어쓰기를 통과시켰다.
        fwd, rev = mappings

        with pytest.raises(ValueError, match="already used"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv",
                quadrant=target, used_quadrants=["B1"],
            )

    def test_a_spent_half_with_no_selection_is_refused_too(self, mappings, tmp_path):
        # 절반을 안 고르면 기본 경로가 좌측 절반을 그리는데 그 경로에는 소진 검사가
        # 걸리지 않아 선언이 통째로 무시된다.
        fwd, rev = mappings

        with pytest.raises(ValueError, match="no half was selected"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv", used_quadrants=["A1"],
            )

    def test_refusal_happens_before_the_file_is_written(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        with pytest.raises(ValueError):
            export_echo_mapping_csv(
                fwd, rev, out, quadrant="A1", used_quadrants=["A1"],
            )

        assert not out.exists()
