"""Echo mapping CSV with a Zephyr quadrant selected.

The source-plate addresses have to land inside the chosen interleaved set,
because that set is what one 96-head stamp can physically fill.
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


class TestQuadrantAddresses:
    @pytest.mark.parametrize("quadrant", ["A1", "A2", "B1", "B2"])
    def test_every_source_well_lies_in_the_chosen_pair(self, mappings, tmp_path, quadrant):
        from kuma_core.kuro.plate_quadrant import paired_quadrant

        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant=quadrant)

        allowed = set(quadrant_wells(quadrant)) | set(quadrant_wells(paired_quadrant(quadrant)))
        for _, well in _source_wells(out):
            assert well in allowed, f"{well} outside quadrant {quadrant}"

    def test_forward_and_reverse_split_across_the_paired_quadrants(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant="A1")

        fwd_wells = {w for name, w in _source_wells(out) if name.endswith("_F")}
        rev_wells = {w for name, w in _source_wells(out) if name.endswith("_R")}

        assert fwd_wells <= set(quadrant_wells("A1"))
        assert rev_wells <= set(quadrant_wells("B1"))
        assert not (fwd_wells & rev_wells)

    def test_a1_maps_the_first_well_to_384_a1(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant="A1")

        wells = dict(_source_wells(out))
        assert wells["M1_F"] == "A1"
        assert wells["M1_R"] == "B1"

    def test_a2_shifts_the_same_layout_one_column_over(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, quadrant="A2")

        wells = dict(_source_wells(out))
        assert wells["M1_F"] == "A2"
        assert wells["M1_R"] == "B2"

    def test_without_a_quadrant_the_old_row_doubled_layout_is_unchanged(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out)

        wells = dict(_source_wells(out))
        # 기존 동작: 행만 2배, 열은 그대로.
        assert wells["M1_F"] == "A1"
        assert wells["M1_R"] == "B1"
        assert wells["M3_F"] == "O12"


class TestUsedQuadrantRefusal:
    def test_refuses_to_dispense_onto_a_spent_quadrant(self, mappings, tmp_path):
        fwd, rev = mappings

        with pytest.raises(ValueError, match="already used"):
            export_echo_mapping_csv(
                fwd, rev, tmp_path / "echo.csv",
                quadrant="A1", used_quadrants=["A1", "B1"],
            )

    def test_second_round_onto_the_free_pair_is_allowed(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        export_echo_mapping_csv(
            fwd, rev, out, quadrant="A2", used_quadrants=["A1", "B1"],
        )

        wells = dict(_source_wells(out))
        assert wells["M1_F"] == "A2"

    def test_refusal_happens_before_the_file_is_written(self, mappings, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"

        with pytest.raises(ValueError):
            export_echo_mapping_csv(
                fwd, rev, out, quadrant="A1", used_quadrants=["B1"],
            )

        assert not out.exists()
