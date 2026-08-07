"""Row-generation and validation tests for the mame JANUS mapping export.

``test_run_meta.py`` covers only the run-meta comment and file creation, and
``test_export.py`` covers header and plate-label. This module targets
``_build_janus_rows`` itself: well conversion, row order, the three fail-fast
guards (empty well, duplicate dest_well, >96 rows), and the ``dest_layout``
option.

Row order is pinned here, and every ordering case below is built so that the
rules it rules out give a *different* answer on the same fixture. Rows follow
the source plate map, column-major, rather than the ``priority_score`` DESC
this export used to follow, and both of those disagree with a row-major reading
of the plate. A fixture where two of the three agree pins neither: that is
how a row-major ``well_sort_key`` passed four ordering tests from June to
August 2026, every one of them holding the row index at 1.
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


# The export now defaults to the instrument-native eight column sheet with a compact
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
    """``count`` replicates on NB01 occupying distinct wells, A1 first.

    Positions ascend in plate order and sizes descend in step with them, so the
    plate map and ``priority_score`` DESC produce the same list. That makes this
    fixture useless for pinning the ordering rule and it is not used for that:
    it exists for the capacity cases, where only the row count matters. The
    ordering cases build their own replicates, on which the two rules disagree.
    """
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


def test_row_order_follows_the_plate_map_not_sequencing_depth() -> None:
    """Depth is the exact reverse of position here, and position wins.

    The operator fills the final plate by hand while reading the step 2.2 plate
    map, so the file has to run in the same direction as the plate in front of
    them. It sorted by ``priority_score`` DESC until this change, which put the
    deepest-sequenced clone first wherever it sat on the source plate.

    The reversal is what makes the case worth anything: on a fixture where the
    deepest clone also holds the lowest well, both rules give the same list.
    """
    replicates = [
        _make_replicate("AT_A1", "NB01", "1_1", size_kb=10.0),
        _make_replicate("AT_D1", "NB01", "4_1", size_kb=500.0),
        _make_replicate("AT_H1", "NB01", "8_1", size_kb=900.0),
    ]
    rows = _rows(replicates)

    assert [r["source_well"] for r in rows] == ["A1", "D1", "H1"]
    assert [r["name"] for r in rows] == ["AT_A1", "AT_D1", "AT_H1"]
    # Named so the discrimination is stated rather than left to be spotted:
    # this is the list the old rule produced from the same three clones.
    depth_desc = ["AT_H1", "AT_D1", "AT_A1"]
    assert [r["name"] for r in rows] != depth_desc


def test_row_order_runs_down_the_column_not_across_the_row() -> None:
    """A1, B1, A2 rather than A1, A2, B1, and neither is the depth order.

    ``2_1`` (B1) and ``1_2`` (A2) are the smallest pair that separates the two
    traversals, because they differ on both barcode axes: column-major reaches
    B1 second, row-major reaches A2 second. A fixture that varies one axis only
    agrees with both readings, which is how a row-major ``well_sort_key``
    survived four ordering tests from June to August 2026, and the
    ``mame-plate-addressing`` group note asks for non-diagonal tokens for
    exactly this reason.

    Depth is a third distinct answer on the same three clones, so the case rules
    out the rule this export used to follow as well.
    """
    replicates = [
        _make_replicate("AT_A2", "NB01", "1_2", size_kb=300.0),
        _make_replicate("AT_B1", "NB01", "2_1", size_kb=200.0),
        _make_replicate("AT_A1", "NB01", "1_1", size_kb=100.0),
    ]
    rows = _rows(replicates, dest_layout="compact")

    # The three candidate rules disagree on this fixture:
    #   priority_score DESC -> A2, B1, A1
    #   row-major position  -> A1, A2, B1
    #   column-major        -> A1, B1, A2   (what the export must do)
    assert [r["source_well"] for r in rows] == ["A1", "B1", "A2"]
    assert [r["name"] for r in rows] == ["AT_A1", "AT_B1", "AT_A2"]
    # Destinations are poured in that same order, so the final plate reads the
    # way the source plate map does.
    assert [r["dest_well"] for r in rows] == ["A1", "B1", "C1"]


def test_one_position_held_on_two_plates_pours_in_plate_order() -> None:
    """The only tie a barcode map can produce, broken the way the deck is numbered.

    One plate holds at most one pick per position, so two picks can share a
    source well only across plates. They break by natural plate order, the same
    ``(nb_order_key, label)`` expression ``JanusSettings.resolve_deck`` uses to
    number the stock plates, so the pour order and the deck naming state one
    thing rather than two.

    The plate names are deliberately unpadded: ``NB2`` and ``NB10`` sort one way
    numerically and the other way as text, so the case pins the numeric key
    instead of an accidental agreement between the two. Depth is reversed
    against plate order for the same reason.
    """
    replicates = [
        _make_replicate("ON_NB10", "sort_barcode10", "1_1", size_kb=900.0),
        _make_replicate("ON_NB2", "sort_barcode2", "1_1", size_kb=10.0),
    ]
    rows = _rows(replicates, dest_layout="compact")

    assert [r["source_plate"] for r in rows] == ["NB2", "NB10"]
    assert [r["name"] for r in rows] == ["ON_NB2", "ON_NB10"]
    assert [r["dest_well"] for r in rows] == ["A1", "B1"]

    # The deck agrees with the pour: first out of the plate the sheet calls
    # "Stock plate1".
    rack_map, _ = _LEGACY_SOURCE.resolve_deck(
        str(row["source_plate"]) for row in rows
    )
    assert [rack_map[str(r["source_plate"])] for r in rows] == [
        "Stock plate1",
        "Stock plate2",
    ]


def test_a_pick_with_no_readable_position_sorts_first() -> None:
    """No position means nothing to order by, so it goes where it is seen.

    ``PlateAddressing.sort_key`` reads an unreadable token as 0 for the same
    reason, and the export never leaves it at that: ``_find_unresolved_wells``
    raises on the same clone, so the file is withheld rather than shipped with a
    blank well.

    Neither of the other rules explains the position here: the broken clone is
    the shallowest of the four, and every readable pick holds a well.
    """
    preview = _preview(
        [
            _make_replicate("AT_A1", "NB01", "1_1", size_kb=900.0),
            _make_replicate("BROKEN", "NB01", "zz", size_kb=1.0),
            _make_replicate("AT_B1", "NB01", "2_1", size_kb=500.0),
        ]
    )

    assert [r["name"] for r in preview["rows"]] == ["BROKEN", "AT_A1", "AT_B1"]
    assert preview["rows"][0]["source_well"] == ""
    # The message says where the row landed and why, so its place at the top
    # does not read as a ranking.
    message = str(preview["errors"][0]["message"])
    assert "ordered by source well" in message


def test_priority_score_survives_the_change_of_ordering_rule() -> None:
    """The depth ranking still reaches the file; it just no longer places anything.

    ``priority_score`` is the read count when one is known and the file size in
    kB otherwise, and both the column and the value are unchanged. Dropping it
    with the sort it used to drive would take the one number that says how well
    a clone was sequenced out of the operator's hands.
    """
    rows = _rows(
        [
            _make_replicate("AT_A1", "NB01", "1_1", size_kb=10.0),
            _make_replicate("AT_B1", "NB01", "2_1", size_kb=900.0),
        ]
    )
    assert [r["name"] for r in rows] == ["AT_A1", "AT_B1"]
    assert [r["priority_score"] for r in rows] == [10.0, 900.0]


def test_priority_score_reaches_the_legacy5_file_out_of_order(tmp_path: Path) -> None:
    """The written file carries the scores, unsorted, in plate order."""
    out = tmp_path / "janus_priority.csv"
    _csv(
        [
            _make_replicate("AT_A1", "NB01", "1_1", size_kb=10.0),
            _make_replicate("AT_B1", "NB01", "2_1", size_kb=900.0),
        ],
        out,
    )
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["name"] for r in rows] == ["AT_A1", "AT_B1"]
    assert [r["priority_score"] for r in rows] == ["10.0", "900.0"]


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
    """Holes close, and the picks are poured in the order the plate map reads.

    Depth runs the other way (the H12 clone is the deepest, the C2 clone the
    shallowest), so the destinations prove the pour follows position.
    """
    replicates = [
        _make_replicate("AT_E7", "NB01", "5_7", size_kb=100.0),
        _make_replicate("AT_C2", "NB01", "3_2", size_kb=10.0),
        _make_replicate("AT_H12", "NB02", "8_12", size_kb=900.0),
    ]
    rows = _rows(replicates, dest_layout="compact")

    assert [r["name"] for r in rows] == ["AT_C2", "AT_E7", "AT_H12"]
    # Column-major order per seq_to_well: A1, B1, C1.
    assert [r["dest_well"] for r in rows] == ["A1", "B1", "C1"]
    # source_well is untouched by compaction.
    assert [r["source_well"] for r in rows] == ["C2", "E7", "H12"]


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
    """A broken clone stays visible: hiding it defeats the preview.

    ``BAD`` is the shallower of the two so that its place at the top is the
    sentinel of ``test_a_pick_with_no_readable_position_sorts_first`` and not
    the depth ranking this export used to follow.
    """
    preview = _preview(
        [
            _make_replicate("BAD", "NB01", "zz", size_kb=100.0),
            _make_replicate("OK", "NB01", "1_1", size_kb=500.0),
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
    """seq_to_well rejects index 97, so compaction must stop at 96.

    Which pick is pushed off follows from the row order, and the order changed:
    the row left without a destination is the one holding the last position on
    the plate map (``M095`` at H12), not the shallowest clone. ``EXTRA`` shares
    A1 with ``M000`` and so lands second, one plate later.
    """
    replicates = _fill_plate(96)
    replicates.append(_make_replicate("EXTRA", "NB02", "1_1", size_kb=0.5))
    preview = _preview(replicates, dest_layout="compact")

    assert preview["row_count"] == 97
    assert [e["code"] for e in preview["errors"]] == ["plate_capacity"]
    assert [r["name"] for r in preview["rows"][:2]] == ["M000", "EXTRA"]
    assert preview["errors"][0]["mutant_ids"] == ["M095"]
    assert preview["rows"][96]["name"] == "M095"
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
        assert set(entry.keys()) == {"code", "severity", "message", "mutant_ids"}
        assert entry["severity"] == "error"
        assert isinstance(entry["mutant_ids"], list)
    for entry in preview["warnings"]:
        assert set(entry.keys()) == {"code", "severity", "message", "mutant_ids"}
        assert entry["severity"] == "warning"


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
