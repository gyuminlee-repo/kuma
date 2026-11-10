"""A combination genotype is one clone, so it takes one well.

The experiment behind this: a combination such as ``A2V/A3G`` is a single clone
grown from one colony and sequenced once, in one well. The expected sheet writes
it as one row per substitution sharing a ``mutant_id`` (``kuro.plate_mapper``
does this, and ``templates/03_mame_expected_mutations.xlsx`` ships it), because
each row orders its own primer pair.

Counting those rows as wells gave that clone a well per substitution and pushed
every later clone, the control and every numeric ID one place down. The verdict
classifier was already right: ``pipeline.py`` accumulates the expected labels per
``mutant_id``, so the well expects both substitutions. What was wrong was where
the well was.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.activity.numeric_id_decode import expected_variant_order
from kuma_core.mame.io.plate_order_check import check_plate_order
from kuma_core.mame.io.variant_list import read_variant_source
from kuma_core.mame.layout import (
    WtPlacement,
    build_draft_layout,
    distinct_occupants,
)
from kuma_core.mame.models import ExpectedMutation

_HEADER = [
    "mutant_id", "position", "wt_aa", "mt_aa", "wt_codon", "mt_codon",
    "group_id", "primer_set_ref", "notation_type", "status",
]

#: Two substitutions of one clone, then a single, then the control. The single
#: comes after the combination on purpose: it is the row a row-count moves.
_COMBO_SHEET = [
    ["G2A/F3W", 2, "G", "A", "GGG", "GCG", "G2A/F3W", "G2A", "combo", "DESIGNED"],
    ["G2A/F3W", 3, "F", "W", "TTT", "TGG", "G2A/F3W", "F3W", "combo", "DESIGNED"],
    ["K4R", 4, "K", "R", "AAA", "CGT", "", "K4R", "substitution", "DESIGNED"],
    ["WT", 0, "-", "-", "-", "-", "", "-", "wt", "DESIGNED"],
]

#: The same plate with the combination written as two separate clones.
_SINGLES_SHEET = [
    ["G2A", 2, "G", "A", "GGG", "GCG", "", "G2A", "substitution", "DESIGNED"],
    ["F3W", 3, "F", "W", "TTT", "TGG", "", "F3W", "substitution", "DESIGNED"],
    ["K4R", 4, "K", "R", "AAA", "CGT", "", "K4R", "substitution", "DESIGNED"],
    ["WT", 0, "-", "-", "-", "-", "", "-", "wt", "DESIGNED"],
]


def _write(path: Path, rows: list[list[object]]) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "expected_mutations"
    ws.append(_HEADER)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _mutation(mutant_id: str, position: int, ref: str) -> ExpectedMutation:
    return ExpectedMutation(
        mutant_id=mutant_id,
        position=position,
        wt_aa="G",
        mt_aa="A",
        wt_codon="GGG",
        mt_codon="GCG",
        group_id=mutant_id if "/" in mutant_id else "",
        primer_set_ref=ref,
        notation_type="combo" if "/" in mutant_id else "substitution",
        status="DESIGNED",
    )


class TestRowOrderPlacement:
    def test_the_combination_takes_one_well_and_moves_nothing(self, tmp_path):
        """Reverted, the combination sits at A1 AND B1 and K4R slides to C1."""
        read = read_variant_source(_write(tmp_path / "combo.xlsx", _COMBO_SHEET))

        draft = build_draft_layout(
            read.expected,
            wt_ordinal=read.wt_ordinal,
            wt_placement=WtPlacement.AFTER_LAST_VARIANT,
        )

        assert draft.layout == {"A1": "G2A/F3W", "B1": "K4R", "C1": "WT"}

    def test_the_control_ordinal_counts_clones(self, tmp_path):
        """Two clones precede the control row, so it is the third occupant.

        Counting rows made it the fourth, which is the well AFTER the one the
        operator's own file names.
        """
        read = read_variant_source(_write(tmp_path / "combo.xlsx", _COMBO_SHEET))

        assert read.wt_ordinal == 3

    def test_the_same_plate_written_as_singles_is_untouched(self, tmp_path):
        """The control of the single-only plate is the fourth occupant.

        The guard on the change: nothing about a sheet without a repeated
        ``mutant_id`` may move, so this is the same assertion as above with the
        number a row count would also have produced.
        """
        read = read_variant_source(_write(tmp_path / "single.xlsx", _SINGLES_SHEET))

        draft = build_draft_layout(
            read.expected,
            wt_ordinal=read.wt_ordinal,
            wt_placement=WtPlacement.AFTER_LAST_VARIANT,
        )

        assert read.wt_ordinal == 4
        assert draft.layout == {
            "A1": "G2A",
            "B1": "F3W",
            "C1": "K4R",
            "D1": "WT",
        }

    def test_capacity_counts_clones(self):
        """96 rows that are 95 clones plus a control fit; 96 clones do not."""
        rows = [_mutation(f"M{i:03d}", i, f"PS{i}") for i in range(1, 95)]
        rows += [_mutation("COMBO/PAIR", 95, "PS95a"), _mutation("COMBO/PAIR", 96, "PS95b")]

        assert len(rows) == 96
        assert len(distinct_occupants(rows)) == 95
        assert build_draft_layout(rows).dropped_mutant_ids == []

        over = rows + [_mutation("M096", 97, "PS96")]
        assert build_draft_layout(over).dropped_mutant_ids == ["M096"]


class TestStatedWells:
    def test_one_clone_may_state_one_well_twice(self):
        """Both rows of the clone name its well, which is one well."""
        rows = [_mutation("G2A/F3W", 2, "G2A"), _mutation("G2A/F3W", 3, "F3W")]

        draft = build_draft_layout(rows, wells=["B2", "B2"], wt_well="H12")

        assert draft.layout == {"B2": "G2A/F3W", "H12": "WT"}

    def test_a_clone_in_two_wells_is_refused(self):
        """One clone, two addresses. Nothing here is entitled to pick one."""
        rows = [_mutation("G2A/F3W", 2, "G2A"), _mutation("G2A/F3W", 3, "F3W")]

        with pytest.raises(ValueError, match="states two wells"):
            build_draft_layout(rows, wells=["B2", "C2"])

    def test_the_length_check_still_counts_rows(self):
        """``wells`` comes out of the reader per row and still has to match."""
        rows = [_mutation("G2A/F3W", 2, "G2A"), _mutation("G2A/F3W", 3, "F3W")]

        with pytest.raises(ValueError, match="do not correspond"):
            build_draft_layout(rows, wells=["B2"])


class TestNumericIdOrder:
    def test_the_decode_order_is_the_plate_the_run_used(self, tmp_path):
        """A numeric ID counts tubes, and the combination is one tube.

        Reverted, this returns three slots for two clones and every ID from the
        second one names the wrong variant.
        """
        path = _write(tmp_path / "combo.xlsx", _COMBO_SHEET)

        order, warnings = expected_variant_order(path)

        assert [(entry[1], entry[2]) for entry in order] == [
            ("G2A/F3W", "A01"),
            ("K4R", "B01"),
        ]
        # The combination has no EVOLVEpro short form, and the slot is kept.
        assert order[0][0] is None
        assert len(warnings) == 1

    def test_it_agrees_with_the_draft_layout(self, tmp_path):
        """The two placements are read by different code and must not diverge."""
        path = _write(tmp_path / "combo.xlsx", _COMBO_SHEET)
        read = read_variant_source(path)
        draft = build_draft_layout(
            read.expected, wt_ordinal=read.wt_ordinal, wt_placement=WtPlacement.NONE
        )

        order, _ = expected_variant_order(path)

        assert [entry[1] for entry in order] == list(draft.layout.values())


class TestPlateOrderCheck:
    def test_a_combination_workbook_is_not_comparable(self, tmp_path):
        """The primer plate holds a well per substitution, the clone plate one.

        The two sheets then describe different numbers of things, so the check
        reports that it cannot compare rather than a mismatch at every well
        after the combination.
        """
        path = tmp_path / "combo_with_plate.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Fwd List"
        ws.append(["Well", "Primer Name", "Sequence", "Mutation"])
        ws.append(["A1", "G2A_F", "ATGNNN", "G2A"])
        ws.append(["B1", "F3W_F", "ATGNNN", "F3W"])
        ws.append(["C1", "K4R_F", "ATGNNN", "K4R"])
        ws2 = wb.create_sheet("expected_mutations")
        ws2.append(_HEADER)
        for row in _COMBO_SHEET:
            ws2.append(row)
        wb.save(path)

        report = check_plate_order(path)

        assert report.comparable is False
        assert report.mismatched is False

    def test_a_single_only_workbook_still_compares(self, tmp_path):
        """The guard: the check keeps working where a clone has one primer pair."""
        path = tmp_path / "singles_with_plate.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Fwd List"
        ws.append(["Well", "Primer Name", "Sequence", "Mutation"])
        ws.append(["A1", "G2A_F", "ATGNNN", "G2A"])
        ws.append(["B1", "F3W_F", "ATGNNN", "F3W"])
        ws.append(["C1", "K4R_F", "ATGNNN", "K4R"])
        ws2 = wb.create_sheet("expected_mutations")
        ws2.append(_HEADER)
        for row in _SINGLES_SHEET:
            ws2.append(row)
        wb.save(path)

        report = check_plate_order(path)

        assert report.comparable is True
        assert report.ok, (
            f"{report.examples} {report.missing_from_expected} "
            f"{report.absent_from_plate}"
        )


class TestTheWellExpectsBothSubstitutions:
    """The scoring contract this placement exists to serve.

    Unchanged by the occupant fix and asserted here because it is the reason
    the well is one well: ``pipeline.py`` accumulates the expected labels per
    ``mutant_id``, so the clone's well is scored against both substitutions.
    """

    # ATG GGG TTT AAA -> M G F K
    _REFERENCE = "ATGGGGTTTAAA"
    _BOTH = "ATGGCGTGGAAA"      # G2A and F3W
    _ONE = "ATGGGGTGGAAA"       # F3W only
    _K4R = "ATGGGGTTTCGT"
    _PAD = "\n" * (52 * 1024)

    def _run(self, tmp_path: Path, a1_body: str) -> dict:
        from kuma_core.mame.ingest import IngestMode
        from kuma_core.mame.pipeline import run_analyze

        expected = _write(tmp_path / "combo.xlsx", _COMBO_SHEET)
        ingest = tmp_path / "consensus"
        # custom_barcode "r_f": A1 is seq 1 ("1_1"), B1 is seq 2 ("2_1").
        for barcode, body in (("1_1", a1_body), ("2_1", self._K4R)):
            path = ingest / "NB01" / f"{barcode}.fasta"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f">{barcode} depth=100\n{body}\n{self._PAD}", encoding="utf-8"
            )
        reference = tmp_path / "reference.fasta"
        reference.write_text(f">ref\n{self._REFERENCE}\n", encoding="utf-8")

        records, _ = run_analyze(
            input_dir=ingest,
            reference_path=reference,
            expected_path=expected,
            output_path=tmp_path / "out.xlsx",
            cds_start=0,
            cds_end=12,
            min_file_size_kb=0.0,
            ingest_mode=IngestMode.BARCODE,
            well_layout={"A1": "G2A/F3W", "B1": "K4R"},
        )
        return {v.translated.barcode.custom_barcode: v for v in records}

    def test_both_substitutions_observed_passes(self, tmp_path):
        records = self._run(tmp_path, self._BOTH)

        assert sorted(records["1_1"].expected_mutations) == ["F3W", "G2A"]
        assert records["1_1"].verdict.value == "PASS"
        assert records["2_1"].verdict.value == "PASS"

    def test_one_substitution_missing_is_wrong_aa(self, tmp_path):
        records = self._run(tmp_path, self._ONE)

        assert records["1_1"].verdict.value == "WRONG_AA"
        assert records["2_1"].verdict.value == "PASS"


class TestKuroExportFeedsThisBack:
    def test_a_combination_designed_by_kuro_lands_in_one_well(self, tmp_path):
        """The two layers in one call chain, against the sheet KURO writes.

        ``mutant_id`` is the clone, so the two rows KURO writes for one
        combination read back as one occupant. With the component notation in
        that column they read back as two clones in two wells, which is the
        plate nobody built.
        """
        from kuma_core.kuro.mutation import Mutation
        from kuma_core.kuro.overlap import OverlapWindow
        from kuma_core.kuro.plate_mapper import _write_expected_mutations_sheet
        from kuma_core.kuro.sdm_engine import SdmPrimerResult

        def result(raw, wt_aa, position, mt_aa, group_id=None):
            window = OverlapWindow(sequence="AAATTTCCC", start=0, end=9, codon_offset=3)
            return SdmPrimerResult(
                mutation=Mutation(
                    raw=raw,
                    wt_aa=wt_aa,
                    position=position,
                    mt_aa=mt_aa,
                    codon_start=0,
                    wt_codon="GTG",
                    mt_codon="TTT",
                    group_id=group_id,
                ),
                forward_seq="AAATTTCCCGGG",
                reverse_seq="CCCGGGAAATTT",
                forward_binding="AAATTT",
                reverse_binding="CCCGGG",
                overlap_window=window,
                tm_fwd=60.0,
                tm_rev=58.0,
                tm_overlap=55.0,
                tm_condition_met=True,
            )

        results = [
            result("A40P", "A", 40, "P", group_id="A40P/E61Y"),
            result("E61Y", "E", 61, "Y", group_id="A40P/E61Y"),
            result("V5F", "V", 5, "F"),
        ]
        wb = openpyxl.Workbook()
        _write_expected_mutations_sheet(wb, [(r, None) for r in results])
        path = tmp_path / "kuro_export.xlsx"
        wb.save(path)

        read = read_variant_source(path)
        draft = build_draft_layout(read.expected, wt_placement=WtPlacement.NONE)

        assert draft.layout == {"A1": "A40P/E61Y", "B1": "V5F"}
