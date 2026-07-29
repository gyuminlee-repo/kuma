"""RPC-level tests for ``export_janus_mapping`` dest_layout wiring.

``tests/mame/test_janus_mapping.py`` covers the core row builder. This module
covers the handler path the app actually calls, so a param that never reaches
the core (or reaches only one of the two format branches) is caught.
"""

from __future__ import annotations

import csv
from pathlib import Path

import openpyxl
import pytest

from kuma_core.mame.models import (
    BarcodeRecord,
    ReplicateResult,
    TranslatedRecord,
    VerdictClass,
    VerdictRecord,
)
from sidecar_mame.core import reset_state, set_last_analyze
from sidecar_mame.handlers.export import handle_export_janus_mapping


def _make_replicate(mutant_id: str, nb: str, custom: str, size_kb: float) -> ReplicateResult:
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
    verdict = VerdictRecord(
        translated=translated,
        expected_mutations=[],
        verdict=VerdictClass.PASS,
        verdict_notes="",
    )
    return ReplicateResult(
        mutant_id=mutant_id,
        plate_verdicts={nb: verdict},
        selected_plate=nb,
        selection_reason="pass",
        failed=False,
    )


@pytest.fixture
def seeded_state():
    """Cache two picks at scattered source positions, highest priority first."""
    replicates = [
        _make_replicate("HIGH", "NB01", "5_7", 300.0),   # E7
        _make_replicate("LOW", "NB02", "8_12", 10.0),    # H12
    ]
    set_last_analyze([], replicates, "/tmp/out.xlsx", run_meta=None)
    yield replicates
    reset_state()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_default_layout_mirrors_source(tmp_path: Path, seeded_state) -> None:
    out = tmp_path / "default.csv"
    handle_export_janus_mapping({"output": str(out)})
    rows = _read_csv(out)
    assert [r["dest_well"] for r in rows] == ["E7", "H12"]


def test_compact_layout_reaches_core_via_csv(tmp_path: Path, seeded_state) -> None:
    out = tmp_path / "compact.csv"
    handle_export_janus_mapping({"output": str(out), "dest_layout": "compact"})
    rows = _read_csv(out)
    assert [r["dest_well"] for r in rows] == ["A1", "B1"]
    assert [r["source_well"] for r in rows] == ["E7", "H12"]


def test_compact_layout_reaches_core_via_xlsx(tmp_path: Path, seeded_state) -> None:
    out = tmp_path / "compact.xlsx"
    handle_export_janus_mapping(
        {"output": str(out), "format": "xlsx", "dest_layout": "compact"}
    )
    ws = openpyxl.load_workbook(out)["Janus Mapping"]
    header = [c.value for c in ws[1]]
    dest_col = header.index("dest_well")
    dest = [row[dest_col].value for row in ws.iter_rows(min_row=2)]
    assert dest == ["A1", "B1"]


def test_invalid_dest_layout_rejected(tmp_path: Path, seeded_state) -> None:
    out = tmp_path / "bad.csv"
    with pytest.raises(ValueError, match="Invalid dest_layout"):
        handle_export_janus_mapping({"output": str(out), "dest_layout": "grid"})
    assert not out.exists(), "invalid params must not produce an output file"


def test_duplicate_dest_surfaces_through_handler(tmp_path: Path) -> None:
    set_last_analyze(
        [],
        [
            _make_replicate("P1_A1", "NB01", "1_1", 200.0),
            _make_replicate("P2_A1", "NB02", "1_1", 100.0),
        ],
        "/tmp/out.xlsx",
        run_meta=None,
    )
    try:
        out = tmp_path / "dup.csv"
        with pytest.raises(ValueError, match="duplicate dest_well"):
            handle_export_janus_mapping({"output": str(out)})
    finally:
        reset_state()
