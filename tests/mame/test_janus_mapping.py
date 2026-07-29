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
    _build_janus_rows,
    export_mame_janus_csv,
)
from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
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
    rows = _build_janus_rows(
        [_make_failed_replicate("BAD", "NB01", "1_2"), _make_replicate("OK", "NB01", "1_1")]
    )
    assert [r["name"] for r in rows] == ["OK"]


def test_replicate_without_selected_plate_excluded() -> None:
    rr = _make_replicate("NOPICK", "NB01", "1_1")
    rr.selected_plate = None
    rows = _build_janus_rows([rr, _make_replicate("OK", "NB02", "2_1")])
    assert [r["name"] for r in rows] == ["OK"]


def test_rows_sorted_by_priority_desc() -> None:
    rows = _build_janus_rows(
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
    rows = _build_janus_rows([_make_replicate("M", "NB01", custom)])
    assert rows[0]["source_well"] == expected
    assert rows[0]["dest_well"] == expected


# ---------------------------------------------------------------------------
# Fail-fast guards
# ---------------------------------------------------------------------------


def test_unparseable_barcode_raises() -> None:
    with pytest.raises(ValueError, match="unparseable custom_barcode") as exc:
        _build_janus_rows([_make_replicate("BADBC", "NB01", "abc")])
    message = str(exc.value)
    assert "BADBC" in message, "error must name the offending mutant"
    assert "abc" in message, "error must name the offending custom_barcode"


def test_out_of_range_barcode_raises() -> None:
    with pytest.raises(ValueError, match="unparseable custom_barcode"):
        _build_janus_rows([_make_replicate("OOR", "NB01", "9_13")])


def test_duplicate_dest_well_raises() -> None:
    with pytest.raises(ValueError, match="duplicate dest_well") as exc:
        _build_janus_rows(
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
        _build_janus_rows(replicates)
    assert "97" in str(exc.value)


def test_exactly_96_rows_allowed() -> None:
    rows = _build_janus_rows(_fill_plate(96))
    assert len(rows) == 96


def test_invalid_dest_layout_raises() -> None:
    with pytest.raises(ValueError, match="Invalid dest_layout"):
        _build_janus_rows([_make_replicate("M", "NB01", "1_1")], dest_layout="grid")


# ---------------------------------------------------------------------------
# dest_layout
# ---------------------------------------------------------------------------


def test_source_layout_is_default_and_mirrors_source() -> None:
    replicates = [
        _make_replicate("HIGH", "NB01", "3_2", size_kb=300.0),
        _make_replicate("LOW", "NB02", "5_7", size_kb=10.0),
    ]
    default_rows = _build_janus_rows(replicates)
    explicit_rows = _build_janus_rows(replicates, dest_layout="source")

    assert default_rows == explicit_rows, "source must be the default layout"
    assert [(r["source_well"], r["dest_well"]) for r in default_rows] == [
        ("C2", "C2"),
        ("E7", "E7"),
    ]


def test_compact_layout_assigns_sequentially_from_a1() -> None:
    replicates = [
        _make_replicate("THIRD", "NB01", "5_7", size_kb=10.0),
        _make_replicate("FIRST", "NB01", "3_2", size_kb=300.0),
        _make_replicate("SECOND", "NB02", "8_12", size_kb=100.0),
    ]
    rows = _build_janus_rows(replicates, dest_layout="compact")

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
    rows = _build_janus_rows(replicates, dest_layout="compact")
    assert [r["dest_well"] for r in rows] == ["A1", "B1"]


def test_compact_layout_wraps_to_next_column() -> None:
    rows = _build_janus_rows(_fill_plate(10), dest_layout="compact")
    assert [r["dest_well"] for r in rows[:10]] == [
        "A1", "B1", "C1", "D1", "E1", "F1", "G1", "H1", "A2", "B2",
    ]


# ---------------------------------------------------------------------------
# Exporter wiring
# ---------------------------------------------------------------------------


def test_csv_export_honours_compact_layout(tmp_path: Path) -> None:
    out = tmp_path / "janus_compact.csv"
    export_mame_janus_csv(
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
        export_mame_janus_csv(
            [
                _make_replicate("P1_A1", "NB01", "1_1"),
                _make_replicate("P2_A1", "NB02", "1_1"),
            ],
            out,
        )
