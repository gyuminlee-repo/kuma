"""Cross-check the three KURO JANUS writers against each other.

The CSV export, the XLSX "primer_mapping file" sheet and the sidecar preview
describe the same physical run, and each used to build its rows from its own
copy of the deck literals. Nothing caught a change applied to one copy only, so
the operator could load a file that disagreed with the preview they approved.

These tests deliberately compare the three outputs *to each other* rather than
to a literal table. Pinning literals only catches a writer drifting away from
the literal; a change that updates the literal and two writers still ships a
third writer out of step. Format pinning against the lab workbook lives in
tests/test_plate_mapper_reference_format.py and is not repeated here.
"""

from __future__ import annotations

import csv

import openpyxl
import pytest
from sidecar_kuro.handlers.export import _build_janus_preview_rows

from kuma_core.kuro.plate_mapper import (
    PlateMapping,
    build_janus_rows,
    export_janus_mapping_csv,
    export_janus_mapping_xlsx,
    janus_row_values,
)
from kuma_core.shared.janus_deck import (
    JANUS_DEVICE_HEADER,
    KURO_PRIMER_DECK,
    JanusDeck,
)

TRANSFER_VOL = 2.0


def _mapping(mutation: str, well: str, sequence: str, primer_type: str) -> PlateMapping:
    return PlateMapping(
        well=well,
        primer_name=f"{mutation}_{primer_type[0].upper()}",
        sequence=sequence,
        primer_type=primer_type,
        mutation=mutation,
    )


@pytest.fixture
def shared_rev_mappings():
    """Four mutations over two reverse primers, so shared-primer expansion runs."""
    fwd = [
        _mapping("A1G", "A1", "AAAAF", "forward"),
        _mapping("C2T", "B1", "CCCCF", "forward"),
        _mapping("G3A", "C1", "GGGGF", "forward"),
        _mapping("T4C", "D1", "TTTTF", "forward"),
    ]
    rev = [
        _mapping("A1G", "A1", "SHARED", "reverse"),
        _mapping("G3A", "B1", "REV2", "reverse"),
    ]
    rev_groups = {"SHARED": ["A1G", "C2T"], "REV2": ["G3A", "T4C"]}
    return fwd, rev, rev_groups


def _csv_rows(path) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def _xlsx_rows(path) -> tuple[list, list[list]]:
    ws = openpyxl.load_workbook(path)["primer_mapping file"]
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    return rows[0], rows[1:]


def _as_text(values: list) -> list:
    """Normalise one row so the three writers are comparable.

    CSV carries every cell as text while XLSX round-trips numbers through Excel,
    which hands back a volume of 2.0 as the int 2. Comparing numbers as numbers
    and everything else as text keeps the assertion about the values the writers
    chose, not about how each container stores them.
    """
    out = []
    for v in values:
        if v is None:
            out.append("")
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(str(v))
    return out


class TestWritersAgree:
    def test_csv_and_xlsx_write_the_same_header(self, shared_rev_mappings, tmp_path):
        fwd, rev, groups = shared_rev_mappings
        csv_path = tmp_path / "janus.csv"
        xlsx_path = tmp_path / "janus.xlsx"
        export_janus_mapping_csv(
            fwd, rev, csv_path, transfer_vol=TRANSFER_VOL, rev_groups=groups
        )
        export_janus_mapping_xlsx(
            fwd, rev, xlsx_path, transfer_vol=TRANSFER_VOL, rev_groups=groups
        )

        csv_header, _ = _csv_rows(csv_path)
        xlsx_header, _ = _xlsx_rows(xlsx_path)

        assert csv_header == JANUS_DEVICE_HEADER
        assert xlsx_header == JANUS_DEVICE_HEADER

    def test_csv_xlsx_and_preview_write_the_same_rows(
        self, shared_rev_mappings, tmp_path
    ):
        fwd, rev, groups = shared_rev_mappings
        csv_path = tmp_path / "janus.csv"
        xlsx_path = tmp_path / "janus.xlsx"
        export_janus_mapping_csv(
            fwd, rev, csv_path, transfer_vol=TRANSFER_VOL, rev_groups=groups
        )
        export_janus_mapping_xlsx(
            fwd, rev, xlsx_path, transfer_vol=TRANSFER_VOL, rev_groups=groups
        )

        _, csv_raw = _csv_rows(csv_path)
        _, xlsx_raw = _xlsx_rows(xlsx_path)
        preview = _build_janus_preview_rows(fwd, rev, TRANSFER_VOL, groups)

        csv_rows = [_as_text(r) for r in csv_raw]
        assert csv_rows, "the fixture must produce rows for the comparison to mean anything"
        assert [_as_text(r) for r in xlsx_raw] == csv_rows
        assert [_as_text(janus_row_values(r)) for r in preview] == csv_rows

    def test_shared_reverse_primer_expands_identically_everywhere(
        self, shared_rev_mappings, tmp_path
    ):
        """Every forward mutation gets a reverse row, in all three writers."""
        fwd, rev, groups = shared_rev_mappings
        csv_path = tmp_path / "janus.csv"
        xlsx_path = tmp_path / "janus.xlsx"
        export_janus_mapping_csv(
            fwd, rev, csv_path, transfer_vol=TRANSFER_VOL, rev_groups=groups
        )
        export_janus_mapping_xlsx(
            fwd, rev, xlsx_path, transfer_vol=TRANSFER_VOL, rev_groups=groups
        )

        _, csv_rows = _csv_rows(csv_path)
        _, xlsx_rows = _xlsx_rows(xlsx_path)
        preview = _build_janus_preview_rows(fwd, rev, TRANSFER_VOL, groups)

        expected = 2 * len(fwd)
        assert len(csv_rows) == expected
        assert len(xlsx_rows) == expected
        assert len(preview) == expected

    def test_preview_carries_every_instrument_column_plus_its_own_fields(
        self, shared_rev_mappings
    ):
        fwd, rev, groups = shared_rev_mappings
        preview = _build_janus_preview_rows(fwd, rev, TRANSFER_VOL, groups)

        for row in preview:
            # janus_row_values raises KeyError if an instrument column is absent.
            assert len(janus_row_values(row)) == len(JANUS_DEVICE_HEADER)
            assert row["mutation"]
            assert row["role"] in ("fwd", "rev")


class TestDeckPolicyReachesEveryWriter:
    """A deck change must move all three writers, or move none of them."""

    def test_non_default_deck_changes_csv_and_xlsx_together(
        self, shared_rev_mappings, tmp_path
    ):
        fwd, rev, groups = shared_rev_mappings
        other = JanusDeck(
            fwd_rack="probe fw plate",
            rev_rack="probe rv plate",
            dest_rack="probe assay plate",
            liquid_class="Test 1pmol/ul",
            sample_type="probe",
        )
        csv_path = tmp_path / "janus.csv"
        xlsx_path = tmp_path / "janus.xlsx"
        export_janus_mapping_csv(
            fwd, rev, csv_path, transfer_vol=TRANSFER_VOL, rev_groups=groups, deck=other
        )
        export_janus_mapping_xlsx(
            fwd, rev, xlsx_path, transfer_vol=TRANSFER_VOL, rev_groups=groups, deck=other
        )

        _, csv_raw = _csv_rows(csv_path)
        _, xlsx_raw = _xlsx_rows(xlsx_path)
        expected = [
            _as_text(janus_row_values(r))
            for r in build_janus_rows(fwd, rev, groups, TRANSFER_VOL, other)
        ]

        assert [_as_text(r) for r in csv_raw] == expected
        assert [_as_text(r) for r in xlsx_raw] == expected
        # Index 3 is Asp. Rack and index 5 Dsp. Rack in the eight column sheet.
        assert {r[3] for r in csv_raw} == {"probe fw plate", "probe rv plate"}
        assert {r[5] for r in csv_raw} == {"probe assay plate"}
        assert {r[1] for r in csv_raw} == {"probe"}
        # The deck states a liquid class and the sheet has no column for it, so
        # it must reach no cell. Asserting its absence everywhere, rather than
        # dropping the old index 2 assertion, is what catches it reappearing in
        # some other column.
        assert not any(other.liquid_class in r for r in csv_raw)

    def test_role_is_stated_not_inferred_from_the_source_plate(
        self, shared_rev_mappings
    ):
        """A consumer could read direction off the source plate; ``role`` frees it.

        The frontend once inferred direction by comparing the aspirate rack to
        the deck. Plate names make that comparison worse, not better, so this
        pins that a swapped deck leaves ``role`` describing the primer.
        """
        fwd, rev, groups = shared_rev_mappings
        swapped = JanusDeck(
            fwd_rack=KURO_PRIMER_DECK.rev_rack,
            rev_rack=KURO_PRIMER_DECK.fwd_rack,
            dest_rack=KURO_PRIMER_DECK.dest_rack,
            liquid_class=KURO_PRIMER_DECK.liquid_class,
            sample_type=KURO_PRIMER_DECK.sample_type,
        )
        rows = build_janus_rows(fwd, rev, groups, TRANSFER_VOL, swapped)

        for row in rows:
            expected_role = "fwd" if row["name"].endswith("-F") else "rev"
            assert row["role"] == expected_role
