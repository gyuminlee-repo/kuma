"""Selection policy, exclusion reporting, and instrument schema for JANUS export.

``test_janus_mapping.py`` pins the row builder against the kuma-internal
5-column output at the source position, which is what that module was written
for. This module covers what the export now does by default: keep only fully
verified clones, report every clone it drops and why, fill the destination plate
from A1, and write the instrument-native eight column worksheet.

The header is asserted against
``tests/fixtures/liquid_handler/reference_format.json``, the transcription of
the workbook the lab imports, in the same way
``test_plate_mapper_reference_format.py`` pins the KURO exporter.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.export.janus_mapping import (
    DEFAULT_SAMPLE_TYPE,
    DEFAULT_VOLUME_UL,
    JanusSettings,
    _build_janus_rows,
    build_janus_preview_rows,
    export_mame_janus_csv,
    export_mame_janus_xlsx,
    normalize_include_verdicts,
)
from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)

_REFERENCE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "liquid_handler"
    / "reference_format.json"
)

# A complete instrument policy. The liquid class is set because an operator sets
# one and the settings object still records it, not because any column or guard
# needs it: the eight column sheet has neither.
_DEVICE = JanusSettings(liquid_class="Cell 100ul")


@pytest.fixture(scope="module")
def reference() -> dict:
    return json.loads(_REFERENCE.read_text(encoding="utf-8"))


def _make_replicate(
    mutant_id: str,
    nb: str,
    custom: str,
    verdict: VerdictClass = VerdictClass.PASS,
    size_kb: float = 80.0,
    is_fallback: bool = False,
) -> ReplicateResult:
    barcode = BarcodeRecord(
        native_barcode=nb,
        custom_barcode=custom,
        consensus_seq="",
        file_size_kb=size_kb,
        source_path=Path("/tmp/mock.fasta"),
    )
    translated = TranslatedRecord(
        barcode=barcode,
        aa_sequence="",
        observed_aa_changes=[],
        observed_nt_changes=[],
    )
    record = VerdictRecord(
        translated=translated,
        expected_mutations=[],
        verdict=verdict,
        verdict_notes="",
    )
    return ReplicateResult(
        mutant_id=mutant_id,
        plate_verdicts={nb: record},
        selected_plate=nb,
        selection_reason="pass",
        failed=False,
        is_fallback=is_fallback,
        fallback_reason="no clean replicate" if is_fallback else None,
    )


def _mixed_bag() -> list[ReplicateResult]:
    """One clone of every disposition the picker can produce.

    Wells ascend down the first column while the sizes do not follow them, so
    the order these clones come back in tells the plate map apart from the
    ``priority_score`` DESC this export used to sort by: ``AMBIG`` (250 kB, C1)
    outranks ``PASS_LO`` (100 kB, B1) by depth and follows it on the plate.
    """
    failed = _make_replicate("FAILED", "NB01", "1_5", VerdictClass.FRAMESHIFT)
    failed.failed = True
    failed.selected_plate = None
    return [
        _make_replicate("PASS_HI", "NB01", "1_1", size_kb=300.0),
        _make_replicate("PASS_LO", "NB01", "2_1", size_kb=100.0),
        _make_replicate("AMBIG", "NB01", "3_1", VerdictClass.AMBIGUOUS, size_kb=250.0),
        _make_replicate("LOWDEP", "NB01", "4_1", VerdictClass.LOWDEPTH, size_kb=200.0),
        # A fallback pick whose plate happens to read PASS: excluded for being a
        # fallback, which a verdict-only filter would miss.
        _make_replicate(
            "FALLBACK", "NB02", "1_1", size_kb=150.0, is_fallback=True
        ),
        failed,
    ]


def _names(rows: list[dict[str, object]]) -> list[str]:
    return [str(r["name"]) for r in rows]


def _reasons(preview: dict[str, object]) -> dict[str, str]:
    return {str(e["mutant_id"]): str(e["reason"]) for e in preview["excluded"]}  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Selection policy
# ---------------------------------------------------------------------------


def test_default_keeps_only_pass() -> None:
    """AMBIGUOUS carries a side indel and LOWDEPTH is unverified: neither ships."""
    rows = _build_janus_rows(_mixed_bag(), settings=_DEVICE)
    assert _names(rows) == ["PASS_HI", "PASS_LO"]


def test_ambiguous_can_be_opted_in() -> None:
    settings = JanusSettings(
        liquid_class="Cell 100ul", include_verdicts=("PASS", "AMBIGUOUS")
    )
    rows = _build_janus_rows(_mixed_bag(), settings=settings)
    # A1, B1, C1: the opted-in clone takes its place on the plate map rather
    # than the place its read depth would once have earned it.
    assert _names(rows) == ["PASS_HI", "PASS_LO", "AMBIG"]


def test_lowdepth_can_be_opted_in() -> None:
    settings = JanusSettings(
        liquid_class="Cell 100ul", include_verdicts=("PASS", "LOWDEPTH")
    )
    rows = _build_janus_rows(_mixed_bag(), settings=settings)
    # A1, B1, D1: LOWDEP sits two wells down the column, not two ranks up the
    # depth list.
    assert _names(rows) == ["PASS_HI", "PASS_LO", "LOWDEP"]


def test_fallback_pick_is_dropped_even_when_its_plate_reads_pass() -> None:
    """The fallback check is independent of the verdict class, not an elif."""
    replicates = [
        _make_replicate("CLEAN", "NB01", "1_1", size_kb=300.0),
        _make_replicate("FB_PASS", "NB02", "2_1", size_kb=200.0, is_fallback=True),
    ]
    assert _names(_build_janus_rows(replicates, settings=_DEVICE)) == ["CLEAN"]

    preview = build_janus_preview_rows(replicates, settings=_DEVICE)
    assert _reasons(preview) == {"FB_PASS": "fallback"}


def test_fallback_can_be_opted_in() -> None:
    replicates = [
        _make_replicate("CLEAN", "NB01", "1_1", size_kb=300.0),
        _make_replicate("FB_PASS", "NB02", "2_1", size_kb=200.0, is_fallback=True),
    ]
    settings = JanusSettings(liquid_class="Cell 100ul", include_fallback=True)
    assert _names(_build_janus_rows(replicates, settings=settings)) == [
        "CLEAN",
        "FB_PASS",
    ]


def test_empty_include_verdicts_is_rejected() -> None:
    """An empty selection would ship an empty plate; fail fast instead."""
    with pytest.raises(ValueError, match="include_verdicts is empty"):
        normalize_include_verdicts([])


def test_unknown_verdict_class_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown verdict class"):
        normalize_include_verdicts(["PASS", "SPLENDID"])


def test_include_verdicts_none_falls_back_to_pass() -> None:
    assert normalize_include_verdicts(None) == ("PASS",)


# ---------------------------------------------------------------------------
# Exclusion reporting
# ---------------------------------------------------------------------------


def test_preview_reports_every_excluded_clone_with_its_reason() -> None:
    preview = build_janus_preview_rows(_mixed_bag(), settings=_DEVICE)

    assert preview["excluded_count"] == 4
    assert _reasons(preview) == {
        "AMBIG": "verdict_class",
        "LOWDEP": "verdict_class",
        "FALLBACK": "fallback",
        "FAILED": "failed",
    }


def test_excluded_entry_carries_verdict_and_plate() -> None:
    preview = build_janus_preview_rows(_mixed_bag(), settings=_DEVICE)
    by_id = {str(e["mutant_id"]): e for e in preview["excluded"]}  # type: ignore[union-attr]

    assert by_id["AMBIG"]["verdict"] == "AMBIGUOUS"
    assert by_id["AMBIG"]["selected_plate"] == "NB01"
    assert by_id["FALLBACK"]["verdict"] == "PASS"
    assert by_id["FALLBACK"]["selected_plate"] == "NB02"
    assert by_id["FALLBACK"]["is_fallback"] is True


def test_replicate_without_a_selected_plate_is_reported() -> None:
    rr = _make_replicate("NOPICK", "NB01", "1_1")
    rr.selected_plate = None
    preview = build_janus_preview_rows(
        [rr, _make_replicate("OK", "NB02", "2_1")], settings=_DEVICE
    )
    assert _reasons(preview) == {"NOPICK": "no_selection"}


def test_exclusion_reason_precedence_is_failure_first() -> None:
    """A failed replicate reports ``failed``, not the verdict it happened to hold."""
    rr = _make_replicate("BOTH", "NB01", "1_1", VerdictClass.AMBIGUOUS, is_fallback=True)
    rr.failed = True
    preview = build_janus_preview_rows([rr], settings=_DEVICE)
    assert _reasons(preview) == {"BOTH": "failed"}


def test_verdict_class_outranks_fallback_in_the_reason() -> None:
    """Both apply; the verdict is the more specific answer for a retry plan."""
    rr = _make_replicate(
        "BOTH", "NB01", "1_1", VerdictClass.AMBIGUOUS, is_fallback=True
    )
    preview = build_janus_preview_rows([rr], settings=_DEVICE)
    assert _reasons(preview) == {"BOTH": "verdict_class"}


def test_included_clones_never_appear_in_the_exclusion_list() -> None:
    preview = build_janus_preview_rows(_mixed_bag(), settings=_DEVICE)
    included = set(_names(preview["rows"]))  # type: ignore[arg-type]
    excluded = {str(e["mutant_id"]) for e in preview["excluded"]}  # type: ignore[union-attr]
    assert included.isdisjoint(excluded)


# ---------------------------------------------------------------------------
# dest_layout default
# ---------------------------------------------------------------------------


def test_default_layout_is_source() -> None:
    """A non-PASS clone drops out before layout is chosen, so the default
    mirrors the source position: a dropped well stays blank on both plates
    instead of being closed up by a compact pack of the survivors."""
    assert JanusSettings().dest_layout == "source"

    replicates = [
        _make_replicate("HIGH", "NB01", "5_7", size_kb=300.0),
        _make_replicate("LOW", "NB02", "8_12", size_kb=10.0),
    ]
    rows = _build_janus_rows(replicates, settings=_DEVICE)
    assert [r["dest_well"] for r in rows] == ["E7", "H12"]
    assert [r["source_well"] for r in rows] == ["E7", "H12"]


# ---------------------------------------------------------------------------
# Instrument-native schema
# ---------------------------------------------------------------------------


def test_default_schema_is_the_instrument_schema() -> None:
    assert JanusSettings().output_schema == "device"


def test_instrument_csv_header_matches_the_workbook(reference, tmp_path: Path) -> None:
    out = tmp_path / "device.csv"
    export_mame_janus_csv([_make_replicate("V5F", "NB01", "1_1")], out, settings=_DEVICE)

    with out.open(encoding="utf-8") as fh:
        header = next(csv.reader(fh))

    assert header == reference["janus"]["mapping_header"]


def test_instrument_xlsx_header_matches_the_workbook(reference, tmp_path: Path) -> None:
    out = tmp_path / "device.xlsx"
    export_mame_janus_xlsx(
        [_make_replicate("V5F", "NB01", "1_1")], out, settings=_DEVICE
    )

    ws = openpyxl.load_workbook(out)["Janus Mapping"]
    header = [c.value for c in ws[1]]
    assert header == reference["janus"]["mapping_header"]


def test_the_instrument_header_is_exactly_these_eight_columns() -> None:
    """Pin the list itself, in order, so a shape change has to be typed out.

    The two tests above compare a writer to the fixture, so an edit moving the
    fixture and the writer together passes both. The predecessor sheet named
    ``Dsp. Rack`` twice and carried a liquid class in its third column, and a
    test once pinned that repetition as deliberate; this states the opposite,
    which is why the negative assertions are here rather than deleted.
    """
    header = JanusSettings().header
    assert header == [
        "name",
        "type",
        "no",
        "Asp. Rack",
        "Asp. Posi",
        "Dsp. Rack",
        "Dsp. Posi",
        "volume",
    ]
    assert len(header) == len(set(header))
    assert not [c for c in header if "class" in c.lower()]


def test_instrument_row_values(tmp_path: Path) -> None:
    out = tmp_path / "device_rows.csv"
    replicates = [
        _make_replicate("HIGH", "NB01", "5_7", size_kb=300.0),
        _make_replicate("LOW", "NB03", "8_12", size_kb=10.0),
    ]
    settings = JanusSettings(
        liquid_class="Cell 100ul", volume=75.0, sample_type="glycerol stock"
    )
    export_mame_janus_csv(replicates, out, settings=settings)

    with out.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))[1:]

    # Two plates in the run, so they are the first and second stock plate and
    # everything goes into the one culture plate. dest_layout is the "source"
    # default, so the destination well (Dsp. Posi) mirrors the source well
    # (Asp. Posi): the stock plate and the final culture plate share one
    # coordinate system.
    assert rows[0] == [
        "HIGH", "glycerol stock", "1", "Stock plate1", "E7",
        "final culture plate", "E7", "75.0",
    ]
    # `no` counts up in the row order, so the sheet counts off the transfers in
    # the order the plate is filled (E7 before H12, whatever the depths say).
    assert rows[1] == [
        "LOW", "glycerol stock", "2", "Stock plate2", "H12",
        "final culture plate", "H12", "75.0",
    ]


def test_instrument_defaults_ask_the_operator_for_nothing_but_volume() -> None:
    settings = JanusSettings()
    assert settings.volume == DEFAULT_VOLUME_UL
    assert settings.sample_type == DEFAULT_SAMPLE_TYPE
    # No stored deck: the plate names come from the plates of the run.
    assert settings.rack_map == {}
    assert settings.dest_rack is None


def test_the_shipped_sample_type_is_the_workbook_word() -> None:
    """``cell stock`` is what the seeding workbook writes in the type column.

    The constant is compared to a literal because the assert above compares it
    to itself and so holds for any word, and because
    ``scripts/sync-check-janus-defaults.mjs`` only proves the TypeScript and
    Python sides agree: both could move together with every gate green.
    """
    assert DEFAULT_SAMPLE_TYPE == "cell stock"


def test_the_shipped_volume_is_the_lab_value(tmp_path: Path) -> None:
    """70 uL is the cell-stock volume this lab transfers for this run, given by
    the operator who runs the instrument, and it stays editable in the export
    dialog for a run that transfers something else.

    The literal is pinned here because the assert above compares the constant to
    itself and so holds for any number, and because
    ``scripts/sync-check-janus-defaults.mjs`` only proves the TypeScript and
    Python sides agree: both could move together with every gate green. The
    written column is checked too, since the operator reads the number off the
    file, not off the constant.
    """
    assert DEFAULT_VOLUME_UL == 70.0
    assert JanusSettings().volume == 70.0

    out = tmp_path / "default_volume.csv"
    export_mame_janus_csv([_make_replicate("V5F", "NB01", "1_1")], out, settings=_DEVICE)

    with out.open(encoding="utf-8") as fh:
        body = list(csv.reader(fh))[1:]
    assert body[0][7] == "70.0"


def test_plate_names_follow_the_plates_of_the_run() -> None:
    """Sources are named in plate order; everything shares one culture plate.

    ``sort_barcode07/08/09`` is the run that produced no file at all before this:
    none of its plates appeared in the fixed NB01/NB02/NB03 map. The input is
    given out of order to show the sort, not the argument order, decides.
    """
    racks, dest = JanusSettings().resolve_deck(["NB09", "NB07", "NB08"])
    assert racks == {
        "NB07": "Stock plate1",
        "NB08": "Stock plate2",
        "NB09": "Stock plate3",
    }
    assert dest == "final culture plate"


def test_the_stock_plate_number_is_a_rank_not_a_plate_number() -> None:
    """The trap in the naming rule, given its own case.

    Every other fixture here uses NB01, NB02, NB03, where the rank and the plate
    number agree, so all of them would pass a writer that read the digits off
    the barcode instead of counting. A run of NB07 and NB10 separates the two:
    the plates are the first and second of the run, not the seventh and tenth.
    """
    racks, dest = JanusSettings().resolve_deck(["NB10", "NB07"])
    assert racks == {"NB07": "Stock plate1", "NB10": "Stock plate2"}
    assert dest == "final culture plate"


def test_plates_are_ordered_numerically_not_as_text() -> None:
    """Unpadded labels are the only input where the two orders disagree.

    ``nb_label`` copies the digit run verbatim, so a run folder written without
    zero padding gives NB9 rather than NB09. Padded labels hide the question
    entirely, since "NB07" sorts before "NB10" as text as well as by value; only
    an unpadded pair separates the rules, because "NB10" sorts before "NB9" as
    text and would make the tenth plate the first stock plate.
    """
    racks, _ = JanusSettings().resolve_deck(["NB10", "NB9"])
    assert racks == {"NB9": "Stock plate1", "NB10": "Stock plate2"}


def test_operator_plate_names_override_the_derived_ones() -> None:
    racks, dest = JanusSettings(
        source_racks=(("NB08", "spare stock plate"),), dest_rack="assay plate"
    ).resolve_deck(["NB07", "NB08", "NB09"])
    assert racks == {
        "NB07": "Stock plate1",
        "NB08": "spare stock plate",
        "NB09": "Stock plate3",
    }
    assert dest == "assay plate"


def test_the_liquid_class_reaches_no_cell(tmp_path: Path) -> None:
    """The sheet has no column for it, and the format is followed exactly.

    Checking every cell rather than the column it used to sit in is what
    catches it reappearing somewhere else.
    """
    out = tmp_path / "no_class.csv"
    export_mame_janus_csv([_make_replicate("V5F", "NB01", "1_1")], out, settings=_DEVICE)
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))

    assert _DEVICE.liquid_class
    assert not [r for r in rows if _DEVICE.liquid_class in r]


def test_a_blank_liquid_class_is_not_reported_at_all() -> None:
    """Warning about a value that reaches no file is noise, so the warning went.

    It used to be reported so the operator knew the third column would ship
    blank. There is no such column now, so the report described nothing the
    operator could act on.
    """
    preview = build_janus_preview_rows([_make_replicate("V5F", "NB01", "1_1")])
    assert preview["errors"] == []
    codes = [w["code"] for w in preview["warnings"]]  # type: ignore[union-attr]
    assert "missing_liquid_class" not in codes


def test_missing_liquid_class_does_not_block_the_legacy_schema(tmp_path: Path) -> None:
    out = tmp_path / "legacy.csv"
    export_mame_janus_csv(
        [_make_replicate("V5F", "NB01", "1_1")],
        out,
        settings=JanusSettings(output_schema="legacy5"),
    )
    with out.open(encoding="utf-8") as fh:
        assert next(csv.reader(fh)) == [
            "name", "source_plate", "source_well", "dest_well", "priority_score",
        ]


def test_a_plate_outside_the_stored_deck_still_gets_a_name(tmp_path: Path) -> None:
    """The v0.15.6 failure: a run whose plates the stored map does not name."""
    out = tmp_path / "unmapped.csv"
    settings = JanusSettings(
        liquid_class="Cell", source_racks=(("NB01", "some other plate"),)
    )
    export_mame_janus_csv(
        [_make_replicate("ONP2", "NB02", "1_1")], out, settings=settings
    )
    with out.open(encoding="utf-8") as fh:
        body = list(csv.reader(fh))[1:]
    # NB02 is the only plate of this run, so it is the first stock plate unless
    # the operator said otherwise, and the destination is the culture plate.
    assert body[0][3] == "Stock plate1"
    assert body[0][5] == "final culture plate"


def test_invalid_output_schema_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid output_schema"):
        JanusSettings(output_schema="device7")


def test_non_positive_volume_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid volume"):
        JanusSettings(liquid_class="Cell", volume=0.0)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        # A deck stored while the columns carried numbers holds integers. Inside
        # the process that is a programming error and must fail loudly; the
        # handler at the wire edge drops the same value instead, so a stale
        # client still gets a file. See test_export_janus_handler.py.
        ({"source_racks": (("NB01", 1),)}, "Invalid source plate name"),
        ({"source_racks": (("NB01", ""),)}, "Invalid source plate name"),
        ({"dest_rack": 4}, "Invalid dest_rack"),
        ({"dest_rack": "   "}, "Invalid dest_rack"),
    ],
)
def test_instrument_plate_names_must_be_non_empty_strings(kwargs, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        JanusSettings(liquid_class="Cell", **kwargs)


# ---------------------------------------------------------------------------
# Preview and export agreement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "settings",
    [
        _DEVICE,
        JanusSettings(liquid_class="Cell", dest_layout="source"),
        JanusSettings(liquid_class="Cell", include_verdicts=("PASS", "AMBIGUOUS")),
        # dest_layout is explicit here (unlike the cases above, which rely on
        # the default): NB01's PASS_HI and NB02's FALLBACK both sit at well A1,
        # and the default "source" layout would mirror both onto dest A1 and
        # raise duplicate_dest_well before agreement is even checked. That
        # collision is real (tests/mame/test_janus_autosave.py covers it); it is
        # simply not what this case is testing.
        JanusSettings(liquid_class="Cell", include_fallback=True, dest_layout="compact"),
        JanusSettings(output_schema="legacy5"),
    ],
)
def test_preview_and_export_agree_on_the_same_settings(settings) -> None:
    """The justification for the export keeping its ``Path`` return.

    The handler attaches the exclusion list by running the preview with the very
    object it exported with, so the two paths must not diverge for any policy.
    """
    replicates = _mixed_bag()
    preview = build_janus_preview_rows(replicates, settings=settings)
    rows = _build_janus_rows(replicates, settings=settings)

    assert preview["rows"] == rows
    covered = set(_names(rows)) | {
        str(e["mutant_id"]) for e in preview["excluded"]  # type: ignore[union-attr]
    }
    assert covered == {rr.mutant_id for rr in replicates}


def test_preview_reports_the_settings_it_used() -> None:
    preview = build_janus_preview_rows([], settings=_DEVICE)
    reported = preview["settings"]

    assert reported["output_schema"] == "device"  # type: ignore[index]
    assert reported["liquid_class"] == "Cell 100ul"  # type: ignore[index]
    assert reported["volume"] == DEFAULT_VOLUME_UL  # type: ignore[index]
    assert reported["columns"] == JanusSettings(liquid_class="x").header  # type: ignore[index]
