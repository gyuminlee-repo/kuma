"""Selection policy, exclusion reporting, and instrument schema for JANUS export.

``test_janus_mapping.py`` pins the row builder against the kuma-internal
5-column output at the source position, which is what that module was written
for. This module covers what the export now does by default: keep only fully
verified clones, report every clone it drops and why, fill the destination plate
from A1, and write the instrument-native 9-column worksheet.

The 9-column header is asserted against
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

# A complete instrument policy: everything the 9-column sheet needs, so a case
# that is not about the liquid-class guard is not blocked by it.
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
    """One clone of every disposition the picker can produce."""
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
    assert _names(rows) == ["PASS_HI", "AMBIG", "PASS_LO"]


def test_lowdepth_can_be_opted_in() -> None:
    settings = JanusSettings(
        liquid_class="Cell 100ul", include_verdicts=("PASS", "LOWDEPTH")
    )
    rows = _build_janus_rows(_mixed_bag(), settings=settings)
    assert _names(rows) == ["PASS_HI", "LOWDEP", "PASS_LO"]


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
    assert by_id["AMBIG"]["selected_plate"] == "P1"
    assert by_id["FALLBACK"]["verdict"] == "PASS"
    assert by_id["FALLBACK"]["selected_plate"] == "P2"
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


def test_default_layout_is_compact() -> None:
    """A stock plate is a new plate, so picks are packed from A1."""
    assert JanusSettings().dest_layout == "compact"

    replicates = [
        _make_replicate("HIGH", "NB01", "5_7", size_kb=300.0),
        _make_replicate("LOW", "NB02", "8_12", size_kb=10.0),
    ]
    rows = _build_janus_rows(replicates, settings=_DEVICE)
    assert [r["dest_well"] for r in rows] == ["A1", "B1"]
    assert [r["source_well"] for r in rows] == ["E7", "H12"]


# ---------------------------------------------------------------------------
# Instrument-native 9-column schema
# ---------------------------------------------------------------------------


def test_default_schema_is_device9() -> None:
    assert JanusSettings().output_schema == "device9"


def test_device9_csv_header_matches_the_workbook(reference, tmp_path: Path) -> None:
    out = tmp_path / "device9.csv"
    export_mame_janus_csv([_make_replicate("V5F", "NB01", "1_1")], out, settings=_DEVICE)

    with out.open(encoding="utf-8") as fh:
        header = next(csv.reader(fh))

    assert header == reference["janus"]["mapping_header"]


def test_device9_xlsx_header_matches_the_workbook(reference, tmp_path: Path) -> None:
    out = tmp_path / "device9.xlsx"
    export_mame_janus_xlsx(
        [_make_replicate("V5F", "NB01", "1_1")], out, settings=_DEVICE
    )

    ws = openpyxl.load_workbook(out)["Janus Mapping"]
    header = [c.value for c in ws[1]]
    assert header == reference["janus"]["mapping_header"]


def test_device9_repeats_the_dsp_rack_column() -> None:
    """Two ``Dsp. Rack`` columns is the workbook, so a dict writer cannot serve."""
    assert JanusSettings().header.count("Dsp. Rack") == 2


def test_device9_row_values(tmp_path: Path) -> None:
    out = tmp_path / "device9_rows.csv"
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

    assert rows[0] == [
        "HIGH", "glycerol stock", "Cell 100ul", "1", "1", "E7", "4", "A1", "75.0",
    ]
    # `no` counts up in the sorted order, so the sheet carries the pick priority.
    assert rows[1] == [
        "LOW", "glycerol stock", "Cell 100ul", "2", "3", "H12", "4", "B1", "75.0",
    ]


def test_device9_defaults_are_the_documented_assumptions() -> None:
    settings = JanusSettings()
    assert settings.volume == DEFAULT_VOLUME_UL
    assert settings.sample_type == DEFAULT_SAMPLE_TYPE
    # Source plates first in workbook labware order, destination last.
    assert settings.rack_map == {"P1": 1, "P2": 2, "P3": 3}
    assert settings.dest_rack == 4


def test_missing_liquid_class_blocks_the_export(tmp_path: Path) -> None:
    """A guessed liquid class would change how the robot handles the cells."""
    out = tmp_path / "no_class.csv"
    with pytest.raises(ValueError, match="liquid class is required"):
        export_mame_janus_csv([_make_replicate("V5F", "NB01", "1_1")], out)
    assert not out.exists()


def test_missing_liquid_class_is_visible_in_the_preview() -> None:
    preview = build_janus_preview_rows([_make_replicate("V5F", "NB01", "1_1")])
    assert [e["code"] for e in preview["errors"]] == ["missing_liquid_class"]  # type: ignore[union-attr]


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


def test_unmapped_source_rack_blocks_the_export(tmp_path: Path) -> None:
    out = tmp_path / "unmapped.csv"
    settings = JanusSettings(liquid_class="Cell", source_racks=(("P1", 1),))
    with pytest.raises(ValueError, match="no Asp. Rack number configured"):
        export_mame_janus_csv(
            [_make_replicate("ONP2", "NB02", "1_1")], out, settings=settings
        )


def test_invalid_output_schema_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid output_schema"):
        JanusSettings(output_schema="device7")


def test_non_positive_volume_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid volume"):
        JanusSettings(liquid_class="Cell", volume=0.0)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"source_racks": (("P1", 1.9),)}, "Invalid source rack number"),
        ({"source_racks": (("P1", True),)}, "Invalid source rack number"),
        ({"dest_rack": 4.7}, "Invalid dest_rack"),
        ({"dest_rack": False}, "Invalid dest_rack"),
    ],
)
def test_device9_rack_numbers_must_be_positive_integers(kwargs, message: str) -> None:
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
        JanusSettings(liquid_class="Cell", include_fallback=True),
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

    assert reported["output_schema"] == "device9"  # type: ignore[index]
    assert reported["liquid_class"] == "Cell 100ul"  # type: ignore[index]
    assert reported["volume"] == DEFAULT_VOLUME_UL  # type: ignore[index]
    assert reported["columns"] == JanusSettings(liquid_class="x").header  # type: ignore[index]
