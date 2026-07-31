"""Row-generation and validation tests for the mame JANUS mapping export.

``test_run_meta.py`` covers only the run-meta comment and file creation, and
``test_export.py`` covers header/sort/plate-label. This module targets
``_build_janus_rows`` itself: well conversion, the three fail-fast guards
(empty well, duplicate dest_well, >96 rows), and the ``dest_layout`` option.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from kuma_core.mame.export.janus_mapping import (
    JanusSettings,
    _build_janus_rows as _build_janus_rows_core,
    build_janus_preview_rows as _build_janus_preview_rows_core,
    export_mame_janus_csv as _export_mame_janus_csv_core,
)
from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)


# The export now defaults to the instrument-native 9-column sheet with a compact
# destination layout. This module targets the row builder, so every case here
# goes through the kuma-internal 5-column schema at the source position; the
# wrappers below pin that policy in one place. The new defaults themselves are
# covered by tests/mame/test_janus_policy.py.
_LEGACY_SOURCE = JanusSettings(output_schema="legacy5", dest_layout="source")


def _rows(replicates, dest_layout=None):
    return _build_janus_rows_core(
        replicates, dest_layout=dest_layout, settings=_LEGACY_SOURCE
    )


def _preview(replicates, dest_layout=None):
    return _build_janus_preview_rows_core(
        replicates, dest_layout=dest_layout, settings=_LEGACY_SOURCE
    )


def _csv(replicates, output_path, dest_layout=None, **kwargs):
    return _export_mame_janus_csv_core(
        replicates,
        output_path,
        dest_layout=dest_layout,
        settings=_LEGACY_SOURCE,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Fixture helpers (mirror tests/mame/test_export.py)
# ---------------------------------------------------------------------------


def _make_verdict(
    nb: str,
    custom: str,
    verdict: VerdictClass = VerdictClass.PASS,
    size_kb: float = 80.0,
) -> VerdictRecord:
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
    return VerdictRecord(
        translated=translated,
        expected_mutations=[],
        verdict=verdict,
        verdict_notes="",
    )


def _make_replicate(
    mutant_id: str,
    nb: str,
    custom: str,
    verdict: VerdictClass = VerdictClass.PASS,
    size_kb: float = 80.0,
) -> ReplicateResult:
    vr = _make_verdict(nb, custom, verdict, size_kb=size_kb)
    return ReplicateResult(
        mutant_id=mutant_id,
        plate_verdicts={nb: vr},
        selected_plate=nb,
        selection_reason="pass",
        failed=False,
    )


def _make_failed_replicate(mutant_id: str, nb: str, custom: str) -> ReplicateResult:
    return ReplicateResult(
        mutant_id=mutant_id,
        plate_verdicts={nb: _make_verdict(nb, custom, VerdictClass.FRAMESHIFT)},
        selected_plate=None,
        selection_reason="all fail",
        failed=True,
    )


def _fill_plate(count: int) -> list[ReplicateResult]:
    """``count`` replicates on NB01 occupying distinct wells, descending priority."""
    out: list[ReplicateResult] = []
    for i in range(count):
        row = i % 8 + 1
        col = i // 8 + 1
        out.append(
            _make_replicate(f"M{i:03d}", "NB01", f"{row}_{col}", size_kb=1000.0 - i)
        )
    return out


# ---------------------------------------------------------------------------
# Row selection and ordering
# ---------------------------------------------------------------------------


def test_failed_replicate_excluded() -> None:
    rows = _rows(
        [_make_failed_replicate("BAD", "NB01", "1_2"), _make_replicate("OK", "NB01", "1_1")]
    )
    assert [r["name"] for r in rows] == ["OK"]


def test_replicate_without_selected_plate_excluded() -> None:
    rr = _make_replicate("NOPICK", "NB01", "1_1")
    rr.selected_plate = None
    rows = _rows([rr, _make_replicate("OK", "NB02", "2_1")])
    assert [r["name"] for r in rows] == ["OK"]


def test_rows_sorted_by_priority_desc() -> None:
    rows = _rows(
        [
            _make_replicate("LOW", "NB01", "1_1", size_kb=10.0),
            _make_replicate("HIGH", "NB01", "2_1", size_kb=300.0),
            _make_replicate("MID", "NB01", "3_1", size_kb=100.0),
        ]
    )
    assert [r["name"] for r in rows] == ["HIGH", "MID", "LOW"]


# ---------------------------------------------------------------------------
# custom_barcode -> well conversion (column-major, per seq_to_well)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("custom", "expected"),
    [
        ("1_1", "A1"),
        ("8_1", "H1"),
        ("1_2", "A2"),
        ("2_3", "B3"),
        ("8_12", "H12"),
    ],
)
def test_custom_barcode_to_well(custom: str, expected: str) -> None:
    rows = _rows([_make_replicate("M", "NB01", custom)])
    assert rows[0]["source_well"] == expected
    assert rows[0]["dest_well"] == expected


# ---------------------------------------------------------------------------
# Fail-fast guards
# ---------------------------------------------------------------------------


def test_unparseable_barcode_raises() -> None:
    with pytest.raises(ValueError, match="unparseable custom_barcode") as exc:
        _rows([_make_replicate("BADBC", "NB01", "abc")])
    message = str(exc.value)
    assert "BADBC" in message, "error must name the offending mutant"
    assert "abc" in message, "error must name the offending custom_barcode"


def test_out_of_range_barcode_raises() -> None:
    with pytest.raises(ValueError, match="unparseable custom_barcode"):
        _rows([_make_replicate("OOR", "NB01", "9_13")])


def test_duplicate_dest_well_raises() -> None:
    with pytest.raises(ValueError, match="duplicate dest_well") as exc:
        _rows(
            [
                _make_replicate("P1_A1", "NB01", "1_1", size_kb=200.0),
                _make_replicate("P2_A1", "NB02", "1_1", size_kb=100.0),
            ]
        )
    message = str(exc.value)
    assert "A1" in message
    assert "P1_A1" in message and "P2_A1" in message
    assert "compact" in message, "error must point at the compact layout remedy"


def test_ninety_seven_rows_raises() -> None:
    replicates = _fill_plate(96)
    replicates.append(_make_replicate("EXTRA", "NB02", "1_1", size_kb=1.0))
    with pytest.raises(ValueError, match="exceed the 96-well") as exc:
        _rows(replicates)
    assert "97" in str(exc.value)


def test_exactly_96_rows_allowed() -> None:
    rows = _rows(_fill_plate(96))
    assert len(rows) == 96


def test_invalid_dest_layout_raises() -> None:
    with pytest.raises(ValueError, match="Invalid dest_layout"):
        _rows([_make_replicate("M", "NB01", "1_1")], dest_layout="grid")


# ---------------------------------------------------------------------------
# dest_layout
# ---------------------------------------------------------------------------


def test_source_layout_mirrors_source_position() -> None:
    """``source`` layout copies the source position onto the destination.

    The layout is no longer the export default (see
    ``test_janus_policy.py::test_default_layout_is_compact``); it stays
    available for runs that must keep the plate coordinates.
    """
    replicates = [
        _make_replicate("HIGH", "NB01", "3_2", size_kb=300.0),
        _make_replicate("LOW", "NB02", "5_7", size_kb=10.0),
    ]
    explicit_rows = _rows(replicates, dest_layout="source")

    assert [(r["source_well"], r["dest_well"]) for r in explicit_rows] == [
        ("C2", "C2"),
        ("E7", "E7"),
    ]


def test_compact_layout_assigns_sequentially_from_a1() -> None:
    replicates = [
        _make_replicate("THIRD", "NB01", "5_7", size_kb=10.0),
        _make_replicate("FIRST", "NB01", "3_2", size_kb=300.0),
        _make_replicate("SECOND", "NB02", "8_12", size_kb=100.0),
    ]
    rows = _rows(replicates, dest_layout="compact")

    assert [r["name"] for r in rows] == ["FIRST", "SECOND", "THIRD"]
    # Column-major order per seq_to_well: A1, B1, C1.
    assert [r["dest_well"] for r in rows] == ["A1", "B1", "C1"]
    # source_well is untouched by compaction.
    assert [r["source_well"] for r in rows] == ["C2", "H12", "E7"]


def test_compact_layout_resolves_source_duplicates() -> None:
    """Same position on two plates is fatal in source layout, fine in compact."""
    replicates = [
        _make_replicate("P1_A1", "NB01", "1_1", size_kb=200.0),
        _make_replicate("P2_A1", "NB02", "1_1", size_kb=100.0),
    ]
    rows = _rows(replicates, dest_layout="compact")
    assert [r["dest_well"] for r in rows] == ["A1", "B1"]


def test_compact_layout_wraps_to_next_column() -> None:
    rows = _rows(_fill_plate(10), dest_layout="compact")
    assert [r["dest_well"] for r in rows[:10]] == [
        "A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1", "A2", "B2",
    ]


# ---------------------------------------------------------------------------
# Exporter wiring
# ---------------------------------------------------------------------------


def test_csv_export_honours_compact_layout(tmp_path: Path) -> None:
    out = tmp_path / "janus_compact.csv"
    _csv(
        [
            _make_replicate("HIGH", "NB01", "5_7", size_kb=300.0),
            _make_replicate("LOW", "NB02", "8_12", size_kb=10.0),
        ],
        out,
        dest_layout="compact",
    )
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["dest_well"] for r in rows] == ["A1", "B1"]
    assert [r["source_well"] for r in rows] == ["E7", "H12"]


def test_csv_export_rejects_duplicate_dest(tmp_path: Path) -> None:
    out = tmp_path / "janus_dup.csv"
    with pytest.raises(ValueError, match="duplicate dest_well"):
        _csv(
            [
                _make_replicate("P1_A1", "NB01", "1_1"),
                _make_replicate("P2_A1", "NB02", "1_1"),
            ],
            out,
        )


# ---------------------------------------------------------------------------
# Preview (dry-run): same rows, problems collected instead of raised
# ---------------------------------------------------------------------------


def test_preview_matches_export_rows() -> None:
    """The preview must show exactly what the export would write."""
    replicates = [
        _make_replicate("HIGH", "NB01", "5_7", size_kb=300.0),
        _make_replicate("MID", "NB02", "1_1", size_kb=200.0),
        _make_replicate("LOW", "NB03", "8_12", size_kb=10.0),
    ]
    preview = _preview(replicates)
    assert preview["rows"] == _rows(replicates)
    assert preview["errors"] == []
    assert preview["row_count"] == 3


def test_preview_compact_matches_export_rows() -> None:
    replicates = [
        _make_replicate("HIGH", "NB01", "5_7", size_kb=300.0),
        _make_replicate("LOW", "NB02", "8_12", size_kb=10.0),
    ]
    preview = _preview(replicates, dest_layout="compact")
    assert preview["rows"] == _rows(replicates, dest_layout="compact")
    assert [r["dest_well"] for r in preview["rows"]] == ["A1", "B1"]
    assert preview["errors"] == []


def test_preview_rejects_unknown_dest_layout() -> None:
    with pytest.raises(ValueError, match="Invalid dest_layout"):
        _preview([], dest_layout="diagonal")


def test_preview_reports_duplicate_dest_instead_of_raising() -> None:
    preview = _preview(
        [
            _make_replicate("P1_A1", "NB01", "1_1", size_kb=200.0),
            _make_replicate("P2_A1", "NB02", "1_1", size_kb=100.0),
        ]
    )
    assert preview["row_count"] == 2
    assert [e["code"] for e in preview["errors"]] == ["duplicate_dest_well"]
    assert preview["errors"][0]["mutant_ids"] == ["P1_A1", "P2_A1"]
    assert "duplicate dest_well" in str(preview["errors"][0]["message"])


def test_preview_compact_clears_duplicate_dest() -> None:
    """Compact is the documented way out of a duplicate; it must report clean."""
    preview = _preview(
        [
            _make_replicate("P1_A1", "NB01", "1_1", size_kb=200.0),
            _make_replicate("P2_A1", "NB02", "1_1", size_kb=100.0),
        ],
        dest_layout="compact",
    )
    assert preview["errors"] == []
    assert [r["dest_well"] for r in preview["rows"]] == ["A1", "B1"]


def test_preview_reports_unresolved_well_and_keeps_the_row() -> None:
    """A broken clone stays visible: hiding it defeats the preview."""
    preview = _preview(
        [
            _make_replicate("BAD", "NB01", "zz", size_kb=500.0),
            _make_replicate("OK", "NB01", "1_1", size_kb=100.0),
        ]
    )
    assert [r["name"] for r in preview["rows"]] == ["BAD", "OK"]
    assert preview["rows"][0]["source_well"] == ""
    assert preview["rows"][0]["dest_well"] == ""
    assert [e["code"] for e in preview["errors"]] == ["unresolved_well"]
    assert preview["errors"][0]["mutant_ids"] == ["BAD"]


def test_preview_blank_wells_are_not_reported_as_duplicates() -> None:
    """Two unresolved wells share a blank dest; that is one problem, not two."""
    preview = _preview(
        [
            _make_replicate("BAD1", "NB01", "zz", size_kb=500.0),
            _make_replicate("BAD2", "NB02", "yy", size_kb=400.0),
        ]
    )
    assert [e["code"] for e in preview["errors"]] == ["unresolved_well"]
    assert preview["errors"][0]["mutant_ids"] == ["BAD1", "BAD2"]


def test_preview_reports_plate_overflow_without_crashing() -> None:
    """seq_to_well rejects index 97, so compaction must stop at 96."""
    replicates = _fill_plate(96)
    replicates.append(_make_replicate("EXTRA", "NB02", "1_1", size_kb=0.5))
    preview = _preview(replicates, dest_layout="compact")

    assert preview["row_count"] == 97
    assert [e["code"] for e in preview["errors"]] == ["plate_capacity"]
    assert preview["errors"][0]["mutant_ids"] == ["EXTRA"]
    assert preview["rows"][95]["dest_well"] == "H12"
    assert preview["rows"][96]["dest_well"] == ""


def test_preview_collects_every_problem_at_once() -> None:
    replicates = _fill_plate(96)
    replicates.append(_make_replicate("BAD", "NB02", "zz", size_kb=0.5))
    replicates.append(_make_replicate("DUP", "NB03", "1_1", size_kb=0.4))
    preview = _preview(replicates)

    assert sorted(str(e["code"]) for e in preview["errors"]) == [
        "duplicate_dest_well",
        "plate_capacity",
        "unresolved_well",
    ]
    # Every entry carries the same shape so consumers never branch on presence.
    for entry in preview["errors"]:
        assert set(entry.keys()) == {"code", "message", "mutant_ids"}
        assert isinstance(entry["mutant_ids"], list)


def test_export_still_fails_fast_on_the_same_problems(tmp_path: Path) -> None:
    """The preview is additive: the write path keeps raising."""
    dup = [
        _make_replicate("P1_A1", "NB01", "1_1"),
        _make_replicate("P2_A1", "NB02", "1_1"),
    ]
    with pytest.raises(ValueError, match="duplicate dest_well"):
        _csv(dup, tmp_path / "dup.csv")
    with pytest.raises(ValueError, match="unparseable custom_barcode"):
        _rows([_make_replicate("BAD", "NB01", "zz")])
    with pytest.raises(ValueError, match="exceed the 96-well"):
        _rows(_fill_plate(96) + [_make_replicate("X", "NB02", "1_1")])
