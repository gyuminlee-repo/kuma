"""Pin the Echo and JANUS export format to the workbooks the lab imports.

The header strings in ``plate_mapper`` had no traceable source in the
repository: the commit that introduced them cites none, and a docstring
claiming a "lab reference format" left no artifact behind. Vendor
documentation spells several columns differently, which invites a correction
that would break an import the lab depends on.

``tests/fixtures/liquid_handler/reference_format.json`` carries the sheet
names, mapping-sheet headers, and layout anchors read out of the two real
workbooks. See the README beside it for provenance and for why only the
format, and not the workbooks, is committed.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import openpyxl
import pytest

from kuma_core.kuro.plate_mapper import (
    PlateMapping,
    export_echo_mapping_csv,
    export_echo_mapping_xlsx,
    export_janus_mapping_csv,
    export_janus_mapping_xlsx,
)

_REFERENCE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "liquid_handler"
    / "reference_format.json"
)


@pytest.fixture(scope="module")
def reference() -> dict:
    return json.loads(_REFERENCE.read_text(encoding="utf-8"))


@pytest.fixture
def mappings() -> tuple[list[PlateMapping], list[PlateMapping]]:
    """Two mutations, each with its own reverse primer."""
    fwd = [
        PlateMapping(
            well="A1",
            primer_name="V5F_F",
            sequence="AAAA",
            primer_type="forward",
            mutation="V5F",
        ),
        PlateMapping(
            well="B1",
            primer_name="V10L_F",
            sequence="CCCC",
            primer_type="forward",
            mutation="V10L",
        ),
    ]
    rev = [
        PlateMapping(
            well="A1",
            primer_name="V5F_R",
            sequence="TTTT",
            primer_type="reverse",
            mutation="V5F",
        ),
        PlateMapping(
            well="B1",
            primer_name="V10L_R",
            sequence="GGGG",
            primer_type="reverse",
            mutation="V10L",
        ),
    ]
    return fwd, rev


def _rev_groups(rev: list[PlateMapping]) -> dict[str, list[str]]:
    return {m.sequence: [m.mutation] for m in rev}


class TestEchoReferenceFormat:
    def test_csv_header_matches_the_workbook(self, mappings, reference, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.csv"
        export_echo_mapping_csv(fwd, rev, out, rev_groups=_rev_groups(rev))

        with open(out, encoding="utf-8") as f:
            header = next(csv.reader(f))

        assert header == reference["echo"]["mapping_header"]

    def test_xlsx_sheets_and_header_match_the_workbook(
        self, mappings, reference, tmp_path
    ):
        fwd, rev = mappings
        out = tmp_path / "echo.xlsx"
        export_echo_mapping_xlsx(fwd, rev, out, rev_groups=_rev_groups(rev))

        wb = openpyxl.load_workbook(out)
        expected = reference["echo"]
        assert expected["mapping_sheet"] in wb.sheetnames
        assert "layout" in wb.sheetnames

        ws = wb[expected["mapping_sheet"]]
        header = [c.value for c in next(ws.iter_rows(max_row=1))]
        assert header[: len(expected["mapping_header"])] == expected["mapping_header"]

    def test_layout_names_the_same_labware(self, mappings, reference, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "echo.xlsx"
        export_echo_mapping_xlsx(fwd, rev, out, rev_groups=_rev_groups(rev))

        lay = openpyxl.load_workbook(out)["layout"]
        cells = {
            str(c.value)
            for row in lay.iter_rows(max_row=10)
            for c in row
            if c.value is not None
        }
        anchors = reference["echo"]["layout_anchors"]
        assert anchors["labware_label"] in cells
        assert anchors["labware_value"] in cells


class TestJanusReferenceFormat:
    def test_csv_header_matches_the_workbook(self, mappings, reference, tmp_path):
        fwd, rev = mappings
        out = tmp_path / "janus.csv"
        export_janus_mapping_csv(fwd, rev, out, rev_groups=_rev_groups(rev))

        with open(out, encoding="utf-8") as f:
            header = next(csv.reader(f))

        assert header == reference["janus"]["mapping_header"]

    def test_duplicate_rack_column_is_intentional(self, reference):
        """`Dsp. Rack` twice is in the source workbook, not a transcription slip."""
        header = reference["janus"]["mapping_header"]
        assert header.count("Dsp. Rack") == 2

    def test_xlsx_sheets_and_header_match_the_workbook(
        self, mappings, reference, tmp_path
    ):
        fwd, rev = mappings
        out = tmp_path / "janus.xlsx"
        export_janus_mapping_xlsx(fwd, rev, out, rev_groups=_rev_groups(rev))

        wb = openpyxl.load_workbook(out)
        expected = reference["janus"]
        assert expected["mapping_sheet"] in wb.sheetnames
        assert "layout" in wb.sheetnames

        ws = wb[expected["mapping_sheet"]]
        header = [c.value for c in next(ws.iter_rows(max_row=1))]
        assert header[: len(expected["mapping_header"])] == expected["mapping_header"]


class TestReferenceFixtureItself:
    def test_records_provenance(self, reference):
        """A format claim without a source is what this fixture exists to prevent."""
        for key in ("echo", "janus"):
            entry = reference[key]
            assert entry["source_file"]
            assert len(entry["sha256"]) == 64
