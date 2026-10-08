"""Echo mapping CSV with a source-plate column parity selected.

The source-plate addresses have to land inside the chosen parity, because that
parity is what one 96-head stamp reaches and two rounds fill the plate.

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


class TestParityAddresses:
    @pytest.mark.parametrize("round_name", ["A1", "A2"])
    def test_every_source_well_lies_in_the_chosen_round(
        self, mappings, tmp_path, round_name
    ):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant=round_name)

        allowed = set(quadrant_wells(round_name))
        for _, well in _source_wells(out):
            assert well in allowed, f"{well} outside round {round_name}"

    @pytest.mark.parametrize("round_name,parity", [("A1", 1), ("A2", 0)])
    def test_a_round_uses_every_other_column(
        self, mappings, tmp_path, round_name, parity
    ):
        # 절반 배치였다면 1~12 또는 13~24 연속 열이 나와 이 검사를 통과하지 못한다.
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant=round_name)

        used = {int(w[1:]) for _, w in _source_wells(out)}
        assert {c % 2 for c in used} == {parity}

    def test_forward_and_reverse_split_across_the_rows_of_one_round(
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
        # 절반 배치에서는 O12 였다. 열을 건너뛰는 기하의 판별점이다.
        assert wells["M3_F"] == "O23"

    def test_a2_shifts_the_same_layout_one_column_over(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant="A2")

        wells = dict(_source_wells(out))
        assert wells["M1_F"] == "A2"
        assert wells["M1_R"] == "B2"
        assert wells["M3_F"] == "O24"

    def test_without_a_round_the_layout_skips_no_column(self, mappings, tmp_path):
        # quadrant 미지정 경로는 1~12 열을 그대로 쓴다. A1 과 1열에서만 겹치므로
        # H12 에서 갈린다.
        fwd, rev = mappings
        plain = tmp_path / "plain.csv"
        export_echo_mapping_csv(fwd, rev, plain)

        wells = dict(_source_wells(plain))
        assert wells["M1_F"] == "A1"
        assert wells["M1_R"] == "B1"
        assert wells["M3_F"] == "O12"


class TestStoredValues:
    @pytest.mark.parametrize(
        "stored,expected_fwd",
        # (b) 교차 시절 저장본. B1/B2 는 같은 라운드의 reverse 쪽 이름이라 접히고
        # 좌표는 하나도 움직이지 않는다.
        [("A1", "A1"), ("A2", "A2"), ("B1", "A1"), ("B2", "A2")],
    )
    def test_a_stored_round_name_exports_where_it_always_did(
        self, mappings, tmp_path, stored, expected_fwd
    ):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant=stored)

        assert dict(_source_wells(out))["M1_F"] == expected_fwd

    def test_a_stored_half_name_is_refused_rather_than_placed_in_a_round(
        self, mappings, tmp_path
    ):
        # (b) v0.16.61 의 half 이름은 어느 열 패리티에도 대응되지 않는다. 한쪽으로
        # 접으면 저장된 프로젝트를 다시 열어 export 할 때 소스 웰이 예전과
        # 달라지는데 그 사실을 어디에서도 알리지 않는다. 작업자가 다시 고르게 한다.
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        with pytest.raises(ValueError, match="source-plate half"):
            export_echo_mapping_csv(fwd, rev, out, quadrant="A13")

        assert not out.exists()


class TestUsedRoundRefusal:
    def test_refuses_to_dispense_onto_a_spent_round(self, mappings, tmp_path):
        fwd, rev = mappings

        with pytest.raises(ValueError, match="already used"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv",
                quadrant="A1", used_quadrants=["A1"],
            )

    def test_an_interleaved_used_name_blocks_the_round_it_folds_onto(
        self, mappings, tmp_path
    ):
        fwd, rev = mappings

        with pytest.raises(ValueError, match="already used"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv",
                quadrant="A1", used_quadrants=["B1"],
            )

    def test_second_round_onto_the_free_one_is_allowed(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        export_echo_mapping_csv(fwd, rev, out, quadrant="A2", used_quadrants=["A1"])

        assert dict(_source_wells(out))["M1_F"] == "A2"

    @pytest.mark.parametrize("target", ["A1", "A2"])
    def test_a_stored_half_in_the_used_list_leaves_no_round_free(
        self, mappings, tmp_path, target
    ):
        # half 하나가 연속 12열을 16행 전부에 걸쳐 채웠으므로 홀수 열 6개와 짝수 열
        # 6개, 곧 두 라운드 각각의 192 웰 중 96 웰 위에 앉는다.
        fwd, rev = mappings

        with pytest.raises(ValueError, match="already used"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv",
                quadrant=target, used_quadrants=["A13"],
            )

    def test_a_spent_round_with_no_selection_is_refused_too(self, mappings, tmp_path):
        # round 를 안 고르면 기본 경로가 열을 건너뛰지 않는 배치를 그리는데 그
        # 경로에는 소진 검사가 걸리지 않아 선언이 통째로 무시된다.
        fwd, rev = mappings

        with pytest.raises(ValueError, match="none was selected"):
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
