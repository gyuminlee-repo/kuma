"""Regression tests: cross-talk check reports its own status, and unattributable
wells are not guessed onto designed mutants.

Two defects covered:

1. ``detect_cross_talk`` collapsed "no data", "too few barcodes" and "flat plate"
   into the same empty list the UI rendered as "no cross-talk candidates", and
   ``_parse_barcode_alignment`` fed ``unclassified`` into the z-score population,
   hiding a genuinely overloaded barcode.
2. ``_assign_mutant_ids`` attributed LOWDEPTH / NO_CALL / WRONG_AA wells to
   ``expected[idx % len(expected)]``, so list position decided the mutant.
"""

from __future__ import annotations

from pathlib import Path

from kuma_core.mame.health import (
    _is_excluded_barcode_label,
    _parse_barcode_alignment,
    detect_cross_talk,
    detect_cross_talk_with_status,
)
from kuma_core.mame.models import (
    BarcodeRecord,
    ExpectedMutation,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from kuma_core.mame.pipeline import _assign_mutant_ids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_alignment(run_dir: Path, rows: list[tuple[str, int]]) -> None:
    lines = ["barcode_arrangement\tnum_reads"]
    lines += [f"{label}\t{count}" for label, count in rows]
    (run_dir / "barcode_alignment_passed.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_verdict(custom_barcode: str, verdict: VerdictClass) -> VerdictRecord:
    barcode = BarcodeRecord(
        native_barcode="NB01",
        custom_barcode=custom_barcode,
        consensus_seq="",
        file_size_kb=60.0,
        source_path=Path("mock.fasta"),
    )
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_nt_changes=[],
        observed_aa_changes=[],
    )
    return VerdictRecord(
        translated=translated,
        expected_mutations=[],
        verdict=verdict,
        verdict_notes="",
    )


def _make_expected(mutant_id: str, pos: int, wt: str, mt: str) -> ExpectedMutation:
    return ExpectedMutation(
        mutant_id=mutant_id,
        position=pos,
        wt_aa=wt,
        mt_aa=mt,
        wt_codon="XXX",
        mt_codon="YYY",
        group_id="",
        primer_set_ref=mutant_id,
        notation_type="substitution",
        status="DESIGNED",
    )


# ---------------------------------------------------------------------------
# (1a) status is distinguishable from a clean plate
# ---------------------------------------------------------------------------


class TestCrossTalkStatus:
    def test_no_distribution_is_not_run(self) -> None:
        assert detect_cross_talk_with_status(None) == ([], "not_run")

    def test_too_few_barcodes_is_insufficient(self) -> None:
        dist = {f"barcode{i:02d}": 1000 for i in range(1, 4)}
        assert detect_cross_talk_with_status(dist) == ([], "insufficient_data")

    def test_zero_variance_is_insufficient(self) -> None:
        dist = {f"barcode{i:02d}": 1000 for i in range(1, 13)}
        assert detect_cross_talk_with_status(dist) == ([], "insufficient_data")

    def test_clean_plate_is_ok(self) -> None:
        dist = {f"barcode{i:02d}": 1000 + i for i in range(1, 13)}
        candidates, status = detect_cross_talk_with_status(dist)
        assert status == "ok"
        assert candidates == []

    def test_outlier_plate_is_ok_with_candidate(self) -> None:
        dist = {f"barcode{i:02d}": 1000 for i in range(1, 13)}
        dist["barcode03"] = 5000
        candidates, status = detect_cross_talk_with_status(dist)
        assert status == "ok"
        assert [c.well for c in candidates] == ["barcode03"]

    def test_list_only_wrapper_matches(self) -> None:
        dist = {f"barcode{i:02d}": 1000 for i in range(1, 13)}
        dist["barcode03"] = 5000
        assert detect_cross_talk(dist) == detect_cross_talk_with_status(dist)[0]


# ---------------------------------------------------------------------------
# (1b) unclassified stays out of the z-score population
# ---------------------------------------------------------------------------


class TestBarcodeAlignmentFiltering:
    def test_excluded_labels(self) -> None:
        assert _is_excluded_barcode_label("unclassified")
        assert _is_excluded_barcode_label("Unclassified")
        assert _is_excluded_barcode_label("barcode00")
        assert _is_excluded_barcode_label("NB00")
        assert not _is_excluded_barcode_label("barcode03")
        assert not _is_excluded_barcode_label("NB03")

    def test_unclassified_dropped_and_real_outlier_surfaces(self, tmp_path: Path) -> None:
        rows = [(f"barcode{i:02d}", 5000 if i == 3 else 1000) for i in range(1, 13)]
        rows.append(("unclassified", 1_000_000))
        _write_alignment(tmp_path, rows)

        dist = _parse_barcode_alignment(tmp_path)
        assert dist is not None
        assert "unclassified" not in dist
        assert len(dist) == 12

        candidates, status = detect_cross_talk_with_status(dist)
        assert status == "ok"
        assert [c.well for c in candidates] == ["barcode03"]

    def test_no_alignment_file_returns_none(self, tmp_path: Path) -> None:
        assert _parse_barcode_alignment(tmp_path) is None
        assert detect_cross_talk_with_status(_parse_barcode_alignment(tmp_path))[1] == "not_run"


# ---------------------------------------------------------------------------
# (2) unattributable wells stay unattributed
# ---------------------------------------------------------------------------


class TestUnattributableWells:
    expected = [
        _make_expected("V5F", 5, "V", "F"),
        _make_expected("K53N", 53, "K", "N"),
        _make_expected("G2A", 2, "G", "A"),
    ]

    def test_lowdepth_wells_are_unknown(self) -> None:
        records = [_make_verdict(f"1_{i}", VerdictClass.LOWDEPTH) for i in (1, 2, 3)]
        grouped = _assign_mutant_ids(records, self.expected)
        assert set(grouped) == {
            "UNKNOWN_NB01_1_1",
            "UNKNOWN_NB01_1_2",
            "UNKNOWN_NB01_1_3",
        }
        for exp in self.expected:
            assert exp.mutant_id not in grouped

    def test_attribution_is_order_independent(self) -> None:
        first = [_make_verdict(cb, VerdictClass.NO_CALL) for cb in ("1_1", "1_2", "1_3")]
        second = [_make_verdict(cb, VerdictClass.NO_CALL) for cb in ("1_3", "1_1", "1_2")]
        _assign_mutant_ids(first, self.expected)
        _assign_mutant_ids(second, self.expected)
        map_first = {vr.translated.barcode.custom_barcode: vr.mutant_id for vr in first}
        map_second = {vr.translated.barcode.custom_barcode: vr.mutant_id for vr in second}
        assert map_first == map_second

    def test_wrong_aa_at_unexpected_position_is_unknown(self) -> None:
        vr = _make_verdict("1_1", VerdictClass.WRONG_AA)
        vr.translated.observed_aa_changes = ["T99A"]
        grouped = _assign_mutant_ids([vr], self.expected)
        assert set(grouped) == {"UNKNOWN_NB01_1_1"}

    def test_observed_label_still_groups(self) -> None:
        vr = _make_verdict("1_1", VerdictClass.PASS)
        vr.translated.observed_aa_changes = ["K53N"]
        grouped = _assign_mutant_ids([vr], self.expected)
        assert set(grouped) == {"K53N"}

    def test_placement_map_still_wins(self) -> None:
        vr = _make_verdict("1_2", VerdictClass.LOWDEPTH)
        from kuma_core.mame.pipeline import _norm_well

        grouped = _assign_mutant_ids(
            [vr], self.expected, well_to_mutant={_norm_well("A02"): "G2A"}
        )
        assert set(grouped) == {"G2A"}
